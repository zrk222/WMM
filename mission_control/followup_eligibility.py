"""Current app-bound preparation and download eligibility, never delivery truth."""
from zoneinfo import ZoneInfo
from .common import digest, iso_time


def binding(app, policy, subject, task):
    """Bind the exact inputs rather than only the current prompt text."""
    return digest({"app": app, "policy": policy, "subject": subject, "task": task})


def permission(policy, subject, task, observed):
    """Closed effective authority and task-state checks precede local scheduling."""
    if not policy or policy["imported"] or not policy["data"]["enabled"]:
        return "PREPARATION_DISABLED"
    if not subject or subject["imported"] or not subject["data"]["confirmed"]:
        return "CONSENT_UNAVAILABLE_OR_REVOKED"
    if not iso_time(subject["data"]["granted_at"]) <= observed < iso_time(subject["data"]["expires_at"]):
        return "CONSENT_OUTSIDE_WINDOW"
    if task["imported"]:
        return "IMPORTED_CHECKPOINT_REQUIRES_REVIEW"
    if task["data"]["state"] != "OPEN":
        return task["data"]["state"]
    return None


def calendar(subject, observed):
    """Derive current local date/quiet hours using the actual DST offset."""
    data = subject["data"]; local = observed.astimezone(ZoneInfo(data["timezone"]))
    wall = local.strftime("%H:%M"); start, end = data["quiet_start"], data["quiet_end"]
    quiet = start <= wall < end if start < end else wall >= start or wall < end
    return local.date().isoformat(), quiet


def eligibility(app, policy, subject, task, handoffs, observed, exclude=None):
    """Explain the first failed mandatory conjunction without changing stored state."""
    scoped = [row for row in (policy, subject, task) if row]
    if any(row["app_id"] != app["id"] for row in scoped + handoffs):
        return {"status": "FOREIGN_SCOPE"}
    reason = permission(policy, subject, task, observed)
    if reason:
        return {"status": reason}
    if observed < iso_time(task["data"]["due_at"]):
        return {"status": "NOT_DUE"}
    if observed >= iso_time(task["data"]["expires_at"]):
        return {"status": "CHECKPOINT_EXPIRED"}
    day, quiet = calendar(subject, observed)
    if quiet:
        return {"status": "QUIET_HOURS", "local_date": day}
    remaining = [h for h in handoffs if h["id"] != exclude]
    if any(h["data"]["task_id"] == task["id"] for h in remaining):
        return {"status": "ALREADY_PREPARED"}
    same_subject = [h for h in remaining if h["data"]["subject_id"] == subject["id"]]
    if any(calendar(subject, iso_time(h["updated"]))[0] == day for h in same_subject):
        return {"status": "DAILY_CAP", "local_date": day}
    return {"status": "ELIGIBLE", "local_date": day, "source_hash": binding(app, policy, subject, task)}
