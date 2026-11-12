"""Opt-in synthetic frozen-runtime acceptance; no application imports."""

import hashlib
from collections import deque
from contextlib import closing, nullcontext
import json
import os
from pathlib import Path
import queue
import re
import socket
import sqlite3
import subprocess
import tempfile
import threading
import time
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "http://127.0.0.1:8765"
GOALS = (
    ("research", "Find a useful marketing angle", [5, 6]),
    ("creative", "Produce or revise a video", [6]),
    ("campaign", "Run an approved campaign", [7]),
    ("measurement", "Understand app results", [3, 4, 10, 11]),
)


def validate_packet(value, expected, goal, stages):
    assert value["schema"] == "wmm.goal-evidence-packet.v1"
    assert value["classification"] == "LOCAL_DRAFT_NO_AUTHORITY"
    assert value["app_id"] == expected["app_id"]
    assert value["manifest_version"] == expected["version"]
    assert value["source_hash"] == expected["source_hash"] and value["source_hash"]
    assert value["goal"] == goal
    assert [row["stage"] for row in value["outputs"]] == stages


def first_app_fixture(width):
    return (
        f"packaged-first-app-{width}",
        dict(
            name=f"Packaged first app {width}",
            audience="Synthetic practice users",
            job="Help users rehearse decisions",
            activation="Save a practice decision",
            release="test-build",
            locale="en-US",
        ),
    )


def exact_app_creation(request, origin, app_id, fields):
    """Admit one known local form submission with no connection or authority data."""
    if request.method != "POST" or request.url != origin + "/api/apps":
        return False
    try:
        body = request.post_data_json
    except (ValueError, TypeError):
        return False
    if not isinstance(body, dict) or set(body) != {"id", "data", "version"}:
        return False
    data = body["data"]
    defaults = dict.fromkeys(
        (
            "currency",
            "website",
            "brand_voice",
            "brand_visual",
            "brand_source",
            "brand_boundaries",
            "growth_cadence",
            "growth_channels",
            "growth_channel",
            "store_app_id",
            "android_package",
            "android_track",
            "social_callback_base_url",
        ),
        "",
    )
    defaults.update(growth_mode="AUTO", growth_metric="activation_rate")
    return (
        body["id"] == app_id
        and body["version"] is None
        and isinstance(data, dict)
        and all(data.get(k) == v for k, v in fields.items())
        and all(k in fields or (k in defaults and v == defaults[k]) for k, v in data.items())
    )


def read_boundary(url, origin, method, status=None):
    """Keep only fixed local API boundary metadata, never secrets or query text."""
    parts, base = urlsplit(url), urlsplit(origin)
    if (parts.scheme, parts.netloc) != (base.scheme, base.netloc):
        return None
    path = parts.path
    if path not in ("/api/bootstrap", "/api/research", "/api/apps") and not re.fullmatch(
        r"/api/apps/(?:sample-one|sample-two|packaged-first-app-(?:1440|390))", path
    ):
        return None
    if method not in ("GET", "HEAD", "POST"):
        return None
    return dict(path=path, method=method, status=status if type(status) is int and 100 <= status <= 599 else None)


