# Configuration reference

Configuration comes from environment variables. The systemd service loads them from the
env file (`/etc/patchbay.env`, or `PREFIX/patchbay.env` with a custom prefix);
`run-local.sh` loads `local.env`. Restart the service after changes.

Empty values are treated as unset.

## Server

| Variable | Default | Description |
|---|---|---|
| `HOST` | `0.0.0.0` | Address the web server listens on. |
| `PORT` | `8080` | Web UI / API port. |
| `LOG_LEVEL` | `info` | `debug`, `info`, `warning` or `error`. |

## Files

| Variable | Default | Description |
|---|---|---|
| `STATE_FILE` | `/var/lib/patchbay/state.json` | Outputs, routes, presets. Set by the systemd unit to the install's state directory. |
| `AUTH_FILE` | `auth.json` in the same directory as `STATE_FILE` | Users, sessions and API keys (hashed). |

## Authentication

| Variable | Default | Description |
|---|---|---|
| `SESSION_DAYS` | `30` | How long a web UI login stays valid. |
| `API_KEY` | – | **Deprecated.** If set, imported once as a managed API key at startup. Remove after migrating. |

Users and API keys are managed in the web UI; see [authentication.md](authentication.md).

## NDI®

| Variable | Default | Description |
|---|---|---|
| `NDI_LIB_PATH` | see below | Path to `libndi.so.6` or its directory. |
| `NDI_GROUPS` | NDI default (`public`) | Comma-separated groups to **discover** sources in, and the default groups outputs are **published** in. An output's own groups (set in the UI) override the default. |
| `NDI_EXTRA_IPS` | – | Comma-separated IPs for unicast discovery of sources on other subnets. |
| `NDI_DISCOVERY_SERVER` | – | Address of an NDI Discovery Server. When set, the router writes `ndi-config.v1.json` into `ndi-config/` next to the state file and uses the server instead of mDNS. |
| `OUTPUT_PREFIX` | – | Text prepended to every output's NDI name, e.g. `RTR-` gives `HOST (RTR-Program)`. |

`libndi.so.6` is searched in this order: `NDI_LIB_PATH`, `$NDI_RUNTIME_DIR_V6`, the
system loader path, `/usr/local/lib`, `/usr/lib`, `/usr/lib/x86_64-linux-gnu`,
`/opt/ndi/lib`. With `--ndi-lib`, the installer copies the library into `PREFIX/lib`
and, when it creates a new env file, sets `NDI_LIB_PATH` to that directory. An existing
env file is never changed.

## Command-line options

`python -m patchbay` (or the `patchbay` script) accepts:

| Option | Overrides | Description |
|---|---|---|
| `--host H` | `HOST` | Listen address |
| `--port P` | `PORT` | Listen port |
| `--state-file PATH` | `STATE_FILE` | State file (auth file defaults next to it) |
| `--fake` | – | Simulated NDI backend with demo sources; no SDK needed |

`python -m patchbay user …` manages users; see
[authentication.md](authentication.md#password-recovery-cli).

## Example env file

```ini
HOST=0.0.0.0
PORT=8080
NDI_LIB_PATH=/opt/patchbay/lib
# NDI_GROUPS=public,Studio
# NDI_EXTRA_IPS=10.40.0.28,192.168.14.10
# NDI_DISCOVERY_SERVER=10.0.0.5
# OUTPUT_PREFIX=RTR-
# SESSION_DAYS=30
LOG_LEVEL=info
```

## Set by the systemd unit

These are fixed in `deploy/patchbay.service` (rendered by the installer):

| Setting | Value |
|---|---|
| `User` / `Group` | the `--user` account |
| `STATE_FILE` | `<state dir>/state.json` |
| `HOME` | state directory (gives the service a writable home) |
| `LD_LIBRARY_PATH` | `PREFIX/lib` (libndi and vendored Avahi libs) |
| `EnvironmentFile` | the env file (optional; missing file is OK) |
| Hardening | `ProtectSystem=strict`, `ReadWritePaths=<state dir>`, `NoNewPrivileges`, `PrivateTmp`, restricted address families |

---

<sub>NDI® is a registered trademark of Vizrt NDI AB. Learn more about NDI at <https://ndi.video/>. Patchbay is an independent product and is not affiliated with, sponsored or endorsed by Vizrt NDI AB.</sub>
