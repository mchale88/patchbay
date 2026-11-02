# Running and operations

Paths below assume the default install (`/opt/patchbay`, `/etc/patchbay.env`,
`/var/lib/patchbay`). With `--prefix DIR` the config is `DIR/patchbay.env` and the
state is in `DIR/state/`. For a checkout started with `run-local.sh`, see
[installation.md](installation.md#3-run-from-a-checkout-no-systemd).

## First start

1. Open `http://<server>:8080/` in a browser.
2. You see **Create admin account**. Choose a username and a password (minimum
   8 characters) and confirm it.
3. You are logged in. Create further users and API keys under **⚙ Settings**.

> Until the first account exists, anyone who can reach the web UI can create it. Do
> this right after installing, or keep the port firewalled until you have.

If you are upgrading from a version that used a single `API_KEY`, that key is imported
automatically as an API key named **Imported from API_KEY**, so existing integrations keep
working. Revoke it in Settings when you have replaced it, and delete the `API_KEY=` line
from the env file.

## Service control

```bash
sudo systemctl status patchbay
sudo systemctl restart patchbay
sudo systemctl stop patchbay
sudo systemctl disable --now patchbay      # stop and do not start at boot
```

The unit restarts the process automatically if it crashes (`Restart=on-failure`), starts
after the network and `avahi-daemon`, and runs as the unprivileged `patchbay` user with
systemd hardening (`ProtectSystem=strict`, only the state directory is writable).

## Logs

```bash
journalctl -u patchbay -f              # follow
journalctl -u patchbay -b              # since boot
journalctl -u patchbay --since "1 hour ago"
```

Useful log lines:

| Message | Meaning |
|---|---|
| `Loaded NDI runtime …` | libndi was found and initialised. |
| `Engine started with N outputs, M presets` | State restored. |
| `Source online: X` / `Source offline: X` | Discovery changes. |
| `Routed PGM -> X` | A route was applied to the NDI® runtime. |
| `NDIlib_routing_create failed … (will retry; is avahi-daemon running?)` | An output could not be advertised; it is retried every few seconds. |
| `NDI output … is now advertised` | A previously failed output recovered. |
| `Failed login for 'x' from IP` | Wrong username or password. |
| `No users yet: open the web UI…` | First-run setup is still pending. |

Set `LOG_LEVEL=debug` in the env file for more detail.

## Changing configuration

```bash
sudoedit /etc/patchbay.env
sudo systemctl restart patchbay
```

All settings are listed in [configuration.md](configuration.md). Outputs, routes, presets,
users and API keys are **not** in the env file; they are managed in the UI or API and
stored in the state directory.

## End-to-end check

1. Web UI → **Sources** lists the NDI sources on your network.
2. Click **+ Output**, name it `Test`, then pick a source from its dropdown. Status
   becomes `live`.
3. On a receiver (NDI Studio Monitor, OBS, …) open `<HOSTNAME> (Test)`. Video from the
   selected source appears, and the output card shows 👁 1.
4. Pick another source; the receiver follows within about a second.
5. `sudo systemctl restart patchbay`; the route is restored and the receiver
   reconnects.

If the output does not appear on the receiver, see
[troubleshooting.md](troubleshooting.md#outputs-do-not-show-up-on-receivers).

## Files and backups

| File | Contents | Back up? |
|---|---|---|
| `STATE_FILE` (`/var/lib/patchbay/state.json`) | outputs, routes, presets | yes |
| `auth.json` (next to the state file) | users, sessions, API keys — all hashed, mode 0600 | yes, keep private |
| `/etc/patchbay.env` | configuration | yes |
| `*.corrupt` (next to the state file) | an unreadable state file that was moved aside on startup | inspect, then delete |

Backup:

```bash
sudo tar czf patchbay-backup-$(date +%F).tgz /var/lib/patchbay /etc/patchbay.env
```

Restore: stop the service, put the files back, fix ownership, start:

```bash
sudo systemctl stop patchbay
sudo tar xzf patchbay-backup-YYYY-MM-DD.tgz -C /
sudo chown -R patchbay:patchbay /var/lib/patchbay
sudo systemctl start patchbay
```

Writes are atomic (write to a temp file, then rename), so a crash never leaves a
half-written file.

## Upgrading

```bash
cd patchbay && git pull           # or unpack the new release
sudo ./deploy/install.sh            # same --prefix/--user as the original install
```

The installer replaces the code and virtualenv, keeps the env file and state, re-links the
unit and restarts the service. Pass `--ndi-lib` again to update the NDI runtime.

## Uninstalling

```bash
sudo systemctl disable --now patchbay
sudo systemctl daemon-reload
sudo rm -rf /opt/patchbay               # code, venv, libs, unit file
sudo rm -rf /var/lib/patchbay /etc/patchbay.env   # state and config (optional)
sudo userdel patchbay                   # optional
```

On TrueNAS, also remove the post-init script and, if wanted, the dataset and user.

---

<sub>NDI® is a registered trademark of Vizrt NDI AB. Learn more about NDI at <https://ndi.video/>. NDI tools (for example NDI Studio Monitor and NDI Access Manager) are available from <https://ndi.video/tools/>. Patchbay is an independent product and is not affiliated with, sponsored or endorsed by Vizrt NDI AB.</sub>
