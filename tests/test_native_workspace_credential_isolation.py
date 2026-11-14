"""Verify restored workspaces cannot reuse another path's native social secret."""

import os
import sqlite3
import unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from mission_control.common import Invalid, canonical
from mission_control.credential_vault import Vault
from mission_control.db import connection
from mission_control.social_secrets import Secrets, name
from mission_control.store import Store


@unittest.skipUnless(os.name == "nt", "Requires native Windows Credential Manager")
class NativeWorkspaceCredentialIsolationTests(unittest.TestCase):
    def test_restore_and_database_copy_require_independent_credentials(self) -> None:
        app = "synthetic-host-proof"
        provider = "facebook"
        sentinel = "wmm-vault-test-" + uuid4().hex
        with TemporaryDirectory(prefix="wmm-vault-proof-") as folder:
            base = Path(folder)
            desktop = Store(base / "desktop.sqlite", seed=False)
            desktop.save_app(app, {"name": "Synthetic WMM Host"})
            host = Store(base / "restored-host.sqlite", seed=False)
            secrets = Secrets(desktop)
            ref = secrets.stage(app, provider, {"access_token": sentinel})
            source_name = name(desktop, app, provider, ref, "access_token")
            try:
                self.assertEqual(secrets.load(app, provider, ref), {"access_token": sentinel})
                snapshot = desktop.export(app)
                self.assertNotIn(sentinel, canonical(snapshot))
                self.assertNotIn(ref, canonical(snapshot))
                host.restore(snapshot)
                self.assertEqual(host.app(app)["id"], app)
                with connection(host.path) as db:
                    for statement in (
                        "SELECT count(*) FROM social_configs WHERE app_id=?",
                        "SELECT count(*) FROM social_flows WHERE app_id=?",
                        "SELECT count(*) FROM social_connections WHERE app_id=?",
                        "SELECT count(*) FROM social_retirements WHERE app_id=?",
                    ):
                        row = db.execute(statement, (app,)).fetchone()
                        assert row is not None
                        self.assertEqual(row[0], 0)
                copy = Store(base / "copied-host.sqlite", seed=False)
                with closing(sqlite3.connect(desktop.path)) as src, closing(sqlite3.connect(copy.path)) as dest:
                    src.backup(dest)
                self.assertEqual(copy.app(app)["id"], app)
                for isolated in (host, copy):
                    with self.subTest(path=isolated.path.name):
                        self.assertNotEqual(name(isolated, app, provider, ref, "access_token"), source_name)
                        with self.assertRaisesRegex(Invalid, "reconnect"):
                            Secrets(isolated).load(app, provider, ref)
                self.assertEqual(secrets.load(app, provider, ref), {"access_token": sentinel})
            finally:
                Vault().delete(source_name)
                self.assertIsNone(Vault().get(source_name))
