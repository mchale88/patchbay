# Overview

Patchbay is a headless video router for NDI® sources. It runs as a background service on a Linux
server and is controlled from a web UI, a REST API and a WebSocket event stream.

## How it routes without touching video

The router is built on the **NDI SDK routing API**. Each router *output* is a virtual
NDI source that the server advertises on the network, for example:

```
STUDIO-SRV (Program)
```

When an NDI receiver (NDI Studio Monitor, OBS, vMix, a decoder, …) opens that output,
the NDI runtime tells the receiver to connect **directly to the real source** the output
currently points at. When you change the route, connected receivers are redirected to
the new source within about a second.

```
                 ┌──────────────── control (HTTP/WebSocket) ───────────────┐
                 │                                                         │
   Browser / Companion / scripts ──► Patchbay server ── mDNS adverts ──► network
                                         │  "STUDIO-SRV (Program)" → CAM-1
                                         │
   Receiver ── "open STUDIO-SRV (Program)" ─┘
   Receiver ◄══════════════ video goes directly ══════════════ CAM-1 (real source)
```

Consequences:

- **No video passes through the server.** CPU and bandwidth use are negligible, and the
  server can be small.
- **Receivers need a network path to the real sources**, not only to the router.
- Switching is a redirect, not a frame-accurate vision-mixer cut. Expect a short
  reconnect on the receiver.

## Features

- **Source discovery** over mDNS, optionally with NDI groups, unicast "extra IPs", or an
  NDI Discovery Server.
- **Outputs:** create, rename, regroup and delete virtual outputs; route or clear each one.
- **Pending routes:** route an output to a source that is offline; the route is applied
  automatically when the source appears.
- **Take mode / salvo:** stage several route changes and apply them together. The whole
  salvo is validated first, so either all changes apply or none do.
- **Presets:** snapshot the current routing under a name; recall, update or delete it.
- **Connection counts:** shows how many receivers are watching each output.
- **Loop protection:** outputs can be routed to other router outputs, but routes that
  would form a loop are rejected.
- **Self-healing outputs:** if an output cannot be advertised (for example avahi-daemon
  was not ready at boot), it is flagged as *not advertised* and retried every few seconds.
- **Persistence:** outputs, routes and presets are stored in a JSON file and restored on
  restart.
- **Security:** username/password login for the web UI; API keys for REST control,
  created and revoked in the web UI. See [authentication.md](authentication.md).

## Components

| Component | File | Role |
|---|---|---|
| NDI binding | `patchbay/ndi.py` | ctypes binding to `libndi.so.6` (find + routing APIs), plus a fake backend for tests |
| Engine | `patchbay/engine.py` | discovery thread, outputs, presets, connection polling, event fan-out |
| Store | `patchbay/store.py` | atomic JSON persistence of outputs and presets |
| Auth | `patchbay/auth.py` | users (scrypt), sessions, API keys (SHA-256), login rate limiting |
| API | `patchbay/api.py` | FastAPI app: REST, WebSocket, auth, serves the UI |
| Web UI | `patchbay/static/index.html` | single-file UI, no build step |
| Entry point | `patchbay/__main__.py` | runs the server (uvicorn) and the `user` CLI |
| Deployment | `deploy/` | installer, systemd unit, TrueNAS post-init script |

## Output names

An output is published on the network as:

```
<HOSTNAME> (<OUTPUT_PREFIX><output name>)
```

`HOSTNAME` is the server's host name in upper case (the NDI runtime adds it). For example,
on host `studio-srv` with no prefix, an output called `PGM` appears as `STUDIO-SRV (PGM)`.

## Output status

| Status | Meaning |
|---|---|
| `idle` | No source selected. |
| `live` | A source is selected and currently online. |
| `pending` | A source is selected but is offline; it is applied when it reappears. |
| `error` | The NDI output could not be created, so receivers cannot see it ("not advertised" in the UI). Retried automatically. |

---

<sub>NDI® is a registered trademark of Vizrt NDI AB. Learn more about NDI at <https://ndi.video/>. NDI tools (for example NDI Studio Monitor and NDI Access Manager) are available from <https://ndi.video/tools/>. Patchbay is an independent product and is not affiliated with, sponsored or endorsed by Vizrt NDI AB.</sub>
