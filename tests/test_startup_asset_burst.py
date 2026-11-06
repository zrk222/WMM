"""Exercise the listening socket's real pending-connection capacity."""
from contextlib import ExitStack
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch
from mission_control.server import Server
from mission_control.store import Store


class StartupAssetBurstTests(unittest.TestCase):
    def pending_asset_connections(self):
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            server=Server(('127.0.0.1',0),Store(Path(folder)/'synthetic.sqlite',seed=False))
            stack.callback(server.server_close)
            # Hold the accept loop briefly: browser connections must queue
            # rather than lose a script while the local server is busy.
            for _ in range(12):
                stack.enter_context(socket.create_connection(server.server_address,timeout=0.5))

    def test_browser_asset_burst_can_queue_before_accept(self):
        self.pending_asset_connections()

    def test_old_five_connection_queue_rejects_the_same_burst(self):
        with patch.object(Server,'request_queue_size',5):
            with self.assertRaises(OSError):
                self.pending_asset_connections()
