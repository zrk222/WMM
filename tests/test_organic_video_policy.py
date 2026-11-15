"""Durable organic policy tests with local fixtures and controlled renderer receipts."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from mission_control.common import Invalid, canonical, digest, now, uid
from mission_control.db import connection
from mission_control.hypit_jobs import HypitRenders
from mission_control.managed_media_store import Media
from mission_control.operation_authority import PROTECTED, bound_owner, protected
from mission_control.organic_video_policy import Policies, admit_output, validate_policy
from mission_control.review_access import Access
from mission_control.store import Store
from mission_control.worker import run_once
from tests.test_creative_rendering import prepared_render
from tests.test_managed_media_store import synthetic_inspection

APP = "render-test"
OWNER = dict(principal="github:321", login="owner")
CONNECTION = "11111111-1111-4111-8111-111111111111"
LOCAL_PLAN = dict(
    ok=True,
    preflight=dict(ok=True),
    requestIssueCount=0,
    producerFailureCount=0,
    providerRequestCount=0,
    unresolvedRequestCount=0,
    unsupportedRequestCount=0,
    requestCount=2,
    localRequestCount=2,
    needs=[dict(endpoint="html.local"), dict(endpoint="media.local")],
)


class Sessions:
    active = True

    def local(self, session, principal, generation=None):
        if not self.active or generation not in (None, 1):
            raise PermissionError("Fixture session expired")
        return dict(session_generation=1)


class OrganicPolicyTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.store = Store(Path(folder.name) / "state.sqlite")
        self.brief, self.request = prepared_render(self.store)
        self.sessions = Sessions()
        Access(self.store).bootstrap(APP, OWNER, dict(confirm_owner=True))

        def inspect_fixture(raw, suffix, alive):
            result = synthetic_inspection(raw, suffix, alive)
            result["metadata"]["duration_seconds"] = 30.0
            result["decoded"]["video_frames"] = 720
            return result

        self.media = Media(self.store, inspector=inspect_fixture)
        version = self.store.app(APP)["version"]
        self.source = self.media.upload(
            APP, "demo.mp4", b"synthetic-owned-source", dict(manifest_version=version, request_key="demo-source")
        )
        self.review = dict(
            expected_version=0,
            manifest_version=version,
            source_sha256=self.source["source_sha256"],
            status="ALLOWED",
            basis="OWNED",
            evidence="Synthetic fixture ownership",
        )
        self.source = self.media.review(APP, self.source["id"], self.review, OWNER)
        self.claims = [row for row in self.brief["data"]["records"] if row["kind"] == "claim"]
        stamp = now()
        with connection(self.store.path) as db:
            db.execute(
                "INSERT INTO social_configs VALUES(?,?,?,?,?,?,?,?)",
                (
                    APP,
                    "facebook",
                    1,
                    canonical(dict(provider="facebook")),
                    "fixture",
                    "CONFIGURED_UNTESTED",
                    stamp,
                    stamp,
                ),
            )
            db.execute(
                "INSERT INTO social_connections VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    APP,
                    CONNECTION,
                    "facebook",
                    1,
                    1,
                    "fixture-subject",
                    canonical(dict(destination=dict(id="123"))),
                    "fixture",
                    "CONNECTED_READ_TESTED",
                    None,
                    None,
                    0,
                    None,
                    0,
                    stamp,
                    stamp,
                ),
            )
        self.policies = Policies(self.store)
        self.template = uid()
        self.render_count = 0
        self.expected_first_hash = hashlib.sha256(b"synthetic-rendered-output-1").hexdigest()
        self.policy = dict(
            connection_id=CONNECTION,
            page_id="123",
            expires_at=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            sources=[dict(id=self.source["id"], sha256=self.source["source_sha256"], review_version=1)],
            claims=[dict(id=row["id"], sha256=row["hash"]) for row in self.claims],
            templates=[
                dict(id=self.template, caption="Exact owner caption", claim_ids=[row["id"] for row in self.claims])
            ],
            transformations=["DECLARATIVE_COMPOSITION"],
            generation_providers=["HYPIT_LOCAL"],
            currency="USD",
            max_model_minor=0,
            max_generations=2,
            max_posts=2,
            max_calls=8,
            approved_output_hashes=[self.expected_first_hash],
        )

    def call(self, action, body):
        operation = "organic-video.policy-" + action
        envelope = dict(app_id=APP, operation=operation, input=body)
        with bound_owner(self.store, envelope, self.sessions, "fixture-session", OWNER):
            with protected(self.store, envelope):
                return getattr(self.policies, action)(APP, body)

    def create(self, policy=None):
        self.creation = dict(request_id=uid(), policy=deepcopy(self.policy if policy is None else policy))
        return self.call("create", self.creation)

    def admission(self, policy, artifact=None, **changes):
        artifact = self.reserved_render(policy) if artifact is None else artifact
        output = dict(
            request_id=uid(),
            artifact_id=artifact["id"],
            artifact_sha256=artifact["sha256"],
            template_id=self.template,
            caption="Exact owner caption",
            transformation="DECLARATIVE_COMPOSITION",
            reserve_calls=4,
            reservation_id=artifact["reservation"]["id"],
            reservation_hash=artifact["reservation"]["hash"],
        )
        output.update(changes)
        return dict(policy_id=policy["id"], policy_hash=policy["hash"], output=output)

    def reservation_body(self, policy):
        return dict(
            policy_id=policy["id"],
            policy_hash=policy["hash"],
            request_id=uid(),
            template_id=self.template,
            render_input=dict(
                self.request,
                footage=[
                    dict(
                        scene_index=0,
                        id=self.source["id"],
                        sha256=self.source["source_sha256"],
                        in_frame=0,
                        audio="MUTE",
                    )
                ],
            ),
        )

    def reserved_render(self, policy, plan=LOCAL_PLAN):
        reservation = self.call("reserve", self.reservation_body(policy))
        artifact = self.render_artifact(reservation, plan)
        return dict(artifact, reservation=reservation)

    def render_artifact(self, reservation, plan=LOCAL_PLAN):
        self.render_count += 1
        render_number = self.render_count
        body = dict(data=reservation["data"]["render_input"], request_key=reservation["data"]["job_request_key"])

        def runtime(folder, scene, alive, submitted, sources):
            build = "bld_FIXTURE_" + str(render_number).zfill(8)
            submitted(build)
            raw = ("synthetic-rendered-output-" + str(render_number)).encode()
            (folder / "video.mp4").write_bytes(raw)
            (folder / "font.ttf").write_bytes(b"fixture-font")
            result = dict(
                build_id=build,
                artifact=dict(sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw)),
                source=dict(source_hashes={}, font_sha256=hashlib.sha256(b"fixture-font").hexdigest()),
                cleanup=dict(worker="STOPPED"),
            )
            if plan is not None:
                result["local_plan"] = deepcopy(plan)
            return result

        with patch(
            "mission_control.hypit_jobs.identity", return_value=dict(launcher="fixture", launcher_sha256="0" * 64)
        ):
            HypitRenders(self.store).queue(APP, body)
        with patch("mission_control.hypit_jobs.render", side_effect=runtime):
            self.assertTrue(run_once(self.store))
        items = HypitRenders(self.store).list(APP)["items"]
        latest = next(
            row for row in items if row["data"]["receipt"]["build_id"] == "bld_FIXTURE_" + str(render_number).zfill(8)
        )
        return dict(id=latest["id"], sha256=latest["data"]["artifact"]["sha256"])

    def test_exact_default_durable_admission_replay_and_immutable_history(self):
        policy = self.create()
        self.assertEqual(policy["data"]["policy"]["mode"], "EXACT")
        self.assertEqual(policy, self.call("create", self.creation))
        body = self.admission(policy)
        result = self.call("admit", body)
        self.assertEqual(result, self.call("admit", body))
        self.assertEqual(result["data"]["model_service_minor"], 0)
        self.assertEqual(result["data"]["provider_calls_reserved"], 4)
        self.assertEqual(result["data"]["output"]["generation"]["cost_status"], "LOCAL_PLAN_NO_PROVIDER_REQUESTS")
        with connection(self.store.path) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM organic_video_admissions").fetchone()[0], 1)
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("UPDATE organic_video_admissions SET hash='changed'")
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("INSERT OR REPLACE INTO organic_video_admissions SELECT * FROM organic_video_admissions")
        for changes in (dict(caption="Changed"), dict(artifact_sha256="0" * 64), dict(reserve_calls=5)):
            altered = dict(body, output=dict(body["output"], **changes))
            with self.subTest(changes=changes), self.assertRaises(Invalid):
                self.call("admit", altered)

    def test_generated_mode_atomic_generation_post_and_call_reservations(self):
        for limit in ("max_posts", "max_calls"):
            proposal = dict(self.policy, mode="STANDING_GENERATED", approved_output_hashes=[])
            proposal[limit] = 4 if limit == "max_calls" else 1
            policy = self.create(proposal)
            bodies = [self.admission(policy, self.reserved_render(policy)) for _ in range(2)]

            def run(body):
                try:
                    return self.call("admit", body)["id"]
                except PermissionError:
                    return "DENIED"

            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(run, bodies))
            self.assertEqual(results.count("DENIED"), 1, limit)

    def test_reserve_precedes_job_and_replays_without_refunding_uncertain_attempts(self):
        policy = self.create(dict(self.policy, mode="STANDING_GENERATED", approved_output_hashes=[], max_generations=1))
        body = self.reservation_body(policy)
        reservation = self.call("reserve", body)
        self.assertEqual(reservation, self.call("reserve", body))
        with connection(self.store.path) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM jobs WHERE app_id=?", (APP,)).fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT count(*) FROM organic_video_generation_reservations").fetchone()[0], 1)
        changed = deepcopy(body)
        changed["render_input"]["footage"][0]["in_frame"] = 1
        with self.assertRaisesRegex(Invalid, "Generation request identity"):
            self.call("reserve", changed)
        # Leaving the reserved render unstarted/uncertain does not restore quota.
        with self.assertRaisesRegex(PermissionError, "generation ceiling"):
            self.call("reserve", self.reservation_body(policy))

    def test_metadata_only_heartbeat_preserves_rights_checks_and_default_reads_bytes(self):
        policy = self.create()
        from mission_control import managed_media_store

        original = managed_media_store._read_original
        with connection(self.store.path) as db:
            row = db.execute("SELECT * FROM organic_video_policies WHERE id=?", (policy["id"],)).fetchone()
            with patch.object(managed_media_store, "_read_original", wraps=original) as reader:
                self.policies._current(db, row, verify_bytes=False)
                reader.assert_not_called()
                self.policies._current(db, row)
                self.assertGreater(reader.call_count, 0)
        self.media.review(APP, self.source["id"], dict(self.review, expected_version=1, status="REVOKED"), OWNER)
        with connection(self.store.path) as db:
            row = db.execute("SELECT * FROM organic_video_policies WHERE id=?", (policy["id"],)).fetchone()
            with self.assertRaises(Invalid):
                self.policies._current(db, row, verify_bytes=False)

    def test_concurrent_generation_reservations_are_atomic(self):
        policy = self.create(dict(self.policy, mode="STANDING_GENERATED", approved_output_hashes=[], max_generations=1))

        def reserve(body):
            try:
                return self.call("reserve", body)["id"]
            except PermissionError:
                return "DENIED"

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(reserve, [self.reservation_body(policy), self.reservation_body(policy)]))
        self.assertEqual(results.count("DENIED"), 1)

    def test_reserved_queue_rejects_fake_and_revoked_and_reuses_one_job(self):
        policy = self.create()
        reservation = self.call("reserve", self.reservation_body(policy))
        body = dict(data=reservation["data"]["render_input"], request_key=reservation["data"]["job_request_key"])
        with patch(
            "mission_control.hypit_jobs.identity", return_value=dict(launcher="fixture", launcher_sha256="0" * 64)
        ):
            with self.assertRaises(Invalid):
                HypitRenders(self.store).queue(APP, dict(body, request_key="organic-video-reservation:" + uid()))
            first = HypitRenders(self.store).queue(APP, body)
            self.assertEqual(first["id"], HypitRenders(self.store).queue(APP, body)["id"])
            self.call("revoke", dict(policy_id=policy["id"], policy_hash=policy["hash"]))
            with self.assertRaisesRegex(PermissionError, "revoked"):
                HypitRenders(self.store).queue(APP, body)
        with connection(self.store.path) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM organic_video_reserved_jobs").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT count(*) FROM jobs").fetchone()[0], 1)

    def test_reserve_then_revoke_blocks_queue_and_queued_revoke_blocks_start(self):
        for queue_first in (False, True):
            with self.subTest(queue_first=queue_first):
                policy = self.create()
                reservation = self.call("reserve", self.reservation_body(policy))
                body = dict(
                    data=reservation["data"]["render_input"], request_key=reservation["data"]["job_request_key"]
                )
                with patch(
                    "mission_control.hypit_jobs.identity",
                    return_value=dict(launcher="fixture", launcher_sha256="0" * 64),
                ):
                    if queue_first:
                        job = HypitRenders(self.store).queue(APP, body)
                    self.call("revoke", dict(policy_id=policy["id"], policy_hash=policy["hash"]))
                    if not queue_first:
                        with self.assertRaisesRegex(PermissionError, "revoked"):
                            HypitRenders(self.store).queue(APP, body)
                if queue_first:
                    with patch("mission_control.hypit_jobs.render") as renderer:
                        self.assertTrue(run_once(self.store))
                        renderer.assert_not_called()
                    with connection(self.store.path) as db:
                        self.assertNotEqual(
                            db.execute("SELECT status FROM jobs WHERE id=?", (job["id"],)).fetchone()[0], "SUCCEEDED"
                        )
                        self.assertEqual(
                            db.execute("SELECT count(*) FROM hypit_renders WHERE job_id=?", (job["id"],)).fetchone()[0],
                            0,
                        )

    def test_revoke_during_render_blocks_artifact_commit(self):
        policy = self.create()
        reservation = self.call("reserve", self.reservation_body(policy))
        body = dict(data=reservation["data"]["render_input"], request_key=reservation["data"]["job_request_key"])
        with patch(
            "mission_control.hypit_jobs.identity", return_value=dict(launcher="fixture", launcher_sha256="0" * 64)
        ):
            job = HypitRenders(self.store).queue(APP, body)

        def runtime(folder, scene, alive, submitted, sources):
            submitted("bld_FIXTURE_00000001")
            raw = b"synthetic-rendered-output-1"
            (folder / "video.mp4").write_bytes(raw)
            return dict(
                build_id="bld_FIXTURE_00000001", artifact=dict(sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))
            )

        original = HypitRenders.commit

        def revoke_before_commit(instance, job, folder, result):
            self.call("revoke", dict(policy_id=policy["id"], policy_hash=policy["hash"]))
            return original(instance, job, folder, result)

        with (
            patch("mission_control.hypit_jobs.render", side_effect=runtime),
            patch.object(HypitRenders, "commit", new=revoke_before_commit),
        ):
            self.assertTrue(run_once(self.store))
        with connection(self.store.path) as db:
            self.assertNotEqual(
                db.execute("SELECT status FROM jobs WHERE id=?", (job["id"],)).fetchone()[0], "SUCCEEDED"
            )
            self.assertEqual(
                db.execute("SELECT count(*) FROM hypit_renders WHERE job_id=?", (job["id"],)).fetchone()[0], 0
            )

    def test_output_requires_exact_reservation_and_job_request_identity(self):
        policy = self.create(dict(self.policy, mode="STANDING_GENERATED", approved_output_hashes=[]))
        first = self.reserved_render(policy)
        second = self.reserved_render(policy)
        body = self.admission(policy, first)
        body["output"]["reservation_id"] = second["reservation"]["id"]
        body["output"]["reservation_hash"] = second["reservation"]["hash"]
        with self.assertRaisesRegex(Invalid, "pre-render reservation"):
            self.call("admit", body)
        body["output"]["reservation_hash"] = "f" * 64
        with self.assertRaisesRegex(Invalid, "reservation differs"):
            self.call("admit", body)
        with connection(self.store.path) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM organic_video_admissions").fetchone()[0], 0)

    def test_policy_limits_and_external_or_unknown_cost_are_rejected(self):
        for changes in (
            dict(max_posts=21),
            dict(max_calls=501),
            dict(max_model_minor=1),
            dict(max_generations=True),
            dict(generation_providers=["PAID_MODEL"]),
            dict(extra="authority"),
            dict(expires_at=(datetime.now(timezone.utc) + timedelta(hours=25)).isoformat()),
        ):
            with self.subTest(changes=changes), self.assertRaises(Invalid):
                validate_policy(dict(self.policy, **changes))
        evidence = dict(
            generation_provider="HYPIT_LOCAL",
            service_cost_minor=0,
            currency="USD",
            cost_status="LOCAL_PLAN_NO_PROVIDER_REQUESTS",
            receipt_hash="a" * 64,
        )
        output = dict(
            request_id=uid(),
            artifact_id=uid(),
            artifact_sha256=self.expected_first_hash,
            template_id=self.template,
            caption="Exact owner caption",
            transformation="DECLARATIVE_COMPOSITION",
            reserve_calls=4,
            reservation_id=uid(),
            reservation_hash="a" * 64,
        )
        for changes in (
            dict(cost_status="UNKNOWN"),
            dict(service_cost_minor=1),
            dict(service_cost_minor=None),
            dict(generation_provider="PAID_MODEL"),
            dict(currency="EUR"),
        ):
            with self.subTest(changes=changes), self.assertRaises(Invalid):
                admit_output(self.policy, output, dict(evidence, **changes))
        for plan in (None, dict(LOCAL_PLAN, providerRequestCount=1), dict(LOCAL_PLAN, localRequestCount=None)):
            policy = self.create(dict(self.policy, mode="STANDING_GENERATED", approved_output_hashes=[]))
            artifact = self.reserved_render(policy, plan)
            with self.subTest(plan=plan), self.assertRaises(Invalid):
                self.call("admit", self.admission(policy, artifact))

    def test_revocation_and_current_page_app_claim_rights_checks(self):
        policy = self.create()
        admission = self.admission(policy)
        body = dict(policy_id=policy["id"], policy_hash=policy["hash"])
        self.assertEqual(self.call("read", body), policy)
        self.assertEqual(self.call("revoke", body)["status"], "REVOKED")
        self.assertEqual(self.call("revoke", body)["status"], "REVOKED")
        with self.assertRaisesRegex(PermissionError, "revoked"):
            self.call("admit", admission)
        with self.assertRaisesRegex(PermissionError, "revoked"):
            self.call("reserve", self.reservation_body(policy))

    def test_page_app_owner_and_expiry_changes_invalidate_policy(self):
        policy = self.create()
        body = self.admission(policy)
        with connection(self.store.path) as db:
            db.execute("UPDATE social_connections SET version=2 WHERE app_id=? AND id=?", (APP, CONNECTION))
        with self.assertRaisesRegex(PermissionError, "Page connection changed"):
            self.call("admit", body)
        with connection(self.store.path) as db:
            db.execute("UPDATE social_connections SET version=1 WHERE app_id=? AND id=?", (APP, CONNECTION))
            db.execute("UPDATE operator_roles SET version=2 WHERE app_id=? AND principal=?", (APP, OWNER["principal"]))
        with self.assertRaisesRegex(Invalid, "role changed"):
            self.call("admit", body)
        with connection(self.store.path) as db:
            db.execute("UPDATE operator_roles SET version=1 WHERE app_id=? AND principal=?", (APP, OWNER["principal"]))
        future = datetime.now(timezone.utc) + timedelta(hours=2)
        with patch("mission_control.organic_video_policy.datetime") as clock:
            clock.now.return_value = future
            with self.assertRaisesRegex(PermissionError, "expired"):
                self.call("admit", body)
        app = self.store.app(APP)
        self.store.save_app(APP, dict(app["data"], name="Changed app"), version=app["version"])
        with self.assertRaisesRegex(PermissionError, "app changed"):
            self.call("admit", body)

    def test_final_recheck_rolls_back_reservation_when_session_expires(self):
        policy = self.create()
        from mission_control.hypit_jobs import artifact_file

        calls = []

        def expire_after_final_bytes(*args):
            result = artifact_file(*args)
            calls.append(True)
            if len(calls) == 2:
                self.sessions.active = False
            return result

        with patch("mission_control.hypit_jobs.artifact_file", side_effect=expire_after_final_bytes):
            with self.assertRaisesRegex(PermissionError, "session expired"):
                self.call("admit", self.admission(policy))
        with connection(self.store.path) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM organic_video_admissions").fetchone()[0], 0)

    def test_exact_envelope_prevents_cross_operation_and_request_substitution(self):
        body = dict(request_id=uid(), policy=self.policy)
        envelope = dict(app_id=APP, operation="organic-video.policy-create", input=body)
        with bound_owner(self.store, envelope, self.sessions, "fixture-session", OWNER):
            with protected(self.store, envelope):
                with self.assertRaisesRegex(PermissionError, "differs from its protected admission"):
                    self.policies.create(APP, dict(body, request_id=uid()))
                with self.assertRaises(PermissionError):
                    self.policies.read(APP, dict(policy_id=uid(), policy_hash="a" * 64))

    def test_source_and_claim_changes_and_expiry_block_admission(self):
        policy = self.create()
        admission = self.admission(policy)
        self.media.review(APP, self.source["id"], dict(self.review, expected_version=1, status="REVOKED"), OWNER)
        with self.assertRaises(Invalid):
            self.call("admit", admission)
        self.media.review(APP, self.source["id"], dict(self.review, expected_version=2), OWNER)
        proposal = deepcopy(self.policy)
        proposal["sources"][0]["review_version"] = 3
        policy = self.create(proposal)
        admission = self.admission(policy)
        claim = self.claims[0]
        self.store.save_record(
            APP,
            dict(
                id=claim["id"],
                version=claim["version"],
                kind="claim",
                title=claim["title"],
                source=claim["source"],
                data=dict(claim["data"], claim="Changed approved claim"),
            ),
        )
        with self.assertRaisesRegex(Invalid, "claim evidence changed"):
            self.call("admit", admission)

    def test_unbound_and_agent_policy_mutations_are_rejected(self):
        body = dict(request_id=uid(), policy=self.policy)
        with self.assertRaises(PermissionError):
            self.policies.create(APP, body)
        context = dict(
            store=str(self.store.path.resolve()),
            grant_id="unavailable",
            envelope=canonical(dict(app_id=APP, operation="organic-video.policy-create", input=body)),
        )
        token = PROTECTED.set(context)
        try:
            with self.assertRaises(PermissionError):
                self.policies.create(APP, body)
        finally:
            PROTECTED.reset(token)
