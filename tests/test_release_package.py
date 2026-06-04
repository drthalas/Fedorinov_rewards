from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from zipfile import ZipFile
import json
import unittest

from scripts import build_release_package, publish_github_release


ROOT = Path(__file__).resolve().parents[1]


class ReleasePackageTests(unittest.TestCase):
    def test_build_release_package_creates_versioned_zip_and_manifest(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            dist = tmp / "dist"
            package_root = dist / "package"
            source_zip = dist / "FedorinovRewards_WebPreview_v0.1.zip"
            notes_path = tmp / "0.1.0.md"
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
                result = build_release_package.build_release_package("0.1.0")

            zip_path = Path(result["zip_path"])
            latest_path = Path(result["latest_json_path"])
            self.assertEqual(zip_path.name, "FedorinovRewards_WebPreview_v0.1.0.zip")
            self.assertTrue(zip_path.exists())
            self.assertTrue(latest_path.exists())

            manifest = json.loads(latest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["version"], "0.1.0")
            self.assertEqual(
                manifest["download_url"],
                "https://github.com/drthalas/Fedorinov_rewards/releases/download/v0.1.0/FedorinovRewards_WebPreview_v0.1.0.zip",
            )
            self.assertEqual(manifest["sha256"], build_release_package.sha256_file(zip_path))
            self.assertEqual(manifest["notes"], ["Человеческое описание"])
            manifest_text = latest_path.read_text(encoding="utf-8")
            self.assertNotIn("/Users/hermes", manifest_text)
            self.assertNotIn("database/", manifest_text)
            self.assertNotIn("Source/", manifest_text)
            self.assertNotIn("SourceMark/", manifest_text)

    def test_build_release_package_rejects_version_mismatch(self) -> None:
        with self.assertRaises(ValueError):
            build_release_package.build_release_package("9.9.9")

    def test_publish_dry_run_does_not_call_gh(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            zip_path = tmp / "FedorinovRewards_WebPreview_v0.1.0.zip"
            manifest_path = tmp / "latest.json"
            notes_path = tmp / "0.1.0.md"
            zip_path.write_bytes(b"zip")
            manifest_path.write_text("{}", encoding="utf-8")
            notes_path.write_text("# notes\n", encoding="utf-8")

            with patch.object(publish_github_release, "versioned_zip_path", return_value=zip_path), patch.object(
                publish_github_release, "latest_json_path", return_value=manifest_path
            ), patch.object(publish_github_release, "release_notes_path", return_value=notes_path), patch.object(
                publish_github_release, "_run_gh"
            ) as run_gh:
                code = publish_github_release.publish_release("0.1.0", dry_run=True)

            self.assertEqual(code, 0)
            run_gh.assert_not_called()

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
        self.assertIn("Input version", workflow)
        self.assertIn("APP_VERSION", workflow)


if __name__ == "__main__":
    unittest.main()
