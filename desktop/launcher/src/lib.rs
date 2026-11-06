use hmac::{Hmac, Mac};
use serde::Deserialize;
use sha2::{Digest, Sha256};
use std::fs::{self, File};
use std::io::{self, Read, Write};
use std::net::{Ipv4Addr, SocketAddr, TcpStream};
use std::path::Path;
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::mpsc;
use std::thread;
use std::time::{Duration, Instant};

const STARTUP_TIMEOUT: Duration = Duration::from_secs(15);
const SHUTDOWN_TIMEOUT: Duration = Duration::from_secs(45);
const PROTOCOL: &str = "wmm.desktop-sidecar.v1";
const MAX_FRAME: usize = 512;
const MAX_PROOF_RESPONSE: usize = 4096;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Ready {
    protocol: String,
    pid: u32,
    port: u16,
    sha256: String,
    packaged: bool,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Proof {
    proof: String,
}

/// An authenticated WMM engine. Dropping the handle closes the lifetime pipe.
pub struct Engine {
    child: Option<Child>,
    control: Option<ChildStdin>,
    address: SocketAddr,
}

impl Engine {
    /// The caller obtains the engine directory and expected digest from trusted package resources.
    pub fn start(engine_directory: &Path, expected_sha256: [u8; 32]) -> io::Result<Self> {
        let executable =
            fs::canonicalize(engine_directory)?.join(if cfg!(windows) { "WMM.exe" } else { "WMM" });
        if !fs::symlink_metadata(&executable)?.is_file() {
            return Err(invalid("The bundled WMM engine must be a regular file."));
        }
        let mut file = File::open(&executable)?;
        let mut digest = Sha256::new();
        io::copy(&mut file, &mut digest)?;
        if <[u8; 32]>::from(digest.finalize()) != expected_sha256 {
            return Err(invalid(
                "The bundled WMM engine does not match its installed digest.",
            ));
        }

        let mut command = Command::new(executable);
        command.arg("--native-sidecar");
        launch(command, expected_sha256)
    }

    pub fn origin(&self) -> String {
        format!("http://{}", self.address)
    }

    /// A clean stop means the engine exited successfully after closing its lifetime pipe.
    pub fn shutdown(mut self) -> io::Result<()> {
        drop(self.control.take());
        let mut child = self.child.take().expect("engine child is owned");
        wait_for_exit(&mut child, SHUTDOWN_TIMEOUT)
    }
}

impl Drop for Engine {
    fn drop(&mut self) {
        drop(self.control.take());
        if let Some(mut child) = self.child.take() {
            thread::spawn(move || {
                let _ = wait_for_exit(&mut child, SHUTDOWN_TIMEOUT);
            });
        }
    }
}

fn launch(mut command: Command, expected_sha256: [u8; 32]) -> io::Result<Engine> {
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000); // CREATE_NO_WINDOW
    }

    let mut child = command
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()?;
    let mut control = child.stdin.take().expect("stdin was piped");
    let output = child.stdout.take().expect("stdout was piped");
    let deadline = Instant::now() + STARTUP_TIMEOUT;

    let ready = (|| {
        let nonce = random_bytes()?;
        writeln!(control, "{}", hex::encode(nonce))?;
        let (send, receive) = mpsc::sync_channel(1);
        thread::spawn(move || {
            let _ = send.send(read_frame(output));
        });
        let frame = receive
            .recv_timeout(time_left(deadline)?)
            .map_err(|error| match error {
                mpsc::RecvTimeoutError::Timeout => timed_out(),
                mpsc::RecvTimeoutError::Disconnected => {
                    invalid("The WMM engine readiness pipe closed.")
                }
            })??;
        let address = validate_frame(&frame, child.id(), expected_sha256)?;
        verify_listener(address, &frame, &nonce, deadline)?;
        control.write_all(b"START\n")?;
        Ok(address)
    })();
    match ready {
        Ok(address) => Ok(Engine {
            child: Some(child),
            control: Some(control),
            address,
        }),
        Err(error) => {
            drop(control);
            let _ = wait_for_exit(&mut child, Duration::from_secs(3));
            Err(error)
        }
    }
}

fn read_frame(output: impl Read) -> io::Result<Vec<u8>> {
    let mut frame = Vec::new();
    output
        .take((MAX_FRAME + 1) as u64)
        .read_to_end(&mut frame)?;
    if frame.len() > MAX_FRAME
        || frame.last() != Some(&b'\n')
        || frame.iter().filter(|byte| **byte == b'\n').count() != 1
    {
        return Err(invalid(
            "The WMM engine must report one bounded readiness frame.",
        ));
    }
    Ok(frame)
}

