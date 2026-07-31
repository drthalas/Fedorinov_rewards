# Mac mini test orchestrator

The Mac mini is the development and test-control host. It must remain reachable
without an active local display, keep the UTM Windows VM running, and expose
only the remote services needed for project work.

The Owner has explicitly authorized automatic login for this dedicated,
physically restricted headless test server. This authorization does not extend
to other macOS security changes or storing credentials in the repository,
documentation, scripts, logs, or Linear.

## Access model

- Primary command channel: macOS Remote Login (SSH).
- Primary headed channel: macOS Screen Sharing.
- Windows VM control: UTM plus the VM channel documented in
  [WINDOWS_VM_GATE.md](WINDOWS_VM_GATE.md).
- Physical release gate: the dedicated SSH/RDP channels documented in
  [WINDOWS_PHYSICAL_GATE.md](WINDOWS_PHYSICAL_GATE.md).

Remote Management/ARD is not required when Screen Sharing is available.

## Audited host state

The current AC power profile has:

- system sleep disabled;
- display sleep disabled;
- standby disabled;
- wake-on-network enabled;
- TCP keepalive enabled;
- Power Nap enabled.

Remote Login and Screen Sharing are enabled. FileVault is off, and supported
macOS automatic login is enabled for the dedicated `hermes` user. The
screen-lock delay remains immediate. Supported macOS power recovery is
enabled: the Mac automatically restarts after a power interruption.

Idle sleep and automatic display blanking are additionally prevented by a
user LaunchAgent:

```text
~/Library/LaunchAgents/com.fedorinov.keep-awake.plist
```

It keeps `/usr/bin/caffeinate -dimsu` running with `RunAtLoad` and
`KeepAlive`. This preserves the existing password and immediate manual-lock
policy. It prevents the automatically loaded GUI session from becoming
unavailable solely because of idle sleep or display sleep.

Verify the state without changing it:

```bash
pmset -g custom
pmset -g assertions
launchctl print-disabled system
launchctl print gui/$(id -u)/com.fedorinov.keep-awake
nc -G 3 -zv localhost 22
nc -G 3 -zv localhost 5900
fdesetup status
sysadminctl -autologin status
sysadminctl -screenLock status
```

Expected identity is `Automatic login user: hermes` with `FileVault is Off`.
The system-managed `/etc/kcpassword` may be checked only for existence,
ownership, mode, and size. Never read, copy, log, or commit its contents.
Do not change automatic login or weaken screen-lock policy as part of ordinary
test setup. Those remain explicit Owner security decisions.

Expected `pmset -g assertions` evidence includes persistent
`PreventUserIdleSystemSleep`, `PreventUserIdleDisplaySleep`, and
`PreventSystemSleep` assertions owned by `caffeinate`.

The post-reboot controlled idle gate kept these assertions active for 30
minutes. Mac boot identity and console user did not change, the VM boot
identity did not change, and the Windows VM remained reachable by key-based
SSH.

## UTM startup after login

The local machine has a user LaunchAgent:

```text
~/Library/LaunchAgents/com.fedorinov.test-orchestrator.plist
```

It runs:

```text
~/Library/Application Support/FedorinovOrchestrator/start-utm-vm.sh
```

The script starts the single project UTM VM only when it is not already
running. It contains no credentials and writes only short operational messages
to the macOS unified log. The LaunchAgent uses `StartInterval = 60` as an
identity-scoped watchdog in addition to `RunAtLoad`.

Verify it with:

```bash
launchctl print gui/$(id -u)/com.fedorinov.test-orchestrator
/opt/homebrew/bin/utmctl list
```

Expected LaunchAgent properties are `RunAtLoad`, `StartInterval = 60`, last
exit code `0`, and the project VM in `started` state.

