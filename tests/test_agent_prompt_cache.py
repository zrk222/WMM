"""Stable prefix structure only; provider KV hit rate is not a local test claim."""
import unittest
from mission_control.agent_contract import prompt


class PromptPrefixTests(unittest.TestCase):
    def test_focus_changes_only_the_suffix(self):
        app = {'data': {'name': 'Synthetic app'}}
        first = prompt(app, 'campaign_plan', 'Improve activation')
        second = prompt(app, 'campaign_plan', 'Improve retention')
        self.assertEqual(first.split('\nFocus: ')[0], second.split('\nFocus: ')[0])
        self.assertTrue(first.endswith('\nFocus: Improve activation'))

    def test_private_context_never_changes_policy_prefix(self):
        first = prompt({'data': {'name': 'First app'}}, 'campaign_plan')
        second = prompt({'data': {'name': 'Second app'}}, 'campaign_plan')
        marker = '\nApproved app context: '
        self.assertEqual(first.split(marker)[0], second.split(marker)[0])
        self.assertNotIn('First app', second)
        self.assertLess(first.index(marker), first.index('\nTask: '))


if __name__ == '__main__':
    unittest.main()
