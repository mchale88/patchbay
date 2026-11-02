# REST and WebSocket API

Base URL: `http://<server>:8080`. Interactive documentation (Swagger) is served at
**`/docs`** and ReDoc at `/redoc`; the OpenAPI schema is at `/openapi.json`.

## Authentication

Create an API key in the web UI (⚙ Settings → API keys) and send it with every request:

```
Authorization: Bearer ndr_xxxxxxxx…
```
or
```
X-API-Key: ndr_xxxxxxxx…
```

The browser UI uses a session cookie instead. Endpoints that manage users and keys
(`/api/users`, `/api/keys`, `/api/auth/password`) accept **only** a logged-in session;
an API key gets 403. See [authentication.md](authentication.md).

## Conventions

- Request and response bodies are JSON; send `Content-Type: application/json`.
- Wherever a path contains `{ref}`, you can use the **id** or the **name**
  (case-insensitive). Outputs can also be addressed by their complete NDI® source name. URL-encode
  spaces: `/api/presets/Show%20open/recall`.
- Sources are identified by their complete NDI source name, e.g. `"CAMERA-PC (Cam 1)"`.

### Errors

Errors have the form `{"detail": "message"}` (422 validation errors from FastAPI have a
list in `detail`).

| Code | Meaning |
|---|---|
| 401 | Missing/invalid API key, or not logged in |
| 403 | API key used on a user/key-management endpoint; cross-origin cookie request; wrong current password |
| 404 | Output, preset, user or key not found |
| 409 | First-run setup already completed |
| 422 | Invalid input: duplicate name, empty name, routing loop, weak password, … |
| 429 | Too many failed logins from this IP |

## Objects

### Source

```json
{ "name": "CAMERA-PC (Cam 1)", "url": "10.40.0.28:5961", "router_output": null }
```

`router_output` is the output id when the source is one of this router's own outputs.

### Output

```json
{
  "id": "ac0bab01",
  "name": "PGM",
  "ndi_name": "STUDIO-SRV (PGM)",
  "groups": "Main",
  "source": "CAMERA-PC (Cam 1)",
  "source_online": true,
  "status": "live",
  "connections": 2,
  "advertised": true
}
```

