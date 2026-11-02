"""Exact owner HTTP schedule review; provider wire is synthetic and network-denied."""
import time,unittest
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
from urllib.request import Request
from urllib.error import HTTPError
from mission_control.operator_client import OperatorClient,ClientError
from mission_control.campaign_execution import CampaignExecutionService
from mission_control.worker import run_once
from mission_control.common import canonical
from tests import test_campaign_access as fixture

class ScheduleHTTPTests(unittest.TestCase):
 setUp=fixture.CampaignGatewayTests.setUp
 setUp_base=fixture.CampaignGatewayTests.setUp_base
 tearDown=fixture.CampaignGatewayTests.tearDown
 body=fixture.CampaignGatewayTests.body
 owner_call=fixture.CampaignGatewayTests.owner_call
 activate=fixture.CampaignGatewayTests.activate
 def prepare_batch(self):
  scope=self.activate()
  return self.owner_call("schedule-prepare",{"scope_id":scope["scope_id"],"items":[{"due_at":(datetime.now(timezone.utc)+timedelta(seconds=1)).isoformat(),"request":self.post}]})
 def test_owner_reviews_exact_hash_then_worker_publishes_once_without_browser(self):
  saved=self.prepare_batch();batch=saved["summary"]["batch_id"]
  with self.assertRaises(ClientError):self.owner_call("schedule-activate",{"batch_id":batch,"summary_hash":"0"*64})
  self.owner_call("schedule-activate",{"batch_id":batch,"summary_hash":saved["summary_hash"]})
  self.assertEqual(self.wire.posts,0)
  time.sleep(1.05)
  from mission_control.campaign_schedule import tick
  original=CampaignExecutionService
  with patch("mission_control.campaign_schedule.CampaignExecutionService",side_effect=lambda store,checker:original(store,checker,self.wire)),patch("mission_control.campaign_transport.MetaTransport.request",side_effect=AssertionError("Real provider forbidden")):
   self.assertEqual(tick(self.store),1);self.assertEqual(tick(self.store),0);self.assertTrue(run_once(self.store));self.assertFalse(run_once(self.store))
  result=self.owner_call("schedule-status",{"batch_id":batch})
  self.assertEqual(self.wire.posts,1);self.assertEqual(result["items"][0]["intent"]["status"],"VERIFIED")
  self.assertNotIn("synthetic-token",canonical(result))
  self.assertEqual(self.owner_call("schedule-history",{})["batches"][0]["id"],batch)
 def test_off_cancels_future_items_and_closed_body_or_anonymous_owner_is_denied(self):
  saved=self.prepare_batch();batch=saved["summary"]["batch_id"]
  active=self.owner_call("schedule-activate",{"batch_id":batch,"summary_hash":saved["summary_hash"]})
  off=self.owner_call("schedule-off",{"batch_id":batch,"version":active["version"]})
  self.assertEqual(off["status"],"OFF");self.assertEqual(off["items"][0]["status"],"CANCELLED")
  with self.assertRaises(ClientError):self.owner_call("schedule-status",{"batch_id":batch,"owner":"other"})
  anonymous=OperatorClient(self.origin);anonymous.bootstrap()
  with self.assertRaises(ClientError):anonymous.request("POST","/api/apps/sample-one/campaigns/schedule-status",{"batch_id":batch})
  self.assertEqual(self.wire.posts,0)
 def test_owner_schedule_routes_reject_stale_csrf_origin_and_foreign_app(self):
  saved=self.prepare_batch();batch=saved["summary"]["batch_id"]
  body=canonical({"batch_id":batch,"summary_hash":saved["summary_hash"]}).encode()
  for override in ({"Origin":"http://foreign.example"},{"X-CSRF-Token":"wrong"}):
   headers={"Origin":self.origin,"X-CSRF-Token":self.owner.csrf,"Content-Type":"application/json",**override}
   request=Request(self.origin+"/api/apps/sample-one/campaigns/schedule-activate",data=body,headers=headers,method="POST")
   with self.assertRaises(HTTPError):self.owner.opener.open(request)
  with self.assertRaises(ClientError):self.owner.request("POST","/api/apps/sample-two/campaigns/schedule-status",{"batch_id":batch})
  self.assertEqual(self.wire.posts,0)
if __name__=="__main__":unittest.main()
