"""Actual owner task-choice UI; synthetic accounts and no external requests."""
from pathlib import Path
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright, expect
from mission_control.db import connection
from mission_control.operation_catalog import OPERATIONS
from mission_control.operator_client import OperatorClient
from tests.test_agent_grants import GrantTests


def counts(store):
    with connection(store.path) as db:
        return {table: db.execute('SELECT count(*) FROM '+table).fetchone()[0]
                for table in ('agent_grants', 'jobs', 'authority_expiry_consents')}


def exercise(browser, width, output):
    fixture = GrantTests('test_owner_issues_once_hash_only_persistence_and_snapshot_no_authority')
    fixture.setUp()
    context = browser.new_context(viewport={'width': width, 'height': 950})
    try:
        context.add_cookies([dict(name=c.name, value=c.value, url=fixture.origin, httpOnly=True)
                            for c in fixture.owner.cookies])
        external, errors = [], []
        def route(request):
            if request.request.url.startswith(fixture.origin+'/'):
                return request.continue_()
            external.append(request.request.url.split('?')[0])
            request.abort()
        context.route('**/*', route)
        page = context.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(fixture.origin)
        page.locator('[data-view="activity"]').click()
        page.get_by_role('button', name='Manage agent grants', exact=True).click()
        page.get_by_role('button', name='Issue an agent grant', exact=True).click()
        form = page.locator('#control-grant-form')
        expect(form).to_be_visible()
        before = counts(fixture.store)
        form.locator('#grant-agent').fill('task-profile-agent')
        date = form.locator('[name="expires_at"]').input_value()
        advanced = form.locator('[data-task-advanced]')
        assert not advanced.evaluate('(node) => node.open')
        task = form.locator('[name="task_profile"]')
        task.focus()
        task.press('ArrowDown')
        expect(task).to_have_value('research')
        expect(form.locator('[data-task-summary]')).to_contain_text('Research')
        selected = form.locator('[name="operations"]:checked').evaluate_all('(nodes) => nodes.map(n => n.value)')
        assert selected and all(OPERATIONS[name]['effect'].startswith('READ_') for name in selected)
        assert counts(fixture.store) == before
        for profile in ('organic', 'meta', 'research'):
            task.select_option(profile)
            assert form.locator('#grant-agent').input_value() == 'task-profile-agent'
            assert form.locator('[name="expires_at"]').input_value() == date
            assert counts(fixture.store) == before, 'Choosing a task must issue no authority'
        advanced.locator('summary').click()
        selected_input = form.locator('[name="operations"]:checked').first
        selected_input.uncheck()
        expect(task).to_have_value('custom')
        task.select_option('research')
        if advanced.evaluate('(node) => node.open'):
            advanced.locator('summary').click()
        page.screenshot(path=str(output/f'task-choice-{width}.png'), full_page=False)
        form.locator('[type="submit"]').focus()
        page.keyboard.press('Enter')
        expect(page.locator('[data-grant-secret]')).to_be_visible()
        after = counts(fixture.store)
        assert after['agent_grants'] == before['agent_grants']+1
        assert after['jobs'] == before['jobs']
        grants = fixture.owner.request('POST', '/api/apps/sample-one/agent-grants/list', {})['grants']
        grant = next(g for g in grants if g['agent_id'] == 'task-profile-agent')
        assert set(grant['operations']) == set(selected)
        assert grant['max_calls'] == 20 and grant['used'] == 0
        assert grant['review_operations'] == [], 'Pure reads need no checker merely because their transport is POST'
        token = page.locator('[data-grant-secret]').input_value()
        agent = OperatorClient(fixture.origin, token)
        agent.call(dict(app_id='sample-one', operation='campaign.history', input={}))
        assert counts(fixture.store)['jobs'] == before['jobs']
        assert not external and not errors, (external, errors)
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        return dict(width=width, task_selection_no_authority=True, research_read_only=True,
                    advanced_custom=True, preserved_agent_and_date=True, explicit_owner_issue=True,
                    total_calls=20, read_post_without_checker=True, jobs_created=0, keyboard=True, no_overflow=True,
                    errors=errors, external_requests=external)
    finally:
        context.close()
        fixture.tearDown()


def main():
    output = ROOT/'.factory/owner-task-presets/browser'
    output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            receipt = dict(status='PASS', chromium=browser.version,
                           observations=[exercise(browser, width, output) for width in (1440, 390)],
                           source_sha256=hashlib.sha256((ROOT/'mission_control/static/agent-control.js').read_bytes()).hexdigest(),
                           limits=['Synthetic temporary owner; no provider effects',
                                   'No independent first-time human or full marketing-cycle acceptance'])
        finally:
            browser.close()
    (output/'receipt.json').write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