`KeepRunningAfterLastWindowClosed` is configured, but the current audit
observed the VM transition to `Stopped` after the console window was closed.
In the post-reboot controlled test, the watchdog restored the exact project VM
to `started` in 26 seconds, and key-based SSH returned after 36 seconds.
Keep the console open or minimized during normal use to avoid an unnecessary
guest reboot. Treat the watchdog as recovery, not as proof that UTM keeps the
guest alive after the last window closes.

## Full reboot autonomy

The LaunchAgent starts UTM after the `hermes` GUI login session exists. It does
not create that login session; supported macOS automatic login now creates it
after boot.

The controlled full reboot gate passed without manual login:

1. macOS acquired a new boot identity;
2. `/dev/console` reported `hermes`;
3. `sysadminctl` reported `Automatic login user: hermes`;
4. keep-awake and the UTM watchdog loaded through `RunAtLoad`;
5. the exact VM UUID reached `started`;
6. VM OpenSSH returned with the expected hostname and automatic `sshd`;
7. Mac SSH and Screen Sharing were reachable from the VM;
8. the physical Windows gate was reachable by its pinned SSH identity when its
   network was available.

No Owner login or unlock was performed after the reboot.

Automatic login reduces physical security because a person with access to the
Mac can obtain the `hermes` session after boot. The Owner accepted this tradeoff
for the dedicated physically restricted server. Manual screen lock still
requires normal authentication; do not disable it.

For a phone-triggered readiness check:

```bash
ssh <mac-mini-host> 'stat -f "%Su" /dev/console'
ssh <mac-mini-host> \
  'launchctl print gui/501/com.fedorinov.keep-awake'
ssh <mac-mini-host> '/opt/homebrew/bin/utmctl list'
ssh <mac-mini-host> \
  'ssh -o BatchMode=yes fedorinov-win-vm "whoami"'
```

To disable automatic login, use System Settings > Users & Groups >
Automatically log in as > Off and authorize the change interactively. Do not
manually edit or copy `/etc/kcpassword`.

## Power-loss recovery

System Settings > Energy is set to **After a power failure**. The corresponding
supported power-management state is:

```text
autorestart 1
autorestartatconnect 0
```

Verify without changing it:

```bash
pmset -g custom | grep -E 'autorestart|autorestartatconnect'
```

To configure the same supported setting from an authorized administrator
session:

```bash
sudo pmset -a autorestart 1
```

`autorestartatconnect` remains disabled because reconnecting AC is not the
selected policy. Do not simulate a power loss by pulling power during routine
QA. A physical power-loss test requires separate Owner authorization and a
verified backup; normal reboot evidence does not prove the electrical recovery
path. A UPS remains the preferred protection against short interruptions.

## Idle check

For a 30-60 minute idle check:

1. Record Mac boot time, UTM PID, VM PID, and VM state.
2. Minimize the UTM window. Closing the last console intentionally tests the
   watchdog and causes a guest restart on the audited UTM version.
3. Leave the host idle for at least 30 minutes.
4. Reconnect through SSH and Screen Sharing.
5. Verify that the PIDs are still present and the VM channel responds.
6. Record `pmset -g assertions` and unexpected wake/sleep events.

An active Screen Sharing assertion is useful evidence but is not the keep-awake
mechanism. The persistent AC power profile must be sufficient on its own.

## Recovery

If the VM is not running after a user login:

```bash
launchctl kickstart -k gui/$(id -u)/com.fedorinov.test-orchestrator
launchctl print gui/$(id -u)/com.fedorinov.test-orchestrator
```

The watchdog normally performs this check within 60 seconds. Manual
`kickstart` is reserved for diagnostics when the interval has elapsed and the
VM is still stopped.

Do not broad-kill UTM, QEMU, SSH, or screen-sharing processes. Confirm process
and VM identity before stopping anything.

To remove only the keep-awake behavior:

```bash
launchctl bootout gui/$(id -u)/com.fedorinov.keep-awake
rm ~/Library/LaunchAgents/com.fedorinov.keep-awake.plist
```

This rollback does not change `pmset`, screen-lock, or automatic-login policy.
