"""Opt-in synthetic frozen-runtime acceptance; no application imports."""
import hashlib
from contextlib import closing
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
ORIGIN = 'http://127.0.0.1:8765'
GOALS = (('research', 'Find a useful marketing angle', [5, 6]),
         ('creative', 'Produce or revise a video', [6]),
         ('campaign', 'Run an approved campaign', [7]),
         ('measurement', 'Understand app results', [3, 4, 10, 11]))


def validate_packet(value, expected, goal, stages):
    assert value['schema'] == 'wmm.goal-evidence-packet.v1'
    assert value['classification'] == 'LOCAL_DRAFT_NO_AUTHORITY'
    assert value['app_id'] == expected['app_id'] == 'sample-one'
    assert value['manifest_version'] == expected['version']
    assert value['source_hash'] == expected['source_hash'] and value['source_hash']
    assert value['goal'] == goal
    assert [row['stage'] for row in value['outputs']] == stages


def verify_packet_browser(origin, output_dir, storage_dir=None, expected_initial_goal=None):
    """Exercise real browser inputs; return evidence, never admit writes."""
    from playwright.sync_api import sync_playwright, expect
    parsed = urlsplit(origin)
    assert parsed.scheme == 'http' and parsed.hostname == '127.0.0.1' and parsed.port
    assert origin == f'http://127.0.0.1:{parsed.port}'
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    results = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            for width in (1440, 390):
                storage = Path(storage_dir) / f'storage-{width}.json' if storage_dir else None
                options = dict(viewport=dict(width=width, height=900))
                if storage and storage.exists():
                    options['storage_state'] = str(storage)
                context = browser.new_context(**options)
                violations, errors = [], []
                def guard(route):
                    request = route.request
                    if not request.url.startswith(origin + '/') or request.method not in ('GET', 'HEAD'):
                        violations.append(dict(url=request.url, method=request.method))
                        route.abort()
                    else:
                        route.continue_()
                context.route('**/*', guard)
                page = context.new_page()
                page.on('pageerror', lambda error: errors.append(str(error)))
                try:
                    page.goto(origin)
                    page.wait_for_function("() => state.workspace?.app?.id==='sample-one'")
                    if expected_initial_goal:
                        expect(page.locator('[data-action="goal-select"][data-goal="'+expected_initial_goal+'"]')).to_have_attribute('aria-pressed', 'true')
                    expected = page.evaluate("() => ({app_id:state.workspace.app.id,version:state.workspace.app.version,source_hash:state.workspace.preparation.source_hash})")
                    for goal, title, stages in GOALS:
                        page.get_by_role('button', name=title, exact=True).press('Enter')
                        page.get_by_role('button', name='Open your first packet', exact=True).press('Enter')
                        dialog = page.get_by_role('dialog')
                        expect(dialog).to_contain_text(title + ' — evidence packet')
                        expect(dialog).to_contain_text('Missing measurements remain unknown')
                        assert dialog.locator('[data-goal-packet-stage]').evaluate_all('(rows)=>rows.map(r=>Number(r.dataset.goalPacketStage))') == stages
                        expect(dialog.locator('details pre').first).to_be_hidden()
                        with page.expect_download() as event:
                            dialog.get_by_role('button', name='Download goal packet', exact=True).click()
                        value = json.loads(Path(event.value.path()).read_text(encoding='utf-8'))
                        validate_packet(value, expected, goal, stages)
                        assert any(row['output'] is None or row['output'].get('missing')
                                   for row in value['outputs']), 'Fresh synthetic evidence unexpectedly complete'
                        (out / f'{goal}-{width}.json').write_text(json.dumps(value, indent=2), encoding='utf-8')
                        page.screenshot(path=str(out / f'{goal}-{width}.png'), full_page=True)
                        page.keyboard.press('Escape')
                        expect(dialog).to_be_hidden()
                    page.reload()
                    page.wait_for_function("() => state.workspace?.app?.id==='sample-one'")
                    expect(page.locator('[data-action="goal-select"][data-goal="measurement"]')).to_have_attribute('aria-pressed', 'true')
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                    assert not violations, violations
                    assert not errors, errors
                    if storage:
                        storage.parent.mkdir(parents=True, exist_ok=True)
                        context.storage_state(path=str(storage))
                    results.append(dict(width=width, goals=[g[0] for g in GOALS], reload=True,
                                        keyboard=True, escape=True, writes=0, external_requests=0))
                finally:
                    context.close()
        finally:
            browser.close()
    return results