def capture_packet_failure(page, out, width, exception, boundaries, page_errors):
    """Best-effort metadata only; never obscure the original acceptance failure."""
    report = dict(
        schema="wmm.packaged-packet-failure.v1",
        width=width,
        exception_type=type(exception).__name__,
        api_boundaries=list(boundaries)[-32:],
        page_error_count=len(page_errors),
    )
    try:
        snapshot = page.evaluate('async () => ({\n            document_ready:document.readyState,\n            boot_loaded:typeof (await import(\'/app.mjs\')).state!==\'undefined\' && !!(await import(\'/app.mjs\')).state.boot,\n            research_loaded:typeof (await import(\'/app.mjs\')).state!==\'undefined\' && !!(await import(\'/app.mjs\')).state.research,\n            workspace_loaded:typeof (await import(\'/app.mjs\')).state!==\'undefined\' && !!(await import(\'/app.mjs\')).state.workspace,\n            selected_app:typeof (await import(\'/app.mjs\')).state!==\'undefined\' ? (await import(\'/app.mjs\')).state.app : null,\n            workspace_app:typeof (await import(\'/app.mjs\')).state!==\'undefined\' ? (await import(\'/app.mjs\')).state.workspace?.app?.id : null,\n            workspace_error:typeof (await import(\'/app.mjs\')).state!==\'undefined\' && !!(await import(\'/app.mjs\')).state.workspaceError,\n            retry_visible:!!document.querySelector(\'#main [data-action="reload"]\')\n        })')
        safe = {}
        for key in ("boot_loaded", "research_loaded", "workspace_loaded", "workspace_error", "retry_visible"):
            safe[key] = snapshot.get(key) is True
        safe["document_ready"] = (
            snapshot.get("document_ready")
            if snapshot.get("document_ready") in ("loading", "interactive", "complete")
            else "UNKNOWN"
        )
        for key in ("selected_app", "workspace_app"):
            value = snapshot.get(key)
            safe[key] = (
                value
                if value is None
                or value in ("sample-one", "sample-two", "packaged-first-app-1440", "packaged-first-app-390")
                else "UNEXPECTED_APP"
            )
        report["readiness"] = safe
    except Exception as error:
        report["snapshot_error_type"] = type(error).__name__
    try:
        target = Path(out) / f"failure-{width}.json"
        target.write_text(json.dumps(report, indent=2), encoding="utf-8")
        exception.add_note("Packaged startup diagnostics: " + str(target))
    except Exception:
        exception.add_note("Packaged startup diagnostics could not be retained")


