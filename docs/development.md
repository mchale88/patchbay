# Development

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[test]'
```

## Run without NDI®

```bash
.venv/bin/python -m patchbay --fake --port 8080 --state-file ./dev-state/state.json
```

`--fake` uses a simulated backend with demo sources (one of them goes offline and comes
back every 20 s) and needs no SDK and no network. On first open, the UI asks you to create
an account; it is stored in `dev-state/auth.json`.

## Tests

```bash
.venv/bin/pytest -q
```

The tests use the fake backend and FastAPI's `TestClient`. They cover routing, pending
routes, loop detection, presets and salvos, persistence, recovery of failed NDI outputs,
first-run setup, login and rate limiting, API keys and their permissions, user
management, the CSRF guard, the WebSocket and the legacy key import.

## Project layout

```
patchbay/
  __main__.py     entry point: server + `user` CLI
  api.py          FastAPI routes, auth dependencies, WebSocket
  auth.py         AuthStore (users, sessions, API keys), LoginLimiter
  config.py       Settings from environment variables
  engine.py       Engine: discovery, outputs, presets, events
  ndi.py          ctypes binding to libndi + FakeBackend
  store.py        atomic JSON state store
  static/index.html   web UI (vanilla JS, no build step)
deploy/           installer, systemd unit template, TrueNAS post-init script
docs/             this documentation
tests/            pytest suite
run-local.sh      run from the checkout without systemd
vendor/           (git-ignored) optional libavahi-client copies
```

## Architecture notes

### Threads

- **uvicorn event loop:** HTTP and WebSocket handling. Sync endpoints run in the
  threadpool.
- **`ndi-monitor` thread** (engine): calls `NDIlib_find_wait_for_sources(1000)` in a loop,
  refreshes the source list, re-applies pending routes, retries outputs whose NDI instance
  failed, and polls connection counts every `poll_interval` (2 s).

All engine state is guarded by one `RLock`. Every mutation persists the state file.

### Events

The engine calls listener functions with event dicts (`sources`, `outputs`, `presets`).
The API registers a listener that hands events to the asyncio loop with
`call_soon_threadsafe` and fans them out to one queue per WebSocket client. Slow clients
(queue > 200) are dropped and resync on reconnect.

### Routing semantics

- `Output.source` is the desired route (persisted). `Output.applied` is what was last
  pushed to the SDK. `_apply()` pushes only when they differ, using the discovered URL
  when available, otherwise routing by name.
- Rename/regroup destroys and recreates the NDI routing instance (NDI names and groups
  are fixed at creation).
- A route to another router output is allowed unless following the chain loops back.

### NDI binding

`ndi.py` binds only the find and routing APIs. Encoded C strings are kept referenced on
the Python objects for as long as the SDK may use them. `FakeBackend` implements the same
interface (`create_finder`, `create_output`, `shutdown`) and makes its outputs visible as
sources, like the real runtime does.

### Auth

- `AuthStore` keeps everything in one JSON file, written atomically with mode 0600.
- Passwords: `hashlib.scrypt`. Session tokens and API keys: random tokens, stored as
  SHA-256.
- `principal()` in `api.py` resolves the caller: API key header → key; otherwise session
  cookie (with an Origin check for writes). `require_user()` additionally rejects API keys.

## Adding an API endpoint

1. Add the engine method (take the lock, mutate, `_persist()`, then `_emit(...)` outside
   the lock).
2. Add the route in `create_app()` with `dependencies=deps` (any authenticated caller) or
   `Depends(require_user)` (web UI users only).
3. Add a test in `tests/test_router.py`.
4. Document it in `docs/api.md`.

## Style

- Python 3.10+, type hints, no extra runtime dependencies beyond FastAPI/uvicorn.
- The web UI stays a single file without a build step.

---

<sub>NDI® is a registered trademark of Vizrt NDI AB. Learn more about NDI at <https://ndi.video/>. Patchbay is an independent product and is not affiliated with, sponsored or endorsed by Vizrt NDI AB.</sub>
