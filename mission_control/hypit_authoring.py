"""Data-only Hypit composition authoring; no request-supplied code or endpoints."""

import hashlib
import json
import re
from xml.sax.saxutils import escape
from .common import Invalid, canonical, digest
from .media_native import SHAPES

MAX_SCENES = 12
MAX_TEXT = 240
MAX_SECONDS = 60
FPS = 24
FOOTAGE_SCHEMA = "growth.hypit-footage-scene.v1"


def literal(value):
    """Preserve Unicode XML text while excluding controls and noncharacters."""
    if not isinstance(value, str) or not value.strip() or len(value) > MAX_TEXT:
        raise Invalid("Use nonempty scene text of at most 240 characters")
    if any(not xml_character(ord(char)) for char in value):
        raise Invalid("Scene text contains an unsupported XML character")
    return value


def xml_character(code):
    """Follow XML character ranges; reject surrogate and noncharacter values."""
    return (
        code in (9, 10, 13) or 32 <= code <= 0xD7FF or 0xE000 <= code <= 0xFFFD or 0x10000 <= code <= 0x10FFFF
    ) and code & 0xFFFF not in (0xFFFE, 0xFFFF)


def scene_contract(value):
    """Freeze exact finite data before content can reach the markup compiler."""
    if not isinstance(value, dict) or set(value) not in (
        {"title", "shape", "scenes"},
        {"schema", "title", "shape", "scenes"},
    ):
        raise Invalid("Choose only title, shape and scenes")
    footage = "schema" in value
    if footage and value["schema"] != FOOTAGE_SCHEMA:
        raise Invalid("Use the supported footage scene version")
    if not isinstance(value["shape"], str) or value["shape"] not in SHAPES:
        raise Invalid("Choose portrait or landscape")
    scenes = value["scenes"]
    if not isinstance(scenes, list) or not 1 <= len(scenes) <= MAX_SCENES:
        raise Invalid("Use 1 through 12 scenes")
    normalized = [footage_item(item) if footage else scene_item(item) for item in scenes]
    if sum(item["seconds"] for item in normalized) > MAX_SECONDS:
        raise Invalid("Keep the composition within 60 seconds")
    result = dict(title=literal(value["title"]), shape=value["shape"], scenes=normalized)
    if footage:
        if not any("media" in item for item in normalized):
            raise Invalid("Choose at least one managed footage segment")
        result["schema"] = FOOTAGE_SCHEMA
    return result


def scene_item(item):
    """Reject hidden commands, media destinations and fractional/bool timing."""
    if not isinstance(item, dict) or set(item) != {"text", "seconds"}:
        raise Invalid("Each scene needs only text and seconds")
    seconds = item["seconds"]
    if type(seconds) is not int or not 1 <= seconds <= 15:
        raise Invalid("Use 1 through 15 integer seconds per scene")
    return dict(text=literal(item["text"]), seconds=seconds)


def footage_item(item):
    """Use the existing studio media identity and 24-fps source frame contract."""
    if not isinstance(item, dict) or set(item) not in ({"text", "seconds"}, {"text", "seconds", "media"}):
        raise Invalid("Each footage scene needs text, seconds and optional managed media")
    result = scene_item({"text": item["text"], "seconds": item["seconds"]})
    if "media" not in item:
        return result
    media = item["media"]
    if (
        not isinstance(media, dict)
        or set(media) != {"id", "sha256", "in_frame", "audio"}
        or not isinstance(media["id"], str)
        or not re.fullmatch(r"[a-f0-9-]{36}", media["id"])
        or not isinstance(media["sha256"], str)
        or not re.fullmatch(r"[a-f0-9]{64}", media["sha256"])
        or type(media["in_frame"]) is not int
        or not 0 <= media["in_frame"] < 180 * FPS
        or media["in_frame"] + result["seconds"] * FPS > 180 * FPS
        or media["audio"] != "MUTE"
    ):
        raise Invalid("Choose managed footage, a valid source frame and MUTE audio")
    result["media"] = dict(media)
    return result


