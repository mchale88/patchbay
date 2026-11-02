# Troubleshooting

Start with the log: `journalctl -u patchbay -n 100` (service) or `state/router.log`
(`run-local.sh`). Then check `curl -s http://localhost:8080/api/health`.

## The service does not start

| Log message | Cause / fix |
|---|---|
| `Could not load the NDI runtime (libndi.so.6)` | Set `NDI_LIB_PATH` to the library or its directory, or reinstall with `--ndi-lib`. |
| `libavahi-client.so.3: cannot open shared object file` | Install `libavahi-client3`, or put the libs in `vendor/lib` and re-run the installer (see [installation](installation.md#avahi)). Check with `ldd /opt/patchbay/lib/libndi.so.6 \| grep 'not found'`. |
| `NDIlib_initialize() failed` | CPU lacks SSE4.2 or the runtime is incompatible. |
| `Could not read auth file …` | `auth.json` is corrupt or unreadable. Fix ownership/permissions, or restore from backup. The service refuses to start rather than reopening first-run setup. |
| `address already in use` | Another app uses the port. Change `PORT` in the env file. |
| `Permission denied` on state | `sudo chown -R patchbay:patchbay /var/lib/patchbay` |

## No sources are listed

- Is `avahi-daemon` running? `systemctl status avahi-daemon`
- Is UDP 5353 allowed by the host firewall?
- Are the sources on the same subnet/VLAN? mDNS does not cross routers. Use
  `NDI_EXTRA_IPS=<source IPs>`, an mDNS reflector on your router, or an NDI® Discovery
  Server (`NDI_DISCOVERY_SERVER`).
- Are the sources in a different NDI group? Set `NDI_GROUPS=public,<group>`.
- Running in a container/VM? It needs bridged/host networking; NAT breaks mDNS.

## Outputs do not show up on receivers

Work through these in order.

1. **Is the output advertised?** In the UI the card must not say *not advertised*
   (API: `"advertised": true`). If it does, `NDIlib_routing_create` failed — usually
   because `avahi-daemon` was not running or not ready when the router started. The
   router retries every few seconds and logs `NDI output … is now advertised` when it
   recovers. If it never does, check avahi and restart the router.
2. **Does the router see its own output?** The *NDI sources* panel should list
   `<HOSTNAME> (<output>)` marked *router*. If the output is in a non-default group, it
   only shows up if `NDI_GROUPS` includes that group.
3. **Groups on the receiver.** NDI receivers only see the `public` group by default. If
   the output has groups (e.g. `Main`), either add that group on the receiver (NDI Access
   Manager → Receive groups) or clear the output's groups (Edit → empty groups field).
4. **Subnets.** The router advertises with mDNS from its own subnet. Receivers on other
   subnets need mDNS reflection in both directions, the router's IP in their NDI Access
   Manager "extra IPs", or a shared Discovery Server.
5. **Firewall on the router host.** Receivers make a short TCP connection to the router's
   NDI port (5960+) to learn where to go; allow TCP 5960–5990 in.

## Output is visible but shows no video

- Status `pending`: the selected source is offline; it is applied when it comes back.
- Status `idle`: no source selected.
- The receiver must reach the **real source** directly (routing redirects it). Check the
  receiver can open the source itself.
- 👁 count 0 while a receiver is open means it never reached the router; see point 5 above.

## Web UI problems

| Symptom | Fix |
|---|---|
| Login says *too many failed logins* | 10 failures from your IP within 5 min; wait 5 minutes. |
| Forgot password | Use the `user passwd` CLI, then restart: [authentication.md](authentication.md#password-recovery-cli). |
| Header shows *reconnecting…* | Server down or network issue; the UI reconnects automatically. |
| Header shows *logged out* after a restart of the browser | Session expired (`SESSION_DAYS`) or your password was changed elsewhere. Log in again. |
| *cross-origin request rejected* behind a reverse proxy | The proxy must forward the original `Host` header (or `X-Forwarded-Host`). |
| A new API key was not copied | It cannot be shown again. Revoke it and create a new one. |

## API problems

| Response | Cause |
|---|---|
| 401 `invalid API key` | Key revoked or mistyped. Check ⚙ Settings → API keys (last used). |
| 403 `API keys cannot manage users or keys` | Use a web UI login for `/api/users`, `/api/keys`. |
| 422 `would create a loop` | The chain of router outputs would point back to itself. |
| 404 on a name with spaces | URL-encode it (`Show%20open`). |

## Collecting diagnostics

```bash
curl -s http://localhost:8080/api/health
journalctl -u patchbay -n 200 --no-pager
systemctl status avahi-daemon --no-pager
ldd /opt/patchbay/lib/libndi.so.6 | grep 'not found'
ss -tlnp | grep -E ':8080|:59[6-9][0-9]'      # web port and NDI listener ports
ip -4 -br addr
```

---

<sub>NDI® is a registered trademark of Vizrt NDI AB. Learn more about NDI at <https://ndi.video/>. Patchbay is an independent product and is not affiliated with, sponsored or endorsed by Vizrt NDI AB.</sub>
