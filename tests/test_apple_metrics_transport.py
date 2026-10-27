"""Synthetic Apple Analytics transport checks; no provider credentials or network calls."""
import hashlib
from email.message import Message
from urllib.error import HTTPError
from urllib.request import Request
import unittest
from unittest.mock import Mock, patch

from mission_control.apple_segments import read_instance_segments
from mission_control import apple_segments, providers
from mission_control.common import Invalid
from mission_control.providers import (
    MAX_COMPRESSED, NoRedirect, analytics_segment_destination,
    download_analytics_segment, report_destination,
)


APP='123'
REPORT='report-1'
INSTANCE='instance-1'
SIGNED_URL='https://asp-qa-us-west-2.s3.us-west-2.amazonaws.com/reports/sample/0.csv.gz?X-Amz-Signature=synthetic-secret'


def readiness_pages():
    return [
        dict(data=dict(id=APP,type='apps')),
        dict(data=[dict(id='request-1',type='analyticsReportRequests',
            attributes=dict(accessType='ONGOING',stoppedDueToInactivity=False))],links={}),
        dict(data=[dict(id=REPORT,type='analyticsReports',
            attributes=dict(name='App Downloads Standard',category='COMMERCE'))],links={}),
        dict(data=[dict(id=INSTANCE,type='analyticsReportInstances',
            attributes=dict(processingDate='2026-10-01',granularity='DAILY'))],links={}),
    ]


def segment(data=b'compressed report fixture',url=SIGNED_URL,**changes):
    attributes=dict(url=url,sizeInBytes=len(data),checksum=hashlib.md5(data,usedforsecurity=False).hexdigest())
    attributes.update(changes)
    return dict(id='segment-1',type='analyticsReportSegments',attributes=attributes,
        relationships=dict(analyticsReportInstance=dict(data=dict(type='analyticsReportInstances',id=INSTANCE))))


class Reader:
    def __init__(self,values):
        self.values=iter(values)
        self.calls=[]

    def read(self,url):
        self.calls.append(url)
        report_destination(url,None)
        return next(self.values)


class Response:
    def __init__(self,body,headers=None,status=200):
        self.body=body
        self.headers=Message()
        for key,value in (headers or {}).items(): self.headers[key]=value
        self.status=status

    def __enter__(self): return self
    def __exit__(self,*args): return False
    def getcode(self): return self.status
    def read(self,maximum): return self.body[:maximum]


class AppleMetricsTransportTests(unittest.TestCase):
    def test_complete_selected_report_downloads_segments_without_returning_signed_url(self):
        payload=b'compressed report fixture'
        reader=Reader(readiness_pages()+[dict(data=[segment(payload)],links={})])
        result=read_instance_segments(reader,APP,REPORT,INSTANCE,
            downloader=lambda url,size,checksum: payload)
        self.assertEqual(result,[dict(id='segment-1',size=len(payload),
            checksum=hashlib.md5(payload,usedforsecurity=False).hexdigest(),data=payload)])
        self.assertNotIn(SIGNED_URL,repr(result))
        self.assertTrue(reader.calls[-1].endswith('/v1/analyticsReportInstances/instance-1/segments?limit=100'))

    def test_app_report_or_instance_mismatch_stops_before_segment_request(self):
        reader=Reader(readiness_pages())
        with self.assertRaisesRegex(Invalid,'complete selected app report inventory'):
            read_instance_segments(reader,APP,'another-report',INSTANCE,
                downloader=Mock(side_effect=AssertionError('must not download')))
        self.assertEqual(len(reader.calls),4)

    def test_incomplete_segment_page_stops_before_any_download(self):
        path='/v1/analyticsReportInstances/'+INSTANCE+'/segments'
        pages=[dict(data=[segment()],links=dict(next='https://api.appstoreconnect.apple.com'+path+'?cursor='+str(i)))
               for i in range(3)]
        reader=Reader(readiness_pages()+pages)
        downloader=Mock(side_effect=AssertionError('partial inventory must not download'))
        with self.assertRaisesRegex(Invalid,'inventory is incomplete'):
            read_instance_segments(reader,APP,REPORT,INSTANCE,downloader=downloader)
        downloader.assert_not_called()

    def test_empty_inventory_and_wrong_segment_parent_are_rejected(self):
        reader=Reader(readiness_pages()+[dict(data=[],links={})])
        with self.assertRaisesRegex(Invalid,'inventory is incomplete'):
            read_instance_segments(reader,APP,REPORT,INSTANCE,downloader=Mock())
        foreign=segment()
        foreign['relationships']['analyticsReportInstance']['data']['id']='foreign-instance'
        reader=Reader(readiness_pages()+[dict(data=[foreign],links={})])
        downloader=Mock(side_effect=AssertionError('foreign segment must not download'))
        with self.assertRaisesRegex(Invalid,'another app'):
            read_instance_segments(reader,APP,REPORT,INSTANCE,downloader=downloader)
        downloader.assert_not_called()

    def test_malformed_segment_metadata_is_rejected_before_download(self):
        for changes in (dict(sizeInBytes=True),dict(sizeInBytes=0),dict(checksum='not-a-checksum')):
            reader=Reader(readiness_pages()+[dict(data=[segment(**changes)],links={})])
            downloader=Mock(side_effect=AssertionError('invalid segment must not download'))
            with self.subTest(changes=changes),self.assertRaises(Invalid):
                read_instance_segments(reader,APP,REPORT,INSTANCE,downloader=downloader)
            downloader.assert_not_called()

    def test_count_and_aggregate_byte_bounds_preflight_before_download(self):
        first=segment()
        second=segment();second['id']='segment-2'
        with patch.object(apple_segments,'MAX_SEGMENTS',1):
            reader=Reader(readiness_pages()+[dict(data=[first,second],links={})])
            downloader=Mock(side_effect=AssertionError('over-count must not download'))
            with self.assertRaisesRegex(Invalid,'outside supported limits'):
                read_instance_segments(reader,APP,REPORT,INSTANCE,downloader=downloader)
            downloader.assert_not_called()
        payload=b'compressed report fixture'
        first=segment(payload)
        second=segment(payload);second['id']='segment-2'
        with patch.object(apple_segments,'MAX_DECOMPRESSED',len(payload)*2-1):
            reader=Reader(readiness_pages()+[dict(data=[first,second],links={})])
            downloader=Mock(side_effect=AssertionError('over-budget manifest must not download'))
            with self.assertRaisesRegex(Invalid,'exceeds supported compressed bytes'):
                read_instance_segments(reader,APP,REPORT,INSTANCE,downloader=downloader)
            downloader.assert_not_called()

    def test_apple_segment_endpoint_is_allowlisted(self):
        report_destination('https://api.appstoreconnect.apple.com/v1/analyticsReportInstances/'+INSTANCE+'/segments?limit=100',None)
        with self.assertRaises(Invalid):
            report_destination('https://api.appstoreconnect.apple.com/v1/apps/123/analyticsReportInstances/'+INSTANCE+'/segments',None)


