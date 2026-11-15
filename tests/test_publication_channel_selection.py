"""Agent planning selections route five channels without widening executor authority."""

import unittest

from mission_control.marketing_agent_manifest import operating_manifest
from mission_control.publication_contract import PUBLICATION_PROVIDERS


class ChannelSelectionTests(unittest.TestCase):
    def test_fivechannel_routes_are_opt_in_and_preserve_executor_boundary(self):
        publication = operating_manifest({"id": "synthetic", "version": 1, "data": {}})["organic_publication"]
        selected = publication["channel_selection"]
        self.assertEqual(set(selected["available"]), {"facebook", "instagram", "tiktok", "youtube", "linkedin"})
        self.assertEqual(selected["default"], [])
        self.assertEqual(set(selected["routes"]), set(selected["available"]))
        self.assertEqual(selected["routes"]["facebook"]["workflow"], "FACEBOOK_CAMPAIGN")
        self.assertEqual(set(publication["supported_channels"]), set(PUBLICATION_PROVIDERS))
        self.assertNotIn("facebook", PUBLICATION_PROVIDERS)
        for channel in PUBLICATION_PROVIDERS:
            self.assertEqual(selected["routes"][channel]["workflow"], "ORGANIC_PUBLICATION")
            self.assertEqual(
                selected["routes"][channel]["operations"],
                ["publication.draft", "publication.prepare", "publication.execute"],
            )
        for rule in ("not approval", "separately", "missing access", "unknown responses", "app/owner/version"):
            self.assertIn(rule, selected["rule"])


if __name__ == "__main__":
    unittest.main()
