# Mac mini test orchestrator

The Mac mini is the development and test-control host. It must remain reachable
without an active local display, keep the UTM Windows VM running, and expose
only the remote services needed for project work.

This runbook does not authorize weakening macOS authentication, enabling
automatic login, or storing credentials in the repository.

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

Remote Login and Screen Sharing are enabled. Automatic login is disabled and
the screen-lock delay is immediate. The system does not currently restart
automatically after a power interruption.

Idle sleep and automatic display blanking are additionally prevented by a
user LaunchAgent:

```text
~/Library/LaunchAgents/com.fedorinov.keep-awake.plist
```

It keeps `/usr/bin/caffeinate -dimsu` running with `RunAtLoad` and
`KeepAlive`. This preserves the existing password, immediate manual-lock
policy, and disabled automatic login. It prevents an active GUI session from
becoming unavailable solely because of idle sleep or display sleep.

Verify the state without changing it:

```bash
pmset -g custom
pmset -g assertions
launchctl print-disabled system
launchctl print gui/$(id -u)/com.fedorinov.keep-awake
nc -G 3 -zv localhost 22
nc -G 3 -zv localhost 5900
sysadminctl -autologin status
sysadminctl -screenLock status
```

Do not enable automatic login or weaken screen-lock policy as part of ordinary
test setup. Those are explicit Owner security decisions.

Expected `pmset -g assertions` evidence includes persistent
`PreventUserIdleSystemSleep`, `PreventUserIdleDisplaySleep`, and
`PreventSystemSleep` assertions owned by `caffeinate`.

The controlled idle gate kept these assertions active for 30 minutes. After
the interval, macOS SSH and Screen Sharing were reachable from the trusted
physical Windows host, and the Windows VM remained reachable by key-based SSH.
This proves idle continuity within the current logged-in boot, not unattended
recovery across a full Mac reboot.

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
The watchdog restored the exact project VM to `started` in 31 seconds during
the controlled close test, and key-based SSH returned after Windows boot.
Keep the console open or minimized during normal use to avoid an unnecessary
guest reboot. Treat the watchdog as recovery, not as proof that UTM keeps the
guest alive after the last window closes.

## Reboot boundary

The LaunchAgent starts UTM after the `hermes` GUI login session exists. It does
not create that login session.

Because automatic login is disabled, an unattended full Mac reboot currently
stops at the macOS login window. Remote Login may still provide a command
channel, but the GUI UTM VM cannot be claimed as automatically restored until a
post-reboot login and VM-start check has passed.

The immediate screen lock also blocks GUI automation, including the UTM
console, after the session locks. Disabling or delaying that lock would weaken
the current security policy and requires a separate explicit Owner decision.

Do not report the Mac reboot gate as PASS while this boundary remains. Options
requiring an Owner decision are:

1. retain the secure login boundary and arrange an Owner login after reboot;
2. approve a dedicated always-on test account and its security policy;
3. replace GUI-session UTM startup with a supported system-level virtualization
   service.

## Power-loss recovery

`autorestart` and `autorestartatconnect` are currently disabled. Enabling either
requires an administrator action and must be reviewed separately. A UPS is the
preferred protection against short power interruptions.

## Idle check

For a 30-60 minute idle check:

1. Record Mac boot time, UTM PID, VM PID, and VM state.
2. Minimize the UTM window. Closing the last console intentionally tests the
   watchdog and causes a guest restart on the audited UTM version.
3. Leave the host idle for at least 60 minutes.
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
