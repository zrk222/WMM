"""Typed operator declarations; capability is distinct from asset and release proof."""
from .common import Invalid,iso_time,now,required,safe_data
EXECUTIONS=("SCREEN_RECORDING","SLIDES","HOST","SILENT_UGC","ANIMATION")
TALENT=("NONE","FOUNDER","TEAM","CONSENTED_CREATOR")
AUDIO=("SILENT","VOICEOVER","MUSIC")
CHANNELS=("SHORT_VIDEO","LINKEDIN","X")
NARRATIVES=("DEMO","PROBLEM_SOLUTION","EDUCATIONAL","STORY","BEFORE_AFTER","LIST","OTHER")
COMMON={"editing_level","cost_minor","time_minutes","source","checked_at"}
PROFILE=COMMON|{"app_hash","executions","talent","audio","channels","capture_available"}
REQUIREMENT=COMMON|{"reference_id","capture_hash","execution","talent","audio","narrative","requires_capture","rights_available"}

def integer(value,name,low,high):
    """Reject booleans and nonintegral or unbounded operator values."""
    if type(value) is not int or not low<=value<=high:raise Invalid(f"{name}: use a whole number {low} through {high}")
    return value

def selected(value,options,name):
    """Require an explicit distinct nonempty list of known capabilities."""
    if not isinstance(value,list) or not value or len(value)>len(options):raise Invalid("Choose "+name)
    if any(not isinstance(v,str) or v not in options for v in value) or len(set(value))!=len(value):raise Invalid("Unknown or duplicate "+name)
    return value

def choice(value,options,name):
    """Reject arbitrary labels that cannot be evaluated as capability."""
    if not isinstance(value,str) or value not in options:raise Invalid("Choose a known "+name)
    return value

def declaration(data,kind):
    """Validate finite typed values and provenance without inferring any fields."""
    safe_data(data)
    fields=PROFILE if kind=="profile" else REQUIREMENT
    if not isinstance(data,dict) or set(data)!=fields:raise Invalid("Complete the production "+kind+" fields")
    integer(data["editing_level"],"Editing level",0,3)
    integer(data["time_minutes"],"Production time",1,10080)
    integer(data["cost_minor"],"Production cost",0,1000000000000)
    required(data["source"],"Production review source",2000)
    if iso_time(data["checked_at"])>iso_time(now()):raise Invalid("Production review cannot be in the future")
    if kind=="profile":profile_fields(data)
    elif kind=="requirement":requirement_fields(data)
    else:raise Invalid("Unknown production declaration")
    return data

def profile_fields(data):
    """Validate team capability separately from each inspected format."""
    required(data["app_hash"],"App hash",120)
    for key,options in (("executions",EXECUTIONS),("talent",TALENT),("audio",AUDIO),("channels",CHANNELS)):
        selected(data[key],options,key)
    if type(data["capture_available"]) is not bool:raise Invalid("Declare whether authentic capture is available")

def requirement_fields(data):
    """Allow explicitly unknown execution only as a blocking declaration."""
    for key in ("reference_id","capture_hash"):required(data[key],key,120)
    for key,options in (("execution",EXECUTIONS+("UNKNOWN",)),("talent",TALENT),("audio",AUDIO),("narrative",NARRATIVES)):
        choice(data[key],options,key)
    for key in ("requires_capture","rights_available"):
        if type(data[key]) is not bool:raise Invalid("Declare "+key.replace("_"," "))

def fresh(data,stamp):
    """Keep old or future supplied reviews out of current production readiness."""
    return 0<=(iso_time(stamp)-iso_time(data["checked_at"])).total_seconds()<=2592000
