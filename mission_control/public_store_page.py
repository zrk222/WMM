"""Closed server-rendered Apple listing parser; scripts/reviews cannot prove copy."""
from html.parser import HTMLParser
import re
import unicodedata
from urllib.parse import urlsplit
from .aeo_transport import public_url, text, evidence

VOID = {"area","base","br","col","embed","hr","img","input","link","meta","param","source","track","wbr"}
HIDDEN = {"script","style","template","dialog","noscript"}


def normalize(value):
    """Normalize Unicode and whitespace without changing copy meaning/case."""
    return " ".join(unicodedata.normalize("NFC",value).split())


def destination(value, country, app_id):
    """Only the selected Apple storefront and exact numeric app may be read."""
    try:
        parsed=urlsplit(public_url(value))
        return parsed.netloc=="apps.apple.com" and bool(re.fullmatch("/"+re.escape(country)+r"/app/(?:[^/]+/)?id"+re.escape(app_id),parsed.path))
    except ValueError:
        return False


def hidden(tag, attrs):
    """Exclude non-rendered and explicitly concealed content."""
    return (tag in HIDDEN or "hidden" in attrs or attrs.get("aria-hidden","").lower()=="true" or
            bool(re.search(r"(?:display\s*:\s*none|visibility\s*:\s*hidden)\b",attrs.get("style", ""),re.I)))


class ListingHTML(HTMLParser):
    def __init__(self):
        """Initialize bounded per-page parsing state."""
        super().__init__(convert_charrefs=True)
        self.stack=[];self.languages=[];self.canonicals=[];self.og=[]
        self.descriptions=[];self.versions=[];self.ambiguous=False

    def metadata(self, tag, attrs):
        """Keep fixed identity metadata only, never arbitrary attributes."""
        if tag=="html":self.languages.append(attrs.get("lang",""))
        if tag=="link" and "canonical" in attrs.get("rel","").lower().split():self.canonicals.append(attrs.get("href",""))
        if tag=="meta" and attrs.get("property","").lower()=="og:url":self.og.append(attrs.get("content",""))

    def frame(self, tag, attrs):
        """Carry description and current-version scopes through nested spans."""
        parent=self.stack[-1] if self.stack else {"hidden":False,"description":None,"recent":False,"metadata":False,"version":None}
        frame={**parent,"tag":tag,"hidden":parent["hidden"] or hidden(tag,attrs)}
        classes=attrs.get("class","").split()
        if self.description_section(tag,attrs,frame,classes):
            frame["description"]=[];self.descriptions.append(frame["description"])
        frame["recent"]=parent["recent"] or (tag=="section" and attrs.get("id")=="mostRecentVersion")
        frame["metadata"]=parent["metadata"] or (frame["recent"] and "metadata" in classes)
        self.version_frame(tag,frame)
        return frame

    def description_section(self,tag,attrs,frame,classes):
        """Exclude Apple privacy/accessibility footers with the same shelf classes."""
        return tag=="section" and not frame["hidden"] and "id" not in attrs and attrs.get("data-test-id")=="shelf-wrapper" and {"shelf","centered"}.issubset(classes)

    def version_frame(self,tag,frame):
        """A current metadata span owns exactly one version buffer."""
        if tag=="span" and frame["metadata"] and frame["version"] is None and not frame["hidden"]:
            frame["version"]=[];self.versions.append(frame["version"])

    def handle_starttag(self, tag, attributes):
        """Track visible scopes while rejecting duplicate attributes."""
        attrs={key:value or "" for key,value in attributes}
        if len(attrs)!=len(attributes):self.ambiguous=True
        # Metadata from scripts or hidden descendants is never an identity assertion.
        if not self.stack or not self.stack[-1]["hidden"]:self.metadata(tag,attrs)
        if tag=="br":self.handle_data("\n")
        if tag not in VOID:self.stack.append(self.frame(tag,attrs))

    def handle_startendtag(self, tag, attrs):
        """Handle explicit self-closing scopes."""
        self.handle_starttag(tag,attrs)
        if tag not in VOID:self.handle_endtag(tag)

    def handle_endtag(self, tag):
        """Reject unmatched closing tags instead of guessing a browser tree."""
        if tag in VOID:return
        if not self.stack or self.stack[-1]["tag"]!=tag:
            self.ambiguous=True
            return
        self.stack.pop()

    def handle_data(self, value):
        """Collect only text inside visible eligible sections."""
        if not self.stack or self.stack[-1]["hidden"]:return
        frame=self.stack[-1]
        for key in ("description","version"):
            if frame[key] is not None:frame[key].append(value)

    def result(self):
        """Ambiguous or unsupported markup is a failed check, never guessed."""
        return {"supported":self.supported(),
                "language":self.language(),
                "canonical":self.canonicals[0] if len(self.canonicals)==1 else None,"og":self.og,
                "version":self.version(),
                "description":normalize("".join(self.descriptions[0])) if len(self.descriptions)==1 else ""}

    def supported(self):
        """Require one closed, unambiguous description and identity."""
        return not self.ambiguous and not self.stack and len(self.descriptions)==1 and len(self.languages)==1 and len(self.canonicals)==1 and len(self.og)<=1

    def language(self):
        """Persist only a bounded language token."""
        if len(self.languages)!=1:return None
        return self.languages[0] if re.fullmatch(r"[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8}){0,3}",self.languages[0]) else None

    def version(self):
        """Persist only a bounded current release token."""
        if len(self.versions)!=1:return None
        value=normalize("".join(self.versions[0]))
        match=re.search(r"(?:^|\s)(\d+(?:\.\d+){0,4}(?:[-+][a-zA-Z0-9.]+)?)$",value)
        return match[1] if match and len(match[1])<=100 else None


def contains_copy(description, expected):
    """Case/punctuation and word boundaries remain significant."""
    expected=normalize(expected or "")
    if not expected:return False
    left=r"(?<!\w)" if expected[0].isalnum() else ""
    right=r"(?!\w)" if expected[-1].isalnum() else ""
    return bool(re.search(left+re.escape(expected)+right,description))


def inspect(resource, expected):
    """Return only sanitized predicates and closed reasons, not page text."""
    report={"resource":evidence(resource),"status":"NOT_OBSERVED","language":None,"version":None,"checks":{},"reasons":[]}
    if resource["status"]!=200:
        report["reasons"]=["HTTP_UNAVAILABLE"];return report
    if not any(v.split(";")[0].strip().lower()=="text/html" for v in resource["headers"].get("content-type",[])):
        report["reasons"]=["CONTENT_TYPE_UNSUPPORTED"];return report
    parser=ListingHTML();parser.feed(text(resource));parser.close();page=parser.result()
    report.update(language=page["language"],version=page["version"])
    checks={"markup":page["supported"],"identity":all(destination(u,expected["country"],expected["store_app_id"]) for u in [resource["url"],page["canonical"],*page["og"]]),
            "language":page["language"] is not None and page["language"].lower()==expected["locale"].lower(),
            "version":page["version"]==expected["release"],"copy":contains_copy(page["description"],expected["copy"])}
    report["checks"]=checks
    reasons={"markup":"MARKUP_UNSUPPORTED","identity":"IDENTITY_MISMATCH","language":"LANGUAGE_MISMATCH","version":"VERSION_MISMATCH","copy":"COPY_NOT_OBSERVED"}
    report["reasons"]=[reasons[k] for k,v in checks.items() if not v]
    if all(checks.values()):report["status"]="SERVER_RENDERED_COPY_OBSERVED"
    return report
