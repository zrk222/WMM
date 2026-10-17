"""Conservative bounded robots policies; unknown input never becomes permission."""
import re
from urllib.parse import quote, urlsplit
from .common import Invalid
from .aeo_transport import ReadError, text


def normalized_path(value):
    """Normalize UTF-8 and unreserved escapes, retaining reserved path octets."""
    if re.search(r"%(?![A-Fa-f0-9]{2})", value):
        raise Invalid("Malformed robots percent encoding")
    value = quote(value, safe="/%*:$@!&'()+,;=-._~")
    def escape(match):
        byte = int(match[1], 16); char = chr(byte)
        return char if re.fullmatch(r"[A-Za-z0-9._~-]", char) else "%"+match[1].upper()
    return re.sub(r"%([A-Fa-f0-9]{2})", escape, value)


def rule_pattern(value):
    """Require supported anchored path syntax and finite wildcard count."""
    if len(value) > 2048 or value.count("*") > 16 or not value.startswith("/"):
        raise Invalid("Unsupported robots rule")
    if re.search(r"[\x00-\x20\x7f\\]", value) or "$" in value.rstrip("$") or value.endswith("$$"):
        raise Invalid("Unsupported robots rule syntax")
    return normalized_path(value)


def matches(pattern, path):
    """Wildcard matching without backtracking regular expressions."""
    terminal = pattern.endswith("$"); body = pattern[:-1] if terminal else pattern
    pieces = body.split("*")
    if not path.startswith(pieces[0]):
        return False
    offset = len(pieces[0])
    if len(pieces) == 1:
        return not terminal or offset == len(path)
    middle = pieces[1:-1] if terminal else pieces[1:]
    for piece in middle:
        found = path.find(piece, offset)
        if found < 0:
            return False
        offset = found + len(piece)
    if terminal:
        return path.endswith(pieces[-1]) and len(path)-len(pieces[-1]) >= offset
    return True


def agent_group(state, value):
    """Start a new group only after rules; consecutive agents share a group."""
    if not re.fullmatch(r"[A-Za-z0-9_-]+|\*", value):
        raise Invalid("Unsupported robots agent")
    if state["has_directives"]:
        state["groups"].append((state["agents"], state["rules"]))
        state["agents"] = []; state["rules"] = []; state["has_directives"] = False
    state["agents"].append(value.lower())


def apply_directive(state, key, value):
    """Keep bounded supported rules; ignore non-permission extension fields."""
    if key == "sitemap":
        if value and value not in state["maps"]:
            state["maps"].append(value)
        if len(state["maps"]) > 32:
            raise Invalid("Robots sitemap limit")
    elif key == "user-agent":
        agent_group(state, value)
    elif key in ("allow", "disallow"):
        state["has_directives"] = True
        if value:
            state["count"] += 1
            if not state["agents"] or state["count"] > 1024:
                raise Invalid("Robots rule limit or missing agent")
            state["rules"].append((key, rule_pattern(value)))


def parse_rules(raw):
    """Keep agent groups and sitemaps; malformed input stops the whole policy."""
    state = {"groups":[], "agents":[], "rules":[], "maps":[], "count":0, "has_directives":False}
    for line in raw.splitlines():
        if len(line) > 2048:
            raise Invalid("Robots line limit")
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        if ":" not in line:
            raise Invalid("Malformed robots directive")
        key, value = (p.strip() for p in line.split(":", 1))
        if not re.fullmatch(r"[A-Za-z][A-Za-z-]*", key):
            raise Invalid("Malformed robots directive name")
        apply_directive(state, key.lower(), value)
    if state["agents"]:
        state["groups"].append((state["agents"], state["rules"]))
    return state["groups"], state["maps"]


def matching_rules(groups, agent):
    """Merge all groups with equally specific matching product tokens."""
    selected = []; best = -1
    for agents, rules in groups:
        lengths = [0 if p == "*" else len(p) for p in agents if p == "*" or agent.lower().startswith(p)]
        if not lengths:
            continue
        score = max(lengths)
        if score > best:
            best = score; selected = list(rules)
        elif score == best:
            selected.extend(rules)
    return selected


def evaluate(groups, path, agent):
    """Longest matching path wins; Allow wins equal specificity."""
    path = normalized_path(path); candidates = []
    for action, pattern in matching_rules(groups, agent):
        if matches(pattern, path):
            size = len(pattern.rstrip("$").replace("*", "").encode())
            candidates.append((size, action == "allow"))
    return "ALLOW" if not candidates or max(candidates)[1] else "DISALLOW"


def policy(resource, url, agent):
    """Return independent permission evidence; errors never imply allowance."""
    if resource.get("status") in (404, 410):
        return {"state": "ALLOW", "reason": "ROBOTS_ABSENT", "sitemaps": []}
    if resource.get("status") != 200:
        return {"state": "UNKNOWN", "reason": "ROBOTS_UNAVAILABLE", "sitemaps": []}
    try:
        types = resource["headers"].get("content-type", [])
        if any("text/html" in t.lower() for t in types):
            raise Invalid("HTML is not a robots policy")
        groups, maps = parse_rules(text(resource))
        return {"state": evaluate(groups, urlsplit(url).path or "/", agent), "reason": "ROBOTS_OBSERVED", "sitemaps": maps}
    except (Invalid, ReadError):
        return {"state": "UNKNOWN", "reason": "ROBOTS_UNSUPPORTED", "sitemaps": []}
