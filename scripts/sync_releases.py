#!/usr/bin/env python3
"""Build local downloads from verified GitHub release assets, or a Google Play link."""
import argparse
import fnmatch
import hashlib
from html import escape
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from urllib.parse import parse_qs, quote, urlsplit
import zipfile
from public_content import release_notes

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_PATTERN = r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+'
ASSET_PATTERN = r'[A-Za-z0-9][A-Za-z0-9._+-]*'


def gh(*args):
    result = subprocess.run(['gh', *args], check=True, capture_output=True, text=True, timeout=300)
    return result.stdout


def read_config(path):
    config = json.loads(path.read_text())
    if config.get('mode') not in ('apk', 'play-store'):
        raise ValueError('distribution mode must be apk or play-store')
    if not re.fullmatch(REPOSITORY_PATTERN, config.get('github_repository', '')):
        raise ValueError('github_repository must be OWNER/REPO')
    if config['mode'] == 'play-store':
        url = urlsplit(config.get('play_store_url') or '')
        if (url.scheme != 'https' or url.netloc != 'play.google.com'
                or url.path != '/store/apps/details' or not parse_qs(url.query).get('id')):
            raise ValueError('play-store mode requires a real HTTPS Google Play app listing URL')
    return config


def select_channels(releases):
    """Use the publisher's prerelease flag, never guesses from the notes or tag."""
    channels = {}
    for release in releases:
        if release.get('draft') or not release.get('published_at'):
            continue
        channel = 'preview' if release['prerelease'] else 'stable'
        key = (datetime.fromisoformat(release['published_at'].replace('Z', '+00:00')), release['id'])
        previous = channels.get(channel)
        if previous is None or key > previous[0]:
            channels[channel] = (key, release)
    return {channel: entry[1] for channel, entry in channels.items()}


def list_releases(repository):
    releases = []
    for page in range(1, 101):
        batch = json.loads(gh('api', f'repos/{repository}/releases?per_page=100&page={page}'))
        if not isinstance(batch, list):
            raise ValueError('GitHub did not return a release list')
        releases.extend(batch)
        if len(batch) < 100:
            return releases
    raise ValueError('Release pagination limit reached; no download page was changed')


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def check_assets(directory, apk_asset, checksum_asset):
    for asset in (apk_asset, checksum_asset):
        path = directory / asset['name']
        if not path.is_file() or path.stat().st_size != asset['size']:
            raise ValueError(f'Asset missing or wrong size: {asset["name"]}')
        expected = asset.get('digest')
        if expected and expected != 'sha256:' + digest(path):
            raise ValueError(f'GitHub asset digest mismatch: {asset["name"]}')
    apk = directory / apk_asset['name']
    sums = (directory / checksum_asset['name']).read_text(encoding='utf-8-sig')
    matches = []
    for line in sums.splitlines():
        match = re.fullmatch(r'([a-fA-F0-9]{64})[ \t]+\*?(.+)', line.strip())
        if match and match[2] == apk.name:
            matches.append(match[1].lower())
    actual = digest(apk)
    if matches != [actual]:
        raise ValueError(f'APK does not match its published SHA256SUMS.txt: {apk.name}')
    with zipfile.ZipFile(apk) as archive:
        if 'AndroidManifest.xml' not in archive.namelist():
            raise ValueError(f'Asset is not an Android APK: {apk.name}')
    return actual


