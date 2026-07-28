from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts" / "windows-gate"
DOCS = ROOT / "docs" / "testing"


class WindowsPhysicalGateContractTests(unittest.TestCase):
    def test_expected_scripts_are_committed(self) -> None:
        expected = {
            "WindowsGate.Common.psm1",
            "Initialize-WindowsPhysicalGate.ps1",
            "Import-ReleaseCandidate.ps1",
            "New-WindowsGateBaseline.ps1",
            "Reset-WindowsPhysicalGate.ps1",
            "Invoke-WindowsPhysicalGate.ps1",
            "Start-WindowsGateRun.ps1",
            "Stop-WindowsGateRun.ps1",
        }
        self.assertEqual(expected, {path.name for path in SCRIPTS.iterdir() if path.is_file()})

    def test_candidate_intake_requires_exact_identity(self) -> None:
        source = (SCRIPTS / "Import-ReleaseCandidate.ps1").read_text(encoding="utf-8")
        for marker in (
            "ExpectedSize",
            "ExpectedSha256",
            "CommitSha",
            "Assert-CandidateArtifact",
            "candidate.json",
        ):
            self.assertIn(marker, source)
        self.assertNotIn("build_release_package", source)

    def test_reset_is_scoped_and_refuses_running_app_backend(self) -> None:
        source = (SCRIPTS / "Reset-WindowsPhysicalGate.ps1").read_text(encoding="utf-8")
        self.assertIn("Assert-GateChildPath", source)
        self.assertIn("Get-AppOwnedBackendProcesses", source)
        self.assertIn("Immutable data baseline fingerprint changed", source)
        self.assertNotRegex(source, r"taskkill|Stop-Process\s+-Name|/IM\s+python")

    def test_gate_uses_normal_launcher_and_strict_identity(self) -> None:
        source = (SCRIPTS / "Invoke-WindowsPhysicalGate.ps1").read_text(encoding="utf-8")
        self.assertIn("start_windows.bat", source)
        self.assertIn("Wait-RuntimeIdentity", source)
        self.assertIn("Get-AppOwnedBackendProcesses", source)
        self.assertIn("UPDATE_MANIFEST_URL", source)
        self.assertIn("data_fingerprint_before", source)
        self.assertIn("data_fingerprint_after", source)

        start = (SCRIPTS / "Start-WindowsGateRun.ps1").read_text(encoding="utf-8")
        stop = (SCRIPTS / "Stop-WindowsGateRun.ps1").read_text(encoding="utf-8")
        self.assertIn("start_windows.bat", start)
        self.assertIn("Wait-RuntimeIdentity", start)
        self.assertIn("[switch]$Hold", start)
        self.assertIn("Wait-Process -Id", start)
        self.assertIn("Runtime identity PID does not match", stop)
        self.assertNotRegex(stop, r"taskkill|Stop-Process\s+-Name|/IM\s+python")

    def test_common_module_rejects_paths_outside_gate_root(self) -> None:
        source = (SCRIPTS / "WindowsGate.Common.psm1").read_text(encoding="utf-8")
        self.assertIn("Path is outside the Windows gate root", source)
        self.assertIn("Reparse points are not allowed", source)
        self.assertRegex(source, re.compile(r"runtime_server\.py", re.IGNORECASE))

    def test_docs_do_not_claim_an_os_snapshot(self) -> None:
        host = (DOCS / "WINDOWS_HOST_PROFILE.md").read_text(encoding="utf-8")
        gate = (DOCS / "WINDOWS_PHYSICAL_GATE.md").read_text(encoding="utf-8")
        self.assertIn("scripted product-and-synthetic-data reset", host)
        self.assertIn("not an OS snapshot", host)
        self.assertIn("Never rebuild between physical acceptance and publication", gate)
        self.assertIn("Headed checks are release-specific evidence", gate)

    def test_no_secret_or_private_key_material_is_committed(self) -> None:
        for path in [*SCRIPTS.iterdir(), *DOCS.glob("WINDOWS_*.md")]:
            if not path.is_file():
                continue
            source = path.read_text(encoding="utf-8")
            self.assertNotIn("BEGIN OPENSSH PRIVATE KEY", source)
            self.assertNotRegex(source, re.compile(r"password\s*=\s*['\"][^'\"]+", re.IGNORECASE))


if __name__ == "__main__":
    unittest.main()
