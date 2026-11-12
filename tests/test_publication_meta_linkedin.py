import hashlib, unittest
from dataclasses import replace
from unittest.mock import Mock, patch
from mission_control.common import Invalid
from mission_control import publication_transport
from mission_control import publication_meta as ig, publication_linkedin as li


class Response:
    def __init__(self, data=None, headers=None):
        self.data = data or {}
        self.headers = headers or {}
        self.status = 200


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.raw = b"video-data"
        self.sha = hashlib.sha256(self.raw).hexdigest()
        self.artifact = {"raw": self.raw, "sha256": self.sha, "bytes": len(self.raw)}
        self.ig = {
            "provider": "instagram",
            "kind": "instagram_reel",
            "destination_id": "123",
            "caption": "Hello",
            "link": None,
            "title": "",
            "settings": {"share_to_feed": True},
            "artifact": {"sha256": self.sha},
        }
        self.igctx = publication_transport.Context(
            "instagram", "123", "secret", lambda: None, lambda: None, login_family="facebook"
        )
        self.li = {
            "provider": "linkedin",
            "kind": "linkedin_video",
            "destination_id": "abc123",
            "caption": "Hello",
            "link": None,
            "title": "Video",
            "settings": {"visibility": "PUBLIC"},
            "artifact": {"sha256": self.sha},
        }
        self.lictx = publication_transport.Context("linkedin", "abc123", "secret", lambda: None, lambda: None)

    def test_instagram_stages_and_account_boundary(self):
        uri = "https://rupload.facebook.com/ig-api-upload/v26.0/456"
        with (
            patch.object(
                ig.http,
                "request",
                side_effect=[
                    Response({"id": "456", "uri": uri}),
                    Response({"id": "456", "status_code": "FINISHED"}),
                    Response({"id": "789"}),
                    Response({"id": "789", "media_type": "VIDEO"}),
                ],
            ) as request,
            patch.object(ig.http, "upload", return_value=Response({"success": True})) as upload,
        ):
            created = ig.create(self.ig, self.artifact, self.igctx)
            self.assertEqual(created["status"], "CREATED")
            processing = ig.upload(self.ig, self.artifact, created, self.igctx)
            self.assertEqual(processing["status"], "PROCESSING")
            ready = ig.read(self.ig, processing, self.igctx)
            self.assertEqual(ready["status"], "READY_TO_PUBLISH")
            posted = ig.publish(self.ig, ready, self.igctx)
            self.assertEqual(posted["status"], "PUBLISH_ACKNOWLEDGED")
            observed = ig.read(self.ig, posted, self.igctx)
            self.assertEqual(observed["status"], "PUBLISHED")
            self.assertEqual(observed["observation"]["public_visibility"], "NOT_VERIFIED")
            self.assertEqual(upload.call_args.kwargs["auth_scheme"], "OAuth")
            self.assertEqual(upload.call_args.kwargs["method"], "POST")
            self.assertEqual(request.call_count, 4)
        with self.assertRaises(Invalid):
            ig.create(self.ig, self.artifact, replace(self.igctx, destination_id="999"))
        with self.assertRaises(Invalid):
            ig.create(self.ig, self.artifact, replace(self.igctx, login_family="instagram"))
        with self.assertRaises(Invalid):
            ig.create({**self.ig, "link": "https://example.com"}, self.artifact, self.igctx)

    def test_instagram_rejects_forged_session_and_unknown_effect(self):
        with patch.object(
            ig.http, "request", return_value=Response({"id": "456", "uri": "https://evil.example/upload"})
        ):
            with self.assertRaises(Invalid):
                ig.create(self.ig, self.artifact, self.igctx)
        state = {"status": "READY_TO_PUBLISH", "asset_id": "456"}
        with patch.object(ig.http, "request", side_effect=TimeoutError()) as req:
            with self.assertRaises(TimeoutError):
                ig.publish(self.ig, state, self.igctx)
            self.assertEqual(req.call_count, 1)
        with patch.object(ig.http, "request", return_value=Response({"id": "456", "status_code": "PUBLISHED"})):
            self.assertEqual(
                ig.read(self.ig, {"status": "PROCESSING", "asset_id": "456"}, self.igctx)["status"], "UNKNOWN"
            )

    def test_linkedin_parts_finalize_read_and_receipt(self):
        ins = [
            {"firstByte": 0, "lastByte": 4, "uploadUrl": "https://www.linkedin.com/dms-uploads/1"},
            {"firstByte": 5, "lastByte": 9, "uploadUrl": "https://www.linkedin.com/dms-uploads/2"},
        ]
        created = Response({"value": {"video": "urn:li:video:V1", "uploadInstructions": ins, "uploadToken": ""}})
        with (
            patch.object(
                li.http,
                "request",
                side_effect=[
                    created,
                    Response(),
                    Response({"id": "urn:li:video:V1", "status": "AVAILABLE"}),
                    Response(headers={"x-restli-id": "urn:li:share:7"}),
                    Response({"id": "urn:li:share:7", "author": "urn:li:person:abc123", "lifecycleState": "PUBLISHED"}),
                ],
            ) as request,
            patch.object(
                li.http,
                "upload",
                side_effect=[Response(headers={"etag": '"one"'}), Response(headers={"etag": '"two"'})],
            ) as upload,
        ):
            s = li.create(self.li, self.artifact, self.lictx)
            self.assertEqual(s["status"], "CREATED")
            s = li.upload(self.li, self.artifact, s, self.lictx)
            self.assertEqual(s["session"]["parts"], ["one"])
            self.assertEqual(upload.call_count, 1)
            s = li.upload(self.li, self.artifact, s, self.lictx)
            self.assertEqual(s["session"]["parts"], ["one", "two"])
            self.assertEqual(upload.call_count, 2)
            s = li.upload(self.li, self.artifact, s, self.lictx)
            self.assertEqual(s["status"], "PROCESSING")
            s = li.read(self.li, s, self.lictx)
            self.assertEqual(s["status"], "READY_TO_PUBLISH")
            s = li.publish(self.li, s, self.lictx)
            self.assertEqual(s["status"], "PUBLISH_ACKNOWLEDGED")
            s = li.read(self.li, s, self.lictx)
            self.assertEqual(s["status"], "PUBLISHED")
            self.assertEqual(s["observation"]["public_visibility"], "NOT_VERIFIED")
            self.assertEqual(request.call_count, 5)

    def test_real_transport_constructs_fixed_facebook_host_and_oauth_upload(self):
        uri = "https://rupload.facebook.com/ig-api-upload/v26.0/456"
        responses = [
            publication_transport.Response(200, {}, {"id": "456", "uri": uri}),
            publication_transport.Response(200, {}, {"success": True}),
        ]
        with patch.object(publication_transport, "_exchange", side_effect=responses) as wire:
            state = ig.create(self.ig, self.artifact, self.igctx)
            ig.upload(self.ig, self.artifact, state, self.igctx)
        first, second = wire.call_args_list
        self.assertEqual(first.args[1].hostname, "graph.facebook.com")
        self.assertEqual(first.args[2:4], ("POST", "/v26.0/123/media"))
        self.assertEqual(first.args[5]["Authorization"], "Bearer secret")
        self.assertEqual(second.args[1].hostname, "rupload.facebook.com")
        self.assertEqual(second.args[2:4], ("POST", "/ig-api-upload/v26.0/456"))
        self.assertEqual(second.args[5]["Authorization"], "OAuth secret")
        self.assertEqual(second.args[5]["file_size"], str(len(self.raw)))

    def test_throttle_is_not_retried(self):
        with patch.object(ig.http, "request", side_effect=RuntimeError("rate limited")) as request:
            with self.assertRaises(RuntimeError):
                ig.create(self.ig, self.artifact, self.igctx)
            self.assertEqual(request.call_count, 1)

    def test_linkedin_negative_and_ambiguous(self):
        with self.assertRaises(Invalid):
            li.create(self.li, self.artifact, replace(self.lictx, destination_id="other"))
        s = {"status": "READY_TO_PUBLISH", "asset_id": "urn:li:video:V1"}
        with patch.object(li.http, "request", side_effect=TimeoutError()) as req:
            with self.assertRaises(TimeoutError):
                li.publish(self.li, s, self.lictx)
            self.assertEqual(req.call_count, 1)
        with patch.object(
            li.http,
            "request",
            return_value=Response(
                {"id": "urn:li:share:7", "author": "urn:li:person:someone", "lifecycleState": "PUBLISHED"}
            ),
        ):
            with self.assertRaises(Invalid):
                li.read(self.li, {"status": "PUBLISH_ACKNOWLEDGED", "remote_id": "urn:li:share:7"}, self.lictx)
        with self.assertRaises(Invalid):
            li.create(self.li, {**self.artifact, "raw": b"evil"}, self.lictx)


if __name__ == "__main__":
    unittest.main()
