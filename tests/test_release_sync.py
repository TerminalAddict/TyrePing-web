import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import sync_releases as sync
from public_content import GITHUB_URL, release_notes


class ReleaseSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def assets(self):
        directory = self.root / 'assets'
        directory.mkdir()
        apk = directory / 'TyrePing-test.apk'
        with zipfile.ZipFile(apk, 'w') as archive:
            archive.writestr('AndroidManifest.xml', b'test fixture')
        sha = sync.digest(apk)
        sums = directory / 'SHA256SUMS.txt'
        sums.write_text(f'{sha}  {apk.name}\n')
        metadata = [{'name': p.name, 'size': p.stat().st_size, 'id': i,
                     'digest': 'sha256:' + sync.digest(p)} for i, p in enumerate((apk, sums), 1)]
        return directory, metadata, sha

    def test_channels_use_publication_date_and_flag_not_input_order_or_body(self):
        releases = [
            {'id': 1, 'published_at': '2026-01-01T00:00:00Z', 'prerelease': False},
            {'id': 2, 'published_at': '2026-01-02T00:00:00Z', 'prerelease': True},
            {'id': 3, 'published_at': '2026-01-03T00:00:00Z', 'prerelease': False, 'body': 'This pre-release...'},
            {'id': 4, 'published_at': '2026-01-04T00:00:00Z', 'prerelease': True, 'draft': True},
            {'id': 5, 'published_at': None, 'prerelease': True},
        ]
        channels = sync.select_channels(list(reversed(releases)))
        self.assertEqual(channels['stable']['id'], 3)
        self.assertEqual(channels['preview']['id'], 2)

    def test_matching_apk_and_checksum_are_accepted(self):
        directory, assets, sha = self.assets()
        self.assertEqual(sync.check_assets(directory, *assets), sha)

    def test_wrong_published_checksum_is_rejected_without_api_digests(self):
        directory, assets, _ = self.assets()
        for asset in assets:
            asset.pop('digest')
        (directory / 'SHA256SUMS.txt').write_text('0' * 64 + '  TyrePing-test.apk\n')
        with self.assertRaisesRegex(ValueError, 'published SHA256SUMS'):
            sync.check_assets(directory, *assets)

    def test_tampered_cached_apk_is_rejected(self):
        directory, assets, _ = self.assets()
        apk = directory / assets[0]['name']
        data = bytearray(apk.read_bytes())
        data[-1] ^= 1
        apk.write_bytes(data)
        with self.assertRaisesRegex(ValueError, 'digest mismatch'):
            sync.check_assets(directory, *assets)

    def test_verified_cache_does_not_redownload(self):
        directory, assets, sha = self.assets()
        cache = self.root / 'cache'
        cache.mkdir()
        directory.rename(cache / '42-1-2')
        release = {'id': 42, 'tag_name': 'test', 'assets': assets}
        with patch.object(sync, 'gh', side_effect=AssertionError('Network call')):
            self.assertEqual(sync.fetch_release('owner/repo', release, cache)[3], sha)

    def test_incomplete_newest_release_is_not_silently_replaced(self):
        with self.assertRaisesRegex(ValueError, 'exactly one'):
            sync.fetch_release('owner/repo', {'id': 1, 'tag_name': 'test', 'assets': []}, self.root)

    def test_missing_preview_channel_has_an_honest_unavailable_state(self):
        content = sync.render_content({'mode': 'apk', 'channels': {}})
        self.assertIn('No published pre-release', content)
        self.assertNotIn('download>Download', content)

    def test_play_mode_has_no_apks_and_does_not_use_github(self):
        output = self.root / 'downloads'
        (output/'files').mkdir(parents=True)
        (output/'files/previously-hosted.apk').write_bytes(b'old mirrored APK')
        (output/'index.html').write_text('Previous APK download page')
        config = {'mode': 'play-store', 'play_store_url': 'https://play.google.com/store/apps/details?id=nz.paulwillard.tyreping'}
        with patch.object(sync, 'gh', side_effect=AssertionError('Network call')):
            manifest = sync.build(config, output, sync.ROOT/'templates/downloads.html', self.root/'cache')
        self.assertEqual(manifest['mode'], 'play-store')
        self.assertEqual(list((output/'files').iterdir()), [])
        self.assertIn('Google Play', (output/'index.html').read_text())
        self.assertIn('RedirectMatch 410', (output/'.htaccess').read_text())
        self.assertNotIn('.apk', (output/'index.html').read_text())

    def test_invalid_store_url_is_rejected(self):
        path = self.root / 'config.json'
        path.write_text(json.dumps({'mode': 'play-store', 'github_repository': 'owner/repo', 'play_store_url': 'https://example.com/app'}))
        with self.assertRaisesRegex(ValueError, 'Google Play'):
            sync.read_config(path)

    def test_failed_fetch_preserves_existing_downloads(self):
        output = self.root / 'downloads'
        output.mkdir()
        (output/'index.html').write_text('previous page')
        release = {'id': 1, 'tag_name': 'test', 'published_at': '2026-01-01T00:00:00Z', 'prerelease': False}
        with patch.object(sync, 'list_releases', return_value=[release]), patch.object(sync, 'fetch_release', side_effect=ValueError('Bad checksum')):
            with self.assertRaisesRegex(ValueError, 'Bad checksum'):
                sync.build({'mode': 'apk', 'github_repository': 'owner/repo'}, output, sync.ROOT/'templates/downloads.html', self.root/'cache')
        self.assertEqual((output/'index.html').read_text(), 'previous page')

    def test_release_notes_are_escaped_and_downloads_stay_local(self):
        content = sync.render_content({'mode': 'apk', 'channels': {'stable': {
            'version': 'test', 'published_at': '2026-01-01T00:00:00Z', 'size': 123,
            'apk_url': '/downloads/files/test/app.apk', 'checksums_url': '/downloads/files/test/SHA256SUMS.txt',
            'sha256': 'a'*64, 'notes': '<script>alert(1)</script>',
        }}})
        self.assertIn('&lt;script&gt;', content)
        self.assertNotIn('<script>', content)
        self.assertNotIn('href="https://github.com', content)

    def test_public_notes_preserve_labels_without_repository_urls(self):
        original = '''Fixed [sensor discovery](https://github.com/owner/repo/pull/42).
Credits: [Contributor](https://GitHub.com/contributor "Profile").
Compare: <https://github.com/owner/repo/compare/a...b>
Assets: //raw.githubusercontent.com/owner/repo/main/image.png
Docs: https://owner.github.io/docs/
Store: [Google Play](https://play.google.com/store/apps/details?id=test)
Plain credit: Vincent Masselis and aveshev.'''
        result = release_notes(original)
        self.assertIn('Fixed sensor discovery.', result)
        self.assertIn('Credits: Contributor.', result)
        self.assertIn('Plain credit: Vincent Masselis and aveshev.', result)
        self.assertIn('https://play.google.com/store/apps/details?id=test', result)
        self.assertNotRegex(result, GITHUB_URL)
        self.assertEqual(release_notes(result), result)

    def test_build_sanitises_notes_in_both_html_and_public_manifest(self):
        directory, assets, sha = self.assets()
        release = {'id': 42, 'tag_name': 'test', 'published_at': '2026-01-01T00:00:00Z',
                   'prerelease': False, 'body': 'Thanks [aveshev](https://github.com/aveshev).'}
        output = self.root / 'downloads'
        with patch.object(sync, 'list_releases', return_value=[release]), patch.object(
                sync, 'fetch_release', return_value=(directory, *assets, sha)):
            manifest = sync.build({'mode': 'apk', 'github_repository': 'owner/repo'},
                                  output, sync.ROOT/'templates/downloads.html', self.root/'cache')
        self.assertEqual(manifest['channels']['stable']['notes'], 'Thanks aveshev.')
        for name in ('index.html', 'releases.json'):
            self.assertNotRegex((output/name).read_text(), GITHUB_URL)
        self.assertEqual(sync.digest(next((output/'files').rglob('*.apk'))), sha)


if __name__ == '__main__':
    unittest.main()