fn validate_frame(frame: &[u8], pid: u32, expected_sha256: [u8; 32]) -> io::Result<SocketAddr> {
    let ready: Ready = serde_json::from_slice(frame)
        .map_err(|_| invalid("Invalid WMM engine readiness frame."))?;
    if ready.protocol != PROTOCOL
        || ready.pid != pid
        || ready.port == 0
        || !ready.packaged
        || ready.sha256 != hex::encode(expected_sha256)
    {
        return Err(invalid(
            "The WMM engine reported an unexpected process or build identity.",
        ));
    }
    Ok(SocketAddr::from((Ipv4Addr::LOCALHOST, ready.port)))
}

fn verify_listener(
    address: SocketAddr,
    frame: &[u8],
    nonce: &[u8; 32],
    deadline: Instant,
) -> io::Result<()> {
    let challenge = random_bytes()?;
    let mut stream = TcpStream::connect_timeout(&address, time_left(deadline)?)?;
    stream.set_write_timeout(Some(time_left(deadline)?))?;
    write!(
        stream,
        "GET /api/desktop-proof HTTP/1.0\r\nHost: {address}\r\nX-WMM-Desktop-Challenge: {}\r\nConnection: close\r\n\r\n",
        hex::encode(challenge)
    )?;
    let mut response = Vec::new();
    let mut buffer = [0u8; 1024];
    loop {
        stream.set_read_timeout(Some(time_left(deadline)?))?;
        let count = stream.read(&mut buffer)?;
        if count == 0 {
            break;
        }
        if response.len() + count > MAX_PROOF_RESPONSE {
            return Err(invalid("The WMM engine proof response was oversized."));
        }
        response.extend_from_slice(&buffer[..count]);
    }

    let mut headers = [httparse::EMPTY_HEADER; 24];
    let mut parsed = httparse::Response::new(&mut headers);
    let body_start = match parsed.parse(&response) {
        Ok(httparse::Status::Complete(start)) if parsed.code == Some(200) => start,
        _ => {
            return Err(invalid(
                "The WMM engine proof endpoint did not return a local success.",
            ))
        }
    };
    let body = &response[body_start..];
    let mut lengths = parsed
        .headers
        .iter()
        .filter(|header| header.name.eq_ignore_ascii_case("Content-Length"));
    let length = lengths
        .next()
        .and_then(|header| std::str::from_utf8(header.value).ok())
        .and_then(|value| value.parse::<usize>().ok());
    if length != Some(body.len())
        || lengths.next().is_some()
        || parsed
            .headers
            .iter()
            .any(|header| header.name.eq_ignore_ascii_case("Transfer-Encoding"))
    {
        return Err(invalid("Invalid WMM engine proof response framing."));
    }
    let proof: Proof =
        serde_json::from_slice(body).map_err(|_| invalid("Invalid WMM engine proof."))?;
    let mut actual = [0; 32];
    hex::decode_to_slice(proof.proof, &mut actual)
        .map_err(|_| invalid("Invalid WMM engine proof."))?;
    let mut mac = Hmac::<Sha256>::new_from_slice(nonce).expect("a fixed-length HMAC key");
    mac.update(frame);
    mac.update(&challenge);
    mac.verify_slice(&actual)
        .map_err(|_| invalid("The WMM engine listener failed authentication."))
}

fn wait_for_exit(child: &mut Child, timeout: Duration) -> io::Result<()> {
    let deadline = Instant::now() + timeout;
    loop {
        if let Some(status) = child.try_wait()? {
            return if status.success() {
                Ok(())
            } else {
                Err(io::Error::other("The WMM engine exited with an error."))
            };
        }
        if Instant::now() >= deadline {
            child.kill()?;
            child.wait()?;
            return Err(io::Error::new(
                io::ErrorKind::TimedOut,
                "The WMM engine did not stop cleanly.",
            ));
        }
        thread::sleep(Duration::from_millis(25));
    }
}

fn random_bytes() -> io::Result<[u8; 32]> {
    let mut bytes = [0; 32];
    getrandom::getrandom(&mut bytes)
        .map_err(|_| io::Error::other("Secure startup randomness is unavailable."))?;
    Ok(bytes)
}

fn invalid(message: &'static str) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, message)
}

fn timed_out() -> io::Error {
    io::Error::new(io::ErrorKind::TimedOut, "WMM engine startup timed out.")
}

fn time_left(deadline: Instant) -> io::Result<Duration> {
    deadline
        .checked_duration_since(Instant::now())
        .filter(|left| !left.is_zero())
        .ok_or_else(timed_out)
}

#[cfg(test)]
mod tests;
