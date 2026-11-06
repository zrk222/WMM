"""Private child protocol for the native desktop launcher."""
import hmac
import os
import re
import sys

from .common import canonical
from .desktop import DesktopRuntime
from .native_runtime_identity import file_identity


def serve(source, output):
    """Prove the owned listener before starting workers, and stop when the parent exits."""
    nonce = source.readline(66)
    if not re.fullmatch(rb'[a-f0-9]{64}\n', nonce):
        raise SystemExit('Native desktop launch requires a valid private startup frame.')

    runtime = DesktopRuntime(preferred_port=0, fixed_port=True)
    try:
        packaged = bool(getattr(sys, 'frozen', False))
        frame = canonical(dict(
            protocol='wmm.desktop-sidecar.v1',
            pid=os.getpid(),
            port=runtime.server.server_port,
            sha256=file_identity(sys.executable) if packaged else runtime.server.service.build_id,
            packaged=packaged,
        )).encode('ascii')
        key = bytes.fromhex(nonce[:-1].decode('ascii'))

        def proof(challenge):
            return hmac.digest(key, frame + b'\n' + bytes.fromhex(challenge), 'sha256').hex()

        runtime.server.desktop_proof = proof
        runtime.start(workers=False)
        output.write(frame + b'\n')
        descriptor = output.fileno()
        output.close()
        os.close(descriptor)  # Python's standard streams do not own their inherited descriptors.
        activate = source.readline(7)
        runtime.server.desktop_proof = None
        if activate == b'START\n':
            runtime.start_workers()
            if source.read(1):
                raise SystemExit('Native desktop received an unexpected control frame.')
        elif activate:
            raise SystemExit('Native desktop received an invalid activation frame.')
    finally:
        runtime.close()
