"""Shared contract for the delivered dashboard's ordered startup scripts."""

import re
from unittest import TestCase


def assert_dashboard_entry(case: TestCase, html: str) -> None:
    """Require the early recovery listener and one unchanged module entry."""
    tags = re.findall(r"<script\b[^>]*>", html, re.IGNORECASE)
    case.assertEqual(
        tags,
        ['<script src="/startup-recovery.js">', '<script type="module" src="/dashboard.mjs">'],
    )