def verify_packet_browser(origin, output_dir, storage_dir=None, expected_initial_goal=None):
    """Use the real form on a fresh profile; read only across restart and upgrade."""
    from playwright.sync_api import sync_playwright, expect

    parsed = urlsplit(origin)
    assert parsed.scheme == "http" and parsed.hostname == "127.0.0.1" and parsed.port
    assert origin == f"http://127.0.0.1:{parsed.port}"
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    results = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            for width in (1440, 390):
                app_id, fields = first_app_fixture(width)
                fresh = expected_initial_goal is None
                storage = Path(storage_dir) / f"storage-{width}.json" if storage_dir else None
                options = dict(viewport=dict(width=width, height=900))
                if storage and storage.exists():
                    options["storage_state"] = str(storage)
                context = browser.new_context(**options)
                violations, errors, setup_writes = [], [], []
                boundaries = deque(maxlen=32)

                def observe(request, status=None):
                    value = read_boundary(request.url, origin, request.method, status)
                    if value is not None:
                        boundaries.append(value)

                context.on("response", lambda response: observe(response.request, response.status))
                context.on("requestfailed", lambda request: observe(request))

                def guard(route):
                    request = route.request
                    if request.url.startswith(origin + "/") and request.method in ("GET", "HEAD"):
                        route.continue_()
                    elif fresh and not setup_writes and exact_app_creation(request, origin, app_id, fields):
                        setup_writes.append(request.method)
                        route.continue_()
                    else:
                        violations.append(dict(url=request.url, method=request.method))
                        route.abort()

                context.route("**/*", guard)
                page = context.new_page()
                page.on("pageerror", lambda error: errors.append(str(error)))
                try:
                    page.goto(origin)
                    if fresh:
                        page.wait_for_function("(context) => {const state=context.state;return (() => state.workspace?.app?.id==='sample-one')(context.original);}", arg={'state': page.evaluate_handle("async () => (await import('/app.mjs')).state"), 'original': None})
                        add_app = page.locator('[data-action="add-app"]' if width == 390 else "#add-app")
                        add_app.press("Enter")
                        form = page.locator("#app-form")
                        expect(form).to_be_visible()
                        for name, value in fields.items():
                            form.locator(f'[name="{name}"]').fill(value)
                        with page.expect_response(
                            lambda r: r.url == origin + "/api/apps" and r.request.method == "POST"
                        ) as saved:
                            form.get_by_role("button", name="Save and choose a goal").press("Enter")
                        assert saved.value.status == 201, "Synthetic app was not created"
                    page.wait_for_function('(context) => {const state=context.state;return (id => state.workspace?.app?.id===id)(context.original);}', arg={'state': page.evaluate_handle("async () => (await import('/app.mjs')).state"), 'original': app_id})
                    expect(page.get_by_role("heading", name="Set your goal", exact=True)).to_be_visible()
                    assert page.evaluate("async () => (await import('/app.mjs')).state.workspace.app.data.name") == fields["name"]
                    if expected_initial_goal:
                        expect(
                            page.locator('[data-action="goal-select"][data-goal="' + expected_initial_goal + '"]')
                        ).to_have_attribute("aria-pressed", "true")
                    expected = page.evaluate(
                        "async () => ({app_id:(await import('/app.mjs')).state.workspace.app.id,version:(await import('/app.mjs')).state.workspace.app.version,source_hash:(await import('/app.mjs')).state.workspace.preparation.source_hash})"
                    )
                    for goal, title, stages in GOALS:
                        page.get_by_role("button", name=title, exact=True).press("Enter")
                        expect(page.locator('[data-action="goal-select"][data-goal="' + goal + '"]')).to_have_attribute(
                            "aria-pressed", "true"
                        )
                        packet_trigger = page.get_by_role("button", name="Open your first packet", exact=True)
                        packet_trigger.press("Enter")
                        dialog = page.get_by_role("dialog")
                        expect(dialog).to_contain_text(title + " — evidence packet")
                        expect(dialog).to_contain_text("Missing measurements remain unknown")
                        assert (
                            dialog.locator("[data-goal-packet-stage]").evaluate_all(
                                "(rows)=>rows.map(r=>Number(r.dataset.goalPacketStage))"
                            )
                            == stages
                        )
                        expect(dialog.locator("details pre").first).to_be_hidden()
                        with page.expect_download() as event:
                            dialog.get_by_role("button", name="Download goal packet", exact=True).click()
                        value = json.loads(Path(event.value.path()).read_text(encoding="utf-8"))
                        validate_packet(value, expected, goal, stages)
                        assert any(row["output"] is None or row["output"].get("missing") for row in value["outputs"]), (
                            "Fresh synthetic evidence unexpectedly complete"
                        )
                        (out / f"{goal}-{width}.json").write_text(json.dumps(value, indent=2), encoding="utf-8")
                        page.screenshot(path=str(out / f"{goal}-{width}.png"), full_page=True)
                        page.keyboard.press("Escape")
                        expect(dialog).to_be_hidden()
                        expect(packet_trigger).to_be_focused()
                    packet_trigger.press("Enter")
                    expect(dialog).to_be_visible()
                    advanced = page.locator("#navigation details")
                    page.evaluate("""() => new Promise(resolve => {
                        const dialog=document.querySelector('#modal');
                        dialog.addEventListener('close', () => resolve(), {once:true});
                        dialog.close();
                        document.querySelector('#navigation details summary').focus();
                    })""")
                    expect(advanced.locator("summary")).to_be_focused()
                    page.keyboard.press("Enter")
                    expect(advanced).to_have_attribute("open", "")
                    page.reload()
                    page.wait_for_function('(context) => {const state=context.state;return (id => state.workspace?.app?.id===id)(context.original);}', arg={'state': page.evaluate_handle("async () => (await import('/app.mjs')).state"), 'original': app_id})
                    expect(page.locator('[data-action="goal-select"][data-goal="measurement"]')).to_have_attribute(
                        "aria-pressed", "true"
                    )
                    assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
                    assert not violations, violations
                    assert not errors, errors
                    assert len(setup_writes) == int(fresh)
                    if storage:
                        storage.parent.mkdir(parents=True, exist_ok=True)
                        context.storage_state(path=str(storage))
                    results.append(
                        dict(
                            width=width,
                            binding=expected,
                            goals=[g[0] for g in GOALS],
                            reload=True,
                            keyboard=True,
                            escape=True,
                            late_close_preserves_focus=True,
                            writes=len(setup_writes),
                            write_scope="SYNTHETIC_APP_SETUP_ONLY" if fresh else "READ_ONLY",
                            external_requests=0,
                        )
                    )
                except Exception as error:
                    capture_packet_failure(page, out, width, error, boundaries, errors)
                    raise
                finally:
                    context.close()
        finally:
            browser.close()
    return results


