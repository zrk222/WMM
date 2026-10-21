"""Public metadata produces review candidates, never verified product or account identity."""
from html.parser import HTMLParser
import re
from urllib.parse import parse_qs, urlsplit
from .common import Invalid
from .aeo_transport import public_url
from .play_contract import PACKAGE

MAX_BYTES = 1048576
MAX_LINKS = 512
MAX_CANDIDATES = 8
MAX_TEXT = 600
FIELDS = ('name', 'job', 'audience', 'locale', 'store_app_id', 'android_package')
INERT = ('script', 'style', 'template', 'noscript')


def apple_link(parsed):
    """Retain a canonical identifier URL, excluding tracking and other query values."""
    match = re.fullmatch(r'/(?:[a-z]{2}(?:-[a-z]{2})?/)?app/(?:[^/]+/)?id([1-9][0-9]{0,19})/?', parsed.path)
    if match:
        return 'store_app_id', match[1], 'https://apps.apple.com/app/id' + match[1]
    return None


def google_link(parsed):
    """A duplicate package query is ambiguous even when its values happen to match."""
    if parsed.path != '/store/apps/details':
        return None
    query = parse_qs(parsed.query, keep_blank_values=True, max_num_fields=20)
    ids = query.get('id', [])
    if len(ids) == 1 and len(ids[0]) <= 255 and re.fullmatch(PACKAGE, ids[0]):
        return 'android_package', ids[0], 'https://play.google.com/store/apps/details?id=' + ids[0]
    return None


def official_link(value):
    """Recognize exact official HTTPS hosts without following links or granting authority."""
    try:
        parsed = urlsplit(value)
        if parsed.scheme != 'https' or parsed.username is not None or parsed.password is not None or parsed.port not in (None, 443):
            return None
        readers = {'apps.apple.com': apple_link, 'play.google.com': google_link}
        reader = readers.get(parsed.hostname)
        return reader(parsed) if reader else None
    except (ValueError, TypeError):
        return None


class Candidates(HTMLParser):
    """Extract finite declarations; scripts and narrative are never executable instructions."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.fields = {key: [] for key in FIELDS}
        self.limited = set()
        self.links = 0
        self.title = None
        self.titles = []
        self.inert = []

    def add(self, field, value, basis, reference=None):
        """Deduplicate exact values and explicitly disclose incomplete projection."""
        value = ' '.join(value.split())
        if not value:
            return
        if len(value) > MAX_TEXT:
            self.limited.add(field)
        value = value[:MAX_TEXT]
        rows = self.fields[field]
        if any(row['value'] == value for row in rows):
            return
        if len(rows) >= MAX_CANDIDATES:
            self.limited.add(field)
            return
        rows.append(dict(value=value, basis=basis, reference=reference, label='PUBLIC_METADATA_UNVERIFIED'))

    def handle_starttag(self, tag, attrs):
        """Duplicate attributes have no chosen browser-dependent interpretation."""
        if tag in INERT:
            self.inert.append(tag)
            return
        if self.inert:
            return
        self.visible_tag(tag, attrs)

    def visible_tag(self, tag, attrs):
        """Project only attributes outside inert document subtrees."""
        keys = [key for key, _ in attrs]
        if len(set(keys)) != len(keys):
            return
        values = {key: value or '' for key, value in attrs}
        if tag == 'title':
            self.title = []
        if tag == 'html':
            self.language(values.get('lang', ''))
        if tag == 'meta':
            self.metadata(values)
        if tag in ('a', 'link') and values.get('href'):
            self.link(values['href'])

    def language(self, value):
        """Do not infer a country or an app-tested locale from the declared page language."""
        if re.fullmatch(r'[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*', value):
            self.add('locale', value, 'HTML_LANG')

    def metadata(self, values):
        """Read supported explicit metadata only; descriptions remain unverified claims."""
        key = (values.get('property') or values.get('name', '')).lower()
        value = values.get('content', '')
        fields = {'application-name': 'name', 'og:site_name': 'name', 'description': 'job', 'og:description': 'job', 'audience': 'audience'}
        if key in fields:
            self.add(fields[key], value, 'META:' + key)
        elif key == 'al:ios:app_store_id' and re.fullmatch(r'[1-9][0-9]{0,19}', value):
            self.add('store_app_id', value, 'META:' + key)
        elif key == 'al:android:package' and len(value) <= 255 and re.fullmatch(PACKAGE, value):
            self.add('android_package', value, 'META:' + key)

    def link(self, value):
        """Bound source inspection and retain canonical official IDs without tracking parameters."""
        self.links += 1
        if self.links > MAX_LINKS:
            return
        found = official_link(value)
        if found:
            self.add(found[0], found[1], 'OFFICIAL_STORE_LINK', found[2])

    def handle_data(self, data):
        """Title capture is bounded independently from the document byte limit."""
        if not self.inert and self.title is not None and sum(map(len, self.title)) <= MAX_TEXT:
            self.title.append(data[:MAX_TEXT + 1])

    def handle_endtag(self, tag):
        """Keep distinct fallback titles rather than silently choosing the first one."""
        if tag in self.inert:
            index = len(self.inert) - 1 - self.inert[::-1].index(tag)
            self.inert = self.inert[:index]
        if self.inert:
            return
        if tag == 'title' and self.title is not None:
            if len(self.titles) < MAX_CANDIDATES:
                self.titles.append(''.join(self.title))
            else:
                self.limited.add('name')
            self.title = None


def extract(html, source_url) -> dict:
    """Extract bounded explicit source metadata and exact official store identities without executing code."""
    if not isinstance(html, str):
        raise Invalid('Public setup metadata must be UTF-8 HTML text')
    try:
        size = len(html.encode('utf-8'))
    except UnicodeError:
        raise Invalid('Public setup metadata is not valid UTF-8') from None
    if size > MAX_BYTES:
        raise Invalid('Public setup metadata exceeds the one MiB source limit')
    source = public_url(source_url)
    parser = Candidates()
    parser.feed(html)
    parser.close()
    if not parser.fields['name']:
        for value in parser.titles:
            parser.add('name', value, 'HTML_TITLE_FALLBACK')
    return dict(source_url=source, fields=parser.fields,
                ambiguous_fields=[key for key, rows in parser.fields.items() if len(rows) > 1],
                limited_fields=sorted(parser.limited), links_inspected=min(parser.links, MAX_LINKS),
                link_limit_reached=parser.links > MAX_LINKS,
                missing_fields=[key for key in (*FIELDS, 'release', 'activation') if not parser.fields.get(key)],
                authority='NO_EXECUTION_AUTHORITY', visibility='RAW_HTML_NOT_RENDERED', approval_required=True,
                ownership='NOT_VERIFIED', product_claims='NOT_VERIFIED', journey_locale='NOT_TESTED', release='NOT_VERIFIED')
