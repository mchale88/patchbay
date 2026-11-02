# Patchbay documentation

| Document | Read it when you want to… |
|---|---|
| [Overview](overview.md) | understand what the router does, how NDI® routing works and how the pieces fit together |
| [Installation](installation.md) | install on Linux, on TrueNAS SCALE, or run straight from a checkout |
| [Running and operations](running.md) | start/stop, first login, logs, backups, upgrades, uninstall |
| [Web UI guide](web-ui.md) | operate the router from the browser: outputs, routing, take mode, presets |
| [Users, API keys and security](authentication.md) | manage logins and API keys, recover a lost password, harden the install |
| [Configuration reference](configuration.md) | look up an environment variable or file location |
| [REST and WebSocket API](api.md) | integrate Companion, Stream Deck, scripts or your own UI |
| [Troubleshooting](troubleshooting.md) | something does not show up or does not work |
| [Development](development.md) | change the code, run the tests, use the fake NDI backend |

Quick start (generic Linux, NDI SDK already extracted):

```bash
sudo ./deploy/install.sh --ndi-lib "NDI SDK for Linux/lib/x86_64-linux-gnu"
# then open http://<server>:8080/ and create the admin account
```

---

<sub>NDI® is a registered trademark of Vizrt NDI AB. Learn more about NDI at <https://ndi.video/>. Patchbay is an independent product and is not affiliated with, sponsored or endorsed by Vizrt NDI AB.</sub>
