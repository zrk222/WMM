#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::path::Path;
use std::process::ExitCode;
use std::sync::Mutex;
use tauri::{webview::NewWindowResponse, Manager, RunEvent, Url, WebviewUrl, WebviewWindowBuilder};
use wmm_native_launcher::Engine;

struct EngineSlot(Mutex<Option<Engine>>);

fn on_dashboard(candidate: &Url, root: &Url) -> bool {
    candidate.origin() == root.origin()
        && candidate.username().is_empty()
        && candidate.password().is_none()
        && candidate.path() == "/"
        && candidate.query().is_none()
}

fn on_repair_screen(candidate: &Url) -> bool {
    matches!(
        (candidate.scheme(), candidate.host_str()),
        ("tauri", Some("localhost")) | ("http", Some("tauri.localhost"))
    ) && candidate.port().is_none()
        && candidate.username().is_empty()
        && candidate.password().is_none()
        && matches!(candidate.path(), "/" | "/index.html")
        && candidate.query().is_none()
}

fn shell_window(
    app: &tauri::App,
    url: WebviewUrl,
) -> WebviewWindowBuilder<'_, tauri::Wry, tauri::App> {
    WebviewWindowBuilder::new(app, "mission-control", url)
        .title("Wize Marketing Machine")
        .inner_size(1280.0, 900.0)
        .min_inner_size(390.0, 420.0)
        .incognito(true)
        .devtools(false)
        .on_new_window(|_, _| NewWindowResponse::Deny)
}

fn dashboard(
    app: &tauri::App,
    engine_directory: &Path,
) -> Result<Engine, Box<dyn std::error::Error>> {
    let mut expected = [0; 32];
    hex::decode_to_slice(env!("WMM_NATIVE_ENGINE_SHA256"), &mut expected)?;
    let engine = Engine::start(engine_directory, expected)?;
    let root: Url = engine.origin().parse()?;
    shell_window(app, WebviewUrl::External(root.clone()))
        .on_navigation(move |candidate| on_dashboard(candidate, &root))
        .build()?;
    Ok(engine)
}

fn main() -> ExitCode {
    let app = tauri::Builder::default()
        .setup(|app| {
            match app
                .path()
                .resource_dir()
                .ok()
                .and_then(|p| dashboard(app, &p.join("WMM")).ok())
            {
                Some(engine) => {
                    app.manage(EngineSlot(Mutex::new(Some(engine))));
                }
                None => {
                    shell_window(app, WebviewUrl::App("index.html".into()))
                        .on_navigation(on_repair_screen)
                        .build()?;
                }
            }
            Ok(())
        })
        .build(tauri::generate_context!());
    let Ok(app) = app else {
        return ExitCode::FAILURE;
    };
    let started = app.try_state::<EngineSlot>().is_some();
    let clean = std::sync::Arc::new(std::sync::atomic::AtomicBool::new(true));
    let stopped = clean.clone();
    let code = app.run_return(move |handle, event| {
        if matches!(event, RunEvent::Exit) {
            if let Some(slot) = handle.try_state::<EngineSlot>() {
                let engine = slot.0.lock().expect("engine slot").take();
                if let Some(engine) = engine {
                    stopped.store(
                        engine.shutdown().is_ok(),
                        std::sync::atomic::Ordering::Relaxed,
                    );
                }
            }
        }
    });
    if started && code == 0 && clean.load(std::sync::atomic::Ordering::Relaxed) {
        ExitCode::SUCCESS
    } else {
        ExitCode::FAILURE
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn repair_screen_only_accepts_bundled_root() {
        for candidate in ["tauri://localhost/", "http://tauri.localhost/index.html"] {
            assert!(on_repair_screen(&Url::parse(candidate).unwrap()));
        }
        for candidate in [
            "tauri://untrusted/",
            "http://tauri.localhost.example.invalid/",
            "http://tauri.localhost:8765/",
            "http://tauri.localhost/index.html?token=fixture",
            "http://127.0.0.1:8765/",
        ] {
            assert!(
                !on_repair_screen(&Url::parse(candidate).unwrap()),
                "{candidate}"
            );
        }
    }

    #[test]
    fn only_exact_owned_dashboard_can_navigate() {
        let root = Url::parse("http://127.0.0.1:17327/").unwrap();
        assert!(on_dashboard(&root, &root));
        assert!(on_dashboard(&root.join("#main").unwrap(), &root));
        for candidate in [
            "http://127.0.0.1:17328/",
            "http://localhost:17327/",
            "https://127.0.0.1:17327/",
            "http://user@127.0.0.1:17327/",
            "http://127.0.0.1:17327/social/callback/facebook",
            "http://127.0.0.1:17327/?code=fixture",
            "https://example.invalid/",
            "blob:http://127.0.0.1:17327/id",
        ] {
            assert!(
                !on_dashboard(&Url::parse(candidate).unwrap(), &root),
                "{candidate}"
            );
        }
    }
}
