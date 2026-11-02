# Installation

There are three ways to run Patchbay:

1. [As a systemd service on Linux](#1-linux-systemd-service) — recommended for production.
2. [As a systemd service on TrueNAS SCALE](#2-truenas-scale) — persistent across TrueNAS updates.
3. [Directly from a checkout](#3-run-from-a-checkout-no-systemd) — for testing or small setups.

## Requirements

| Requirement | Notes |
|---|---|
| Linux x86-64 | Tested on Ubuntu 26.04 and TrueNAS SCALE. |
| Python 3.10+ | `python3` with `venv`. If `ensurepip` is missing (TrueNAS), the installer bootstraps pip with `curl`. |
| NDI® SDK for Linux v6 | Provides `libndi.so.6`. Must be downloaded by you (licence forbids redistribution). |
| Avahi | `avahi-daemon` running, and the client library `libavahi-client.so.3`. libndi uses them for mDNS discovery and advertising. |
| Network | Host networking on the same L2 network as sources and receivers (or mDNS reflection / Discovery Server across subnets). UDP 5353 open. |
| Root | Needed only for the installer. The service itself runs as an unprivileged user. |

## 0. Get the NDI runtime

1. Download **NDI SDK for Linux** from <https://ndi.video/for-developers/ndi-sdk/>.
2. Extract it and accept the licence:
   ```bash
   sh Install_NDI_SDK_v6_Linux.sh
   ls "NDI SDK for Linux/lib/x86_64-linux-gnu/libndi.so.6"
   ```
3. Note the directory `NDI SDK for Linux/lib/x86_64-linux-gnu`; you pass it to the
   installer as `--ndi-lib`.

### Avahi

On Debian/Ubuntu:

```bash
sudo apt install avahi-daemon libavahi-client3
sudo systemctl enable --now avahi-daemon
```

If you cannot install packages (for example on an appliance), put
`libavahi-client.so.3*` and `libavahi-common.so.3*` into `vendor/lib/` in the checkout.
You can extract them from the Debian packages:

```bash
mkdir -p vendor/debs vendor/lib && cd vendor/debs
apt download libavahi-client3 libavahi-common3      # on any Debian/Ubuntu machine
for d in *.deb; do dpkg-deb -x "$d" x; done
cp -a x/usr/lib/x86_64-linux-gnu/libavahi-*.so* ../lib/
```

The installer copies them next to libndi when the system has no `libavahi-client`, and
`run-local.sh` adds `vendor/lib` to the library path. `avahi-daemon` itself must still be
running on the host.

## 1. Linux (systemd service)

From the checkout, as root:

```bash
sudo ./deploy/install.sh --ndi-lib "NDI SDK for Linux/lib/x86_64-linux-gnu"
```

What the installer does:

1. Creates the system user `patchbay` (if missing).
2. Copies the application to `/opt/patchbay/src` and builds a virtualenv in
   `/opt/patchbay/venv`.
3. Copies `libndi.so*` (and vendored Avahi libs if needed) to `/opt/patchbay/lib`.
4. Writes `/etc/patchbay.env` from `deploy/patchbay.env.example` (kept if it already exists).
5. Creates `/var/lib/patchbay` for state.
6. Installs, enables and starts `patchbay.service`.

Installer options:

| Option | Default | Meaning |
|---|---|---|
| `--prefix DIR` | `/opt/patchbay` | Install location. With a custom prefix, state goes to `DIR/state` and config to `DIR/patchbay.env`. |
| `--user NAME` | `patchbay` | Service account (created if it does not exist). |
| `--ndi-lib PATH` | – | `libndi.so.6` file or its directory; copied into `PREFIX/lib`. |
| `--no-start` | – | Install and enable, but do not start now. |

Then **open `http://<server>:8080/` immediately and create the admin account** (see
[running.md](running.md#first-start)).

## 2. TrueNAS SCALE

A TrueNAS update replaces the root filesystem: anything in `/opt`, `/etc/systemd`, and
users created with `useradd` disappear. Keep everything on a dataset and re-register the
service at boot.

1. **Create a dataset**, e.g. `tank/apps/patchbay` (mounted at `/mnt/tank/apps/patchbay`).
2. **Create the service user** in *Credentials → Users*: username `patchbay`,
   no home directory, shell `nologin`. Users created in the UI survive updates.
3. **Install into the dataset** from a root shell in the checkout:
   ```bash
   ./deploy/install.sh --prefix /mnt/tank/apps/patchbay --user patchbay \
       --ndi-lib "NDI SDK for Linux/lib/x86_64-linux-gnu"
   ```
   Config: `/mnt/tank/apps/patchbay/patchbay.env`; state:
   `/mnt/tank/apps/patchbay/state/`.
4. **Add a post-init script** in *System → Advanced → Init/Shutdown Scripts*:
   - Type: *Script*, When: *Post Init*
   - Script: `/mnt/tank/apps/patchbay/src/deploy/truenas-postinit.sh /mnt/tank/apps/patchbay`
5. **Check the port.** 8080 may already be used by another app; change `PORT` in the env
   file and `systemctl restart patchbay`.
6. **Avahi:** make sure `avahi-daemon` runs on the host (or inside the VM/container that
   runs the router).

## 3. Run from a checkout (no systemd)

Useful for testing, or when you cannot install a service.

```bash
cd patchbay
python3 -m venv .venv && .venv/bin/pip install -e .
cat > local.env <<'EOF'
HOST=0.0.0.0
PORT=8080
NDI_LIB_PATH="/path/to/NDI SDK for Linux/lib/x86_64-linux-gnu"
STATE_FILE=/path/to/patchbay/state/state.json
LOG_LEVEL=info
EOF
chmod 600 local.env
./run-local.sh          # start in background; logs in state/router.log
./run-local.sh status
./run-local.sh stop
./run-local.sh fg       # run in the foreground (Ctrl+C to stop)
```

`run-local.sh` loads `local.env`, adds `vendor/lib` to `LD_LIBRARY_PATH` and writes
`state/router.pid`. `local.env` and `state/` are git-ignored because they contain
secrets.

## Verify the installation

```bash
curl -s http://localhost:8080/api/health
# {"status":"ok","version":"1.0.0","ndi_runtime":"NDI SDK LINUX ... 6.x","uptime_s":12,"setup_required":true}
```

- `ndi_runtime` shows the loaded NDI version. If the service does not start, see
  [troubleshooting.md](troubleshooting.md).
- `setup_required: true` means no account exists yet: open the web UI and create one.

Then follow the end-to-end check in [running.md](running.md#end-to-end-check).

---

<sub>NDI® is a registered trademark of Vizrt NDI AB. Learn more about NDI at <https://ndi.video/>. Patchbay is an independent product and is not affiliated with, sponsored or endorsed by Vizrt NDI AB.</sub>
