"""Reject only newly introduced public functions without complete annotations."""

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "check_new_public_annotations", ROOT / "tools/check_new_public_annotations.py"
)
assert SPEC and SPEC.loader
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)


class NewPublicAnnotationsTests(unittest.TestCase):
    def test_new_public_function_requires_parameter_and_return_annotations(self) -> None:
        self.assertEqual(
            checker.check_sources("sample.py", "", "def read(value):\n    return value\n"),
            [
                "sample.py: Missing parameter annotation: read.value",
                "sample.py: Missing return annotation: read",
            ],
        )
        self.assertEqual(
            checker.check_sources("sample.py", "", "def read(value: object) -> str:\n    return str(value)\n"),
            [],
        )

    def test_legacy_unannotated_functions_are_not_retroactively_rejected(self) -> None:
        before = "def legacy(value):\n    return value\n"
        after = before + "def current(value: object) -> str:\n    return str(value)\n"
        self.assertEqual(checker.check_sources("sample.py", before, after), [])

    def test_new_public_methods_and_constructors_require_annotations(self) -> None:
        source = """class Handler:
    def __init__(self, store): pass
    def session(self) -> str: return "token"
    def boundary(self, write): return "token"
    def _internal(self, value): return value
"""
        self.assertEqual(
            checker.check_sources("sample.py", "", source),
            [
                "sample.py: Missing parameter annotation: Handler.__init__.store",
                "sample.py: Missing return annotation: Handler.__init__",
                "sample.py: Missing parameter annotation: Handler.boundary.write",
                "sample.py: Missing return annotation: Handler.boundary",
            ],
        )

    def test_new_private_functions_do_not_gain_a_new_requirement(self) -> None:
        self.assertEqual(checker.check_sources("sample.py", "", "def _read(value):\n    return value\n"), [])


if __name__ == "__main__":
    unittest.main()
