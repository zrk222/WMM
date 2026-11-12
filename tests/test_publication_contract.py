"""Pure, provider-free tests for the organic publication review contract."""

from copy import deepcopy
import unittest
import uuid

from mission_control.common import Invalid
from mission_control.common import digest
from mission_control.publication_contract import (
    DRAFT_SCHEMA,
    KINDS,
    SCHEMA,
    channel_catalog,
    channel_descriptor,
    preview_summary,
    validate_draft,
)


def draft(provider, kind):
    values = dict(
        schema=SCHEMA,
        request_id=str(uuid.UUID(int=1)),
        app_id="practice-app",
        manifest_version=3,
        provider=provider,
        connection_id=str(uuid.UUID(int=2)),
        connection_version=4,
        destination_id="member:channel_7",
        kind=kind,
        title="Practice short",
        caption="A useful first step.",
        link="https://example.com/start?source=preview",
        artifact=None if kind == "linkedin_text" else dict(id=str(uuid.UUID(int=3)), sha256="a" * 64),
        rights_hashes=["b" * 64],
        source_hashes=["c" * 64],
    )
    values["settings"] = {
        "instagram": dict(share_to_feed=True),
        "tiktok": dict(
            privacy_level="SELF_ONLY",
            disable_duet=True,
            disable_comment=False,
            disable_stitch=True,
            brand_content_toggle=False,
            brand_organic_toggle=False,
            is_aigc=False,
        ),
        "youtube": dict(privacy_status="private", self_declared_made_for_kids=False, contains_synthetic_media=False),
        "linkedin": dict(visibility="CONNECTIONS"),
    }[provider]
    if kind == "youtube_short":
        values["title"] = "A required YouTube Short title"
    return values


