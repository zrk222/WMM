"""Dynamic compiled controls, session scope, private data and proposal boundaries."""
import copy
import json
import unittest
from unittest.mock import patch
from mission_control import hypit_control_view as target
from mission_control.common import Invalid


class ControlTests(unittest.TestCase):
    def setUp(self):
        self.scope=dict(app_id='synthetic-app',session_id='synthetic-session')
        self.key=b'synthetic-private-session-key-123456789'
        self.snapshot=dict(revision=4,source=dict(text='PRIVATE_SOURCE_PREIMAGE'),preview=dict(srcdoc='<script>PRIVATE_HTML</script>'),tracks=[
          dict(id=r'C:\private\film.svml::track',items=[dict(id=r'C:\private\film.svml::item',inspector=[
            dict(id=r'C:\private\field-number',label='Size',domain='how',page=dict(id='type',label='Type'),section=dict(id='font',label='Font'),
              control='number',schema=dict(kind='number',minimum=1),value=38,unit='px',edit=dict(source=dict(path='film.svml',preimage='PRIVATE_SOURCE_PREIMAGE'))),
            dict(id='readonly',label='Derived',control='text',value='derived fact')])],inspectorObjects=[
             dict(id='object',inspector=[dict(id='records',label='Layout',control='record',value=dict(x=1),
                 schema=dict(kind='object',fields=dict(x=dict(schema=dict(kind='number')))),edit=dict(source=dict(path='layout.svs')))])])])
        self.view=target.ControlView(self.scope,self.snapshot,self.key)

    def body(self,owner=0,field=0,value=50):
        public=self.view.public();row=public['owners'][owner]
        return dict(revision=public['revision'],view_hash=public['view_hash'],owner_id=row['id'],field_id=row['fields'][field]['id'],value=value)

    def test_all_compiled_item_and_object_fields_keep_public_schema(self):
        public=self.view.public()
        self.assertEqual(len(public['owners']),2)
        self.assertEqual(sum(len(v['fields']) for v in public['owners']),3)
        field=public['owners'][0]['fields'][0]
        self.assertEqual(field['schema'],dict(kind='number',minimum=1));self.assertEqual(field['unit'],'px')
        self.assertTrue(field['writable']);self.assertFalse(public['owners'][0]['fields'][1]['writable'])
        self.assertEqual(public['owners'][1]['kind'],'track-object')

    def test_private_endpoints_source_and_html_are_absent(self):
        public=self.view.public();raw=json.dumps(public)
        for value in ('PRIVATE_SOURCE_PREIMAGE','PRIVATE_HTML','private','srcdoc','preimage','film.svml'):
            self.assertNotIn(value,raw)
        self.assertNotIn('edit',public['owners'][0]['fields'][0])
        self.assertNotIn('source',public)

    def test_current_proposal_resolves_exact_native_item_and_object(self):
        proposal=self.view.parameter(self.body())
        self.assertEqual(set(proposal),{'type','revision','owner','parameterId','value'})
        self.assertEqual(proposal['type'],'parameter.adjust');self.assertEqual(proposal['value'],50)
        self.assertEqual(proposal['owner']['itemId'],self.snapshot['tracks'][0]['items'][0]['id'])
        proposal=self.view.parameter(self.body(1,value=dict(x=2)))
        self.assertEqual(proposal['owner'],dict(kind='track-object',trackId=self.snapshot['tracks'][0]['id'],objectId='object'))

    def test_foreign_scope_keys_and_snapshot_hashes_cannot_be_reused(self):
        original=self.body()
        for scope,key in ((dict(self.scope,app_id='foreign'),self.key),(dict(self.scope,session_id='foreign'),self.key),(self.scope,b'other-private-session-key-123456789')):
            other=target.ControlView(scope,self.snapshot,key)
            self.assertNotEqual(other.public()['owners'][0]['id'],self.view.public()['owners'][0]['id'])
            with self.assertRaises(Invalid):other.parameter(original)
        changed=copy.deepcopy(self.snapshot);changed['tracks'][0]['items'][0]['inspector'][0]['value']=99
        with self.assertRaisesRegex(Invalid,'view changed'):target.ControlView(self.scope,changed,self.key).parameter(original)

    def test_stale_revision_foreign_owner_extra_fields_and_readonly_reject(self):
        for change in (dict(revision=3),dict(revision=True),dict(view_hash='changed'),dict(owner_id='foreign'),dict(field_id='foreign'),dict(source='raw patch')):
            with self.assertRaises(Invalid):self.view.parameter(dict(self.body(),**change))
        with self.assertRaisesRegex(Invalid,'read only'):self.view.parameter(self.body(field=1,value='edit derived'))
        with self.assertRaises(Invalid):self.view.parameter(self.body(1,value=2))

    def test_primitive_types_and_finite_json_reject(self):
        for value in (True,'50',float('nan'),float('inf'),object()):
            with self.assertRaises(Invalid):self.view.parameter(self.body(value=value))
        for control,value in [('text',4),('color',3),('boolean',1),('list',{}),('record',[])]:
            snapshot=copy.deepcopy(self.snapshot);field=snapshot['tracks'][0]['items'][0]['inspector'][0];field['control']=control
            view=target.ControlView(self.scope,snapshot,self.key);public=view.public();row=public['owners'][0]
            with self.assertRaises(Invalid):view.parameter(dict(revision=4,view_hash=public['view_hash'],owner_id=row['id'],field_id=row['fields'][0]['id'],value=value))

    def test_dynamic_lists_records_and_select_options_survive(self):
        for control,value,options in [('list',[dict(text='hello')],None),('record',dict(layout=[1,2]),None),('select','center',['start',dict(value='center',label='Centre')])]:
            snapshot=copy.deepcopy(self.snapshot);f=snapshot['tracks'][0]['items'][0]['inspector'][0]
            f.update(control=control,value=value)
            if options is not None:f['options']=options
            view=target.ControlView(self.scope,snapshot,self.key);p=view.public();row=p['owners'][0]
            body=dict(revision=4,view_hash=p['view_hash'],owner_id=row['id'],field_id=row['fields'][0]['id'],value=value)
            self.assertEqual(view.parameter(body)['value'],value)
            if options is not None:
                with self.assertRaises(Invalid):view.parameter(dict(body,value='outside'))

    def test_identity_duplicates_and_invalid_scope_reject(self):
        duplicate=copy.deepcopy(self.snapshot);duplicate['tracks'][0]['items'].append(duplicate['tracks'][0]['items'][0])
        with self.assertRaises(Invalid):target.ControlView(self.scope,duplicate,self.key)
        duplicate=copy.deepcopy(self.snapshot);fields=duplicate['tracks'][0]['items'][0]['inspector'];fields.append(fields[0])
        with self.assertRaises(Invalid):target.ControlView(self.scope,duplicate,self.key)
        for scope in ({},dict(app_id='',session_id='a')):
            with self.assertRaises(Invalid):target.ControlView(scope,self.snapshot,self.key)
        with self.assertRaises(Invalid):target.ControlView(self.scope,self.snapshot,b'short')

    def test_bounds_private_metadata_and_mutable_return_values(self):
        for name,value in [('MAX_FIELDS',1),('MAX_OWNERS',1),('MAX_JSON_BYTES',10),('MAX_DEPTH',1)]:
            with patch.object(target,name,value),self.assertRaises(Invalid):target.ControlView(self.scope,self.snapshot,self.key)
        with self.assertRaisesRegex(Invalid,'private path'):target.public_data(dict(label=r'C:\private\file'))
        public=self.view.public();public['owners'].clear()
        self.assertEqual(len(self.view.public()['owners']),2)
        self.snapshot['revision']=100
        self.assertEqual(self.view.parameter(self.body())['revision'],4)

    def test_projection_explicitly_has_no_execution_or_approval(self):
        public=self.view.public()
        self.assertEqual(public['execution'],'NOT_RUN_PROPOSAL_ONLY')
        self.assertEqual(public['upstream_validation'],'REQUIRED')
        self.assertEqual(public['approval'],'NOT_ESTABLISHED')

    def test_nested_private_metadata_and_windows_forward_paths_reject(self):
        self.assertEqual(target.public_data('https://example.test/media'),'https://example.test/media')
        for name,value in [('schema',dict(kind='number',source=dict(path='relative.svml',preimage='PRIVATE'))),
            ('page',dict(id='layout',label='Layout',srcdoc='<script>PRIVATE</script>')),
            ('number',dict(scale=1,endpoint='PRIVATE')),
            ('options',[dict(value='x',label='X',preview=dict(kind='font',family='Test',preimage='PRIVATE'))]),
            ('label','C:/work/film.svml')]:
            snapshot=copy.deepcopy(self.snapshot);snapshot['tracks'][0]['items'][0]['inspector'][0][name]=value
            with self.assertRaises(Invalid):target.ControlView(self.scope,snapshot,self.key)

    def test_malformed_containers_and_lone_surrogates_raise_invalid(self):
        for snapshot in ([],None,1,'snapshot',dict(revision=1,tracks=[dict(id='t',items=None)]),
                         dict(revision=1,tracks=[dict(id='t',inspectorObjects={})])):
            with self.assertRaises(Invalid):target.ControlView(self.scope,snapshot,self.key)
        with self.assertRaises(Invalid):target.finite(chr(0xD800))
        with self.assertRaises(Invalid):self.view.parameter(self.body(value=chr(0xD800)))

    def test_typed_metadata_cannot_smuggle_nested_private_objects(self):
        for name,value in [('label',dict(source=dict(preimage='PRIVATE'))),('summary',[]),
                           ('number',dict(scale=dict(srcdoc='PRIVATE'))),
                           ('schema',dict(kind='number',minimum=dict(hidden='PRIVATE'))),
                           ('page',dict(id=dict(hidden='PRIVATE'),label='Page'))]:
            snapshot=copy.deepcopy(self.snapshot);snapshot['tracks'][0]['items'][0]['inspector'][0][name]=value
            with self.assertRaises(Invalid):target.ControlView(self.scope,snapshot,self.key)

    def test_all_absolute_path_forms_reject_but_public_urls_remain_usable(self):
        for value in ('/etc/private.conf','/var/lib/customer/project.svml',r'\\server\private\film.svml',
                      'C:/work/file.svml',r'C:\work\file.svml','file:///tmp/private'):
            with self.assertRaisesRegex(Invalid,'private path'):target.public_data(dict(value=value))
        self.assertEqual(target.public_data(dict(value='https://example.test/a/b')),dict(value='https://example.test/a/b'))

    def test_projection_rejects_embedded_credentials_and_private_paths(self):
        values=['https://synthetic-user:synthetic-secret@example.test/media',
                'Open https://synthetic-user@example.test/media now',
                'Loaded from /var/lib/customer/project.svml',
                'Loaded from (/etc/private.conf)',r'Loaded from \\server\private\file',
                'https://example.test/media then /var/private/file',
                'https://user%40example.test/private','path=/var/lib/customer/file.svml',
                'source:/etc/private.conf','root=[/var/private]','path=\\\\server\\private\\file']
        for value in values:
            for key in ('label','summary','value'):
                snapshot=copy.deepcopy(self.snapshot);snapshot['tracks'][0]['items'][0]['inspector'][0][key]=value
                with self.assertRaises(Invalid):target.ControlView(self.scope,snapshot,self.key)
        for value in ('Watch https://example.test/media now','Use start/end to align','Width / Height','https://example.test/a/b'):
            self.assertEqual(target.public_data(value),value)

    def test_url_control_character_normalization_cannot_hide_credentials(self):
        for separator in ('\t','\r','\n','\r\n'):
            for value in ('https://synthetic-user:'+separator+'synthetic-secret@example.test/media',
                          'https://synthetic-user'+separator+'@example.test/media'):
                snapshot=copy.deepcopy(self.snapshot);snapshot['tracks'][0]['items'][0]['inspector'][0]['value']=value
                with self.assertRaises(Invalid):target.ControlView(self.scope,snapshot,self.key)
        self.assertEqual(target.public_data('Line one\nLine two'),'Line one\nLine two')

    def test_non_json_python_containers_and_subclasses_reject_recursively(self):
        class HiddenString(str):pass
        class HiddenList(list):pass
        values=[('/var/private/file',),dict(nested=({'preimage':'PRIVATE'},)),
                {'nested':{1,2}},HiddenString('hello'),HiddenList(['hello'])]
        for value in values:
            with self.assertRaises(Invalid):target.finite(value)
            snapshot=copy.deepcopy(self.snapshot);snapshot['tracks'][0]['items'][0]['inspector'][0]['value']=value
            with self.assertRaises(Invalid):target.ControlView(self.scope,snapshot,self.key)
        self.assertEqual(target.finite(dict(nested=[None,False,3,2.5,'safe'])),dict(nested=[None,False,3,2.5,'safe']))


if __name__=='__main__':unittest.main()
