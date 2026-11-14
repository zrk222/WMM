"""Closed creative learning composes saved evidence without new authority."""

import unittest

from mission_control.creative_learning import summary


def workspace(**overrides):
    value = dict(
        references=[dict(id="reference")],
        analyses=[dict(id="analysis")],
        briefs=[],
        rankings=dict(report=[]),
        renders=dict(items=[]),
        hypit_renders=dict(items=[]),
        provider_actions=[],
        experiments=[],
        learning=dict(programs=[], uses=[]),
    )
    value.update(overrides)
    return value


class CreativeLearningTests(unittest.TestCase):
    def test_empty_loop_names_every_missing_stage(self):
        result = summary(workspace(briefs=[], references=[], analyses=[]))
        self.assertEqual(result["status"], "NO_INPUT")
        self.assertIn("Prepare a production brief", result["gaps"])
        self.assertIn("Record a publication readback", result["gaps"])

    def test_briefed_render_published_and_learning_states(self):
        brief = dict(id="brief", status="READY")
        render = dict(id="render", status="SUCCEEDED")
        action = dict(id="action", status="VERIFIED")
        program = dict(id="program", state="ACTIVE", active=True, data=dict(definition=dict(pattern="outcome-first")))
        result = summary(
            workspace(
                briefs=[brief],
                rankings=dict(report=[dict(reference_id="top", rank=1)]),
                renders=dict(items=[render]),
                provider_actions=[action],
                experiments=[dict(id="e", state="DECIDED", assessments=[dict(id="a")])],
                learning=dict(programs=[program], uses=[dict(id="u")]),
            )
        )
        self.assertEqual(result["status"], "LEARNING_ACTIVE")
        self.assertEqual(result["counts"]["briefs"], 1)
        self.assertEqual(result["counts"]["renders"], 1)
        self.assertEqual(result["counts"]["publications"], 1)
        self.assertEqual(result["learned"]["active_pattern"], "outcome-first")
        self.assertEqual(result["gaps"], [])

    def test_top_ranked_source_and_pattern_seed_the_next_brief(self):
        result = summary(
            workspace(
                briefs=[dict(id="brief")],
                rankings=dict(report=[dict(reference_id="top", rank=1)]),
                learning=dict(
                    programs=[
                        dict(id="p", state="ACTIVE", active=True, data=dict(definition=dict(pattern="proof-first")))
                    ],
                    uses=[],
                ),
            )
        )
        self.assertEqual(result["next_brief"]["source_id"], "top")
        self.assertEqual(result["next_brief"]["learning_pattern"], "proof-first")
        self.assertIn("proof-first", result["next_brief"]["seed"])


if __name__ == "__main__":
    unittest.main()
