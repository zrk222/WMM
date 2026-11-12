"""Synthetic source fixtures: the audit never executes these modules."""

from pathlib import Path
import importlib.util
import sys
import tempfile
import unittest

_spec = importlib.util.spec_from_file_location(
    "wmm_effect_audit", Path(__file__).resolve().parents[1] / "tools" / "audit_operation_effects.py"
)
_module = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _module
_spec.loader.exec_module(_module)
Audit = _module.Audit


class OperationEffectAuditTests(unittest.TestCase):
    def fixture(self, runtime, effect="WRITE_LOCAL_PLAN", extra=None, operations=None):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        package = root / "mission_control"
        package.mkdir()
        entries = operations or {"sample.save": effect}
        catalog = (
            "OPERATIONS={"
            + ",".join(
                repr(key) + ":descriptor('POST','/sample'," + repr(label) + ")" for key, label in entries.items()
            )
            + "}\n"
        )
        (package / "operation_catalog.py").write_text(catalog, encoding="utf-8")
        (package / "operation_runtime.py").write_text(runtime, encoding="utf-8")
        for name, text in (extra or {}).items():
            (package / name).write_text(text, encoding="utf-8")
        return root

    def test_local_write_to_provider_transport_fails_with_path(self):
        root = self.fixture(
            "from .local import save\ndef execute(service,envelope):\n return {'sample.save':lambda:save()}[envelope['operation']]()\n",
            extra={
                "local.py": "from .social_transport import request as send\ndef save():\n return send()\n",
                "social_transport.py": 'def request():\n raise AssertionError("must never execute")\n',
            },
        )
        report = Audit(root).run()
        self.assertFalse(report["ok"])
        result = report["results"][0]
        self.assertEqual("FAIL", result["status"])
        self.assertIn("social_transport.py", str(result["provider_paths"]))
        self.assertIn("local.py", str(result["provider_paths"]))

    def test_local_handler_passes_without_importing(self):
        root = self.fixture(
            "from .local import save\ndef execute(service,envelope):\n return {'sample.save':lambda:save()}[envelope['operation']]()\n",
            extra={"local.py": 'raise RuntimeError("import forbidden")\ndef save():\n return 1\n'},
        )
        report = Audit(root).run()
        self.assertTrue(report["ok"])
        self.assertTrue(report["heuristic"])

    def test_missing_root_fails(self):
        root = self.fixture('def execute(service,envelope):\n return {}[envelope["operation"]]()\n')
        report = Audit(root).run()
        self.assertFalse(report["ok"])
        self.assertEqual("unresolved handler root", report["results"][0]["reason"])

    def test_parse_error_fails_closed(self):
        root = self.fixture("def execute(:\n")
        report = Audit(root).run()
        self.assertFalse(report["ok"])
        self.assertTrue(report["errors"])

    def test_prefix_dispatch_specializes_action_and_follows_class(self):
        root = self.fixture(
            "def execute(service,envelope):\n if envelope['operation'].startswith('sample.'):\n  from .local import dispatch\n  return dispatch(envelope['operation'].split('.')[1])\n",
            extra={
                "local.py": "from .social_transport import request\ndef dispatch(action):\n if action=='read':return read()\n if action=='save':return request()\ndef read():return 1\n",
                "social_transport.py": "def request():pass\n",
            },
            operations={"sample.read": "READ_PRIVATE_LOCAL_DATA", "sample.save": "WRITE_LOCAL_PLAN"},
        )
        report = Audit(root).run()
        results = {r["operation"]: r for r in report["results"]}
        self.assertEqual("PASS", results["sample.read"]["status"])
        self.assertEqual("FAIL", results["sample.save"]["status"])

    def test_external_label_reports_provider_path(self):
        root = self.fixture(
            "from .social_transport import request\ndef execute(service,envelope):\n return request()\n",
            effect="PUBLISH_WITH_EXACT_ORGANIC_POLICY",
            extra={"social_transport.py": "def request():pass\n"},
        )
        report = Audit(root).run()
        self.assertTrue(report["ok"])
        self.assertTrue(report["results"][0]["provider_paths"])

    def test_dynamic_root_does_not_pass(self):
        root = self.fixture('def execute(service,envelope):\n return getattr(service,envelope["operation"])()\n')
        report = Audit(root).run()
        self.assertFalse(report["ok"])
        self.assertTrue(report["results"][0]["unresolved_dynamic_edges"])

    def test_network_context_manager_is_followed(self):
        root = self.fixture(
            "from .local import save\ndef execute(service,envelope):return save()\n",
            extra={
                "local.py": 'from urllib.request import urlopen\ndef save():\n with urlopen("https://example.invalid") as response:\n  return 1\n'
            },
        )
        report = Audit(root).run()
        self.assertFalse(report["ok"])
        self.assertIn("urlopen", str(report["results"][0]["provider_paths"]))

    def test_provider_call_in_keyword_argument_is_followed(self):
        root = self.fixture(
            "from .local import save\ndef execute(service,envelope):return save()\n",
            extra={
                "local.py": "from .social_transport import request\ndef save():\n return dict(value=request())\n",
                "social_transport.py": "def request():pass\n",
            },
        )
        self.assertFalse(Audit(root).run()["ok"])

    def test_provider_call_in_constructor_is_followed(self):
        root = self.fixture(
            "from .local import Handler\ndef execute(service,envelope):return Handler().run()\n",
            extra={
                "local.py": "from .social_transport import request\nclass Handler:\n def __init__(self):request()\n def run(self):return 1\n",
                "social_transport.py": "def request():pass\n",
            },
        )
        report = Audit(root).run()
        self.assertFalse(report["ok"])
        self.assertIn("__init__", str(report["results"][0]["provider_paths"]))

    def test_provider_call_in_try_else_is_followed(self):
        root = self.fixture(
            "from .local import save\ndef execute(service,envelope):return save()\n",
            extra={
                "local.py": "from .social_transport import request\ndef save():\n try:pass\n except ValueError:pass\n else:request()\n",
                "social_transport.py": "def request():pass\n",
            },
        )
        self.assertFalse(Audit(root).run()["ok"])

    def test_current_catalog_inventory_is_complete(self):
        root = Path(__file__).resolve().parents[1]
        audit = Audit(root)
        catalog = audit.catalog()
        report = audit.run()
        self.assertEqual(set(catalog), {r["operation"] for r in report["results"]})
        self.assertEqual(len(catalog), report["operations_audited"])
        self.assertFalse(report["errors"])
        self.assertTrue(
            report["ok"], [(r["operation"], r["reason"]) for r in report["results"] if r["status"] == "FAIL"]
        )


if __name__ == "__main__":
    unittest.main()
