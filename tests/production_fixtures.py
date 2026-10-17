"""Explicit synthetic declarations, confined to isolated test stores."""
from mission_control.common import digest,now
from mission_control.production_feasibility import Capabilities

def profile(store,app,stamp=None,**changes):
    return dict(dict(app_hash=digest(store.app(app)["data"]),executions=["SCREEN_RECORDING","SLIDES","HOST","SILENT_UGC","ANIMATION"],
        talent=["NONE","FOUNDER","TEAM","CONSENTED_CREATOR"],audio=["SILENT","VOICEOVER","MUSIC"],channels=["SHORT_VIDEO","LINKEDIN","X"],
        editing_level=3,cost_minor=100000,time_minutes=10080,capture_available=True,
        source="Synthetic fixture; no real-world rights or team capability asserted",checked_at=stamp or now()),**changes)

def requirement(source,stamp=None,**changes):
    return dict(dict(reference_id=source["id"],capture_hash=source["current"]["hash"],execution="SCREEN_RECORDING",talent="NONE",audio="SILENT",narrative="DEMO",
        editing_level=1,cost_minor=1000,time_minutes=10,requires_capture=True,rights_available=True,
        source="Synthetic inspected fixture only",checked_at=stamp or now()),**changes)

def ready_capabilities(store,app,sources,stamp=None):
    service=Capabilities(store);saved=service.list(app)
    if not saved["profile"]:service.save(app,"profile",{"data":profile(store,app,stamp)})
    existing={r["current"]["data"]["reference_id"]:r for r in saved["requirement"]}
    for source in sources:
        if source["id"] not in existing:service.save(app,"requirement",{"data":requirement(source,stamp)})
