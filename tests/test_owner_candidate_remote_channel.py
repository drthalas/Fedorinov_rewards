from __future__ import annotations

from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen
import zipfile

from scripts.install_owner_candidate_channel_macos import launch_agent
from scripts.owner_candidate_channel_server import CandidateChannel, handler_factory
from scripts.publish_owner_candidate_channel import publish, sha256_file


COMMIT = "a" * 40
VERSION = "2.0.14"


class OwnerCandidateRemoteChannelTests(unittest.TestCase):
    def _artifact(self, root: Path) -> Path:
        artifact = root / f"FedorinovRewards_WebPreview_v{VERSION}.zip"
        with zipfile.ZipFile(artifact, "w") as archive:
            archive.writestr(
                "FedorinovRewards_WebPreview/backend/app/version.py",
                f'APP_VERSION = "{VERSION}"\n',
            )
        return artifact

    def _publish(self, root: Path) -> tuple[Path, dict[str, object]]:
        artifact = self._artifact(root)
        checksum = sha256_file(artifact)
        source_manifest = root / "source-latest.json"
        source_manifest.write_text(
            json.dumps(
                {
                    "version": VERSION,
                    "released_at": "2026-08-15",
                    "download_url": "https://production.invalid/artifact.zip",
                    "sha256": checksum,
                    "notes": ["Owner candidate"],
                }
            ),
            encoding="utf-8",
        )
        channel_root = root / "channel"
        with patch("scripts.publish_owner_candidate_channel.git") as git:
            git.side_effect = ["", f'APP_VERSION = "{VERSION}"']
            state = publish(
                artifact=artifact,
                source_manifest=source_manifest,
                channel_root=channel_root,
                base_url="http://owner-channel.test:18387",
                expected_commit=COMMIT,
                expected_version=VERSION,
                expected_sha256=checksum,
                expected_size=artifact.stat().st_size,
                expected_public_version="2.0.13",
                production_manifest={"version": "2.0.13"},
            )
        return channel_root, state

    def test_publish_writes_exact_owner_manifest_without_changing_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            channel_root, state = self._publish(root)
            manifest = json.loads((channel_root / "latest.json").read_text(encoding="utf-8"))
            artifact = channel_root / "artifacts" / manifest["filename"]

            self.assertEqual(manifest["version"], VERSION)
            self.assertEqual(manifest["sha256"], sha256_file(artifact))
            self.assertEqual(manifest["size"], artifact.stat().st_size)
            self.assertEqual(manifest["candidate_commit"], COMMIT)
            self.assertEqual(manifest["channel"], "owner-candidate")
            self.assertEqual(state["production_version_at_publish"], "2.0.13")
            self.assertTrue(state["channels_separate"])

    def test_publish_rejects_production_version_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            artifact = self._artifact(root)
            checksum = sha256_file(artifact)
            manifest = root / "latest.json"
            manifest.write_text(
                json.dumps({"version": VERSION, "sha256": checksum}),
                encoding="utf-8",
            )
            with patch("scripts.publish_owner_candidate_channel.git") as git:
                git.side_effect = ["", f'APP_VERSION = "{VERSION}"']
                with self.assertRaisesRegex(ValueError, "production channel version changed"):
                    publish(
                        artifact=artifact,
                        source_manifest=manifest,
                        channel_root=root / "channel",
                        base_url="http://owner-channel.test:18387",
                        expected_commit=COMMIT,
                        expected_version=VERSION,
                        expected_sha256=checksum,
                        expected_size=artifact.stat().st_size,
                        expected_public_version="2.0.13",
                        production_manifest={"version": "2.0.14"},
                    )

    def test_server_exposes_only_manifest_health_and_current_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            channel_root, state = self._publish(Path(temp_dir))
            channel = CandidateChannel(channel_root, ["127.0.0.0/8"])
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler_factory(channel))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://127.0.0.1:{server.server_port}"
                manifest = json.loads(urlopen(f"{base}/latest.json").read())
                payload = urlopen(f"{base}/artifacts/{manifest['filename']}").read()
                health = json.loads(urlopen(f"{base}/health.json").read())
                self.assertEqual(sha256_file(channel_root / "artifacts" / manifest["filename"]), manifest["sha256"])
                self.assertEqual(len(payload), manifest["size"])
                self.assertEqual(health["candidate_commit"], state["candidate_commit"])
                for path in ("/", "/artifacts/", "/../latest.json"):
                    with self.assertRaises(HTTPError) as error:
                        urlopen(base + path)
                    self.assertEqual(error.exception.code, 404)
                    error.exception.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_server_rejects_clients_outside_trusted_networks(self) -> None:
        channel = CandidateChannel(Path.cwd(), ["127.0.0.0/8", "192.168.1.0/24"])
        self.assertTrue(channel.client_allowed("127.0.0.1"))
        self.assertTrue(channel.client_allowed("192.168.1.87"))
        self.assertFalse(channel.client_allowed("192.168.2.10"))
        self.assertFalse(channel.client_allowed("203.0.113.10"))

    def test_launch_agent_is_persistent_and_lan_scoped(self) -> None:
        root = Path("/tmp/owner-channel")
        plist = launch_agent(root, Path("/usr/bin/python3"), 18387, "192.168.1.0/24")
        arguments = plist["ProgramArguments"]
        self.assertTrue(plist["RunAtLoad"])
        self.assertTrue(plist["KeepAlive"])
        self.assertIn("127.0.0.0/8", arguments)
        self.assertIn("192.168.1.0/24", arguments)
        self.assertNotIn("fedorinov-win-gate", " ".join(arguments))


if __name__ == "__main__":
    unittest.main()
