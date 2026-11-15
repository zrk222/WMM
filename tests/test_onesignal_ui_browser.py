"""Real Chromium fixture for the OneSignal owner setup; no provider traffic."""

import os
import unittest
from pathlib import Path

BROWSER_PROFILE = os.environ.get("WMM_BROWSER_TEST_PROFILE") == "1"
if BROWSER_PROFILE:
    from playwright.sync_api import sync_playwright

SCRIPT = Path(__file__).resolve().parents[1] / "mission_control/static/onesignal-setup.js"


@unittest.skipUnless(BROWSER_PROFILE, "Run the explicitly provisioned browser profile")
class OneSignalUIBrowserTests(unittest.TestCase):
    def test_owner_setup_and_uncertain_recovery(self):
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 390, "height": 844})
            page.route(
                "http://127.0.0.1/**",
                lambda route: route.fulfill(
                    status=200, content_type="text/html", body='<dialog id="modal" open><div id="body"></div></dialog>'
                ),
            )
            page.goto("http://127.0.0.1/fixture")
            page.add_script_tag(path=str(SCRIPT))
            page.evaluate(r"""() => {
              window.calls=[]; window.outcome='SUCCEEDED';
              window.saved={state:'KEY_NOT_CONFIGURED',protected_key:false,sdk:'SDK_BUILD_NOT_VERIFIED',device:'DEVICE_SUBSCRIPTION_NOT_VERIFIED'};
              window.effects=[];
              const app={id:'local',version:1,data:{name:'Fixture App'}};
              const state={app:'local',workspace:{app,identity:{principal:'owner',status:'AUTHENTICATED'},access:{members:[{principal:'owner',status:'ACTIVE',role:'OWNER',version:1}]}},boot:{csrf:'fixture'}};
              window.ctx={state,document,FormData,modal:(title,html)=>{document.querySelector('#body').innerHTML=html},api:async(path,body)=>{
                const action=path.split('/').pop(); window.calls.push({action,body});
                if(action==='status') return window.saved;
                if(action==='history') return {effects:window.effects};
                if(action==='save-key') {window.saved={state:'KEY_SAVED_UNBOUND',protected_key:true,key_kind:body.kind,version:1,sdk:'SDK_BUILD_NOT_VERIFIED',device:'DEVICE_SUBSCRIPTION_NOT_VERIFIED'};return window.saved;}
                if(action==='read') return [{id:'11111111-1111-4111-8111-111111111111',name:'Fixture App',organization_id:'22222222-2222-4222-8222-222222222222'}];
                if(action==='bind') {window.saved={...window.saved,state:'APP_BOUND',version:2,provider_app_id:body.provider_app_id,organization_id:body.expected_org,name:body.expected_name};return window.saved;}
                if(action==='prepare') return {id:'33333333-3333-4333-8333-333333333333',source_hash:'a'.repeat(64),proposal:{action:body.action,provider_app_id:window.saved.provider_app_id,organization_id:body.details.organization_id,details:body.details,expires_at:'2099-01-01'}};
                if(action==='execute') {if(window.outcome==='UNKNOWN')window.effects=[{id:body.effect_id,status:'UNKNOWN',action:'create'}];return {status:window.outcome};}
                if(action==='recovery-prepare') return {id:'44444444-4444-4444-8444-444444444444',source_hash:'b'.repeat(64),proposal:{effect_action:'create',effect_id:body.effect_id,effect_status:'UNKNOWN',provider_identity:{id:body.provider_app_id,name:'Fixture App',organization_id:'22222222-2222-4222-8222-222222222222'},original:{app_version:1,role_version:1,connection_version:1},current:{app_version:2,role_version:2,connection_version:2},expires_at:'2099-01-01'}};
                if(action==='recovery-confirm') {window.effects[0].recovery='RECOVERED_READBACK_ONLY';return {status:'RECOVERED_READBACK_ONLY'};}
                return {};
              }};
              document.addEventListener('click',e=>{const n=e.target.closest('[data-action^="onesignal-"]');if(n) WMMOneSignal.action(n,ctx)});
              document.addEventListener('submit',e=>{if(e.target.id.startsWith('onesignal-')){e.preventDefault();WMMOneSignal.submit(e.target,ctx)}});
              WMMOneSignal.open(ctx);
            }""")
            page.wait_for_selector("#onesignal-key-form")
            page.add_style_tag(path=str(SCRIPT.parent / "style.css"))
            evidence = SCRIPT.parents[1].parent / ".factory" / "onesignal-setup" / "browser"
            evidence.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(evidence / "onesignal-mobile.png"), full_page=True)
            page.locator("script").evaluate_all("(nodes) => nodes.forEach(n => n.remove())")
            (evidence / "onesignal-setup.html").write_text(page.content(), encoding="utf-8")
            page.select_option("[name=kind]", "org")
            page.fill("[name=key]", "synthetic-secret")
            page.click("#onesignal-key-form button")
            page.wait_for_selector("#onesignal-read-form")
            assert "synthetic-secret" not in page.locator("#onesignal-root").inner_text()
            page.click("#onesignal-read-form button")
            page.wait_for_selector('[data-action="onesignal-bind"]')
            page.click('[data-action="onesignal-bind"]')
            page.wait_for_function("() => window.saved.state === 'APP_BOUND'")
            bound = page.evaluate("() => calls.find(x => x.action === 'bind').body")
            assert bound == {
                "provider_app_id": "11111111-1111-4111-8111-111111111111",
                "expected_name": "Fixture App",
                "expected_org": "22222222-2222-4222-8222-222222222222",
                "version": 1,
            }
            page.locator("#onesignal-channel-options > summary").click()
            page.fill("[name=fcm_v1_service_account_json]", "synthetic-channel-secret")
            page.click("#onesignal-channel-form button")
            page.wait_for_selector('[data-action="onesignal-execute"]')
            assert "synthetic-channel-secret" not in page.locator("#onesignal-root").inner_text()
            assert "PROTECTED_VALUE_SELECTED" in page.locator("#onesignal-root").inner_text()
            assert page.evaluate("() => !calls.some(x => x.action === 'execute')")
            page.click('[data-action="onesignal-refresh"]')
            page.locator("#onesignal-create-options > summary").click()
            page.wait_for_selector("#onesignal-create-form")
            page.fill("[name=organization_id]", "22222222-2222-4222-8222-222222222222")
            page.click("#onesignal-create-form button")
            page.wait_for_selector('[data-action="onesignal-execute"]')
            assert page.evaluate("() => !calls.some(x => x.action === 'execute')")
            prepared = page.evaluate("() => calls.filter(x => x.action === 'prepare').at(-1).body")
            assert prepared["details"] == {
                "name": "Fixture App",
                "organization_id": "22222222-2222-4222-8222-222222222222",
            }
            assert len(prepared["request_key"]) == 36
            page.evaluate("() => {ctx.state.app='other-app'; WMMOneSignal.invalidate(ctx.state)}")
            page.click('[data-action="onesignal-execute"]')
            assert page.evaluate("() => !calls.some(x => x.action === 'execute')")
            page.evaluate("() => {ctx.state.app='local'; WMMOneSignal.open(ctx)}")
            page.locator("#onesignal-create-options > summary").click()
            page.wait_for_selector("#onesignal-create-form")
            page.fill("[name=organization_id]", "22222222-2222-4222-8222-222222222222")
            page.click("#onesignal-create-form button")
            page.wait_for_selector('[data-action="onesignal-execute"]')
            page.evaluate("() => {ctx.state.workspace.app.version++; WMMOneSignal.invalidate(ctx.state)}")
            page.click('[data-action="onesignal-execute"]')
            assert page.evaluate("() => !calls.some(x => x.action === 'execute')")
            page.evaluate("() => WMMOneSignal.open(ctx)")
            page.locator("#onesignal-create-options > summary").click()
            page.wait_for_selector("#onesignal-create-form")
            page.fill("[name=organization_id]", "22222222-2222-4222-8222-222222222222")
            page.click("#onesignal-create-form button")
            page.wait_for_selector('[data-action="onesignal-execute"]')
            page.click('[data-action="onesignal-execute"]')
            page.wait_for_function("() => calls.filter(x => x.action === 'execute').length === 1")
            page.locator("#onesignal-create-options > summary").click()
            page.wait_for_selector("#onesignal-create-form")
            sent = page.evaluate("() => calls.find(x => x.action === 'execute').body")
            assert sent == {
                "effect_id": "33333333-3333-4333-8333-333333333333",
                "source_hash": "a" * 64,
                "confirmed": True,
            }
            page.fill("[name=organization_id]", "22222222-2222-4222-8222-222222222222")
            page.click("#onesignal-create-form button")
            page.wait_for_selector('[data-action="onesignal-execute"]')
            page.evaluate("() => window.outcome='UNKNOWN'")
            page.click('[data-action="onesignal-execute"]')
            page.wait_for_selector("#onesignal-recovery-form")
            assert page.evaluate("() => calls.filter(x => x.action === 'execute').length === 2")
            assert page.locator('[data-action="onesignal-execute"]').count() == 0
            assert "do not retry" in page.locator("#onesignal-root").inner_text().lower()
            page.fill("#onesignal-recovery-form [name=provider_app_id]", "11111111-1111-4111-8111-111111111111")
            page.fill("#onesignal-recovery-form [name=key]", "synthetic-recovery-secret")
            page.click("#onesignal-recovery-form button")
            page.wait_for_selector('[data-action="onesignal-recovery-confirm"]')
            assert "synthetic-recovery-secret" not in page.locator("#onesignal-root").inner_text()
            assert page.evaluate("() => !calls.some(x => x.action === 'recovery-confirm')")
            page.click('[data-action="onesignal-recovery-confirm"]')
            page.locator("#onesignal-key-options > summary").click()
            page.wait_for_selector("#onesignal-key-form")
            assert page.evaluate("() => calls.filter(x => x.action === 'execute').length === 2")
            recovery = page.evaluate("() => calls.find(x => x.action === 'recovery-confirm').body")
            assert recovery == {
                "recovery_id": "44444444-4444-4444-8444-444444444444",
                "source_hash": "b" * 64,
                "confirmed": True,
            }
            browser.close()
