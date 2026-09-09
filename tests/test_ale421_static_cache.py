from hashlib import sha256
import os
from pathlib import Path
import re
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from backend.app.routers import templates
from scripts import build_windows_preview_package as packager


class StaticCacheTests(unittest.TestCase):
    def tearDown(self):
        templates.static_asset_digest.cache_clear()

    def test_same_path_version_size_and_timestamp_cannot_reuse_previous_build_url(self):
        with TemporaryDirectory() as tmp, patch.object(templates, 'PROJECT_ROOT', Path(tmp)):
            asset = Path(tmp) / 'backend/app/static/legacy_rewards.js'
            asset.parent.mkdir(parents=True)
            asset.write_bytes(b'old script')
            stamp = asset.stat()
            old_url = templates.static_url('legacy_rewards.js')
            self.assertEqual(templates.static_url('legacy_rewards.js'), old_url)
            self.assertEqual(templates.static_asset_digest.cache_info().misses, 1)
            asset.write_bytes(b'new script')
            os.utime(asset, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
            templates.static_asset_digest.cache_clear()  # Normal runtime restart.
            new_url = templates.static_url('legacy_rewards.js')
            self.assertNotEqual(old_url, new_url)
            self.assertEqual(urlsplit(old_url).path, urlsplit(new_url).path)
            query = parse_qs(urlsplit(new_url).query)
            self.assertEqual(query['sha'], [sha256(b'new script').hexdigest()])
            self.assertEqual(query['v'], [templates.STATIC_ASSET_VERSION])
            templates.static_asset_digest.cache_clear()
            self.assertEqual(templates.static_url('legacy_rewards.js'), new_url)

    def test_static_url_matches_actual_file_and_never_uses_the_old_version_only_key(self):
        path = templates.PROJECT_ROOT / 'backend/app/static/legacy_rewards.js'
        url = templates.static_url('legacy_rewards.js')
        self.assertEqual(parse_qs(urlsplit(url).query)['sha'], [sha256(path.read_bytes()).hexdigest()])
        self.assertIn(b'searchValue: inputValue', path.read_bytes())
        self.assertNotIn(b'searchValue: cleanQuery', path.read_bytes())

    def test_packaged_transformed_assets_are_fingerprinted_after_packaging(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / 'package'
            with patch.object(packager, 'PACKAGE_ROOT', root):
                packager._copy_required_files()
                packager._embed_ui_assets()
                packager._embed_booklet_paper()
                packager._bundle_legacy_updater_compatible_transition_assets()
            with patch.object(templates, 'PROJECT_ROOT', root):
                for name in ('base.html', 'legacy_base.html', 'person_booklet.html', 'person_booklet2.html'):
                    source = (root / 'backend/app/templates' / name).read_text(encoding='utf-8')
                    for asset in re.findall(r"static_url\('([^']+)'\)", source):
                        url = templates.static_url(asset)
                        actual = (root / 'backend/app/static' / asset).read_bytes()
                        self.assertEqual(parse_qs(urlsplit(url).query)['sha'], [sha256(actual).hexdigest()], asset)
                self.assertNotEqual(
                    parse_qs(urlsplit(templates.static_url('styles.css')).query)['sha'],
                    [sha256((packager.PROJECT_ROOT / 'backend/app/static/styles.css').read_bytes()).hexdigest()],
                )

    def test_no_escape_from_static_directory_or_silent_missing_asset_fallback(self):
        with self.assertRaises(ValueError):
            templates.static_url('../version.py')
        with self.assertRaises(FileNotFoundError):
            templates.static_url('missing-ale421.js')


if __name__ == '__main__':
    unittest.main()
