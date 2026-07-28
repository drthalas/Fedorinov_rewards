# Physical Windows Gate Host Profile

This document records the non-secret baseline for the dedicated Fedorinov Rewards
physical Windows acceptance host. Machine-local evidence lives under
`C:\FedorinovGate\Evidence` and is not committed.

## Identity

- Host alias from the Mac mini: `fedorinov-win-gate`
- Hostname: `COPEW-04C68047F`
- Hardware: HP EliteBook 745 G6
- Architecture: x64
- CPU: AMD Ryzen 5 PRO 3500U, 8 logical processors
- Memory: approximately 7.43 GiB
- Storage: 256 GB WDC PC SN520 SSD, NTFS, SMART status `OK`
- Network: trusted RFC1918 Ethernet LAN, current host address `192.168.1.86`

The IP address is operational configuration, not an internet-facing endpoint.
Confirm it before a release gate because DHCP may change it.

## Windows

- Windows 10 Enterprise LTSC, version `10.0.19044`, build `19044`
- UI language, culture, and system locale: `ru-RU`
- Console code page: OEM 866
- Time zone: `Russian Standard Time`
- PowerShell: Windows PowerShell 5.1
- Workgroup host; it is not domain joined
- Desktop and Downloads are local to `C:\Users\codex`; OneDrive redirection is absent
- Automatic sleep and hibernation are disabled

## Access

- OpenSSH for Windows 9.5p1 listens on TCP 22.
- `sshd` is `Running` with startup type `Automatic`.
- Public-key and password authentication are enabled.
- The dedicated Mac mini key is stored outside the repository.
- Strict host-key checking is enabled in the Mac mini SSH profile.
- RDP listens on TCP/UDP 3389 with Network Level Authentication required.
- Remote Desktop Services is `Running` with startup type `Automatic`.

The primary unattended channel is SSH key authentication. RDP plus the dedicated
test account password is the intended headed fallback. The password is not
stored in this repository, Linear, scripts, or evidence. Keychain-backed RDP
automation is not considered configured until a native login has been verified.

## Security posture

- UAC is enabled.
- Kaspersky Endpoint Security and the Kaspersky Security Center agent are active.
- Windows Firewall profiles are disabled because Kaspersky is the registered
  firewall provider. Do not enable a competing firewall or alter managed
  Kaspersky policy during a release gate.
- Defender services are inactive while Kaspersky is registered.
- Controlled Folder Access is not enabled.
- No system protection was disabled for ALE-329.
- SSH and RDP are reachable on the trusted local network. External router
  exposure was not configured and must remain disabled.

## Test tooling

- Python 3.11.9 was installed from the official Python Software Foundation
  installer after a valid Authenticode signature check.
- Git is intentionally absent.
- Packaged release checks must use files from the exact candidate ZIP and its
  pinned requirements. They must not depend on a repository checkout.
- Gate-control scripts are kept in `C:\FedorinovGate\Control`, outside each
  tested installation.

## Known constraints

- The host has no hypervisor snapshot or full-disk image capability configured.
  Reset is a scripted product-and-synthetic-data reset, not an OS snapshot.
- Kaspersky firewall rule scope is centrally managed and cannot be proven or
  narrowed from project scripts without changing security policy.
- The test account password still follows the host's account policy. SSH keys
  remain the durable primary access mechanism.
- Native Windows prompts, Explorer double-click, browser launch, and folder
  picker acceptance require an RDP session and are recorded separately for each
  release candidate.
- On the first ALE-329 reboot check, Ethernet did not restore its DHCP address
  and fell back to an APIPA address. Neither SSH nor RDP returned. The host is
  not a ready physical gate until the LAN lease is made stable and both channels
  pass after another reboot.