def fetch_release(repository, release, cache_root):
    tag = release['tag_name']
    if not isinstance(tag, str) or not tag or tag.startswith('-'):
        raise ValueError('Invalid release tag')
    assets = [a for a in release['assets'] if a.get('state', 'uploaded') == 'uploaded']
    apks = [a for a in assets if fnmatch.fnmatchcase(a['name'], 'TyrePing-*.apk')]
    sums = [a for a in assets if a['name'] == 'SHA256SUMS.txt']
    if len(apks) != 1 or len(sums) != 1:
        raise ValueError(f'{tag} needs exactly one TyrePing APK and SHA256SUMS.txt; refusing to silently use an older release')
    apk, checksum = apks[0], sums[0]
    for asset in (apk, checksum):
        if not re.fullmatch(ASSET_PATTERN, asset['name']):
            raise ValueError('Unsafe release asset filename')
        if not isinstance(asset['id'], int) or not isinstance(asset['size'], int) or asset['size'] <= 0:
            raise ValueError('Invalid release asset metadata')
    cache = cache_root / f'{release["id"]}-{apk["id"]}-{checksum["id"]}'
    try:
        sha = check_assets(cache, apk, checksum)
    except (OSError, ValueError, zipfile.BadZipFile):
        cache_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='fetch-', dir=cache_root) as temp:
            staging = Path(temp)
            gh('release', 'download', tag, '--repo', repository,
               '--pattern', apk['name'], '--pattern', checksum['name'], '--dir', str(staging))
            sha = check_assets(staging, apk, checksum)
            if cache.exists():
                shutil.rmtree(cache)
            shutil.copytree(staging, cache)
    return cache, apk, checksum, sha


