"""Explicit effect uncertainty; input rejection cannot prove an external rollback."""
from .common import Invalid


class EffectUncertain(Invalid):
    """Public fixed guidance, without raw native errors or automatic retry authority."""
    def __init__(self):
        super().__init__('Local operation outcome is uncertain; inspect the saved attempt before retrying')
