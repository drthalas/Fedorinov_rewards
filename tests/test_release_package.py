from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from zipfile import ZipFile
import base64
import json
import re
import unittest

from backend.app.services.update_archive_policy import SYSTEM_UI_ASSET_PATHS, forbidden_relative_reason
from scripts import (
    build_recovery_package,
    build_release_package,
    build_windows_preview_package,
    check_package_safety,
    publish_github_release,
)
from backend.app.version import APP_VERSION


ROOT = Path(__file__).resolve().parents[1]


class ReleasePackageTests(unittest.TestCase):
    def test_transition_assets_use_only_paths_present_in_public_v207_package(self) -> None:
        with TemporaryDirectory() as tmp:
            package_root = Path(tmp) / "package"
            with patch.object(build_windows_preview_package, "PACKAGE_ROOT", package_root):
                build_windows_preview_package._copy_required_files()
                build_windows_preview_package._bundle_legacy_updater_compatible_transition_assets()

            for relative in build_windows_preview_package.TRANSITION_ASSET_PATHS:
                self.assertFalse((package_root / relative).exists(), relative)
            bundled = (package_root / "backend/app/static/escape_back.js").read_text(encoding="utf-8")
            self.assertIn("window.FedorinovWriteFeedback", bundled)
            self.assertIn("window.FedorinovTransitionLifecycle", bundled)
            for name in ("base.html", "legacy_base.html"):
                template = (package_root / "backend/app/templates" / name).read_text(encoding="utf-8")
                self.assertIn("data-document-transition-curtain", template)
                self.assertIn("document-transition:ready", template)
                self.assertNotIn("document_transition.js", template)
                self.assertNotIn("transition_lifecycle.js", template)
                self.assertNotIn("write_feedback.js", template)
            booklet = (package_root / "backend/app/templates/person_booklet.html").read_text(encoding="utf-8")
            self.assertIn("escape_back.js", booklet)
            self.assertNotIn("transition_lifecycle.js", booklet)
            self.assertNotIn("write_feedback.js", booklet)

    def test_visual_assets_are_embedded_for_legacy_updater_compatibility(self) -> None:
        for parts in SYSTEM_UI_ASSET_PATHS:
            relative = Path(*parts)
            self.assertTrue(build_windows_preview_package._is_excluded(ROOT / relative))
            self.assertIsNone(forbidden_relative_reason(relative))

        self.assertTrue(build_windows_preview_package._is_excluded(ROOT / "Source" / "77" / "photo.jpg"))
        self.assertIsNotNone(
            check_package_safety._is_forbidden("FedorinovRewards_WebPreview/Source/77/photo.jpg")
        )

    def test_packaged_css_contains_all_visual_assets_as_data_uris(self) -> None:
        with TemporaryDirectory() as tmpdir:
            package_root = Path(tmpdir) / "FedorinovRewards_WebPreview"
            styles_path = package_root / "backend/app/static/styles.css"
            styles_path.parent.mkdir(parents=True)
            styles_path.write_text((ROOT / "backend/app/static/styles.css").read_text(encoding="utf-8"), encoding="utf-8")

            with patch.object(build_windows_preview_package, "PACKAGE_ROOT", package_root):
                build_windows_preview_package._embed_ui_assets()

            packaged = styles_path.read_text(encoding="utf-8")
            for parts in SYSTEM_UI_ASSET_PATHS:
                relative = Path(*parts)
                self.assertNotIn(build_windows_preview_package._asset_web_path(relative), packaged)
                variable = build_windows_preview_package._asset_variable(relative)
                match = re.search(rf"{re.escape(variable)}: url\(\"data:[^;]+;base64,([^\"]+)\"\)", packaged)
                self.assertIsNotNone(match)
                self.assertEqual(base64.b64decode(match.group(1)), (ROOT / relative).read_bytes())
            self.assertEqual(packaged.count(";base64,"), len(SYSTEM_UI_ASSET_PATHS))

    def test_build_release_package_creates_versioned_zip_and_manifest(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            dist = tmp / "dist"
            package_root = dist / "package"
            source_zip = dist / "FedorinovRewards_WebPreview_v0.1.zip"
            notes_path = tmp / f"{APP_VERSION}.md"
            notes_path.write_text("- Человеческое описание\n", encoding="utf-8")

            def fake_build() -> int:
                package_root.mkdir(parents=True)
                with ZipFile(source_zip, "w") as archive:
                    archive.writestr("FedorinovRewards_WebPreview/README.md", "ok")
                return 0

            with patch.object(build_release_package, "DIST_ROOT", dist), patch.object(
                build_release_package.build_windows_preview_package, "ZIP_PATH", source_zip
            ), patch.object(build_release_package, "release_notes_path", return_value=notes_path), patch.object(
                build_release_package.build_windows_preview_package, "main", side_effect=fake_build
            ):
                result = build_release_package.build_release_package(APP_VERSION)

            zip_path = Path(result["zip_path"])
            latest_path = Path(result["latest_json_path"])
            self.assertEqual(zip_path.name, f"FedorinovRewards_WebPreview_v{APP_VERSION}.zip")
            self.assertTrue(zip_path.exists())
            self.assertTrue(latest_path.exists())

            manifest = json.loads(latest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["version"], APP_VERSION)
            self.assertEqual(
                manifest["download_url"],
                f"https://github.com/drthalas/Fedorinov_rewards/releases/download/v{APP_VERSION}/FedorinovRewards_WebPreview_v{APP_VERSION}.zip",
            )
            self.assertEqual(manifest["sha256"], build_release_package.sha256_file(zip_path))
            self.assertEqual(manifest["notes"], ["Человеческое описание"])
            manifest_text = latest_path.read_text(encoding="utf-8")
            self.assertNotIn("/Users/hermes", manifest_text)
            self.assertNotIn("database/", manifest_text)
            self.assertNotIn("Source/", manifest_text)
            self.assertNotIn("SourceMark/", manifest_text)

    def test_release_notes_012_include_owner_visible_items(self) -> None:
        notes = (ROOT / "release_notes" / "0.1.2.md").read_text(encoding="utf-8")
        for expected in ["шахмат", "CSV", "Открыть каталог", "Архивировать", "фотограф", "PDF-буклет", "рабочий режим"]:
            self.assertIn(expected, notes)

    def test_build_release_package_rejects_version_mismatch(self) -> None:
        with self.assertRaises(ValueError):
            build_release_package.build_release_package("9.9.9")

    def test_publish_dry_run_does_not_call_gh(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            zip_path = tmp / f"FedorinovRewards_WebPreview_v{APP_VERSION}.zip"
            manifest_path = tmp / "latest.json"
            recovery_path = tmp / f"FedorinovRewards_Recovery_v{APP_VERSION}.zip"
            notes_path = tmp / f"{APP_VERSION}.md"
            zip_path.write_bytes(b"zip")
            recovery_path.write_bytes(b"recovery")
            manifest_path.write_text("{}", encoding="utf-8")
            notes_path.write_text("# notes\n", encoding="utf-8")

            with patch.object(publish_github_release, "versioned_zip_path", return_value=zip_path), patch.object(
                publish_github_release, "latest_json_path", return_value=manifest_path
            ), patch.object(
                publish_github_release, "recovery_zip_path", return_value=recovery_path
            ), patch.object(publish_github_release, "release_notes_path", return_value=notes_path), patch.object(
                publish_github_release, "_run_gh"
            ) as run_gh:
                code = publish_github_release.publish_release(APP_VERSION, dry_run=True)

            self.assertEqual(code, 0)
            run_gh.assert_not_called()

    def test_v206_publication_requires_main_recovery_and_manifest_assets(self) -> None:
        assets = publish_github_release.release_assets("2.0.6")
        self.assertEqual(
            [path.name for path in assets],
            [
                "FedorinovRewards_WebPreview_v2.0.6.zip",
                "FedorinovRewards_Recovery_v2.0.6.zip",
                "latest.json",
            ],
        )

    def test_v207_corrective_publication_requires_recovery_asset(self) -> None:
        assets = publish_github_release.release_assets("2.0.7")
        self.assertEqual(
            [path.name for path in assets],
            [
                "FedorinovRewards_WebPreview_v2.0.7.zip",
                "FedorinovRewards_Recovery_v2.0.7.zip",
                "latest.json",
            ],
        )

    def test_future_publication_does_not_require_recovery_asset_by_default(self) -> None:
        assets = publish_github_release.release_assets("2.0.8")
        self.assertEqual(
            [path.name for path in assets],
            ["FedorinovRewards_WebPreview_v2.0.8.zip", "latest.json"],
        )

    def test_manual_release_workflow_is_manual_and_safe_by_default(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "manual_release.yml").read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", workflow)
        self.assertNotIn("\n  push:", workflow)
        self.assertIn("contents: write", workflow)
        self.assertIn('default: "false"', workflow)
        self.assertIn("publish != 'true'", workflow)
        self.assertIn("publish == 'true'", workflow)
        self.assertIn("actions/upload-artifact", workflow)
        self.assertIn("gh release create", workflow)
        self.assertIn("build_recovery_package.py", workflow)
        self.assertIn("check_recovery_package_safety.py", workflow)
        self.assertIn("FedorinovRewards_Recovery_v", workflow)
        self.assertIn("Input version", workflow)
        self.assertIn("APP_VERSION", workflow)


if __name__ == "__main__":
    unittest.main()
