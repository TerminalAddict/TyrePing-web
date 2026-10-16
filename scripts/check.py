#!/usr/bin/env python3
"""Check static routes, anchors, assets, JSON-LD and search metadata before upload."""
import hashlib
import json
import re
import struct
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1] / 'public'
ORIGIN = 'https://www.tyreping.com'
errors = []


class Page(HTMLParser):
    def __init__(self, path):
        super().__init__(convert_charrefs=True)
        self.path, self.ids, self.refs, self.meta = path, set(), [], {}
        self.canonical, self.h1, self.title = [], 0, ''
        self.in_title = False
        self.in_json = False
        self.json_text = ''
        self.structured = []
        self.feed(path.read_text())

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs:
            if attrs['id'] in self.ids:
                errors.append(f'{self.path.name}: duplicate id {attrs["id"]}')
            self.ids.add(attrs['id'])
        for key in ('src', 'href'):
            if attrs.get(key):
                self.refs.append(attrs[key])
        if attrs.get('srcset'):
            self.refs.extend(item.strip().split()[0] for item in attrs['srcset'].split(','))
        if tag == 'meta':
            self.meta[attrs.get('name', attrs.get('property', ''))] = attrs.get('content', '')
        if tag == 'link' and attrs.get('rel') == 'canonical':
            self.canonical.append(attrs.get('href'))
        if tag == 'h1':
            self.h1 += 1
        if tag == 'title':
            self.in_title = True
        if tag == 'script' and attrs.get('type') == 'application/ld+json':
            self.in_json = True
            self.json_text = ''
        if tag == 'img' and not all(key in attrs for key in ('alt', 'width', 'height')):
            errors.append(f'{self.path.name}: image missing alt/dimensions')
        if tag == 'img' and not (attrs.get('src') or attrs.get('srcset')):
            errors.append(f'{self.path.name}: image missing src/srcset')
        if 'style' in attrs or any(key.startswith('on') for key in attrs):
            errors.append(f'{self.path.name}: inline code conflicts with CSP')

    def handle_data(self, data):
        if self.in_title:
            self.title += data
        if self.in_json:
            self.json_text += data

    def handle_endtag(self, tag):
        if tag == 'title':
            self.in_title = False
        if tag == 'script' and self.in_json:
            try:
                self.structured.append(json.loads(self.json_text))
            except json.JSONDecodeError as err:
                errors.append(f'{self.path.name}: invalid JSON-LD: {err}')
            self.in_json = False


def route(path):
    target = ROOT / unquote(path).lstrip('/')
    return target / 'index.html' if target.is_dir() else target


pages = {path: Page(path) for path in ROOT.rglob('*.html')}
for path, page in pages.items():
    relative = path.relative_to(ROOT).as_posix()
    urlpath = '/' + relative.removesuffix('index.html')
    expected = ORIGIN + urlpath
    if page.canonical != [expected]:
        errors.append(f'{relative}: canonical should be {expected}')
    if not page.title or page.h1 != 1 or not page.structured:
        errors.append(f'{relative}: missing title/JSON-LD or not exactly one h1')
    for key in ('description', 'robots', 'og:title', 'og:description', 'og:image', 'og:url', 'twitter:card', 'twitter:image'):
        if not page.meta.get(key):
            errors.append(f'{relative}: missing {key}')
    for ref in page.refs:
        url = urlsplit(ref)
        if url.scheme or url.netloc:
            continue
        if url.path.startswith('/'):
            target = route(url.path)
        elif url.path:
            target = path.parent / unquote(url.path)
        else:
            target = path
        if not target.exists():
            errors.append(f'{relative}: broken reference {ref}')
        elif url.fragment:
            if target in pages and url.fragment not in pages[target].ids:
                errors.append(f'{relative}: missing anchor {ref}')
            elif target.suffix == '.svg':
                ids = {element.get('id') for element in ET.parse(target).iter()}
                if url.fragment not in ids:
                    errors.append(f'{relative}: missing SVG symbol {ref}')

for stylesheet in (ROOT/'assets').glob('*.css'):
    for ref in re.findall(r'url\([\'"]?([^\)\'\"]+)', stylesheet.read_text()):
        if not route(ref).is_file():
            errors.append(f'CSS asset missing: {ref}')

