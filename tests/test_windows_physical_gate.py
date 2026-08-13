import unittest
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
DISCOVERY = ROOT / "scripts/testing/discover_physical_windows_gate.sh"
WATCHDOG = ROOT / "scripts/windows/physical_access_watchdog.ps1"
INSTALLER = ROOT / "scripts/windows/install_physical_access_watchdog.ps1"
ROLLBACK = ROOT / "scripts/windows/rollback_physical_access_watchdog.ps1"


class PhysicalWindowsDiscoveryContractTests(unittest.TestCase):
    def test_proxy_preserves_ssh_transport_stdin(self):
        source = DISCOVERY.read_text(encoding="utf-8")
        self.assertIn("exec 3<&0", source)
        self.assertIn('exec /usr/bin/nc "$address" "$PORT" <&3', source)

    def test_discovery_reports_distinct_failure_states(self):
        source = DISCOVERY.read_text(encoding="utf-8")
        for state in (
            "LOCAL_LAN_UNAVAILABLE",
            "HOST_KEY_MISMATCH",
            "SSH_BANNER_TIMEOUT",
            "HOST_REACHABLE_SSHD_UNAVAILABLE",
            "HOST_NOT_FOUND",
        ):
            self.assertIn(state, source)

    def test_cache_is_checked_before_mdns_and_subnet_scan(self):
        source = DISCOVERY.read_text(encoding="utf-8")
        cache = source.index('if [ -r "$CACHE_PATH" ]')
        inspection = source.index("inspect_candidates", cache)
        mdns = source.index('if [ -n "$GATE_MDNS_NAME" ]')
        subnet = source.index('populate_arp "$prefix"')
        self.assertLess(cache, inspection)
        self.assertLess(inspection, mdns)
        self.assertLess(mdns, subnet)

    def test_cached_proxy_connect_relies_on_outer_openssh_identity_check(self):
        source = DISCOVERY.read_text(encoding="utf-8")
        cache = source.index('cached_address=$(/usr/bin/head -n 1 "$CACHE_PATH")')
        relay = source.index(
            'exec /usr/bin/nc "$cached_address" "$PORT" <&3', cache
        )
        full_inspection = source.index('append_candidate "$cached_address" cache', cache)
        self.assertLess(relay, full_inspection)
        self.assertIn("StrictHostKeyChecking", source[cache:full_inspection])

    def test_mdns_addresses_are_consumed_outside_a_pipeline_subshell(self):
        source = DISCOVERY.read_text(encoding="utf-8")
        self.assertIn('> "$scan_dir/mdns-addresses"', source)
        self.assertIn('done < "$scan_dir/mdns-addresses"', source)
        self.assertNotIn("| while IFS= read -r address", source)

class PhysicalWindowsWatchdogContractTests(unittest.TestCase):
    def test_watchdog_changes_ac_power_only(self):
        source = WATCHDOG.read_text(encoding="utf-8")
        self.assertIn("/setacvalueindex", source)
        self.assertNotIn("/setdcvalueindex", source)
        self.assertNotIn("/hibernate off", source)
        self.assertNotIn("Set-NetAdapterPowerManagement", source)

    def test_service_repair_allowlist_is_exact(self):
        source = WATCHDOG.read_text(encoding="utf-8")
        self.assertIn("Ensure-ServiceReady sshd", source)
        self.assertIn("Ensure-ServiceReady TermService", source)
        calls = re.findall(r"^\s*Ensure-ServiceReady\s+(\w+)\s*$", source, re.MULTILINE)
        self.assertEqual(calls, ["sshd", "TermService"])

    def test_snapshot_precedes_task_registration(self):
        source = INSTALLER.read_text(encoding="utf-8")
        self.assertLess(
            source.index("rollback-before-install.json"),
            source.index("Register-ScheduledTask"),
        )
        self.assertIn("sshd_failure_actions_base64", source)
        self.assertIn("services = @($services)", source)

    def test_rollback_uses_snapshot_and_ac_only(self):
        source = ROLLBACK.read_text(encoding="utf-8")
        self.assertIn("rollback-before-install.json", source)
        self.assertIn("Unregister-ScheduledTask -TaskName $TaskName", source)
        self.assertIn("/setacvalueindex", source)
        self.assertNotIn("/setdcvalueindex", source)


if __name__ == "__main__":
    unittest.main()