def _workspace_state(private):
    databases = list(Path(private).rglob("mission-control.sqlite3"))
    assert len(databases) == 1
    with closing(sqlite3.connect(databases[0].resolve().as_uri() + "?mode=ro", uri=True)) as db:
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        counts = {
            t: dict(status="PRESENT", count=db.execute("SELECT count(*) FROM " + t).fetchone()[0])
            if t in tables
            else dict(status="ABSENT", count=None)
            for t in ("jobs", "automation_policies", "campaign_intents", "campaign_paid_intents")
        }
        apps = [
            dict(id=r[0], version=r[1], data_sha256=hashlib.sha256(r[2].encode("utf-8")).hexdigest())
            for r in db.execute("SELECT id,version,data FROM apps ORDER BY id")
        ]
        records = (
            [
                dict(
                    app_id=r[0],
                    id=r[1],
                    version=r[2],
                    hash=r[3],
                    data_sha256=hashlib.sha256(r[4].encode("utf-8")).hexdigest(),
                )
                for r in db.execute("SELECT app_id,id,version,hash,data FROM records ORDER BY app_id,id,version")
            ]
            if "records" in tables
            else []
        )
    assert all(v["status"] == "ABSENT" or v["count"] == 0 for v in counts.values()), counts
    assert any(app["id"] == "sample-one" for app in apps)
    return dict(apps=apps, records=records, empty_effect_tables=counts)


def _same_bindings(current, previous):
    assert current["apps"] == previous["apps"], "Durable app manifests changed across restart"
    assert current["records"] == previous["records"], "Durable source records changed across restart"


def preflight(env):
    if env.get("CI", "").lower() != "true" or env.get("WMM_PACKAGED_FIRST_PACKET_TEST") != "1":
        raise RuntimeError("Requires CI=true and WMM_PACKAGED_FIRST_PACKET_TEST=1 in isolated CI")
    with socket.socket() as probe:
        if os.name == "nt":
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        else:
            # Ignore closed TCP connections in TIME_WAIT, never an active
            # listener. SO_REUSEPORT is deliberately not enabled.
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        probe.bind(("127.0.0.1", 8765))  # Never attach to or stop an existing listener.


def _start(binary, folder, env):
    child = subprocess.Popen(
        [str(binary), "--headless"],
        cwd=folder,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    lines = queue.Queue(maxsize=64)

    def read():
        for _ in range(128):
            line = child.stdout.readline(8193)
            if not line or len(line) > 8192:
                break
            try:
                lines.put_nowait(line)
            except queue.Full:
                break

    reader = threading.Thread(target=read, daemon=True)
    child._wmm_stdout_reader = reader
    reader.start()
    try:
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            assert child.poll() is None, "Frozen runtime exited before readiness"
            try:
                value = json.loads(lines.get(timeout=min(1, max(0.01, deadline - time.monotonic()))))
            except (queue.Empty, json.JSONDecodeError):
                continue
            if isinstance(value, dict) and value.get("status") == "RUNNING":
                assert value.get("origin") == ORIGIN and value.get("mode") == "HEADLESS"
                assert child.poll() is None
                return child
        raise TimeoutError("Frozen runtime did not report readiness within 45 seconds")
    except BaseException:
        _stop(child)
        raise


def _stop(child):
    if child.poll() is None:
        child.terminate()
        try:
            child.wait(timeout=10)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=10)
    assert child.poll() is not None, "Owned child survived cleanup"
    reader = getattr(child, "_wmm_stdout_reader", None)
    if isinstance(reader, threading.Thread):
        reader.join(timeout=5)
        assert not reader.is_alive(), "Owned stdout reader survived cleanup"
    child.stdout.close()


