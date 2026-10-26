"""Explicit Secret Service adapter contracts with synthetic native seams."""
import copy
import json
import sys
import time
import types
import unittest
from unittest.mock import patch, Mock
from mission_control import linux_vault as native
from mission_control import credential_vault as vault
from mission_control.common import Invalid


class Item:
    def __init__(self, collection, attributes, raw):self.collection=collection;self.attributes=dict(attributes);self.raw=raw;self.locked=False
    def get_attributes(self):return self.attributes
    def is_locked(self):return self.locked
    def get_secret(self):return self.raw
    def delete(self):self.collection.items.remove(self)


class Collection:
    def __init__(self):self.items=[];self.locked=False;self.calls=[]
    def is_locked(self):return self.locked
    def search_items(self, attributes):return iter([item for item in self.items if item.attributes==attributes])
    def create_item(self,label,attributes,raw,**kwargs):
        self.calls.append((label,dict(attributes),raw,kwargs));self.items=[x for x in self.items if x.attributes!=attributes];self.items.append(Item(self,attributes,raw))


class LinuxVaultTests(unittest.TestCase):
    def setUp(self):
        self.collection=Collection();self.bus=Mock();self.session=types.SimpleNamespace(encrypted=True)
        self.library=types.SimpleNamespace(dbus_init=Mock(return_value=self.bus),Collection=Mock(return_value=self.collection))
        self.util=types.ModuleType('secretstorage.util');self.util.open_session=Mock(return_value=self.session)
        module=patch.dict(sys.modules,{'secretstorage':self.library,'secretstorage.util':self.util});module.start();self.addCleanup(module.stop)
        self.native=native.LinuxVault()

    def test_roundtrip_scope_replace_delete_and_metadata_are_exact(self):
        one='DriveMedia/database-one/app/ref/access_token';two='DriveMedia/database-two/app/ref/access_token'
        self.native.put(one,dict(token='SYNTHETIC_SECRET'));self.native.put(two,dict(token='SECOND'))
        self.assertEqual(self.native.get(one),dict(token='SYNTHETIC_SECRET'));self.native.put(one,dict(token='REPLACED'))
        self.assertEqual(self.native.get(one),dict(token='REPLACED'));self.assertEqual(self.native.get(two),dict(token='SECOND'))
        label,attributes,raw,options=self.collection.calls[0]
        self.assertNotIn('SYNTHETIC_SECRET',str(attributes));self.assertNotIn(one,str(attributes));self.assertEqual(label,'WMM protected connection')
        self.assertEqual(options,dict(replace=True,content_type='application/json'));self.native.delete(one);self.native.delete(one)
        self.assertIsNone(self.native.get(one));self.assertEqual(self.native.get(two),dict(token='SECOND'))
        self.assertEqual(self.bus.close.call_count,self.library.dbus_init.call_count)

    def test_locked_collection_item_and_plain_transport_preserve_secret(self):
        self.native.put('synthetic',dict(token='before'));item=self.collection.items[0]
        for mode in ('collection','item','transport'):
            self.collection.locked=mode=='collection';item.locked=mode=='item';self.session.encrypted=mode!='transport'
            for action in (lambda:self.native.put('synthetic',dict(token='after')),lambda:self.native.get('synthetic'),lambda:self.native.delete('synthetic')):
                with self.subTest(mode=mode),self.assertRaises(Invalid):action()
            self.assertEqual(item.raw,b'{"token":"before"}')
        self.assertEqual(len(self.collection.items),1)

    def test_duplicate_wrong_attributes_and_corruption_fail_closed(self):
        self.native.put('synthetic',dict(token='before'));item=self.collection.items[0];self.collection.items.append(copy.copy(item))
        with self.assertRaises(Invalid):self.native.get('synthetic')
        self.collection.items.pop();item.attributes={'wrong':'address'}
        with patch.object(self.collection,'search_items',return_value=iter([item])),self.assertRaises(Invalid):self.native.get('synthetic')
        for raw in (b'x'*2561,b'{"x":1,"x":2}',b'\xff',b'not-json'):
            with self.subTest(raw=raw[:20]),self.assertRaises(Invalid):native.decode(raw)

    def test_bounds_address_and_reply_deadline(self):
        self.assertEqual(len(native.encode('x'*2558)),2560)
        with self.assertRaises(Invalid):native.encode('x'*2559)
        for name in ('','x'*2049,'bad\nname',None):
            with self.assertRaises(Invalid):native.address(name)
        self.assertNotEqual(native.address('Case'),native.address('case'))
        bus=native.BoundedBus(self.bus);bus.send_and_get_reply('synthetic-message');self.assertGreater(self.bus.send_and_get_reply.call_args.kwargs['timeout'],0)
        self.assertLessEqual(self.bus.send_and_get_reply.call_args.kwargs['timeout'],15)
        bus.deadline=time.monotonic()-1
        with self.assertRaises(TimeoutError):bus.send_and_get_reply('synthetic-message')

    def test_unavailable_service_and_dependency_redact_native_errors(self):
        self.library.Collection.side_effect=RuntimeError('PRIVATE_NATIVE_ERROR')
        with self.assertRaises(Invalid)as error:self.native.get('synthetic')
        self.assertNotIn('PRIVATE_NATIVE_ERROR',str(error.exception));self.bus.close.assert_called_once()
        with patch.object(native.importlib,'import_module',side_effect=ImportError('private-path')):
            with self.assertRaises(Invalid)as error:native.LinuxVault()
        self.assertNotIn('private-path',str(error.exception))

    def test_platform_selection_has_no_backend_fallback(self):
        with patch.object(vault.os,'name','posix'),patch.object(vault.sys,'platform','linux'):
            self.assertIsInstance(vault.Vault().backend,native.LinuxVault)
        with patch.object(vault.os,'name','posix'),patch.object(vault.sys,'platform','darwin'):
            with self.assertRaises(Invalid):vault.Vault()
        with patch.object(vault.os,'name','nt'),patch.object(vault,'WindowsVault')as windows:
            v=vault.Vault();v.put('one',{});windows.return_value.put.assert_called_once_with('one',{})

    def test_namespace_preserves_linux_case_and_existing_windows_normalization(self):
        with patch.object(vault.os,'name','posix'),patch.object(vault,'Path')as path:
            path.return_value.resolve.return_value='/home/Case/db';one=vault.namespace('db')
            path.return_value.resolve.return_value='/home/case/db';two=vault.namespace('db')
            self.assertNotEqual(one,two)
        with patch.object(vault.os,'name','nt'),patch.object(vault,'Path')as path:
            path.return_value.resolve.return_value='C:/Case/db';one=vault.namespace('db')
            path.return_value.resolve.return_value='c:/case/db';self.assertEqual(one,vault.namespace('db'))
