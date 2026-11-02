"""Agent-submitted human assertions require an exact independent checkpoint."""
import unittest
import base64
from mission_control.agent_checkpoints import Checkpoints
from mission_control.agent_review_dispatch import ReviewedDispatch
from mission_control.operator_client import ClientError,OperatorClient
from mission_control.review_access import Access
from mission_control.creative_library import Library
from tests import test_agent_grants as fixture
from tests import test_verified_review as identities
from tests.test_creative_library import reference


class CreativeAttestationTests(unittest.TestCase):
    setUp=fixture.GrantTests.setUp
    tearDown=fixture.GrantTests.tearDown
    body=fixture.GrantTests.body
    issue=fixture.GrantTests.issue
    envelope=fixture.GrantTests.envelope

    def test_unreviewed_agent_cannot_assert_inspection_or_rights(self):
        operations=['creative.source.save','creative.analysis.save','creative.profile.save',
                    'creative.requirement.save','creative.brief.save']
        token=self.issue(operations)['token'];client=OperatorClient(self.origin,grant_token=token)
        for operation in operations:
            with self.subTest(operation=operation),self.assertRaises(ClientError) as error:
                client.call(self.envelope(operation,dict(data={})))
            self.assertEqual(error.exception.status,403)

    def test_independently_reviewed_exact_source_uses_existing_service(self):
        Access(self.store).save('sample-one',identities.OWNER,identities.CHECKER,
            dict(login=identities.CHECKER['login'],role='CHECKER',status='ACTIVE',version=None))
        issued=self.owner.request('POST','/api/apps/sample-one/agent-grants/issue',
            dict(self.body(['creative.source.save']),review_operations=['creative.source.save']))
        request=self.envelope('creative.source.save',dict(data=reference()))
        dispatch=ReviewedDispatch(self.server.service);checkpoints=Checkpoints(self.store)
        waiting=dispatch.prepare(issued['token'],'source-review',request)['checkpoint']
        approved=checkpoints.approve('sample-one','source-review',identities.CHECKER['principal'],waiting['revision'],waiting['hash'])
        result=dispatch.resume(issued['token'],'sample-one','source-review',approved['revision'],approved['hash'])
        self.assertEqual(result['checkpoint']['state'],'SUCCEEDED')
        self.assertEqual(result['result']['data']['status'],'SAVED')

    def test_reviewed_source_correction_uses_exact_version(self):
        Access(self.store).save('sample-one',identities.OWNER,identities.CHECKER,
            dict(login=identities.CHECKER['login'],role='CHECKER',status='ACTIVE',version=None))
        first=Library(self.store).save('sample-one',dict(data=reference()))
        issued=self.owner.request('POST','/api/apps/sample-one/agent-grants/issue',
            dict(self.body(['creative.source.save']),review_operations=['creative.source.save']))
        data=reference(relevance_note='Synthetic corrected observation')
        request=self.envelope('creative.source.save',dict(id=first['id'],version=1,data=data))
        dispatch=ReviewedDispatch(self.server.service);checkpoints=Checkpoints(self.store)
        def reviewed(identity):
            waiting=dispatch.prepare(issued['token'],identity,request)['checkpoint']
            approved=checkpoints.approve('sample-one',identity,identities.CHECKER['principal'],waiting['revision'],waiting['hash'])
            return dispatch.resume(issued['token'],'sample-one',identity,approved['revision'],approved['hash'])
        self.assertEqual(reviewed('source-fix-one')['result']['data']['status'],'REFRESHED')
        self.assertEqual(reviewed('source-fix-stale')['result']['outcome'],'FAILED')
        del request['input']['version']
        self.assertEqual(reviewed('source-fix-incomplete')['result']['outcome'],'FAILED')
        self.assertEqual(Library(self.store).list('sample-one')[0]['current']['version'],2)

    def test_asset_rights_assertion_requires_exact_review(self):
        Access(self.store).save('sample-one',identities.OWNER,identities.CHECKER,
            dict(login=identities.CHECKER['login'],role='CHECKER',status='ACTIVE',version=None))
        raw=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jmrkAAAAASUVORK5CYII=')
        asset=self.server.service.upload('sample-one','synthetic.png',raw)
        body=dict(id=asset['id'],version=asset['version'],manifest_version=1,kind='asset',title='Synthetic screenshot',
                  source='Synthetic fixture',data=dict(asset['data'],authentic=True,rights_cleared=True))
        request=self.envelope('evidence.save',body)
        ordinary=self.issue(['evidence.save'])
        with self.assertRaises(ClientError) as error:OperatorClient(self.origin,grant_token=ordinary['token']).call(request)
        self.assertEqual(error.exception.status,403)
        self.assertFalse(next(x for x in self.store.records('sample-one') if x['id']==asset['id'])['data']['rights_cleared'])
        reviewed=self.owner.request('POST','/api/apps/sample-one/agent-grants/issue',
            dict(self.body(['evidence.save']),review_operations=['evidence.save']))
        dispatch=ReviewedDispatch(self.server.service);checkpoints=Checkpoints(self.store)
        waiting=dispatch.prepare(reviewed['token'],'asset-review',request)['checkpoint']
        approved=checkpoints.approve('sample-one','asset-review',identities.CHECKER['principal'],waiting['revision'],waiting['hash'])
        result=dispatch.resume(reviewed['token'],'sample-one','asset-review',approved['revision'],approved['hash'])
        self.assertEqual(result['checkpoint']['state'],'SUCCEEDED')
        self.assertTrue(next(x for x in self.store.records('sample-one') if x['id']==asset['id'])['data']['rights_cleared'])


if __name__=='__main__':unittest.main()
