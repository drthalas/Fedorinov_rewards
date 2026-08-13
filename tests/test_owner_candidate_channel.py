from __future__ import annotations

from functools import partial
import hashlib
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock
from urllib.request import urlopen
import zipfile

from scripts import owner_candidate_channel_server
from scripts import prepare_owner_candidate_channel


class OwnerCandidateChannelTests(unittest.TestCase):
    def _candidate(self, root: Path) -> tuple[Path, Path, str]:
        artifact = root / "FedorinovRewards_WebPreview_v2.0.13.zip"
        with zipfile.ZipFile(artifact, "w") as archive:
            archive.writestr(
                "FedorinovRewards_WebPreview/backend/app/version.py",
                'APP_VERSION = "2.0.13"\n',
            )
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        manifest = root / "latest.json"
        manifest.write_text(
            json.dumps(
                {
                    "version": "2.0.13",
                    "download_url": "https://example.test/v2.0.13.zip",
                    "sha256": digest,
                    "notes": ["Candidate"],
                }
            ),
            encoding="utf-8",
        )
        return artifact, manifest, digest

    def test_candidate_validation_keeps_channels_separate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact, manifest, digest = self._candidate(Path(temp_dir))
            with mock.patch.object(
                prepare_owner_candidate_channel,
                "git",
                side_effect=["", 'APP_VERSION = "2.0.13"'],
            ):
                owner_manifest, evidence = prepare_owner_candidate_channel.validate_candidate(
                    artifact=artifact,
                    manifest_path=manifest,
                    expected_commit="a" * 40,
                    expected_version="2.0.13",
                    expected_sha256=digest,
                    expected_public_version="2.0.12",
                    production_manifest={"version": "2.0.12"},
                    candidate_port=18387,
                )
        self.assertEqual(
            owner_manifest["download_url"],
            "http://127.0.0.1:18387/FedorinovRewards_WebPreview_v2.0.13.zip",
        )
        self.assertEqual(evidence["public_version"], "2.0.12")
        self.assertEqual(evidence["candidate_version"], "2.0.13")
        self.assertTrue(evidence["channels_separate"])

    def test_candidate_validation_rejects_sha_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact, manifest, _ = self._candidate(Path(temp_dir))
            with mock.patch.object(
                prepare_owner_candidate_channel,
                "git",
                side_effect=["", 'APP_VERSION = "2.0.13"'],
            ):
                with self.assertRaisesRegex(ValueError, "candidate SHA mismatch"):
                    prepare_owner_candidate_channel.validate_candidate(
                        artifact=artifact,
                        manifest_path=manifest,
                        expected_commit="a" * 40,
                        expected_version="2.0.13",
                        expected_sha256="0" * 64,
                        expected_public_version="2.0.12",
                        production_manifest={"version": "2.0.12"},
                        candidate_port=18387,
                    )

    def test_candidate_validation_rejects_production_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact, manifest, digest = self._candidate(Path(temp_dir))
            with mock.patch.object(
                prepare_owner_candidate_channel,
                "git",
                side_effect=["", 'APP_VERSION = "2.0.13"'],
            ):
                with self.assertRaisesRegex(ValueError, "production manifest version mismatch"):
                    prepare_owner_candidate_channel.validate_candidate(
                        artifact=artifact,
                        manifest_path=manifest,
                        expected_commit="a" * 40,
                        expected_version="2.0.13",
                        expected_sha256=digest,
                        expected_public_version="2.0.12",
                        production_manifest={"version": "2.0.13"},
                        candidate_port=18387,
                    )

    def test_windows_oem_output_is_decoded_without_credential_logging(self) -> None:
        message = "Ошибка запуска"
        self.assertEqual(
            prepare_owner_candidate_channel.decode_windows_output(message.encode("cp866")),
            message,
        )

    def test_loopback_server_disables_cache_and_reports_health(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "latest.json").write_text(
                json.dumps({"version": "2.0.13", "sha256": "abc"}),
                encoding="utf-8",
            )
            handler = partial(
                owner_candidate_channel_server.CandidateChannelHandler,
                directory=str(root),
            )
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with urlopen(f"http://127.0.0.1:{server.server_port}/healthz") as response:
                    payload = json.loads(response.read())
                    self.assertEqual(response.headers["Cache-Control"], "no-cache, no-store, must-revalidate")
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()
        self.assertEqual(payload, {"status": "ok", "version": "2.0.13", "sha256": "abc"})

    def test_physical_config_is_loopback_only_and_restorable(self) -> None:
        script = (
            prepare_owner_candidate_channel.PROJECT_ROOT
            / "scripts"
            / "configure_owner_candidate_channel.ps1"
        ).read_text(encoding="utf-8")
        self.assertIn('"http://127.0.0.1:$port/latest.json"', script)
        self.assertIn("production_manifest_url", script)
        self.assertIn("Set-EnvValue", script)
        self.assertIn("if ($Action -eq 'Restore')", script)
        self.assertNotIn("REWARDS_DATA_DIR=", script)
        self.assertNotIn("REWARDS_DB_PATH=", script)

    def test_visibility_gate_never_submits_update_form(self) -> None:
        script = (
            prepare_owner_candidate_channel.PROJECT_ROOT
            / "scripts"
            / "verify_owner_candidate_visibility.py"
        ).read_text(encoding="utf-8")
        self.assertIn("Проверить обновления", script)
        self.assertIn("location.href.includes('tab=about')", script)
        self.assertIn("update_not_applied", script)
        self.assertNotIn("requestSubmit", script)
        self.assertNotIn("confirm_update", script)
        handoff = (
            prepare_owner_candidate_channel.PROJECT_ROOT
            / "scripts"
            / "verify_owner_candidate_handoff.ps1"
        ).read_text(encoding="utf-8")
        self.assertIn("FedorinovRewards-Public-Current", handoff)
        self.assertIn("FedorinovRewards-Physical-GUI", handoff)
        self.assertIn("update_not_applied", handoff)
        self.assertNotIn("/updates/apply", handoff)

    def test_release_docs_do_not_require_duplicate_vm_gate_after_owner_pass(self) -> None:
        release_process = (
            prepare_owner_candidate_channel.PROJECT_ROOT / "docs" / "RELEASE_PROCESS.md"
        ).read_text(encoding="utf-8")
        channel_runbook = (
            prepare_owner_candidate_channel.PROJECT_ROOT
            / "docs"
            / "OWNER_CANDIDATE_CHANNEL.md"
        ).read_text(encoding="utf-8")
        self.assertIn("Do not repeat the full suite, Windows VM updater gate", release_process)
        self.assertIn("manual Owner update", release_process)
        self.assertIn("не повторяет VM updater", channel_runbook)
        self.assertIn("pre-publication updater gate", channel_runbook)


if __name__ == "__main__":
    unittest.main()