def composition(value):
    """Emit a fixed vocabulary; literal text never becomes an attribute or import."""
    width, height = SHAPES[value["shape"]]
    seconds = sum(item["seconds"] for item in value["scenes"])
    windows = []
    tracks = []
    layers = []
    media_declarations = []
    media_layers = []
    has_footage = any("media" in item for item in value["scenes"])
    footage_frames = (
        (
            '<space:Frame id="picture" within={canvas.bounds} left="8%" top="23%" right="92%" bottom="75%"/>\n'
            '<space:Frame id="caption" within={canvas.bounds} left="8%" top="79%" right="92%" bottom="94%"/>\n'
        )
        if has_footage
        else ""
    )
    start = 0
    for index, item in enumerate(value["scenes"]):
        name = "scene" + str(index)
        windows.append(f'<time:Window id="{name}" from="{start}s" for="{item["seconds"]}s"/>')
        text_frame = "caption" if "media" in item else "body"
        tracks.append(
            f'<typo:Flow id="{name}" timeline={{clock.timeline}} within={{{text_frame}}} style={{body-style}} z="20" align="center" block-align="center" during={{clock.{name}}}>{escape(item["text"])}</typo:Flow>'
        )
        layers.append(f"<film:Track source={{{name}.visual}}/>")
        if "media" in item:
            media_declarations.append(
                f'<media:Video id="original{index}" src="./assets/scene{index}.mp4"/>\n'
                f'<mediaop:Normalize id="normalized{index}" source={{original{index}}} video="primary-moving" audio="none" span-authority="video" clock={{fps}}/>\n'
                f'<visual:Track id="footage{index}" timeline={{clock.timeline}}><visual:Clip id="clip{index}" media={{normalized{index}.media}} during={{clock.{name}}} frame={{picture}} z="0" fit="contain"/></visual:Track>'
            )
            media_layers.append(f"<film:Track source={{footage{index}.visual}}/>")
        start += item["seconds"]
    imports = (
        (
            '<import as="mediaop" from="@hypit/media-operations@1"/>\n'
            '<import as="visual" from="@hypit/visual-track@1"/>\n'
        )
        if media_declarations
        else ""
    )
    media_source = "\n".join(media_declarations) + "\n" if media_declarations else ""
    return f'''<?svml using="@hypit/markup@1"?>
<svml>
<import as="time" from="@hypit/timeline-author@1"/>
<import as="space" from="@hypit/spatial@1"/>
<import as="media" from="@hypit/media@1"/>
{imports}<import as="typo" from="@hypit/text-fine@1"/>
<import as="film" from="@hypit/film@1"/>
<import as="html" from="@hypit/html-video@1"/>
<import as="style" source="./style.svs"/>
<time:Clock id="fps" frame-rate="{FPS}"/>
<time:Timeline id="clock" clock={{fps}} end="{seconds}s">{"".join(windows)}</time:Timeline>
<space:Canvas id="canvas" width="{width}" height="{height}"/>
<space:Frame id="heading" within={{canvas.bounds}} left="8%" top="6%" right="92%" bottom="22%"/>
<space:Frame id="body" within={{canvas.bounds}} left="8%" top="27%" right="92%" bottom="88%"/>
{footage_frames}<media:Font id="font" src="./font.ttf" weight="400" style="normal"/>
<typo:Style id="title-style" recipe={{style.text.title}} font={{font}}/>
<typo:Style id="body-style" recipe={{style.text.body}} font={{font}}/>
{media_source}<typo:Flow id="title" timeline={{clock.timeline}} within={{heading}} style={{title-style}} z="10" align="center" block-align="center" during={{clock.window}}>{escape(value["title"])}</typo:Flow>
{"".join(tracks)}
<film:Film id="main" canvas={{canvas.canvas}} timeline={{clock.timeline}} appearance={{style.film.main}}>
{"".join(media_layers)}<film:Track source={{title.visual}}/>{"".join(layers)}
</film:Film>
<html:Video id="final" composition={{main.composition}} timeline={{clock.timeline}}/>
</svml>
'''


def project(value):
    """Return fixed editable files and exact hashes without filesystem side effects."""
    value = scene_contract(value)
    runtime = dict(
        format="hypit.runtime-local@1",
        dataRoot=".hypit/runtimes/local",
        endpoints={
            "media.local": dict(use="@hypit/media-local", config=dict(defaultConcurrency=1)),
            "html.local": dict(use="@hypit/provider-html-local", config=dict(workers=1, defaultConcurrency=1)),
        },
    )
    files = {
        "package.json": canonical(
            dict(name="wmm-agent-video", version="0.0.0", private=True, type="module", hypit=dict(project=True))
        )
        + "\n",
        "film.svml": composition(value),
        "style.svs": '<?svml using="@hypit/recipe@1"?>\n<sheet version="1">\nfilm.main { background: #102124; }\ntext.title { size: 38; weight: 400; fill: #A7E8C1; }\ntext.body { size: 42; weight: 400; line-height: 1.3; fill: #FFFFFF; }\n</sheet>\n',
        "build.svrun": '<?svml using="@hypit/markup/run@1"?>\n<svrun version="1"><author source="./film.svml"/><target output="final.video"/></svrun>\n',
        "runtime.json": json.dumps(runtime, sort_keys=True, indent=2) + "\n",
    }
    return dict(
        files=files,
        receipt=dict(
            schema="growth.hypit-authoring.v1",
            scene_hash=digest(value),
            source_hashes={name: hashlib.sha256(text.encode()).hexdigest() for name, text in files.items()},
            duration_seconds=sum(item["seconds"] for item in value["scenes"]),
            shape=value["shape"],
            video_generation="NOT_REQUIRED_BY_PROFILE",
            publication="NOT_RUN",
        ),
    )
