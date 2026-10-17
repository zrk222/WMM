"""Closed operator scope for credential-free, bounded REA browser inspection."""
from urllib.parse import urlsplit
from .common import Invalid, required
from .aeo_transport import public_url, origin

MODES = ("PUBLIC_PASSIVE", "OWNED_FIXTURE")
ACTIONS = ("goto", "click", "press", "select_option", "wait_for")
SHAPES = {"mobile": (390, 844), "desktop": (1440, 1000)}


def exact(value, fields):
    """Reject unknown client fields before any native action."""
    if not isinstance(value, dict) or set(value) != set(fields):
        raise Invalid("Inspection fields changed; reopen the form")


def fixture_url(value):
    """Require a credential-free exact IPv4 loopback fixture address."""
    text = required(value, "Fixture URL", 200)
    try:
        u = urlsplit(text)
        valid = fixture_origin(u)
    except ValueError as exc:
        raise Invalid("Use an explicit http://127.0.0.1:port fixture") from exc
    if not valid or "?" in text or "#" in text or any(c.isspace() for c in text) or "\\" in text:
        raise Invalid("Use a loopback fixture without credentials, query or fragment")
    return text


def fixture_origin(value):
    """Restrict fixture authority independently from path validation."""
    return (value.scheme == "http" and value.hostname == "127.0.0.1" and value.port is not None
            and value.username is None and value.password is None)


def target(value, mode, app):
    """Bind public navigation to the exact manifest website origin."""
    if mode == "OWNED_FIXTURE":
        return fixture_url(value)
    url = public_url(value)
    if not app["data"].get("website") or origin(url) != origin(app["data"]["website"]):
        raise Invalid("Public inspection must use this app's website origin")
    return url


def step(value, index, mode, start, app):
    """Produce only declared typed actions; never evaluate JavaScript or inject storage."""
    exact(value, ("action", "selector", "value"))
    action = value["action"]
    if action not in ACTIONS:
        raise Invalid("Choose a supported inspection action")
    if mode == "PUBLIC_PASSIVE" and action not in ("goto", "wait_for"):
        raise Invalid("Interactive steps require an explicitly owned isolated fixture")
    item = {"step_id": "step-" + str(index), "action": action, "timeout_ms": 5000}
    if action == "goto":
        url = target(value["value"], mode, app)
        if urlsplit(url).netloc != urlsplit(start).netloc:
            raise Invalid("Every navigation must remain on the exact start origin")
        if value["selector"]:
            raise Invalid("Navigation has no selector")
        return dict(item, destination={"url": url, "query": []}, wait_until="domcontentloaded")
    selector = required(value["selector"], "CSS selector", 200)
    item["locator"] = {"kind": "css", "selector": selector}
    return step_value(item, value["value"])


def step_value(item, value):
    """Validate fixed wait, key and option values."""
    action = item["action"]
    if action == "wait_for":
        if value not in ("visible", "hidden", "attached", "detached"):
            raise Invalid("Choose the expected visibility")
        item["state"] = value
    elif action == "press":
        item["key"] = required(value, "Key", 200)
    elif action == "select_option":
        item["value"] = {"source": "literal", "value": required(value, "Option", 200)}
    elif value:
        raise Invalid("Click has no value")
    return item


def scope(body, app, tools):
    """Freeze the current app, tools, viewport and declared action sequence."""
    exact(body, ("manifest_version", "tool_id", "mode", "start_url", "viewport", "steps", "confirm_scope"))
    if type(body["manifest_version"]) is not int or body["manifest_version"] != app["version"]:
        raise Invalid("App setup changed; reopen inspection setup")
    if body["confirm_scope"] is not True:
        raise Invalid("Confirm the declared credential-free scope and fixture ownership")
    if tools["status"] != "READY" or body["tool_id"] != tools["id"]:
        raise Invalid("Native installation changed or is unavailable; refresh detected tools")
    mode = body["mode"]
    shape(mode,body["viewport"])
    steps = body["steps"]
    if not isinstance(steps, list) or not 1 <= len(steps) <= 12:
        raise Invalid("Declare between 1 and 12 inspection steps")
    url = target(body["start_url"], mode, app)
    width, height = SHAPES[body["viewport"]]
    scenario = {"browser": {"mode": "launch", "executable_path": tools["browser"], "headless": True},
                "start_url": {"url": url, "query": []},
                "environment": {"viewport": {"width": width, "height": height}},
                "actions": [step(v, i, mode, url, app) for i, v in enumerate(steps)],
                "storage": {"cookies": [], "local_storage": [], "session_storage": []}, "secrets": [],
                "capture": {"after_each_step": ["url"], "at_end": ["url", "dom", "accessibility", "screenshot"],
                            "events": ["page-errors", "network"]}}
    return {"mode": mode, "request": body, "scenario": scenario, "tool_id": tools["id"]}


def shape(mode,viewport):
    """Reject untyped or unknown viewport fields without leaking a server error."""
    if mode not in MODES or not isinstance(viewport,str) or viewport not in SHAPES:
        raise Invalid("Choose scope mode and viewport")