| Field | Description |
|---|---|
| `groups` | NDI groups for this output, or `null` for the server default |
| `source` | selected source name, or `null` |
| `status` | `idle`, `live`, `pending` or `error` (see [overview](overview.md#output-status)) |
| `connections` | receivers currently connected (updated every ~2 s) |
| `advertised` | `false` if the NDI output could not be created (status `error`) |

### Preset

```json
{ "id": "5f2c9a10", "name": "Show open", "routes": { "ac0bab01": "CAMERA-PC (Cam 1)", "77d0e1f2": null } }
```

`routes` maps output id → source name (`null` = clear).

## Endpoints

### System

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/health` | none | `{"status","version","ndi_runtime","uptime_s","setup_required"}` |

### Sources

| Method | Path | Description |
|---|---|---|
| GET | `/api/sources` | List discovered sources, sorted by name |

### Outputs

| Method | Path | Body | Description |
|---|---|---|---|
| GET | `/api/outputs` | – | List outputs |
| POST | `/api/outputs` | `{"name", "groups"?, "source"?}` | Create (201). `groups` is comma-separated. |
| GET | `/api/outputs/{ref}` | – | Get one output |
| PATCH | `/api/outputs/{ref}` | `{"name"?, "groups"?}` | Rename / regroup. Recreates the NDI source; receivers reconnect. `"groups": ""` resets to default. |
| DELETE | `/api/outputs/{ref}` | – | Delete (204). Also removed from presets. |

### Routing

| Method | Path | Body | Description |
|---|---|---|---|
| PUT | `/api/outputs/{ref}/route` | `{"source": "NAME" \| null}` | Route (or clear with `null`). Offline sources are accepted → `pending`. |
| DELETE | `/api/outputs/{ref}/route` | – | Clear the route |
| POST | `/api/routes` | `{"routes": [{"output": "ref", "source": "NAME" \| null}, …]}` | Salvo / take: validated as a whole, applied together. Returns the updated outputs. |

### Presets

| Method | Path | Body | Description |
|---|---|---|---|
| GET | `/api/presets` | – | List presets |
| POST | `/api/presets` | `{"name", "routes"?}` | Create (201). Omit `routes` to snapshot the current routing. `routes` keys may be output ids or names. |
| GET | `/api/presets/{ref}` | – | Get one preset |
| PUT | `/api/presets/{ref}` | `{"name"?, "routes"?, "snapshot"?}` | Rename and/or replace routes; `"snapshot": true` replaces routes with the current routing. |
| DELETE | `/api/presets/{ref}` | – | Delete (204) |
| POST | `/api/presets/{ref}/recall` | – | Apply as a salvo. Returns the updated outputs. |

### Auth (web UI session)

| Method | Path | Body | Description |
|---|---|---|---|
| GET | `/api/auth/me` | – | `{"user": "name" \| null, "setup_required": bool}` (no auth needed) |
| POST | `/api/auth/setup` | `{"username", "password"}` | Create the first user and log in (201). 409 once any user exists. |
| POST | `/api/auth/login` | `{"username", "password"}` | Log in; sets the session cookie |
| POST | `/api/auth/logout` | – | End the session (204) |
| POST | `/api/auth/password` | `{"current_password", "new_password"}` | Change own password (204) — session only |

### Users (session only)

| Method | Path | Body | Description |
|---|---|---|---|
| GET | `/api/users` | – | `[{"username", "created_at"}]` |
| POST | `/api/users` | `{"username", "password"}` | Create (201) |
| PUT | `/api/users/{username}/password` | `{"password"}` | Set password; logs the user out everywhere (204) |
| DELETE | `/api/users/{username}` | – | Delete (204). Not yourself, not the last user. |

### API keys (session only)

| Method | Path | Body | Description |
|---|---|---|---|
| GET | `/api/keys` | – | `[{"id", "name", "hint", "created_at", "created_by", "last_used_at"}]` |
| POST | `/api/keys` | `{"name"}` | Create (201). The response contains `"key"` — the only time it is returned. |
| DELETE | `/api/keys/{id}` | – | Revoke (204) |

Timestamps are Unix seconds (float).

## WebSocket: `/api/ws`

Live updates for dashboards and control surfaces.

- **Auth:** API key as `?token=<key>` or `X-API-Key` header; or the browser session
  cookie (same origin only). Unauthorized connections are closed with code **4401**.
- **First message:** a snapshot of everything:
  ```json
  { "type": "snapshot", "sources": [...], "outputs": [...], "presets": [...] }
  ```
- **Then events** whenever something changes, each carrying the full current list:
  ```json
  { "type": "sources", "sources": [...] }
  { "type": "outputs", "outputs": [...] }
  { "type": "presets", "presets": [...] }
  ```
- **Keep-alive:** `{"type": "ping"}` after 25 s of silence; ignore it.
- Messages sent by the client are ignored.
- A client that falls far behind is disconnected; reconnect to get a fresh snapshot.

```bash
websocat "ws://router:8080/api/ws?token=$KEY"
```

## Examples

### curl

```bash
R=http://router:8080
K="Authorization: Bearer $KEY"
J='Content-Type: application/json'

curl -s -H "$K" $R/api/sources
curl -s -H "$K" -H "$J" -d '{"name":"Program"}' $R/api/outputs
curl -s -H "$K" -H "$J" -X PUT -d '{"source":"CAMERA-PC (Cam 1)"}' $R/api/outputs/Program/route
curl -s -H "$K" -X DELETE $R/api/outputs/Program/route
curl -s -H "$K" -H "$J" -d '{"routes":[{"output":"Program","source":"CAMERA-PC (Cam 2)"},{"output":"Aux","source":null}]}' $R/api/routes
curl -s -H "$K" -H "$J" -d '{"name":"Show open"}' $R/api/presets
curl -s -H "$K" -X POST "$R/api/presets/Show%20open/recall"
```

### Python

```python
import requests

R = "http://router:8080"
s = requests.Session()
s.headers["Authorization"] = "Bearer ndr_xxxxxxxx"

s.put(f"{R}/api/outputs/Program/route", json={"source": "CAMERA-PC (Cam 1)"}).raise_for_status()
for o in s.get(f"{R}/api/outputs").json():
    print(o["name"], o["status"], o["source"], o["connections"])
```

### Bitfocus Companion (Generic HTTP module)

1. Create an API key named e.g. `Companion`.
2. In the module's connection settings, set the base URL `http://router:8080` and add a
   header `Authorization: Bearer ndr_…`.
3. Button action **PUT**:
   - URL: `/api/outputs/Program/route`
   - Body: `{"source":"CAMERA-PC (Cam 1)"}`
   - Content type: `application/json`
4. Preset recall button: **POST** `/api/presets/Show%20open/recall` with an empty body.

### Stream Deck (HTTP request plugins)

Use the same URLs, methods, bodies and the `Authorization` header as above.

---

<sub>NDI® is a registered trademark of Vizrt NDI AB. Learn more about NDI at <https://ndi.video/>. Patchbay is an independent product and is not affiliated with, sponsored or endorsed by Vizrt NDI AB.</sub>