def pretty_date(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00')).strftime('%d %B %Y')


def render_content(manifest):
    if manifest['mode'] == 'play-store':
        return f'''<div class="doc-heading"><span class="eyebrow">Get TyrePing</span><h1>Find TyrePing<br>on Google Play.</h1><p>Use Google Play to see current pricing, device compatibility and release information, and to purchase and install the app.</p></div><div class="store-download"><a class="button" href="{escape(manifest['play_store_url'], quote=True)}">Get TyrePing on Google Play →</a><p>Installation and updates are managed through Google Play.</p></div><section class="release-notes-section" id="release-notes"><h2>Release information</h2><p>Check the Google Play listing for the current version, requirements and release notes.</p></section>'''
    intro = '''<div class="doc-heading"><span class="eyebrow">Direct from TyrePing</span><h1>Choose your build.</h1><p>Download the latest stable release or try the latest pre-release. APKs and checksums are served here on tyreping.com.</p><p class="doc-meta">Release versions and notes below are synchronised from the app project. Read the notes for your chosen build before installing.</p></div>'''
    cards, notes = [], []
    for channel, label in (('stable', 'Latest stable release'), ('preview', 'Latest pre-release')):
        entry = manifest['channels'].get(channel)
        if entry is None:
            cards.append(f'<article class="release-download" id="{channel}"><span class="eyebrow">{label}</span><h2>Not currently available</h2><p>No published {"stable release" if channel == "stable" else "pre-release"} is available from the project.</p></article>')
            continue
        version, apk_url, sums_url = (escape(entry[key], quote=True) for key in ('version', 'apk_url', 'checksums_url'))
        date, size = pretty_date(entry['published_at']), f'{entry["size"] / (1024 * 1024):.1f} MB'
        channel_copy = ('The release published in the stable channel. See its notes for features and testing status.'
                        if channel == 'stable' else 'A testing build that may contain experimental changes. It can be older than the stable build; compare versions before installing.')
        cards.append(f'''<article class="release-download" id="{channel}"><span class="eyebrow">{label}</span><h2>{version}</h2><p class="release-published">Published <time datetime="{escape(entry['published_at'], quote=True)}">{date}</time> · {size}</p><p>{channel_copy}</p><a class="button" href="{apk_url}" download>Download {"stable" if channel == 'stable' else 'pre-release'} APK ↓</a><div class="release-download-links"><a href="{sums_url}" download>SHA-256 checksums</a><a href="#notes-{channel}">Release notes</a></div><p class="release-hash"><span>APK SHA-256</span><code>{entry['sha256']}</code></p></article>''')
        body = escape(entry['notes'] or 'No release notes were provided for this build.')
        notes.append(f'<section class="local-release-notes" id="notes-{channel}"><h3>{label}: {version}</h3><pre>{body}</pre></section>')
    return intro + '<div class="release-downloads">' + ''.join(cards) + f'''</div><p class="downloads-help">Need a hand? <a href="/install/">Read the manual install guide</a>. Use the checksum from the same build as your APK. Installing an older APK over a newer version may be blocked by Android.</p><section class="release-notes-section" id="release-notes" aria-labelledby="release-notes-title"><h2 id="release-notes-title">Release notes</h2>{''.join(notes)}</section>'''


def build(config, output, template, cache_root):
    manifest = {'mode': config['mode']}
    cached = []
    if config['mode'] == 'play-store':
        manifest['play_store_url'] = config['play_store_url']
    else:
        channels = select_channels(list_releases(config['github_repository']))
        if not channels:
            raise ValueError('No published releases found; existing downloads are unchanged')
        manifest['channels'] = {}
        for channel, release in channels.items():
            cache, apk, checksum, sha = fetch_release(config['github_repository'], release, cache_root)
            folder = f'{release["id"]}-{sha[:16]}'
            entry = {'version': release['tag_name'], 'published_at': release['published_at'],
                     'release_id': release['id'], 'size': apk['size'], 'sha256': sha,
                     'apk_url': f'/downloads/files/{folder}/{quote(apk["name"])}',
                     'checksums_url': f'/downloads/files/{folder}/SHA256SUMS.txt',
                     'notes': release_notes(release.get('body') or '')}
            manifest['channels'][channel] = entry
            cached.append((cache, folder))
    content = template.read_text()
    if content.count('<!-- DISTRIBUTION_CONTENT -->') != 1:
        raise ValueError('Downloads template must contain exactly one content marker')
    html = content.replace('<!-- DISTRIBUTION_CONTENT -->', render_content(manifest))
    # All network calls and verification finish before the current output is replaced.
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.downloads-build-', dir=output.parent) as temp:
        staged = Path(temp) / 'downloads'
        (staged / 'files').mkdir(parents=True)
        for cache, folder in cached:
            shutil.copytree(cache, staged / 'files' / folder)
        (staged / 'index.html').write_text(html)
        (staged / 'releases.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
        access = '''Options -Indexes
AddType application/vnd.android.package-archive .apk
<IfModule mod_headers.c>
  <FilesMatch "\\.apk$">
    Header set Content-Disposition "attachment"
    Header set Cache-Control "no-store"
    Header set X-Robots-Tag "noindex, nofollow"
  </FilesMatch>
  <FilesMatch "\\.json$">
    Header set Cache-Control "no-cache"
    Header set X-Robots-Tag "noindex, nofollow"
  </FilesMatch>
</IfModule>
'''
        if manifest['mode'] == 'play-store':
            access += 'RedirectMatch 410 ^/downloads/files/\n'
        (staged / '.htaccess').write_text(access)
        previous = Path(temp) / 'previous'
        try:
            if output.exists():
                output.rename(previous)
            staged.rename(output)
        except OSError:
            if previous.exists() and not output.exists():
                previous.rename(output)
            raise
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT / 'config/distribution.json')
    parser.add_argument('--output', type=Path, default=ROOT / 'public/downloads')
    parser.add_argument('--cache', type=Path, default=ROOT / '.cache/releases')
    args = parser.parse_args()
    config = read_config(args.config)
    manifest = build(config, args.output, ROOT / 'templates/downloads.html', args.cache)
    if manifest['mode'] == 'play-store':
        print('Built Google Play download page; public APK hosting is disabled.')
    else:
        for channel, release in manifest['channels'].items():
            print(f'Verified {channel}: {release["version"]} ({release["size"]:,} bytes)')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError, zipfile.BadZipFile) as error:
        print(f'Release sync failed; nothing was published: {error}', file=sys.stderr)
        sys.exit(1)
