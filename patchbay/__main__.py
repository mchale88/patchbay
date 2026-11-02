"""Entry point.

    python -m patchbay [--fake] [--host H] [--port P]     run the server
    python -m patchbay user list|add|passwd|delete [NAME]  manage web UI users
"""

from __future__ import annotations

import argparse
import getpass
import logging
import sys
import threading
from pathlib import Path

import uvicorn

from .api import create_app
from .auth import AuthError, AuthNotFound, AuthStore
from .config import Settings
from .engine import Engine
from .ndi import FakeBackend, NDIBackend, NDIError, Source, write_discovery_config
from .store import Store


def _fake_backend() -> FakeBackend:
    base = [
        Source("CAMERA-PC (Cam 1)", "fake://10.0.0.11"),
        Source("CAMERA-PC (Cam 2)", "fake://10.0.0.11"),
        Source("GFX (Lower Thirds)", "fake://10.0.0.20"),
        Source("PLAYOUT (Clip Player)", "fake://10.0.0.30"),
    ]
    flaky = Source("WIRELESS (Handheld)", "fake://10.0.0.40")
    be = FakeBackend(base + [flaky])

    def flap():  # exercise offline/pending handling in dev mode
        online = True
        while True:
            threading.Event().wait(20)
            online = not online
            be.set_sources(base + ([flaky] if online else []))

    threading.Thread(target=flap, daemon=True).start()
    return be


def user_cli(argv: list[str]) -> int:
    """Recovery / scripting: manage users without the web UI. Run as the
    service user (or root) so the auth file stays readable by the service."""
    s = Settings()
    ap = argparse.ArgumentParser(prog="patchbay user", description="Manage web UI users")
    ap.add_argument("action", choices=["list", "add", "passwd", "delete"])
    ap.add_argument("username", nargs="?")
    ap.add_argument("--auth-file", default=s.auth_path())
    a = ap.parse_args(argv)
    store = AuthStore(a.auth_file)
    if a.action == "list":
        for u in store.list_users():
            print(u["username"])
        return 0
    if not a.username:
        ap.error("username required")

    def ask() -> str:
        pw = getpass.getpass("New password: ")
        if pw != getpass.getpass("Repeat: "):
            raise AuthError("passwords do not match")
        return pw

    try:
        if a.action == "add":
            store.create_user(a.username, ask())
        elif a.action == "passwd":
            store.set_password(a.username, ask())
        else:
            store.delete_user(a.username)
    except (AuthError, AuthNotFound) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(f"ok ({a.auth_file}); the running service picks this up after a restart")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["user"]:
        return user_cli(argv[1:])
    s = Settings()
    ap = argparse.ArgumentParser(prog="patchbay", description="Patchbay: headless router for NDI(R) sources")
    ap.add_argument("--host", default=s.host)
    ap.add_argument("--port", type=int, default=s.port)
    ap.add_argument("--state-file", default=s.state_file)
    ap.add_argument("--fake", action="store_true", help="use a simulated NDI backend (no SDK needed)")
    args = ap.parse_args(argv)

    logging.basicConfig(
        level=s.log_level.upper(),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    log = logging.getLogger("patchbay")

    if args.fake:
        backend = _fake_backend()
        log.warning("Running with FAKE NDI backend")
    else:
        if s.ndi_discovery_server:
            write_discovery_config(Path(args.state_file).parent / "ndi-config", s.ndi_discovery_server)
            log.info("Using NDI Discovery Server %s", s.ndi_discovery_server)
        try:
            backend = NDIBackend(s.ndi_lib_path)
        except NDIError as e:
            log.error("%s", e)
            return 2

    try:
        auth = AuthStore(s.auth_path(args.state_file), session_ttl_s=s.session_days * 86400)
    except RuntimeError as e:
        log.error("%s", e)
        return 2
    if s.api_key:
        auth.import_legacy_key(s.api_key)
    if auth.setup_required():
        log.warning("No users yet: open the web UI to create the first account")

    engine = Engine(
        backend,
        Store(args.state_file),
        groups=s.ndi_groups,
        extra_ips=s.ndi_extra_ips,
        output_prefix=s.output_prefix,
    )
    app = create_app(engine, auth)
    uvicorn.run(app, host=args.host, port=args.port, log_level=s.log_level.lower(),
                proxy_headers=True, ws_ping_interval=20)
    return 0


if __name__ == "__main__":
    sys.exit(main())
