"""Reject fake and overriding connection objects before any helper effects."""
import importlib
import inspect
import sqlite3
import unittest

HELPERS=[['creative_briefs', 'bound_record'], ['creative_briefs', 'latest_proof'], ['creative_briefs', 'critical_findings'], ['creative_briefs', 'bind'], ['creative_library', 'latest_capture'], ['creative_library', 'append_capture'], ['creative_library', 'write_reference'], ['creative_library', 'restore_reference'], ['discovery_store', 'latest'], ['discovery_store', 'append'], ['discovery_store', 'reviews'], ['discovery_store', 'source_results'], ['funnel_store', 'app_context'], ['funnel_store', 'cohort_binding'], ['funnel_store', 'creative_binding'], ['funnel_store', 'research_binding'], ['funnel_store', 'Funnels.insert'], ['managed_media_store', '_manifest'], ['managed_media_store', '_history'], ['managed_media_store', '_reviewer_current'], ['managed_media_store', '_public'], ['managed_media_store', 'Media._insert_review'], ['managed_media_store', 'derivative_snapshot'], ['packaging_bindings', 'shot_claims'], ['packaging_store', 'latest']]

class Fake:
    def execute(self,*args,**kwargs):raise AssertionError('fake execute must never run')

class Overriding(sqlite3.Connection):
    def execute(self,*args,**kwargs):raise AssertionError('override execute must never run')

class NativeEntryTests(unittest.TestCase):
    def check_rejected(self,db):
        for module,path in HELPERS:
            with self.subTest(helper=module+'.'+path):
                fn=importlib.import_module('mission_control.'+module)
                for part in path.split('.'):fn=getattr(fn,part)
                args={name:db if name=='db' else None for name in inspect.signature(fn).parameters}
                with self.assertRaisesRegex(TypeError,'Native SQLite connection required'):fn(**args)
    def test_fake_connection_cannot_execute(self):self.check_rejected(Fake())
    def test_subclass_override_cannot_execute(self):
        db=sqlite3.connect(':memory:',factory=Overriding)
        try:self.check_rejected(db)
        finally:db.close()
