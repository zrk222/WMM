"""Isolated real UI/server/PDF acceptance; synthetic source data, no provider calls."""
from pathlib import Path
import json
import sys
import tempfile
import threading
import fitz
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mission_control.server import Server
from mission_control.store import Store
from mission_control.growth_review_store import GrowthReviews
from tests.test_benchmark_ads import saved_report, SEGMENT
from tests.test_benchmark_context import records
from playwright.sync_api import sync_playwright, expect


def seed(store):
    for identity in ('sample-one', 'sample-two'):
        store.save_app(identity, dict(name='Synthetic Café 東京 ' + identity, release='build-1', locale='en-US', currency='USD', store_app_id='123'))
    saved_report(store)


def fill_listing(page, platform='iOS'):
    page.get_by_label('Store platform', exact=True).select_option(platform)
    page.get_by_label('Change or test surface').select_option('MANUAL_METADATA')
    for name, value in dict(title='Café 東京 useful step', subtitle='Remember a useful next step', keywords='useful,progress', description='Original description. ' * 160 + 'DESCRIPTION_END_MARKER').items():
        page.locator('#growth-' + name).fill(value)
    page.locator('#growth-promotional_text').fill('Original optional promotional text')


def save_form(page):
    with page.expect_response(lambda response: '/subscription-growth/entries' in response.url and response.request.method == 'POST') as response:
        page.get_by_role('button', name='Save evidence', exact=True).click()
    assert response.value.status == 201, response.value.text()
    result = response.value.json()
    expect(page.locator('#modal')).not_to_be_visible()
    return result


def fill_reference(page):
    reference, _ = records()
    reference.update(period_start='2026-10-01T00:00:00+00:00', period_end='2026-10-08T00:00:00+00:00', published_at='2026-10-10T00:00:00+00:00', retrieved_at='2026-10-22T00:00:00+00:00')
    for name, value in reference.items():
        if name == 'denominator':
            continue
        locator = page.locator('#growth-' + name)
        if name in ('metric', 'platform', 'coverage'):
            locator.select_option(value)
        else:
            locator.fill(str(value))


def compare(page, reference_id):
    page.get_by_role('button', name='Compare saved report', exact=True).click()
    page.locator('#growth-reference_id').select_option(reference_id)
    page.locator('#growth-job_id').select_option('job-one')
    page.locator('#growth-metric').select_option('CPT_MINOR')
    for name, value in SEGMENT.items():
        page.locator('#growth-' + name).fill(value)
    return save_form(page)


def export_pdf(page, path):
    with page.expect_popup() as waiting:
        page.locator('#modal [data-action="growth-report"]').focus()
        page.keyboard.press('Enter')
    popup = waiting.value
    popup.wait_for_load_state('load')
    css = (ROOT / 'mission_control/static/page-reporting.css').read_text(encoding='utf-8')
    path.with_suffix('.html').write_text(popup.content().replace('</head>', '<style>' + css + '</style></head>'), encoding='utf-8')
    assert popup.evaluate('window.opener===null')
    assert popup.locator('input,textarea').count() == 0
    popup.pdf(path=str(path), format='A4', print_background=True)
    with fitz.open(path) as document:
        text = '\n'.join(item.get_text() for item in document)
        assert 'Café' in text and '東京' in text
        assert 'DESCRIPTION_END_MARKER' in text
        assert 'PRIVATE_SENTINEL' not in text
        assert 'limit 30' in text and 'Source hash' in text
        assert len(document) >= 2
        pages = len(document)
    popup.close()
    return pages