def _profile(profile_dir, folder):
    profile = Path(profile_dir)
    assert profile.is_absolute() and profile.is_dir(), "Existing absolute isolated profile required"
    base = Path(folder).resolve(strict=True)
    profile = profile.resolve(strict=True)
    assert profile == base or base in profile.parents, "Profile must remain inside isolated caller folder"
    checkpoint = profile / "first-packet-checkpoint.json"
    assert not checkpoint.is_symlink(), "Acceptance checkpoint must not be a symlink"
    prior = None
    if checkpoint.exists():
        assert not checkpoint.is_symlink() and checkpoint.stat().st_size <= 1048576
        prior = json.loads(checkpoint.read_text(encoding="utf-8"))
        assert prior["schema"] == "wmm.first-packet-profile.v1"
        _same_bindings(_workspace_state(profile), prior["workspace"])
    else:
        assert not list(profile.rglob("mission-control.sqlite3")), (
            "Existing workspace requires its acceptance checkpoint"
        )
    return profile, checkpoint, prior


def verify_frozen_first_packet(binary, folder, env=None, label="runtime", *, profile_dir=None):
    env = dict(os.environ if env is None else env)
    preflight(env)
    assert re.fullmatch(r"[A-Za-z0-9_-]{1,80}", label), "Unsafe evidence label"
    binary = Path(binary).resolve(strict=True)
    out = ROOT / ".factory" / "packaged-first-packet" / label
    out.mkdir(parents=True, exist_ok=True)
    profile, checkpoint, prior = _profile(profile_dir, folder) if profile_dir is not None else (None, None, None)
    with (
        nullcontext(str(profile)) if profile is not None else tempfile.TemporaryDirectory(prefix="wmm-first-packet-")
    ) as private:
        env.update(LOCALAPPDATA=private, XDG_DATA_HOME=private)
        child = _start(binary, folder, env)
        try:
            views = verify_packet_browser(
                ORIGIN, out / "initial", Path(private) / "browser-storage", "measurement" if prior else None
            )
            assert child.poll() is None
            before = _workspace_state(private)
            if prior:
                _same_bindings(before, prior["workspace"])
        finally:
            _stop(child)
        preflight(env)
        child = _start(binary, folder, env)
        try:
            _same_bindings(_workspace_state(private), before)
            resumed = verify_packet_browser(ORIGIN, out / "restart", Path(private) / "browser-storage", "measurement")
            assert child.poll() is None
            after = _workspace_state(private)
            _same_bindings(after, before)
            assert [row["binding"] for row in resumed] == [row["binding"] for row in views]
            evidence = dict(
                classification="SYNTHETIC_NOT_HUMAN_OR_PROVIDER",
                github_sha=env.get("GITHUB_SHA"),
                executable_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
                browser=views,
                restart_browser=resumed,
                workspace=before,
                restart_workspace=after,
                provider_data="NOT_RUN",
                public_outcomes="NOT_RUN",
                nontechnical_person="NOT_RUN",
                offline_restart="PASS_SAME_PRIVATE_WORKSPACE_AND_BROWSER_STORAGE",
                profile_reused=prior is not None,
                network="BROWSER_EXTERNAL_BLOCKED_NOT_OS_OFFLINE",
            )
        finally:
            _stop(child)
        if checkpoint:
            payload = json.dumps(dict(schema="wmm.first-packet-profile.v1", workspace=after))
            assert len(payload.encode("utf-8")) <= 1048576
            checkpoint.write_text(payload, encoding="utf-8")
    (out / "evidence.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    return evidence
