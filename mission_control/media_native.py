"""Bounded offline FFmpeg rendering. Source text never becomes shell/filter code."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import textwrap
import time
from .common import Invalid

SHAPES={"PORTRAIT":(720,1280),"LANDSCAPE":(1280,720)}
MAX_BYTES=8388608
FONT_PATHS=(Path(os.environ.get("WINDIR","C:/Windows"))/"Fonts/segoeui.ttf",Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"))


def capability():
    """Report native tools and a known Latin font without installing anything."""
    tools={name:shutil.which(name) for name in ("ffmpeg","ffprobe")}
    font=next((str(p) for p in FONT_PATHS if p.is_file()),None)
    return dict(status="READY" if all(tools.values()) and font else "UNAVAILABLE",tools=tools,font=font,
                repair="Install FFmpeg with FFprobe and a supported Segoe UI or DejaVu Sans font; restart Mission Control.",
                script_support="Latin captions only; other scripts require a verified font implementation.")


def caption_lines(script,seconds,shape):
    """Reject unsupported glyphs and overflow; preserve exact original copy separately."""
    if not isinstance(script,str) or not script.strip():raise Invalid("Every video beat needs its original caption")
    if any(not supported(c) for c in script):raise Invalid("Caption has an unsupported script or control character; use a verified font workflow for this language")
    if len(script.split())>seconds*3:raise Invalid("Caption reads too fast; revise the brief objective/claims or choose a longer duration")
    width=40 if shape=="PORTRAIT" else 76
    lines=[line for paragraph in script.splitlines() for line in textwrap.wrap(paragraph,width=width,replace_whitespace=False)]
    if len(lines)>6:raise Invalid("Caption exceeds the readable video area; shorten approved copy or revise the brief")
    return "\n".join(lines)


def supported(char):
    """Keep a bounded verified Latin repertoire; never silently draw missing glyphs."""
    code=ord(char)
    return char=="\n" or 32<=code<=591 or 768<=code<=879 or 8192<=code<=8303


def invoke(argv,cwd,alive,deadline):
    """Poll a private child, heartbeat ownership, and terminate only that child on failure."""
    flags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0
    with (Path(cwd)/"native.log").open("wb") as log:
        process=subprocess.Popen(argv,cwd=cwd,stdin=subprocess.DEVNULL,stdout=log,stderr=log,creationflags=flags)
        try:
            while process.poll() is None:
                alive()
                if time.monotonic()>deadline:raise Invalid("Native render timed out; retry with fewer screens after checking local resources")
                time.sleep(0.2)
            if process.returncode:raise Invalid("Native media processing failed; verify that the selected screen decodes correctly and FFmpeg supports H.264/drawtext")
            alive()
        finally:
            if process.poll() is None:
                process.terminate()
                try:process.wait(timeout=3)
                except subprocess.TimeoutExpired:process.kill();process.wait(timeout=3)


def video_metadata(path,tools=None):
    """Read actual video-only metadata from bytes using a bounded local FFprobe process."""
    tools=tools or capability()["tools"]
    if not tools.get("ffprobe"):raise Invalid("FFprobe is required to validate video bytes")
    flags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0
    try:
        result=subprocess.run([tools["ffprobe"],"-v","error","-protocol_whitelist","file,pipe","-show_streams","-show_format","-of","json",str(path)],capture_output=True,timeout=15,creationflags=flags)
        if result.returncode:raise Invalid("Video bytes did not decode; no artifact was accepted")
        parsed=json.loads(result.stdout);streams=parsed["streams"]
        if len(streams)!=1 or streams[0].get("codec_type")!="video":raise Invalid("Rendered media must contain exactly one silent video stream")
        stream=streams[0]
        return dict(codec=stream["codec_name"],pixel_format=stream.get("pix_fmt"),width=stream["width"],height=stream["height"],
                    duration_seconds=float(parsed["format"]["duration"]),frame_rate=stream["avg_frame_rate"],audio=False)
    except (ValueError,KeyError,subprocess.TimeoutExpired) as exc:raise Invalid("Could not validate native video metadata") from exc


def validate_video(path,request,tools=None):
    """Require bounded actual H.264 output with exact dimensions and near-exact duration."""
    size=path.stat().st_size
    if not 0<size<=MAX_BYTES:raise Invalid("Video exceeds the bounded artifact size; use a shorter brief")
    metadata=video_metadata(path,tools)
    width,height=SHAPES[request["shape"]]
    if (metadata["width"],metadata["height"])!=(width,height) or metadata["codec"]!="h264" or metadata["pixel_format"]!="yuv420p":raise Invalid("Video encoding or dimensions do not match the requested render")
    if abs(metadata["duration_seconds"]-request["duration_seconds"])>0.15 or metadata["frame_rate"]!="24/1":raise Invalid("Video timing does not match the frozen brief")
    return dict(metadata=metadata,bytes=size,sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def filters(shape):
    """Compose contained authentic screens above readable caption space; no overlay on controls."""
    width,height=SHAPES[shape];caption_height=300 if shape=="PORTRAIT" else 240
    screen_height=height-caption_height-64;fontsize=28
    return (f"scale={width-64}:{screen_height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:32:color=0x102124,setsar=1,"
            f"drawtext=fontfile=font.ttf:textfile=caption.txt:expansion=none:fontcolor=white:fontsize={fontsize}:"
            f"line_spacing=8:x=32:y={height-caption_height+24}")


def render_native(folder,request,screens,alive):
    """Render four captioned segments then fast-start concatenate, all from private local files."""
    native=capability()
    if native["status"]!="READY":raise Invalid(native["repair"])
    shutil.copyfile(native["font"],folder/"font.ttf");deadline=time.monotonic()+180
    beats=request["captions"];quarter=request["duration_seconds"]/4
    for index,beat in enumerate(beats):
        (folder/"caption.txt").write_text(caption_lines(beat,quarter,request["shape"]),encoding="utf-8")
        output=f"part{index}.mp4"
        argv=[native["tools"]["ffmpeg"],"-hide_banner","-loglevel","error","-nostdin","-y","-protocol_whitelist","file,pipe","-loop","1","-i",str(screens[index%len(screens)]),
              "-t",str(quarter),"-vf",filters(request["shape"]),"-r","24","-an","-c:v","libx264","-preset","ultrafast","-crf","28","-pix_fmt","yuv420p",output]
        invoke(argv,folder,alive,deadline)
    (folder/"segments.txt").write_text("".join(f"file 'part{i}.mp4'\n" for i in range(4)),encoding="ascii")
    output=folder/"video.mp4"
    invoke([native["tools"]["ffmpeg"],"-hide_banner","-loglevel","error","-nostdin","-y","-f","concat","-safe","1","-i","segments.txt","-c","copy","-movflags","+faststart","video.mp4"],folder,alive,deadline)
    return output,validate_video(output,request,native["tools"])