def exercise(page, origin, store, width, out):
    page.goto(origin)
    page.locator('[data-view="results"]').click()
    expect(page.locator('#growth-review-title')).to_be_visible()
    page.locator('#growth-review-panel [data-action="growth-listing"]').focus()
    page.keyboard.press('Enter')
    fill_listing(page)
    page.screenshot(path=str(out / f'listing-form-{width}.png'))
    # A real server error leaves all original input values available for correction/retry.
    page.route('**/subscription-growth/entries', lambda route: route.fulfill(status=400, content_type='application/json', body=json.dumps({'error':'Synthetic recoverable rejection'})))
    page.get_by_role('button', name='Save evidence', exact=True).click()
    expect(page.locator('#growth-form-error')).to_contain_text('Inputs are preserved')
    expect(page.locator('#growth-title')).to_have_value('Café 東京 useful step')
    page.unroute('**/subscription-growth/entries')
    listing = save_form(page)
    current = next(row for row in GrowthReviews(store).list('sample-one')['history'] if row['id'] == listing['id'])
    assert current['readout']['analysis']['status'] == 'READY_FOR_REVIEW'
    page.locator(f'[data-action="growth-detail"][data-id="{listing["id"]}"]').click()
    expect(page.locator('#modal-body')).to_contain_text('limit 30')
    page.evaluate('window.savedOpen=window.open; window.open=()=>null')
    page.locator('#modal [data-action="growth-report"]').click()
    expect(page.locator('#toast')).to_contain_text('Allow a report window')
    expect(page.locator('#modal')).to_be_visible()
    page.evaluate('window.open=window.savedOpen; delete window.savedOpen')
    page.evaluate("state.privateDraft='PRIVATE_SENTINEL'; state.workspace.credentials='PRIVATE_SENTINEL'")
    pdf_pages = export_pdf(page, out / f'listing-{width}.pdf')
    page.locator('#modal [data-action="growth-note"]').click()
    page.locator('#growth-decision').select_option('REVISE')
    page.locator('#growth-rationale').fill('Keep the source and test a shorter title. Local reasoning only.')
    note = save_form(page)
    assert note['data']['target_hash'] == listing['hash']
    page.locator('[data-action="growth-reference"]').click()
    fill_reference(page)
    reference = save_form(page)
    comparison = compare(page, reference['id'])
    current = next(row for row in GrowthReviews(store).list('sample-one')['history'] if row['id'] == comparison['id'])
    assert current['readout']['analysis']['difference'] == 100
    page.locator(f'[data-action="growth-detail"][data-id="{comparison["id"]}"]').click()
    expect(page.locator('#modal-body')).to_contain_text('Numerator 3000.00; denominator 10 TAPS')
    expect(page.locator('#modal-body')).to_contain_text('advisory difference 100')
    page.locator('#close-modal').click()
    page.reload()
    page.locator('[data-view="results"]').click()
    expect(page.locator(f'[data-action="growth-detail"][data-id="{listing["id"]}"]')).to_be_visible()
    # A server-side manifest change during editing cannot save into the changed setup.
    page.locator('[data-action="growth-listing"]').click()
    fill_listing(page, 'Android')
    before = len(GrowthReviews(store).list('sample-one')['history'])
    app = store.app('sample-one')
    store.save_app('sample-one', dict(app['data'], job='Changed during the form'), app['version'])
    page.get_by_role('button', name='Save evidence', exact=True).click()
    expect(page.locator('#growth-form-error')).to_contain_text('Inputs are preserved')
    assert len(GrowthReviews(store).list('sample-one')['history']) == before
    expect(page.locator('#growth-title')).to_have_value('Café 東京 useful step')
    page.locator('#close-modal').click()
    page.reload()
    page.locator('[data-view="results"]').click()
    # Verify the second platform can actually save under a newly current app version.
    page.locator('[data-action="growth-listing"]').click()
    fill_listing(page, 'Android')
    android = save_form(page)
    assert android['data']['listing']['platform'] == 'Android'
    assert 'keywords' not in android['data']['listing']['fields']
    page.screenshot(path=str(out / f'results-{width}.png'), full_page=True)
    page.screenshot(path=str(out / f'results-viewport-{width}.png'))
    css = (ROOT / 'mission_control/static/style.css').read_text(encoding='utf-8') + (ROOT / 'mission_control/static/page-reporting.css').read_text(encoding='utf-8')
    (out / f'results-{width}.html').write_text(page.content().replace('</head>', '<style>' + css + '</style></head>'), encoding='utf-8')
    assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth'), 'Horizontal overflow'
    page.locator('#app-select').select_option('sample-two')
    expect(page.locator('#growth-review-panel')).to_contain_text('No saved entries yet')
    assert page.locator(f'[data-action="growth-detail"][data-id="{listing["id"]}"]').count() == 0
    return dict(width=width, saved_entries=5, pdf_pages=pdf_pages, durable_readback=True, manifest_rejection=True, keyboard=True, privacy=True, app_switch=True, horizontal_overflow=False)


def main():
    out = ROOT / '.factory/growth-review-ui'
    out.mkdir(parents=True, exist_ok=True)
    observations = []
    with tempfile.TemporaryDirectory(prefix='wmm-growth-ui-') as folder, sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            for width in (1440, 390):
                store = Store(Path(folder) / f'ui-{width}.sqlite', seed=False)
                seed(store)
                server = Server(('127.0.0.1', 0), store)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                page = browser.new_page(viewport={'width':width, 'height':900 if width==1440 else 844})
                try:
                    observations.append(exercise(page, f'http://127.0.0.1:{server.server_port}', store, width, out))
                except Exception:
                    (out / f'failure-{width}.html').write_text(page.content(), encoding='utf-8')
                    page.screenshot(path=str(out / f'failure-{width}.png'), full_page=True)
                    print(page.locator('#toast').text_content(), flush=True)
                    raise
                finally:
                    page.close()
                    server.shutdown()
                    server.server_close()
                    thread.join()
            (out / 'browser.json').write_text(json.dumps(dict(status='PASS', browser=browser.version, observations=observations), indent=2), encoding='utf-8')
            print(json.dumps(observations))
        finally:
            browser.close()


if __name__ == '__main__':
    main()