class AppleSignedSegmentTests(unittest.TestCase):
    def test_apple_documented_signed_s3_destination_shape_is_required(self):
        self.assertEqual(analytics_segment_destination(SIGNED_URL),SIGNED_URL)
        bad=(SIGNED_URL.replace('https://','http://'),
             SIGNED_URL.replace('asp-qa-us-west-2.s3.us-west-2.amazonaws.com','attacker.example'),
             SIGNED_URL.replace('https://','https://user@'),
             SIGNED_URL.replace('.com/reports/','.com:443/reports/'),
             SIGNED_URL.replace('/reports/sample/','/reports/%2e%2e/'),
             SIGNED_URL.split('?')[0],SIGNED_URL+'#fragment')
        for url in bad:
            with self.subTest(url=url),self.assertRaises(Invalid) as raised:
                analytics_segment_destination(url)
            self.assertNotIn('synthetic-secret',str(raised.exception))

    def test_signed_read_has_no_authorization_and_blocks_redirects(self):
        body=b'bytes from signed report'
        checksum=hashlib.md5(body,usedforsecurity=False).hexdigest()
        response=Response(body,{'Content-Length':str(len(body)),'Content-Encoding':'identity'})
        opener=Mock();opener.open.return_value=response
        with patch('mission_control.providers.build_opener',return_value=opener) as build:
            self.assertEqual(download_analytics_segment(SIGNED_URL,len(body),checksum),body)
        self.assertIsInstance(build.call_args.args[0],NoRedirect)
        request=opener.open.call_args.args[0]
        self.assertEqual(opener.open.call_args.kwargs['timeout'],15)
        self.assertEqual(request.get_method(),'GET')
        self.assertIsNone(request.data)
        self.assertIsNone(request.get_header('Authorization'))
        headers={key.lower():value for key,value in request.header_items()}
        self.assertEqual(headers.get('accept-encoding'),'identity')
        with self.assertRaisesRegex(Invalid,'redirect blocked'):
            NoRedirect().redirect_request(Request(SIGNED_URL),None,302,'Found',{},SIGNED_URL)

    def test_size_checksum_encoding_and_error_failures_are_sanitized(self):
        body=b'known report segment'
        checksum=hashlib.md5(body,usedforsecurity=False).hexdigest()
        cases=(Response(body,{'Content-Length':str(len(body)+1)}),
               Response(body,{'Content-Length':str(len(body)),'Content-Encoding':'gzip'}),
               Response(body+b'x',{'Content-Length':str(len(body))}))
        for response in cases:
            opener=Mock();opener.open.return_value=response
            with patch('mission_control.providers.build_opener',return_value=opener),self.assertRaises(Invalid):
                download_analytics_segment(SIGNED_URL,len(body),checksum)
        opener=Mock();opener.open.return_value=Response(body,{'Content-Length':str(len(body))})
        with patch('mission_control.providers.build_opener',return_value=opener),self.assertRaisesRegex(Invalid,'checksum'):
            download_analytics_segment(SIGNED_URL,len(body),'0'*32)
        opener=Mock();opener.open.side_effect=HTTPError(SIGNED_URL,403,'Forbidden',{},None)
        with patch('mission_control.providers.build_opener',return_value=opener),self.assertRaises(Invalid) as raised:
            download_analytics_segment(SIGNED_URL,len(body),checksum)
        self.assertNotIn('synthetic-secret',str(raised.exception))

    def test_oversized_segment_is_rejected_without_network(self):
        with patch('mission_control.providers.build_opener') as build,self.assertRaises(Invalid):
            download_analytics_segment(SIGNED_URL,MAX_COMPRESSED+1,'0'*32)
        build.assert_not_called()

    def test_response_body_cap_is_enforced_when_content_length_is_missing(self):
        body=b'x'*33
        checksum=hashlib.md5(body[:32],usedforsecurity=False).hexdigest()
        opener=Mock();opener.open.return_value=Response(body)
        with patch.object(providers,'MAX_COMPRESSED',32), \
             patch('mission_control.providers.build_opener',return_value=opener),self.assertRaises(Invalid):
            download_analytics_segment(SIGNED_URL,32,checksum)


if __name__=='__main__':
    unittest.main()
