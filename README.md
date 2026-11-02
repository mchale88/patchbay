# Patchbay

**A headless router for NDI® sources.** You control it from a web UI or a REST API, and
it pushes live updates over a WebSocket.

Patchbay uses the NDI® SDK routing API: each *output* is a virtual NDI source (for
example `STUDIO-SRV (Program)`) that redirects receivers straight to whichever real source
it points at. No video passes through the server, so it uses almost no CPU or bandwidth,
and route changes take effect immediately.

> NDI® is a registered trademark of Vizrt NDI AB. Learn more about NDI at
> <https://ndi.video/>. Patchbay is an independent product and is not affiliated with,
> sponsored or endorsed by Vizrt NDI AB.

## Features

- Source discovery over mDNS, with optional NDI groups, unicast extra IPs or an NDI
  Discovery Server.
- Create, rename and delete outputs; route or clear each one.
- Pending routes to offline sources, applied when the source appears.
- Take mode / salvo: apply several routes at once, all-or-nothing.
- Presets: save, recall, update.
- Receiver connection counts per output; routing-loop protection.
- Outputs that fail to advertise are flagged and retried automatically.
- Username/password login for the web UI; API keys for REST control, managed in the UI.
- Light and dark theme.
- State persisted to JSON and restored after restart.

## Quick start

```bash
# 1. Download the NDI SDK for Linux from https://ndi.video/for-developers/ndi-sdk/,
#    accept Vizrt's license and extract it (it is not included in this repository)
sh Install_NDI_SDK_v6_Linux.sh

# 2. Install as a systemd service
sudo ./deploy/install.sh --ndi-lib "NDI SDK for Linux/lib/x86_64-linux-gnu"

# 3. Open http://<server>:8080/ and create the admin account right away
```

Without systemd: `./run-local.sh` (see [installation](docs/installation.md#3-run-from-a-checkout-no-systemd)).
Without the SDK at all: `python -m patchbay --fake`.

## Documentation

| | |
|---|---|
| [Overview](docs/overview.md) | How it works, components, output status |
| [Installation](docs/installation.md) | Linux, TrueNAS SCALE, run from a checkout |
| [Running and operations](docs/running.md) | First start, service control, logs, backup, upgrade, uninstall |
| [Web UI guide](docs/web-ui.md) | Outputs, routing, take mode, presets, settings |
| [Users, API keys and security](docs/authentication.md) | Accounts, keys, password recovery, hardening |
| [Configuration reference](docs/configuration.md) | All environment variables and options |
| [REST and WebSocket API](docs/api.md) | Endpoints, events, curl/Python/Companion examples |
| [Troubleshooting](docs/troubleshooting.md) | Sources or outputs missing, startup errors |
| [Development](docs/development.md) | Tests, fake backend, architecture |

The running server also serves interactive API docs at `/docs`.

## License

Patchbay is **source-available** under the
[PolyForm Noncommercial License 1.0.0](LICENSE):

- **Free for noncommercial use**: personal and hobby use, research, education, charities,
  religious organizations, government and other noncommercial organizations.
- **Commercial use requires a commercial license.** See [COMMERCIAL.md](COMMERCIAL.md).

The **NDI® SDK is not included** and is licensed separately by Vizrt NDI AB. Using
Patchbay with the NDI SDK is also subject to the terms in
[NDI-SDK-NOTICE.md](NDI-SDK-NOTICE.md). Some deployments, such as locked-down appliances,
locked hosted/SaaS environments or embedded devices, need a commercial license from
Vizrt NDI AB as well.

Third-party Python dependencies, installed from PyPI and not included here: FastAPI and
Pydantic (MIT), Starlette, Uvicorn and websockets (BSD-3-Clause).

Contributions: see [CONTRIBUTING.md](CONTRIBUTING.md).
