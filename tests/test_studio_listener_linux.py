"""Synthetic protocol/descriptor branching only; native acceptance is separate."""
from contextlib import ExitStack, nullcontext
import errno
import socket
import stat
import struct
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from mission_control.common import Invalid
from mission_control import studio_listener_linux as listener


def row(port=4123, inode=55, address='127.0.0.1', cookie=(6,7)):
    data=bytearray(72);data[0:2]=bytes((socket.AF_INET,10))
    struct.pack_into('!H',data,4,port);data[8:12]=socket.inet_aton(address)
    struct.pack_into('=II',data,44,*cookie);struct.pack_into('=I',data,68,inode)
    return bytes(data)


def frame(payload, kind=20, seq=9, pid=10, flags=2):
    value=struct.pack('=IHHII',16+len(payload),kind,flags,seq,pid)+payload
    return value+bytes((-len(value))%4)


def scope():
    value=Mock(spec=listener.RetainedCgroup);value.members.return_value=(12,13)
    return value


class ListenerTests(unittest.TestCase):
    def environment(self):
        stack=ExitStack();self.addCleanup(stack.close)
        stack.enter_context(patch.object(listener.sys,'platform','linux'))
        stack.enter_context(patch.object(listener.os,'pidfd_open',create=True,return_value=20))
        stack.enter_context(patch.object(listener.socket,'AF_NETLINK',16,create=True))
        return stack

    def test_listener_exact_identity_repeats_and_closes_pinned_witnesses(self):
        self.environment();current=scope();record=listener.diag_row(row())
        with patch.object(listener,'diagnostic',return_value=record) as diagnostic, \
             patch.object(listener,'witness',side_effect=[(12,20,b'0::/unit\n'),(12,21,b'0::/unit\n')]) as witness, \
             patch.object(listener,'live',return_value=True),patch.object(listener.os,'close') as close:
            self.assertTrue(listener.owns_listener(current,4123));self.assertEqual(diagnostic.call_count,2)
            self.assertIs(diagnostic.call_args_list[0].args[2],diagnostic.call_args_list[1].args[2])
            self.assertEqual(witness.call_args.args[-1],12);self.assertEqual({x.args[0] for x in close.call_args_list},{20,21})

    def test_listener_exact_identity_rejects_socket_cookie_replacement(self):
        self.environment();first=listener.diag_row(row());second=listener.diag_row(row(cookie=(8,9)))
        with patch.object(listener,'diagnostic',side_effect=[first,second]), \
             patch.object(listener,'witness',return_value=(12,20,b'0::/unit\n')), \
             patch.object(listener,'live',return_value=True),patch.object(listener.os,'close') as close:
            self.assertFalse(listener.owns_listener(scope(),4123));close.assert_called_once_with(20)

    def test_listener_fail_closed_dead_migrated_missing_and_inaccessible_members(self):
        self.environment();record=listener.diag_row(row())
        cases=[(False,(12,21,b'0::/unit\n')),(True,None),(True,(12,21,b'0::/moved\n')),(True,(13,21,b'0::/unit\n'))]
        for alive,second in cases:
            with self.subTest(alive=alive,second=second),patch.object(listener,'diagnostic',return_value=record), \
                 patch.object(listener,'witness',side_effect=[(12,20,b'0::/unit\n'),second]), \
                 patch.object(listener,'live',return_value=alive),patch.object(listener.os,'close'):
                self.assertFalse(listener.owns_listener(scope(),4123))
        with patch.object(listener,'diagnostic',return_value=record),patch.object(listener,'witness',side_effect=PermissionError('private')), \
             self.assertRaisesRegex(Invalid,'^LISTENER_INSPECTION_UNAVAILABLE$'):
            listener.owns_listener(scope(),4123)

    def test_listener_fail_closed_membership_revocation_before_admission(self):
        self.environment();current=scope();current.validate.side_effect=Invalid('LISTENER_SCOPE_REVOKED')
        with patch.object(listener,'diagnostic') as diagnostic,self.assertRaisesRegex(Invalid,'SCOPE_REVOKED'):
            listener.owns_listener(current,4123)
        diagnostic.assert_not_called()

    def test_listener_fail_closed_final_pidfd_death_or_membership_loss(self):
        self.environment();record=listener.diag_row(row())
        for states,members in (([True,False],(12,13)),([True,True,True],())):
            current=scope();current.members.return_value=members
            with self.subTest(states=states,members=members),patch.object(listener,'diagnostic',return_value=record), \
                 patch.object(listener,'witness',side_effect=[(12,20,b'0::/unit\n'),(12,21,b'0::/unit\n')]), \
                 patch.object(listener,'live',side_effect=states),patch.object(listener.os,'close'):
                self.assertFalse(listener.owns_listener(current,4123))

    def test_listener_bounded_resources_final_scope_callback_cannot_return_success_late(self):
        self.environment();clock=[0.0];record=listener.diag_row(row())
        current=object.__new__(listener.RetainedCgroup);current._fd=7;current._identity=(3,4)
        validations=[0]
        def owner_alive():
            validations[0]+=1
            if validations[0]==2:clock[0]=3.0
            return True
        current._owner_alive=owner_alive
        with patch.object(listener.os,'fstat',return_value=SimpleNamespace(st_dev=3,st_ino=4)),patch.object(listener,'filesystem'), \
             patch.object(listener.time,'monotonic',side_effect=lambda:clock[0]), \
             patch.object(listener,'read_file',side_effect=[b'domain\n',b'12\n']),patch.object(listener,'diagnostic',return_value=record), \
             patch.object(listener,'witness',side_effect=[(12,20,b'0::/unit\n'),(12,21,b'0::/unit\n')]), \
             patch.object(listener,'live',return_value=True),patch.object(listener.os,'close') as close:
            with self.assertRaisesRegex(Invalid,'DEADLINE'):listener.observed(current,4123,2.0)
            self.assertEqual({x.args[0] for x in close.call_args_list},{20,21})

    def test_listener_bounded_resources_members_rechecks_after_final_validation(self):
        current=object.__new__(listener.RetainedCgroup);current._fd=7;clock=[0.0];calls=[0]
        def validate():
            calls[0]+=1
            if calls[0]==2:clock[0]=3.0
        with patch.object(current,'validate',side_effect=validate),patch.object(listener.time,'monotonic',side_effect=lambda:clock[0]), \
             patch.object(listener,'read_file',side_effect=[b'domain\n',b'12\n']):
            with self.assertRaisesRegex(Invalid,'DEADLINE'):current.members(2.0)

    def test_listener_bounded_resources_final_members_return_rechecks_elapsed_time(self):
        self.environment();clock=[0.0];current=scope();record=listener.diag_row(row())
        def members(deadline):clock[0]=3.0;return (12,)
        current.members.side_effect=members
        with patch.object(listener.time,'monotonic',side_effect=lambda:clock[0]),patch.object(listener,'diagnostic',return_value=record), \
             patch.object(listener,'witness',side_effect=[(12,20,b'0::/unit\n'),(12,21,b'0::/unit\n')]), \
             patch.object(listener,'live',return_value=True),patch.object(listener.os,'close'):
            with self.assertRaisesRegex(Invalid,'DEADLINE'):listener.observed(current,4123,2.0)

    def test_listener_bounded_resources_cleanup_delay_cannot_return_success_late(self):
        self.environment();clock=[0.0];current=scope();record=listener.diag_row(row())
        def close(fd):clock[0]=3.0
        with patch.object(listener.time,'monotonic',side_effect=lambda:clock[0]),patch.object(listener,'diagnostic',return_value=record), \
             patch.object(listener,'witness',side_effect=[(12,20,b'0::/unit\n'),(12,21,b'0::/unit\n')]), \
             patch.object(listener,'live',return_value=True),patch.object(listener.os,'close',side_effect=close):
            with self.assertRaisesRegex(Invalid,'DEADLINE'):listener.observed(current,4123,2.0)

    def test_listener_evidence_boundary_request_deadline_and_nonlinux_have_no_kernel_side_effect(self):
        with patch.object(listener.sys,'platform','win32'),patch.object(listener,'observed') as observed, \
             self.assertRaisesRegex(Invalid,'UNSUPPORTED'):listener.owns_listener(scope(),4123)
        observed.assert_not_called();self.environment()
        for port,timeout in ((True,1),(0,1),(65536,1),(3,0),(3,3),(3,float('nan')),(3,True)):
            with self.subTest(port=port,timeout=timeout),self.assertRaises(Invalid):listener.owns_listener(scope(),port,timeout)
            with self.assertRaises(Invalid):listener.request_deadline(scope(),port,timeout)
        with self.assertRaises(Invalid):listener.owns_listener('saved-unit',4123)

    def test_listener_live_scope_duplicates_validates_and_closes_only_duplicate(self):
        self.environment();info=SimpleNamespace(st_mode=stat.S_IFDIR,st_dev=3,st_ino=4)
        with patch.object(listener.os,'dup',return_value=7),patch.object(listener.os,'set_inheritable'), \
             patch.object(listener.os,'fstat',return_value=info),patch.object(listener,'filesystem'),patch.object(listener.os,'close') as close:
            alive=Mock(return_value=True);current=listener.RetainedCgroup(6,alive)
            with patch.object(listener,'read_file',side_effect=[b'domain\n',b'12\n13\n']):
                self.assertEqual(current.members(listener.time.monotonic()+1),(12,13))
            alive.return_value=False
            with self.assertRaisesRegex(Invalid,'SCOPE_REVOKED'):current.validate()
            current.close();current.close();close.assert_called_once_with(7)
            with self.assertRaisesRegex(Invalid,'SCOPE_CLOSED'):current.validate()

    def test_listener_live_scope_constructor_failure_releases_duplicate(self):
        self.environment()
        with patch.object(listener.os,'dup',return_value=7),patch.object(listener.os,'set_inheritable'), \
             patch.object(listener.os,'fstat',return_value=SimpleNamespace(st_mode=stat.S_IFREG)),patch.object(listener.os,'close') as close:
            with self.assertRaises(Invalid):listener.RetainedCgroup(6,lambda:True)
            close.assert_called_once_with(7)

    def test_listener_live_scope_malformed_threaded_or_oversized_members_fail(self):
        current=object.__new__(listener.RetainedCgroup);current._fd=7
        for values in ((b'threaded\n',),(b'domain\n',b'0\n'),(b'domain\n',b'12\n12\n'),(b'domain\n',b'1\n2\n')):
            with self.subTest(values=values),patch.object(current,'validate'),patch.object(listener,'read_file',side_effect=values), \
                 patch.object(listener,'MAX_TASKS',1),self.assertRaises(Invalid):current.members(listener.time.monotonic()+1)

    def diagnostic_stream(self, datagrams):
        self.environment();stream=Mock();stream.__enter__=Mock(return_value=stream);stream.__exit__=Mock(return_value=False)
        stream.getsockname.return_value=(10,0);stream.sendto.return_value=72
        stream.recvmsg.side_effect=datagrams
        return stream

    def test_listener_exact_identity_kernel_dump_filters_wildcard_and_ambiguity(self):
        for rows,expected in (([row()],True),([row(address='0.0.0.0')],False),([row(),row(inode=56)],False),([],False)):
            stream=self.diagnostic_stream([(b''.join(frame(r) for r in rows)+frame(bytes(4),kind=3),[],0,(0,0))])
            with self.subTest(rows=len(rows)),patch.object(listener.socket,'socket',return_value=stream),patch.object(listener.secrets,'randbits',return_value=9):
                result=listener.diagnostic(4123,listener.time.monotonic()+1)
                self.assertEqual(result is not None,expected);stream.__exit__.assert_called_once()

    def test_listener_fail_closed_rejects_truncation_sender_sequence_dump_errors(self):
        packets=[(frame(row())+frame(bytes(4),kind=3),[],socket.MSG_TRUNC,(0,0)),(frame(row()),[],0,(3,0)),
                 (frame(row(),seq=8),[],0,(0,0)),(frame(row(),flags=0x12),[],0,(0,0)),
                 (frame(bytes(4),kind=2),[],0,(0,0)),(b'bad',[],0,(0,0)),
                 (frame(bytes(4),kind=3)+frame(row()),[],0,(0,0))]
        for packet in packets:
            stream=self.diagnostic_stream([packet])
            with self.subTest(packet=packet),patch.object(listener.socket,'socket',return_value=stream), \
                 patch.object(listener.secrets,'randbits',return_value=9),self.assertRaises(Invalid):
                listener.diagnostic(4123,listener.time.monotonic()+1)
            stream.__exit__.assert_called_once()

    def test_listener_bounded_resources_receive_dump_bytes_messages_and_deadline(self):
        packet=(frame(row())+frame(bytes(4),kind=3),[],0,(0,0))
        for name,value in (('MAX_BYTES',8),('MAX_MESSAGES',1)):
            stream=self.diagnostic_stream([packet])
            with patch.object(listener.socket,'socket',return_value=stream),patch.object(listener.secrets,'randbits',return_value=9), \
                 patch.object(listener,name,value),self.assertRaises(Invalid):listener.receive_dump(stream,9,10,4123,listener.time.monotonic()+1)
        with self.assertRaisesRegex(Invalid,'DEADLINE'):listener.remaining(listener.time.monotonic()-1)

    def test_listener_bounded_resources_shared_receive_dump_budget(self):
        packet=(frame(row())+frame(bytes(4),kind=3),[],0,(0,0));budget=[0,0]
        stream=self.diagnostic_stream([packet,packet])
        with patch.object(listener,'MAX_BYTES',len(packet[0])+1):
            self.assertEqual(len(listener.receive_dump(stream,9,10,4123,listener.time.monotonic()+1,budget)),1)
            with self.assertRaisesRegex(Invalid,'DIAG_BYTE_BOUND'):
                listener.receive_dump(stream,9,10,4123,listener.time.monotonic()+1,budget)

    def test_listener_fail_closed_malformed_ipv6_and_attributes(self):
        for value in (b'bad',bytes([10])+row()[1:],row()+b'bad',row()+b'\x03\x00\x01\x00'):
            with self.subTest(value=value),self.assertRaises(Invalid):listener.diag_row(value)
        self.assertEqual(len(listener.diag_request(9)),72)
        for packet in (frame(row(),pid=11),struct.pack('=IHHII',15,20,2,9,10),frame(row())[:-1]):
            with self.assertRaises(Invalid):listener.messages(packet,9,10)
        matches=[]
        self.assertTrue(listener.consume([(20,row()),(3,bytes(4))],matches,4123))
        self.assertEqual(matches,[listener.diag_row(row())])

    def test_listener_exact_identity_select_member_inherited_holders_and_inaccessible_unrelated_pid_not_scanned(self):
        current=scope();seen=[];pins=[]
        def member(proc,pid,inode,deadline,budget):
            seen.append(pid)
            if pid==99:raise PermissionError('unrelated process')
            return (pid,pid+100,b'0::/unit\n')
        with patch.object(listener,'directory',return_value=3),patch.object(listener,'filesystem'), \
             patch.object(listener,'holder',side_effect=member),patch.object(listener.os,'close',side_effect=pins.append), \
             patch.object(listener.os,'scandir',side_effect=AssertionError('Global enumeration is forbidden')):
            found=listener.witness(current,listener.diag_row(row()),listener.time.monotonic()+1)
            self.assertEqual(found[0],12);self.assertEqual(seen,[12,13]);self.assertEqual(pins,[113])
            pins.clear();seen.clear()
            found=listener.select_member(3,current.members(None),listener.diag_row(row()),listener.time.monotonic()+1,13)
            self.assertEqual(found[0],13);self.assertEqual(pins,[112])

    def test_listener_fail_closed_inaccessible_required_member_releases_prior_witness(self):
        current=scope()
        with patch.object(listener,'directory',return_value=3),patch.object(listener,'filesystem'), \
             patch.object(listener,'holder',side_effect=[(12,112,b'0::/unit\n'),PermissionError()]),patch.object(listener.os,'close') as close:
            with self.assertRaises(PermissionError):listener.witness(current,listener.diag_row(row()),listener.time.monotonic()+1)
            close.assert_called_once_with(112)

    def test_listener_bounded_resources_fd_links_and_read_cleanup(self):
        entry=SimpleNamespace(name='1');entries=nullcontext([entry,entry])
        with patch.object(listener.os,'scandir',return_value=entries),patch.object(listener.os,'readlink',return_value='socket:[55]'), \
             patch.object(listener,'MAX_FDS',1),self.assertRaisesRegex(Invalid,'FD_BOUND'):
            listener.holds(3,55,listener.time.monotonic()+1,[0])
        with patch.multiple(listener.os,O_NOFOLLOW=0,O_CLOEXEC=0,O_NONBLOCK=0,create=True),patch.object(listener.os,'open',return_value=7), \
             patch.object(listener.os,'read',return_value=b'12345'),patch.object(listener.os,'close') as close,patch.object(listener,'MAX_READ',4):
            with self.assertRaisesRegex(Invalid,'READ_BOUND'):listener.read_file(3,'cgroup.procs',listener.time.monotonic()+1)
            close.assert_called_once_with(7)

    def test_listener_fail_closed_holder_dead_and_not_found_release_pidfd(self):
        self.environment()
        with patch.object(listener,'live',return_value=False),patch.object(listener.os,'close') as close:
            self.assertIsNone(listener.holder(3,12,55,listener.time.monotonic()+1,[0]));close.assert_called_once_with(20)
        with patch.object(listener.os,'pidfd_open',side_effect=ProcessLookupError(errno.ESRCH,'gone')):
            self.assertIsNone(listener.holder(3,12,55,listener.time.monotonic()+1,[0]))

    def test_listener_fail_closed_foreign_or_migrated_scope_has_no_witness(self):
        current=scope()
        with patch.object(listener,'directory',return_value=3),patch.object(listener,'filesystem'), \
             patch.object(listener,'holder',return_value=None):
            self.assertIsNone(listener.witness(current,listener.diag_row(row()),listener.time.monotonic()+1))
        current.members.side_effect=[(12,13),()]
        with patch.object(listener,'directory',return_value=3),patch.object(listener,'filesystem'), \
             patch.object(listener,'holder',side_effect=[(12,112,b'0::/unit\n'),None]),patch.object(listener.os,'close') as close:
            self.assertIsNone(listener.witness(current,listener.diag_row(row()),listener.time.monotonic()+1))
            close.assert_called_once_with(112)

    def test_listener_fail_closed_filesystem_and_scope_errors_are_closed(self):
        self.environment()
        with patch.object(listener.ctypes,'CDLL') as library:
            library.return_value.fstatfs.return_value=-1
            with self.assertRaisesRegex(Invalid,'^LISTENER_FILESYSTEM$'):listener.filesystem(3,0x63677270)
        with patch.object(listener.os,'dup',side_effect=PermissionError('private path')):
            with self.assertRaisesRegex(Invalid,'^LISTENER_SCOPE_UNAVAILABLE$'):listener.RetainedCgroup(3,lambda:True)


if __name__=='__main__':unittest.main()
