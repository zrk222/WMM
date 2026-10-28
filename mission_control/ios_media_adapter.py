"""Trusted native decoder seam; inspection is never taken from operation JSON."""
from .common import Invalid
from .ios_bridge import decode_document, encode_response


def inspection_from_native(proof):
    """Accept only the dedicated signed-host inspection parameter, not agent input.

    Reuse shared metadata normalization and original-byte verification. This parser
    validates a trusted decoder's evidence; it cannot prove a caller ran AVFoundation.
    """
    from fractions import Fraction
    from .managed_media_validation import media_metadata
    if not isinstance(proof,bytes) or len(proof)>16384:raise Invalid('Native inspection exceeds its evidence bound')
    result=decode_document(proof)
    if not isinstance(result,dict) or set(result)!={'sha256','bytes','metadata','decoded'}:
        raise Invalid('Use exact native inspection fields')
    metadata=result['metadata']
    if not isinstance(metadata,dict) or type(metadata.get('audio')) is not bool:
        raise Invalid('Native inspection metadata is malformed')
    keys={'codec','width','height','duration_seconds','frame_rate','audio'}
    if metadata['audio']:keys.add('audio_metadata')
    if set(metadata)!=keys or type(metadata['frame_rate']) not in (int,float):raise Invalid('Native metadata fields differ')
    try:rate=Fraction(str(metadata['frame_rate'])).limit_denominator(1000000)
    except (ValueError,OverflowError):raise Invalid('Native frame rate is malformed') from None
    streams=[dict(codec_type='video',codec_name=metadata['codec'],width=metadata['width'],height=metadata['height'],
                  avg_frame_rate=f'{rate.numerator}/{rate.denominator}')]
    if metadata['audio']:
        audio=metadata['audio_metadata']
        if not isinstance(audio,dict) or set(audio)!={'codec','channels','sample_rate'} or type(audio['sample_rate']) is not int:
            raise Invalid('Native audio evidence is malformed')
        streams.append(dict(codec_type='audio',codec_name=audio['codec'],channels=audio['channels'],sample_rate=str(audio['sample_rate'])))
    result['metadata']=media_metadata(dict(streams=streams,format=dict(duration=metadata['duration_seconds'])))
    def inspect(raw,suffix,alive=lambda:None):
        alive()
        # Media._validated verifies digest, size and decoded picture/audio counts.
        return result
    return inspect


def no_native_inspection(*args,**kwargs):
    raise Invalid('Native original inspection is required before upload')


class NativeMediaAdapter:
    def __init__(self, service, identities, inspector):
        from .managed_media_store import Media
        if not callable(inspector): raise TypeError('A trusted native video inspector is required')
        self.service = service
        self.identities = identities
        self.media = Media(service.store, inspector=inspector)

    def _run(self, session, app_id, action, body, execute):
        from .operation_authority import bound_owner, protected
        user = self.identities.fresh(session)
        # Internal fixed owner action, never an agent catalog admission.
        envelope = dict(app_id=app_id,operation='native.media.'+action,input=body)
        with bound_owner(self.service.store,envelope,self.identities,session,user):
            with protected(self.service.store,envelope):
                result = execute(user)
        return encode_response(result)

    def upload(self, session, app_id, filename, raw, payload):
        from .managed_media_store import MAX_BYTES
        if type(raw) is not bytes or not 1 <= len(raw) <= MAX_BYTES:
            raise Invalid('Choose original video bytes within the 64 MiB media bound')
        body = decode_document(payload)
        # The inspector is constructor-injected and cannot be supplied in body.
        if not isinstance(body,dict) or set(body) != {'manifest_version','request_key'}:
            raise Invalid('Use exact upload version and request key; native inspection is not request data')
        return self._run(session,app_id,'upload',body,
            lambda user:self.media.upload(app_id,filename,raw,body))

    def list(self, session, app_id):
        return self._run(session,app_id,'list',{},lambda user:self.media.list(app_id))

    def review(self, session, app_id, media_id, payload):
        body = decode_document(payload)
        return self._run(session,app_id,'review',dict(media_id=media_id,review=body),
            lambda user:self.media.review(app_id,media_id,body,user))

    def resolve(self, session, app_id, media_id, sha256):
        # The filesystem path is for the trusted native renderer only. It is not
        # returned by list/read/protocol JSON and must never enter model prompts.
        from .operation_authority import bound_owner, protected
        user = self.identities.fresh(session)
        envelope=dict(app_id=app_id,operation='native.media.resolve',input=dict(id=media_id,sha256=sha256))
        with bound_owner(self.service.store,envelope,self.identities,session,user):
            with protected(self.service.store,envelope):
                return self.media.resolve(app_id,media_id,sha256,require_reuse=True)
