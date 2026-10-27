"""Bounded Apple Analytics segment retrieval; signed URLs never leave this module."""
import hashlib
import re

from .apple_analytics import collection, identity, read_analytics, relationship, resource
from .apple_analytics_parser import MAX_COMPRESSED, MAX_DECOMPRESSED, MAX_SEGMENTS
from .common import Invalid, required
from .providers import analytics_segment_destination, download_analytics_segment


def read_instance_segments(reader, store_id, report_id, instance_id, downloader=download_analytics_segment):
    """Download a complete supported instance only after verifying its app/report ancestry."""
    store_id=required(store_id,'Store app ID',30)
    if not re.fullmatch(r'[0-9]{1,30}',store_id):
        raise Invalid('Analytics store app identity must be numeric')
    report_id=identity(report_id)
    instance_id=identity(instance_id)
    inventory=read_analytics(reader,store_id)
    report=next((item for item in inventory['reports'] if item['id']==report_id),None)
    if (inventory['coverage']!='COMPLETE' or report is None
            or not any(item['id']==instance_id for item in report['instances'])):
        raise Invalid('Apple analytics instance is not in the complete selected app report inventory')
    rows,covered=collection(reader,'/v1/analyticsReportInstances/'+instance_id+'/segments','analyticsReportSegments')
    if not covered or not rows or len(rows)>MAX_SEGMENTS:
        raise Invalid('Apple analytics segment inventory is incomplete or outside supported limits')
    manifest=[]
    total=0
    for row in rows:
        segment_id,attributes=resource(row,'analyticsReportSegments')
        relationship(row,'analyticsReportInstance','analyticsReportInstances',instance_id)
        size=attributes.get('sizeInBytes')
        checksum=attributes.get('checksum')
        url=analytics_segment_destination(attributes.get('url'))
        if (type(size) is not int or not 1<=size<=MAX_COMPRESSED
                or not isinstance(checksum,str) or not re.fullmatch(r'[0-9a-fA-F]{32}',checksum)):
            raise Invalid('Apple analytics segment metadata is invalid')
        total+=size
        if total>MAX_DECOMPRESSED:
            raise Invalid('Apple analytics instance exceeds supported compressed bytes')
        manifest.append(dict(id=segment_id,size=size,checksum=checksum.lower(),url=url))
    result=[]
    for item in manifest:
        data=downloader(item['url'],item['size'],item['checksum'])
        if (not isinstance(data,bytes) or len(data)!=item['size']
                or hashlib.md5(data,usedforsecurity=False).hexdigest()!=item['checksum']):
            raise Invalid('Apple analytics segment bytes failed integrity validation')
        result.append(dict(id=item['id'],size=item['size'],checksum=item['checksum'],data=data))
    return result
