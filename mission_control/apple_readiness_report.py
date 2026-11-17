"""Secret-free, current-source Apple scheduled-read report projection."""

import json
import math
from datetime import date, datetime, timezone

from .apple_analytics import CAMPAIGN_DOWNLOADS, REPORTS, identity
from .apple_metrics_schedule import (
    INVENTORY_SELECTION,
    check_scheduled_db,
    schedule_options,
    source_state,
    valid_inventory,
    valid_numeric,
    valid_waiting,
)
from .common import Invalid, iso_time

WATCH_REASONS = {
    "WAITING_FOR_REPORTS": (
        "Apple has not supplied report rows for this verified scheduled read. This does not mean zero activity."
    ),
    "APPLE_CAMPAIGN_FILE_AVAILABLE": "Apple lists a daily Detailed file for this app. Download counts are still unknown.",
    "APPLE_REPORT_SETUP_REQUIRED": "This check found no active Apple reporting stream for the app.",
}


def _time(value, ceiling):
    try:
        stamp = iso_time(value) if isinstance(value, str) else None
        return stamp.isoformat() if stamp is not None and stamp <= ceiling else None
    except (Invalid, ValueError, TypeError, OverflowError):
        return None


def _due(value):
    try:
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            return None
        return datetime.fromtimestamp(value, timezone.utc).isoformat()
    except (ValueError, OverflowError, OSError):
        return None


def _stopped_failure(db, row, ceiling):
    """A stopped schedule may expose only an exactly bound terminal failure."""
    if not row["last_job"]:
        return None, None
    job = db.execute(
        "SELECT action,status,data,updated FROM jobs WHERE app_id=? AND id=?", (row["app_id"], row["last_job"])
    ).fetchone()
    if job is None or job["action"] != "sync" or job["status"] not in ("FAILED", "BLOCKED", "CANCELLED"):
        return None, None
    data = json.loads(job["data"])
    if (
        not isinstance(data, dict)
        or not row["id"]
        or _due(row["last_due"]) is None
        or data.get("analytics_schedule_id") != row["id"]
        or type(data.get("analytics_schedule_version")) is not int
        or data.get("analytics_schedule_version") != row["version"]
        or type(data.get("analytics_schedule_due")) not in (int, float)
        or data.get("analytics_schedule_due") != row["last_due"]
        or data.get("connection_id") != row["connection_id"]
        or type(data.get("connection_version")) is not int
        or data.get("connection_version") != row["connection_version"]
        or type(data.get("manifest_version")) is not int
        or data.get("manifest_version") != row["app_version"]
        or data.get("options") != schedule_options(row)
        or (row["report_id"] == INVENTORY_SELECTION and data.get("connection_hash") != row["connection_hash"])
    ):
        return None, None
    observed = _time(job["updated"], ceiling)
    return (job["status"], observed) if observed else (None, None)