def _workspace_state(private):
    databases = list(Path(private).rglob('mission-control.sqlite3'))
    assert len(databases) == 1
    with closing(sqlite3.connect(databases[0].resolve().as_uri()+'?mode=ro', uri=True)) as db:
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        counts = {t: dict(status='PRESENT', count=db.execute('SELECT count(*) FROM '+t).fetchone()[0])
                  if t in tables else dict(status='ABSENT', count=None)
                  for t in ('jobs', 'automation_policies', 'campaign_intents', 'campaign_paid_intents')}
        apps = [r[0] for r in db.execute('SELECT id FROM apps ORDER BY id')]
    assert all(v['status'] == 'ABSENT' or v['count'] == 0 for v in counts.values()), counts
    assert 'sample-one' in apps
    return dict(app_ids=apps, empty_effect_tables=counts)


def preflight(env):
    if env.get('CI', '').lower() != 'true' or env.get('WMM_PACKAGED_FIRST_PACKET_TEST') != '1':
        raise RuntimeError('Requires CI=true and WMM_PACKAGED_FIRST_PACKET_TEST=1 in isolated CI')
    with socket.socket() as probe:
        if os.name == 'nt':
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        probe.bind(('127.0.0.1', 8765))  # Never attach to or stop an existing listener.


def _start(binary, folder, env):
    child = subprocess.Popen([str(binary), '--headless'], cwd=folder, env=env,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                             creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
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
    threading.Thread(target=read, daemon=True).start()
    try:
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            assert child.poll() is None, 'Frozen runtime exited before readiness'
            try:
                value = json.loads(lines.get(timeout=min(1, max(.01, deadline-time.monotonic()))))
            except (queue.Empty, json.JSONDecodeError):
                continue
            if isinstance(value, dict) and value.get('status') == 'RUNNING':
                assert value.get('origin') == ORIGIN and value.get('mode') == 'HEADLESS'
                assert child.poll() is None
                return child
        raise TimeoutError('Frozen runtime did not report readiness within 45 seconds')
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
    assert child.poll() is not None, 'Owned child survived cleanup'
    child.stdout.close()


def verify_frozen_first_packet(binary, folder, env=None, label='runtime'):
    env = dict(os.environ if env is None else env)
    preflight(env)
    assert re.fullmatch(r'[A-Za-z0-9_-]{1,80}', label), 'Unsafe evidence label'
    binary = Path(binary).resolve(strict=True)
    out = ROOT / '.factory' / 'packaged-first-packet' / label
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='wmm-first-packet-') as private:
        env.update(LOCALAPPDATA=private, XDG_DATA_HOME=private)
        child = _start(binary, folder, env)
        try:
            views = verify_packet_browser(ORIGIN, out / 'initial', Path(private) / 'browser-storage')
            assert child.poll() is None
            before = _workspace_state(private)
        finally:
            _stop(child)
        preflight(env)
        child = _start(binary, folder, env)
        try:
            assert _workspace_state(private)['app_ids'] == before['app_ids']
            resumed = verify_packet_browser(ORIGIN, out / 'restart', Path(private) / 'browser-storage', 'measurement')
            assert child.poll() is None
            after = _workspace_state(private)
            assert after['app_ids'] == before['app_ids']
            evidence = dict(classification='SYNTHETIC_NOT_HUMAN_OR_PROVIDER',
                            github_sha=env.get('GITHUB_SHA'), executable_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
                            browser=views, restart_browser=resumed, workspace=before, restart_workspace=after, provider_data='NOT_RUN',
                            public_outcomes='NOT_RUN', nontechnical_person='NOT_RUN',
                            offline_restart='PASS_SAME_PRIVATE_WORKSPACE_AND_BROWSER_STORAGE',
                            network='BROWSER_EXTERNAL_BLOCKED_NOT_OS_OFFLINE')
        finally:
            _stop(child)
    (out / 'evidence.json').write_text(json.dumps(evidence, indent=2), encoding='utf-8')
    return evidence