manifest = json.loads((ROOT/'site.webmanifest').read_text())
for item in manifest['icons']:
    path = route(item['src'])
    if not path.is_file():
        errors.append(f'Manifest icon missing: {item["src"]}')
        continue
    width, height = struct.unpack('>II', path.read_bytes()[16:24])
    if item['sizes'] != f'{width}x{height}':
        errors.append(f'Manifest icon dimensions incorrect: {item["src"]}')
social = ROOT/'assets/images/social-card.png'
if struct.unpack('>II', social.read_bytes()[16:24]) != (1200, 630):
    errors.append('Social card must be 1200x630')

ns = {'s': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
sitemap = {node.text for node in ET.parse(ROOT/'sitemap.xml').findall('.//s:loc', ns)}
expected = {p.canonical[0] for p in pages.values() if 'noindex' not in p.meta.get('robots', '')}
if sitemap != expected:
    errors.append(f'Sitemap differs from indexable canonical pages: {sitemap ^ expected}')
if f'Sitemap: {ORIGIN}/sitemap.xml' not in (ROOT/'robots.txt').read_text():
    errors.append('robots.txt missing sitemap')
app = next(n for n in pages[ROOT/'index.html'].structured[0]['@graph'] if n['@type'] == 'SoftwareApplication')
if app['downloadUrl'].replace(ORIGIN, '') not in pages[ROOT/'install/index.html'].refs:
    errors.append('Application JSON-LD download differs from install page')
release_url = ORIGIN + '/downloads/'
if app.get('softwareVersion'):
    errors.append('Do not pin softwareVersion in static marketing metadata; generated downloads own version information')
if app['downloadUrl'] != release_url or app.get('releaseNotes') != release_url:
    errors.append('Application metadata must link to the local downloads page')
for relative in ('index.html', 'install/index.html'):
    page = pages[ROOT/relative]
    if '/downloads/' not in page.refs:
        errors.append(f'{relative}: missing local downloads link')
    if re.search(r'(?<![\w.])v?\d+\.\d+\.\d+(?![\w.])', page.path.read_text()):
        errors.append(f'{relative}: hard-coded app version; keep product copy version-independent')
    for ref in page.refs:
        if ref.startswith('https://github.com/TerminalAddict/TyrePing/releases'):
            errors.append(f'{relative}: release/download link must stay on tyreping.com: {ref}')

distribution = json.loads((ROOT.parent/'config/distribution.json').read_text())
release_manifest = ROOT/'downloads/releases.json'
if not release_manifest.is_file():
    errors.append('Build downloads first: python3 scripts/sync_releases.py')
else:
    downloads = json.loads(release_manifest.read_text())
    if downloads['mode'] != distribution['mode']:
        errors.append('Downloads mode differs from distribution.json; rebuild downloads')
    if downloads['mode'] == 'play-store':
        if list((ROOT/'downloads/files').rglob('*.apk')):
            errors.append('Google Play mode must not publish APK files')
        if downloads.get('play_store_url') != distribution.get('play_store_url'):
            errors.append('Google Play URL differs from distribution.json')
    else:
        for channel, release in downloads['channels'].items():
            apk = route(release['apk_url'])
            if not apk.is_file() or apk.stat().st_size != release['size']:
                errors.append(f'{channel}: downloaded APK missing or wrong size')
            else:
                with apk.open('rb') as stream:
                    if hashlib.file_digest(stream, 'sha256').hexdigest() != release['sha256']:
                        errors.append(f'{channel}: downloaded APK checksum mismatch')
            if not route(release['checksums_url']).is_file():
                errors.append(f'{channel}: matching checksums missing')
for screenshot in app.get('screenshot', []):
    url = urlsplit(screenshot['contentUrl'])
    if f'{url.scheme}://{url.netloc}' != ORIGIN or not route(url.path).is_file():
        errors.append(f'Application screenshot missing: {screenshot["contentUrl"]}')
    if url.path not in pages[ROOT/'index.html'].refs:
        errors.append(f'Application screenshot is absent from page: {url.path}')

if errors:
    print('\n'.join(errors), file=sys.stderr)
    sys.exit(1)
print(f'PASS: {len(pages)} pages; routes, anchors, metadata, JSON-LD, sitemap, icons and assets checked.')
