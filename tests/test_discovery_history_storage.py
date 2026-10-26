"""Real SQLite replacement semantics cannot overwrite an immutable research revision."""
import sqlite3
import unittest
from mission_control.db import connection
from mission_control.store import Store
from mission_control.common import canonical,digest
from tests import test_discovery_intelligence as fixture


class ResearchStorageTests(unittest.TestCase):
    def setUp(self):
        self.case=fixture.DiscoveryTests('test_deduplicated_immutable_collection_revisions_survive_restart')
        self.case.setUp();self.addCleanup(self.case.tearDown)
        self.path=self.case.store.path
        with connection(self.path) as db:
            self.original=tuple(db.execute('SELECT * FROM discovery_documents ORDER BY rowid LIMIT 1').fetchone())

    def test_replacement_rejects_with_both_recursive_trigger_settings_and_keeps_original(self):
        value=dict(revision='synthetic-replacement')
        changed=(*self.original[:4],canonical(value),digest(value),self.original[6])
        for recursive in (0,1):
            for action in ('REPLACE','INSERT OR REPLACE'):
                with self.subTest(recursive=recursive,action=action):
                    with self.assertRaises(sqlite3.IntegrityError),connection(self.path) as db:
                        db.execute('PRAGMA recursive_triggers='+str(recursive))
                        db.execute(action+' INTO discovery_documents VALUES(?,?,?,?,?,?,?)',changed)
                    with connection(self.path) as db:
                        self.assertEqual(tuple(db.execute('SELECT * FROM discovery_documents ORDER BY rowid LIMIT 1').fetchone()),self.original)
        with connection(self.path) as db:
            fresh=(*self.original[:2],self.original[2]+1,*self.original[3:])
            db.execute('INSERT INTO discovery_documents VALUES(?,?,?,?,?,?,?)',fresh)
            self.assertEqual(db.execute('SELECT count(*) FROM discovery_documents').fetchone()[0],2)

    def test_existing_database_upgrade_adds_replacement_guard_without_rewriting_history(self):
        with connection(self.path) as db:
            db.execute('DROP TRIGGER IF EXISTS discovery_no_replace')
            db.execute('DROP TRIGGER IF EXISTS discovery_no_rowid_replace')
        Store(self.path)
        with self.assertRaises(sqlite3.IntegrityError),connection(self.path) as db:
            db.execute('INSERT OR REPLACE INTO discovery_documents VALUES(?,?,?,?,?,?,?)',self.original)
        with connection(self.path) as db:
            self.assertEqual(tuple(db.execute('SELECT * FROM discovery_documents ORDER BY rowid LIMIT 1').fetchone()),self.original)

    def _assert_explicit_rowid_preserved(self):
        with connection(self.path) as db:
            rowid=db.execute('SELECT rowid FROM discovery_documents').fetchone()[0]
        fresh=(self.original[0],'synthetic-different-id',*self.original[2:])
        for recursive in (0,1):
            for action in ('REPLACE','INSERT OR REPLACE'):
                with self.subTest(recursive=recursive,action=action):
                    with self.assertRaises(sqlite3.IntegrityError),connection(self.path) as db:
                        db.execute('PRAGMA recursive_triggers='+str(recursive))
                        db.execute(action+' INTO discovery_documents(rowid,app_id,id,version,kind,data,hash,created) VALUES(?,?,?,?,?,?,?,?)',(rowid,*fresh))
                    with connection(self.path) as db:
                        self.assertEqual(tuple(db.execute('SELECT * FROM discovery_documents').fetchone()),self.original)
        with connection(self.path) as db:
            db.execute('INSERT INTO discovery_documents VALUES(?,?,?,?,?,?,?)',fresh)
            self.assertEqual(db.execute('SELECT count(*) FROM discovery_documents').fetchone()[0],2)

    def test_explicit_rowid_replacement_cannot_delete_a_different_history_identity(self):
        self._assert_explicit_rowid_preserved()

    def test_upgrade_installs_rowid_guard_even_when_composite_guard_already_exists(self):
        with connection(self.path) as db:
            db.execute('DROP TRIGGER IF EXISTS discovery_no_rowid_replace')
        Store(self.path)
        self._assert_explicit_rowid_preserved()
