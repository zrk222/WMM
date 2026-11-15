"""Real loopback HTTP owner publication flow; no provider traffic."""

from datetime import datetime, timedelta, timezone
import json, threading, unittest
from urllib.request import Request
from urllib.error import HTTPError
from unittest.mock import patch
from mission_control.common import canonical
from mission_control.db import connection
from mission_control.operator_client import OperatorClient, ClientError
from mission_control.server import Server
from tests import test_publication_authority as authority
from tests import test_verified_review as identities

APP = authority.APP


class PublicationServerTests(unittest.TestCase):
    def setUp(self):
        self.f = authority.PublicationAuthorityTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.store = self.f.store
        with connection(self.store.path) as db:
            row = db.execute("SELECT data FROM social_connections WHERE id=?", (self.f.connection,)).fetchone()
            data = json.loads(row["data"])
            data["destination"].update(name="Synthetic member", kind="PROFILE", tasks=[])
            data["identity"] = {
                "subject_id": "profile1",
                "name": "Synthetic member",
                "destinations": [data["destination"]],
                "permissions": ["openid", "profile", "w_member_social"],
            }
            db.execute("UPDATE social_connections SET data=? WHERE id=?", (canonical(data), self.f.connection))

        def synthetic_owner(path, token):
            user = identities.synthetic_identity(path, token)
            return (
                dict(user, principal=authority.OWNER["principal"], login=authority.OWNER["login"])
                if token == identities.OWNER_TOKEN
                else user
            )

        self.mock = patch("mission_control.operator_identity.github_read", side_effect=synthetic_owner)
        self.mock.start()
        self.addCleanup(self.mock.stop)
        self.server = Server(("127.0.0.1", 0), self.store)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close)
        self.origin = "http://127.0.0.1:" + str(self.server.server_port)
        self.owner = OperatorClient(self.origin)
        self.owner.bootstrap()
        self.owner.request("POST", "/api/identity/login", {"token": identities.OWNER_TOKEN})
        self.base = "/api/apps/" + APP + "/publications"

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def draft_input(self):
        return {
            "provider": "linkedin",
            "kind": "linkedin_text",
            "connection_id": self.f.connection,
            "connection_version": 1,
            "destination_id": "profile1",
            "title": "",
            "caption": "Synthetic owner review",
            "link": None,
            "artifact_id": None,
            "settings": {"visibility": "PUBLIC"},
        }

    def test_owner_read_prepare_approve_queue_and_revoke(self):
        listed = self.owner.request("GET", self.base)
        self.assertIn("linkedin", [x["provider"] for x in listed["channels"]])
        self.assertEqual(listed["authorities"], [])
        draft = self.owner.request("POST", self.base + "/draft", self.draft_input())["draft"]
        self.assertEqual(draft["caption"], "Synthetic owner review")
        self.assertEqual(draft["destination_id"], "profile1")
        item = self.owner.request("POST", self.base + "/prepare", {"draft": draft, "preflight_id": None})
        self.assertEqual(item["status"], "PREPARED")
        body = {
            "review_hash": item["review_hash"],
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            "max_calls": 20,
            "extended_expiry_consent": False,
            "confirm_publish": True,
            "confirm_rights": True,
            "due_at": None,
        }
        result = self.owner.request("POST", self.base + "/" + item["id"] + "/activate", body)
        self.assertEqual(result["status"], "APPROVED")
        with connection(self.store.path) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM jobs WHERE action='social_publication'").fetchone()[0], 0)
        schedule = self.owner.request("POST", self.base + "/execute", {"id": item["id"]})
        self.assertEqual(schedule["status"], "QUEUED")
        result = self.owner.request("POST", self.base + "/" + item["id"] + "/revoke", {"version": result["version"]})
        self.assertEqual(result["status"], "REVOKED")
        with connection(self.store.path) as db:
            self.assertEqual(
                db.execute("SELECT status FROM jobs WHERE id=?", (schedule["job_id"],)).fetchone()[0], "CANCELLED"
            )

    def test_wrong_csrf_and_anonymous_are_denied(self):
        raw = json.dumps(self.draft_input()).encode()
        cookies = "; ".join(c.name + "=" + c.value for c in self.owner.cookies)
        req = Request(
            self.origin + self.base + "/draft",
            data=raw,
            method="POST",
            headers={
                "Origin": self.origin,
                "Content-Type": "application/json",
                "X-CSRF-Token": "forged",
                "Cookie": cookies,
            },
        )
        with self.assertRaises(HTTPError) as error:
            self.owner.opener.open(req, timeout=10)
        self.assertEqual(error.exception.code, 403)
        error.exception.close()
        anon = OperatorClient(self.origin)
        anon.bootstrap()
        with self.assertRaises(ClientError):
            anon.request("POST", self.base + "/draft", self.draft_input())
        other = OperatorClient(self.origin)
        other.bootstrap()
        other.request("POST", "/api/identity/login", {"token": identities.CHECKER_TOKEN})
        with self.assertRaises(ClientError):
            other.request("POST", self.base + "/draft", self.draft_input())
        with self.assertRaises(ClientError):
            other.request("GET", self.base)
        with self.assertRaises(ClientError):
            self.owner.request(
                "POST",
                self.base + "/preflight",
                {"connection_id": self.f.connection, "connection_version": 1, "destination_id": "profile1", "info": {}},
            )


if __name__ == "__main__":
    unittest.main()
