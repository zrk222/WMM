use super::*;
use std::io::{BufRead, BufReader};
use std::net::TcpListener;

const NONCE: [u8; 32] = [14; 32];
const FRAME: &[u8] = b"fixture-frame\n";

#[test]
fn rejects_duplicate_truncated_and_oversized_frames() {
    assert_eq!(read_frame(&b"{}\n"[..]).unwrap(), b"{}\n");
    for bytes in [&b"{}\n{}\n"[..], &b"{}"[..], &vec![b'x'; MAX_FRAME + 1][..]] {
        assert!(read_frame(bytes).is_err());
    }
}

#[test]
fn frame_requires_exact_child_identity() {
    let sha = [32; 32];
    let mut ready = serde_json::json!({
        "protocol": PROTOCOL, "pid": 341, "port": 43434, "sha256": hex::encode(sha), "packaged": true
    });
    let bytes = serde_json::to_vec(&ready).unwrap();
    assert_eq!(
        validate_frame(&bytes, 341, sha).unwrap(),
        "127.0.0.1:43434".parse().unwrap()
    );
    assert!(validate_frame(&bytes, 342, sha).is_err());
    assert!(validate_frame(&bytes, 341, [33; 32]).is_err());
    ready["packaged"] = false.into();
    assert!(validate_frame(&serde_json::to_vec(&ready).unwrap(), 341, sha).is_err());
    ready["packaged"] = true.into();
    ready["origin"] = "http://127.0.0.1:1".into();
    assert!(validate_frame(&serde_json::to_vec(&ready).unwrap(), 341, sha).is_err());
}

fn responder(status: &str, extra_header: &str, authentic: bool) -> io::Result<()> {
    let listener = TcpListener::bind((Ipv4Addr::LOCALHOST, 0)).unwrap();
    let address = listener.local_addr().unwrap();
    let status = status.to_owned();
    let extra_header = extra_header.to_owned();
    let worker = thread::spawn(move || {
        let (mut stream, _) = listener.accept().unwrap();
        stream
            .set_read_timeout(Some(Duration::from_secs(3)))
            .unwrap();
        let reader = BufReader::new(&mut stream);
        let lines = reader
            .lines()
            .map(Result::unwrap)
            .take_while(|line| !line.is_empty())
            .collect::<Vec<_>>();
        assert_eq!(lines[0], "GET /api/desktop-proof HTTP/1.0");
        assert_eq!(lines[1], format!("Host: {address}"));
        assert_eq!(lines.len(), 4);
        let challenge =
            hex::decode(lines[2].strip_prefix("X-WMM-Desktop-Challenge: ").unwrap()).unwrap();
        let key = if authentic { NONCE } else { [0; 32] };
        let mut mac = Hmac::<Sha256>::new_from_slice(&key).unwrap();
        mac.update(FRAME);
        mac.update(&challenge);
        let body =
            serde_json::json!({"proof": hex::encode(mac.finalize().into_bytes())}).to_string();
        write!(
            stream,
            "HTTP/1.0 {status}\r\nContent-Length: {}\r\n{extra_header}\r\n{body}",
            body.len()
        )
        .unwrap();
    });
    let result = verify_listener(
        address,
        FRAME,
        &NONCE,
        Instant::now() + Duration::from_secs(3),
    );
    worker.join().unwrap();
    result
}

#[test]
fn proves_listener_without_following_redirects_or_accepting_bad_framing() {
    responder("200 OK", "", true).unwrap();
    assert!(responder("200 OK", "", false).is_err());
    assert!(responder("302 Found", "Location: https://example.invalid/\r\n", true).is_err());
    assert!(responder("200 OK", "Content-Length: 1\r\n", true).is_err());
    assert!(responder("200 OK", "Transfer-Encoding: chunked\r\n", true).is_err());
}

#[test]
fn starts_and_stops_real_python_engine_with_simulated_bundle_identity() {
    let python = std::env::var_os("WMM_TEST_PYTHON").unwrap_or_else(|| "python".into());
    let path = Command::new(&python)
        .args(["-B", "-c", "import sys; print(sys.executable)"])
        .output()
        .unwrap();
    assert!(path.status.success());
    let executable = std::str::from_utf8(&path.stdout).unwrap().trim();
    let bytes = fs::read(executable).unwrap();
    let expected = Sha256::digest(bytes).into();
    let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    let mut command = Command::new(python);
    command.current_dir(root).args([
        "-B",
        "-c",
        r#"
import os
import sys
from tempfile import TemporaryDirectory
from mission_control.desktop_sidecar import serve
with TemporaryDirectory() as directory:
    os.environ.update(LOCALAPPDATA=directory, XDG_DATA_HOME=directory, HOME=directory)
    sys.frozen = True
    serve(sys.stdin.buffer, sys.stdout.buffer)
"#,
    ]);
    let engine = launch(command, expected).unwrap();
    assert!(engine.origin().starts_with("http://127.0.0.1:"));
    engine.shutdown().unwrap();
}
