# Users, API keys and security

Patchbay has two kinds of credentials:

| | Web UI users | API keys |
|---|---|---|
| For | People using the browser UI | Companion, Stream Deck, scripts, other systems |
| Credential | Username + password | Random token `ndr_…` |
| Sent as | HttpOnly session cookie (after login) | `Authorization: Bearer <key>` or `X-API-Key: <key>` (`?token=` for WebSocket) |
| Can route, manage outputs/presets | yes | yes |
| Can manage users and API keys | yes | **no** (403) |
| Managed in | ⚙ Settings → Users, or the `user` CLI | ⚙ Settings → API keys |

All users have the same (full) permissions; there are no roles.

## First account

When no users exist, the web UI shows **Create admin account**, and `GET /api/health`
reports `"setup_required": true`. The setup endpoint works only while no users exist;
afterwards it returns 409.

> Whoever reaches the UI first can create the account. Create it immediately after
> installing, or keep port 8080 firewalled until you have.

## Managing users

In **⚙ Settings → Users**:

- **Add user:** username (1–64 characters: letters, digits, `.` `_` `@` `-`;
  case-insensitive unique) and password (at least 8 characters).
- **Set password:** sets another user's password and logs that user out everywhere.
- **Delete:** removes the user and ends their sessions. You cannot delete yourself or the
  last remaining user.

In **⚙ Settings → My password** you change your own password. Your other sessions are
logged out; the current one stays.

Sessions last `SESSION_DAYS` (default 30) and survive service restarts.

## API keys

In **⚙ Settings → API keys**:

1. Enter a descriptive name (e.g. `Companion studio A`) and click **Create key**.
2. **Copy the key now.** It is displayed only once; the server stores only a hash.
3. Use it in your integration:
   ```bash
   curl -H "Authorization: Bearer ndr_xxxxxxxx…" http://router:8080/api/outputs
   ```

The table shows each key's first characters, creator, creation time and **last used**
time (updated at most once per minute), so you can spot unused keys. **Revoke** takes
effect immediately.

Use one key per integration so you can revoke one without breaking the others.

### Legacy `API_KEY`

Earlier versions used a single `API_KEY` from the env file. If that variable is still
set, the value is imported at startup as an API key named **Imported from API_KEY**
(only once; restarts do not duplicate it). Revoke it in the UI when no longer needed and
delete the line from the env file — otherwise it is re-imported on the next restart.

## Password recovery (CLI)

If you lock yourself out, use the `user` command on the server. Run it as the service
user so the auth file stays owned by it, and point it at the right state directory:

```bash
# default install
sudo -u patchbay env STATE_FILE=/var/lib/patchbay/state.json \
     /opt/patchbay/venv/bin/python -m patchbay user passwd admin
sudo systemctl restart patchbay

# checkout started with run-local.sh
.venv/bin/python -m patchbay user passwd admin --auth-file state/auth.json
./run-local.sh stop && ./run-local.sh start
```

Commands:

| Command | Effect |
|---|---|
| `user list` | list usernames |
| `user add NAME` | create a user (prompts for the password twice) |
| `user passwd NAME` | set a password and log the user out everywhere |
| `user delete NAME` | delete a user (not the last one) |

Options: `--auth-file PATH` (default: `AUTH_FILE`, else `auth.json` next to `STATE_FILE`).
Restart the service afterwards; the running server reads the file at startup.

## How credentials are stored

`auth.json` (mode 0600, next to the state file unless `AUTH_FILE` is set) contains:

- **Passwords:** scrypt hashes (N=16384, r=8, p=1, random 16-byte salt).
- **Session tokens and API keys:** SHA-256 hashes only. Stealing the file does not give
  usable keys or sessions.

The file is written atomically. If it is unreadable, the service refuses to start rather
than reopening first-run setup.

## Protections

- **Login rate limit:** after 10 failed logins from one IP address within 5 minutes,
  further attempts from that address get HTTP 429 until the window passes. Failed logins
  are logged with username and IP.
- **No user enumeration:** unknown usernames take the same time to reject as wrong
  passwords.
- **CSRF / cross-site WebSocket:** the session cookie is `HttpOnly` and `SameSite=Strict`,
  and cookie-authenticated write requests and WebSocket connections whose `Origin` does
  not match the server are rejected (403). API-key requests are not affected.
- **Secure cookie over HTTPS:** behind an HTTPS reverse proxy that sends
  `X-Forwarded-Proto: https`, the cookie is marked `Secure`. Forwarded headers are only
  trusted from `127.0.0.1`, so run the proxy on the same host (or the cookie is simply
  not marked `Secure`).

## Hardening checklist

- Create the admin account right after install.
- Put the router on a management network or VLAN, or restrict port 8080 with a firewall.
- Use HTTPS via a reverse proxy (Caddy, nginx, Traefik) if the UI is reachable from
  untrusted networks; HTTP sends passwords and keys in clear text.
- One API key per integration; revoke unused keys.
- Remove `API_KEY` from the env file after migrating.
- Back up `auth.json` with the rest of the state, and keep the backup private.

### Reverse proxy example (Caddy)

```
router.example.lan {
    reverse_proxy 127.0.0.1:8080
}
```

WebSockets are proxied automatically by Caddy. For nginx, add `proxy_http_version 1.1;`
and the `Upgrade`/`Connection` headers for `/api/ws`, and pass `Host` and
`X-Forwarded-Proto`.

---

<sub>NDI® is a registered trademark of Vizrt NDI AB. Learn more about NDI at <https://ndi.video/>. Patchbay is an independent product and is not affiliated with, sponsored or endorsed by Vizrt NDI AB.</sub>