class PublicationContractTests(unittest.TestCase):
    def test_all_provider_kind_contracts_round_trip_without_authority(self):
        for provider, kinds in KINDS.items():
            for kind in kinds:
                with self.subTest(provider=provider, kind=kind):
                    source = draft(provider, kind)
                    original = deepcopy(source)
                    value = validate_draft(source)
                    self.assertEqual(source, original)
                    self.assertEqual(value["provider"], provider)
                    self.assertEqual(value["kind"], kind)
                    self.assertEqual(
                        channel_descriptor(value),
                        dict(
                            provider=provider,
                            kind=kind,
                            destination_id="member:channel_7",
                            connection_id=str(uuid.UUID(int=2)),
                        ),
                    )
                    summary = preview_summary(value)
                    self.assertEqual(summary["review_hash"], digest(value))
                    self.assertEqual(summary["ad_spend_minor"], 0)
                    self.assertEqual(summary["authority"], "NOT_GRANTED")
                    self.assertEqual(summary["privacy"], value["settings"])
                    self.assertNotIn("access_token", summary)

    def test_contract_rejects_identity_revision_channel_and_extra_field_drift(self):
        base = draft("instagram", "instagram_reel")
        mutations = [
            lambda x: x.update(extra_authority=True),
            lambda x: x.update(schema="wmm.organic-publication.v2"),
            lambda x: x.update(request_id="not-a-uuid"),
            lambda x: x.update(app_id="../practice"),
            lambda x: x.update(manifest_version=True),
            lambda x: x.update(manifest_version=0),
            lambda x: x.update(connection_id="../vault"),
            lambda x: x.update(connection_version=False),
            lambda x: x.update(destination_id="x" * 161),
            lambda x: x.update(provider="facebook"),
            lambda x: x.update(kind="tiktok_video"),
            lambda x: x.update(settings={**x["settings"], "owner_approved": True}),
        ]
        for mutate in mutations:
            value = deepcopy(base)
            mutate(value)
            with self.subTest(value=value), self.assertRaises(Invalid):
                validate_draft(value)

    def test_reviewed_media_rights_copy_and_public_link_are_bounded(self):
        base = draft("instagram", "instagram_reel")
        for mutate in (
            lambda x: x.update(artifact=None),
            lambda x: x.update(artifact={**x["artifact"], "sha256": "A" * 64}),
            lambda x: x.update(rights_hashes=[]),
            lambda x: x.update(rights_hashes=["b" * 64, "a" * 64]),
            lambda x: x.update(source_hashes=["z" * 64, "c" * 64]),
            lambda x: x.update(link="http://example.com"),
            lambda x: x.update(link="https://user:password@example.com/video"),
            lambda x: x.update(link="https://example.com/video?access_token=private"),
            lambda x: x.update(link="https://example.com:8443/video"),
            lambda x: x.update(caption=" "),
            lambda x: x.update(caption="é" * 2201),
            lambda x: x.update(title="x" * 101),
        ):
            value = deepcopy(base)
            mutate(value)
            with self.subTest(mutation=mutate), self.assertRaises(Invalid):
                validate_draft(value)

    def test_inclusive_field_and_hash_list_limits(self):
        value = draft("instagram", "instagram_reel")
        value["title"] = "t" * 100
        value["caption"] = "c" * 2200
        value["rights_hashes"] = [f"{index:064x}" for index in range(100)]
        value["source_hashes"] = [f"{index:064x}" for index in range(100, 200)]
        self.assertEqual(len(validate_draft(value)["rights_hashes"]), 100)
        value["source_hashes"].append("f" * 64)
        with self.assertRaises(Invalid):
            validate_draft(value)

    def test_provider_options_are_explicit_and_exact(self):
        invalid_settings = [
            ("instagram", "instagram_reel", dict(share_to_feed=1)),
            ("tiktok", "tiktok_video", {**draft("tiktok", "tiktok_video")["settings"], "privacy_level": "DEFAULT"}),
            ("tiktok", "tiktok_video", {**draft("tiktok", "tiktok_video")["settings"], "is_aigc": 1}),
            (
                "youtube",
                "youtube_short",
                {**draft("youtube", "youtube_short")["settings"], "privacy_status": "friends"},
            ),
            (
                "youtube",
                "youtube_short",
                {**draft("youtube", "youtube_short")["settings"], "contains_synthetic_media": "false"},
            ),
            ("linkedin", "linkedin_video", dict(visibility="PRIVATE")),
        ]
        for provider, kind, settings in invalid_settings:
            value = draft(provider, kind)
            value["settings"] = settings
            with self.subTest(provider=provider, settings=settings), self.assertRaises(Invalid):
                validate_draft(value)

    def test_linkedin_text_has_no_artifact_and_youtube_title_is_required(self):
        text = draft("linkedin", "linkedin_text")
        self.assertIsNone(validate_draft(text)["artifact"])
        text["artifact"] = draft("linkedin", "linkedin_video")["artifact"]
        with self.assertRaises(Invalid):
            validate_draft(text)
        short = draft("youtube", "youtube_short")
        short["title"] = "  "
        with self.assertRaises(Invalid):
            validate_draft(short)

    def test_public_catalog_and_machine_schema_match_supported_kinds(self):
        catalog = channel_catalog()
        self.assertEqual(set(catalog), set(KINDS))
        self.assertTrue(
            all(
                not row["contract_only"] and row["execution_implemented"] and not row["advertising"]
                for row in catalog.values()
            )
        )
        schema_pairs = {
            (row["properties"]["provider"]["const"], row["properties"]["kind"]["const"])
            for row in DRAFT_SCHEMA["oneOf"]
        }
        expected = {(provider, kind) for provider, kinds in KINDS.items() for kind in kinds}
        self.assertEqual(schema_pairs, expected)
        try:
            import jsonschema
        except ImportError:
            self.skipTest("Optional jsonschema package is unavailable; structural agreement checked above")
        validator = jsonschema.Draft202012Validator(DRAFT_SCHEMA)
        for provider, kinds in KINDS.items():
            for kind in kinds:
                value = draft(provider, kind)
                validated = validate_draft(value)
                validator.validate(validated)
                bad = deepcopy(value)
                bad["provider"] = "linkedin" if provider != "linkedin" else "instagram"
                self.assertFalse(validator.is_valid(bad))


if __name__ == "__main__":
    unittest.main()