def _catchup_note(row, job, observed):
    """Explain a missed cadence using the bound slot and the job's enqueue time."""
    scheduled = _due(row["last_due"])
    queued = _time(job["created"], iso_time(observed))
    if not scheduled or not queued:
        return ""
    delay = (iso_time(queued) - iso_time(scheduled)).total_seconds()
    if delay < row["interval_hours"] * 3600:
        return ""
    hours = int(delay // 3600)
    return (
        f" WMM queued this read {hours} hours after it was due. Keep WMM running, or use "
        "your own always-on host for reads while this computer is off."
    )


def _listed_inventory_action(reports):
    """Give a campaign action only for a normalized, complete Detailed file listing."""
    if not 1 <= len(reports) <= len(REPORTS):
        raise Invalid("Apple availability result has no verified file listing")
    other_files = False
    for report in reports:
        if not isinstance(report, dict) or report.get("name") not in REPORTS or report.get("coverage") != "COMPLETE":
            raise Invalid("Apple availability report is incomplete")
        instances = report.get("instances")
        if not isinstance(instances, list) or len(instances) > 300:
            raise Invalid("Apple availability file list is invalid")
        if not instances:
            continue
        identity(report.get("id"))
        other_files = True
        if report["name"] != CAMPAIGN_DOWNLOADS:
            continue
        for item in instances:
            if not isinstance(item, dict):
                raise Invalid("Apple availability file entry is invalid")
            if item.get("granularity") != "DAILY":
                continue
            identity(item.get("id"))
            processing = item.get("processing_date")
            if not isinstance(processing, str) or date.fromisoformat(processing).isoformat() != processing:
                raise Invalid("Apple availability processing date is invalid")
            return (
                "APPLE_CAMPAIGN_FILE_AVAILABLE",
                "Open Apple Analytics and choose a Detailed daily file to collect. This check did not read downloads.",
            )
    if not other_files:
        raise Invalid("Apple availability result did not list any files")
    return (
        "APPLE_REPORT_FILES_LISTED",
        "Apple listed report files, but this check found no daily Detailed downloads file. Keep watching for it.",
    )


def _inventory_summary(db, row, job, ceiling):
    result = job["result"]
    if not valid_inventory(db, row, job, result, schedule_checked=True) or not (
        observed := _time(result["observed_at"], ceiling)
    ):
        return None
    state = result["status"]
    if state == "WAITING_FOR_REPORTS":
        action = "Apple had no report files. WMM will check again at the next scheduled time."
        if row["next_due"] < ceiling.timestamp():
            action = "The report availability check is overdue. Check that the WMM worker is running."
    elif state == "REPORT_SETUP_REQUIRED":
        state = "APPLE_REPORT_SETUP_REQUIRED"
        action = "Ask an App Store Connect Admin to start ongoing reports for this app, then check availability again."
    else:
        state, action = _listed_inventory_action(result["reports"])
    return dict(read=state, observed_at=observed, next_action=action + _catchup_note(row, job, observed))


def summary(db, app_id, store_app_id, observed_at):
    """Use one schedule and its exact current job; never return source identifiers."""
    row = db.execute("SELECT * FROM apple_metrics_schedules WHERE app_id=?", (app_id,)).fetchone()
    if row is None and (not isinstance(store_app_id, str) or not store_app_id.isdigit()):
        return None
    result = dict(
        schedule="NOT_CONFIGURED",
        read="NOT_RUN",
        observed_at=None,
        next_due=None,
        next_action="Connect Apple analytics and configure a scheduled read if desired.",
    )
    if row is None:
        return result
    result.update(
        schedule="UNCONFIRMED",
        read="UNCONFIRMED",
        next_action="Review the Apple connection and refresh settings before relying on this read.",
    )
    try:
        ceiling = iso_time(observed_at)
        stop = row["stop_at"]
        if row["status"] == "EXPIRED" or (row["enabled"] == 1 and stop is not None and stop <= ceiling.timestamp()):
            result.update(
                schedule="EXPIRED",
                next_action="The Apple check window ended. Review saved inventory or set a new check window.",
            )
            return result
        valid, _ = source_state(db, row)
        if not valid:
            result.update(
                schedule="SOURCE_CHANGED",
                next_action="Review the current app and Apple connection, then update the schedule.",
            )
            return result
        if (
            row["enabled"] not in (0, 1)
            or row["status"] not in ("ENABLED", "PAUSED", "BLOCKED", "CONNECTION_CHANGED")
            or type(row["interval_hours"]) is not int
            or not 24 <= row["interval_hours"] <= 168
            or type(row["version"]) is not int
            or row["version"] < 1
        ):
            return result
        if row["status"] != "ENABLED" or row["enabled"] != 1:
            if row["enabled"] != 0 or row["status"] == "ENABLED":
                return result
            result.update(
                schedule=row["status"], next_action="Review the Apple connection and schedule before resuming reads."
            )
            failure, observed = _stopped_failure(db, row, ceiling)
            if failure:
                result.update(read=failure, observed_at=observed)
            return result
        due = _due(row["next_due"])
        if due is None:
            return result
        result.update(
            schedule="ENABLED",
            read="NOT_RUN",
            next_due=due if stop is None or row["next_due"] < stop else None,
            next_action=(
                "Keep the local service running until the next scheduled read."
                if stop is None or row["next_due"] < stop
                else "No further read is due before the check window ends."
            ),
        )
        if not row["last_job"]:
            return result
        saved = db.execute("SELECT * FROM jobs WHERE app_id=? AND id=?", (app_id, row["last_job"])).fetchone()
        if saved is None or saved["action"] != "sync":
            result.update(read="UNCONFIRMED", next_action="Review the scheduled read and connection before retrying.")
            return result
        job = dict(saved)
        job["data"] = json.loads(job["data"])
        job["result"] = json.loads(job["result"]) if job["result"] else None
        if check_scheduled_db(db, job) is None:
            raise Invalid("Scheduled read binding is unavailable")
        if job["status"] in ("QUEUED", "RUNNING"):
            result.update(read=job["status"], next_action="Keep the local service running and check the read again.")
        elif job["status"] == "SUCCEEDED" and row["report_id"] == INVENTORY_SELECTION:
            availability = _inventory_summary(db, row, job, ceiling)
            if availability is None:
                raise Invalid("Scheduled Apple report availability is unconfirmed")
            result.update(availability)
        elif (
            job["status"] == "SUCCEEDED"
            and isinstance(job["result"], dict)
            and valid_waiting(db, row, job, job["result"])
            and (observed := _time(job["result"]["observed_at"], ceiling))
        ):
            next_action = "Apple had no daily report at this observation. Keep the schedule enabled and check later."
            if row["next_due"] < ceiling.timestamp():
                next_action = (
                    "The scheduled refresh is overdue. Check that the WMM worker is running, "
                    "then review the saved refresh in Apple analytics."
                )
            next_action += _catchup_note(row, job, observed)
            result.update(read="WAITING_FOR_REPORTS", observed_at=observed, next_action=next_action)
        elif (
            job["status"] == "SUCCEEDED"
            and isinstance(job["result"], dict)
            and valid_numeric(db, row, job, job["result"])
            and (observed := _time(job["result"]["observed_at"], ceiling))
        ):
            result.update(
                read="DOWNLOAD_OBSERVATIONS_AVAILABLE",
                observed_at=observed,
                next_action=(
                    "Read completed; inspect saved Apple download observations in this report."
                    + _catchup_note(row, job, observed)
                ),
            )
        elif job["status"] in ("FAILED", "BLOCKED", "CANCELLED") and (observed := _time(job["updated"], ceiling)):
            result.update(
                read=job["status"],
                observed_at=observed,
                next_action="Review the scheduled read and Apple connection before retrying.",
            )
        else:
            result.update(read="UNCONFIRMED", next_action="Review the scheduled read and connection before retrying.")
        if result["read"] == "WAITING_FOR_REPORTS" and result["next_due"] is None:
            result["next_action"] = "Apple had no files at this check. No further read is due before the window ends."
        return result
    except (Invalid, ValueError, TypeError, KeyError, AttributeError, OverflowError):
        result.update(
            schedule="UNCONFIRMED",
            read="UNCONFIRMED",
            observed_at=None,
            next_due=None,
            next_action="Review the Apple connection and refresh settings before relying on this read.",
        )
        return result
