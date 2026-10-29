"""Trusted native device presence; this is not a pipeline dispatch capability."""
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

DEVICE_HOST=ContextVar('wmm_native_device_host',default=None)


@contextmanager
def native_device_context(service,identities,session):
    user=identities.fresh(session)
    token=DEVICE_HOST.set(dict(store=str(Path(service.store.path).resolve()),
                              identities=identities,session=session,user=user))
    try:yield
    finally:DEVICE_HOST.reset(token)
