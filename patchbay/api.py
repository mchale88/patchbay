"""FastAPI app: REST API, WebSocket event stream, user/API-key auth, web UI."""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from . import __version__
from .auth import AuthError, AuthNotFound, AuthStore, LoginLimiter, Principal
from .engine import Engine, Invalid, NotFound

log = logging.getLogger(__name__)
STATIC = Path(__file__).parent / "static"
COOKIE = "patchbay_session"


# ---------------------------------------------------------------- models -- #
class OutputCreate(BaseModel):
    name: str = Field(..., examples=["Program"])
    groups: str | None = Field(None, description="Comma-separated NDI groups")
    source: str | None = Field(None, description="Initial source name")


class OutputUpdate(BaseModel):
    name: str | None = None
    groups: str | None = Field(None, description="Set to empty string for default groups")


class RouteBody(BaseModel):
    source: str | None = Field(..., description="NDI source name, or null to clear",
                               examples=["CAMERA-PC (Cam 1)"])


class RouteItem(BaseModel):
    output: str = Field(..., description="Output id or name")
    source: str | None


class RoutesBody(BaseModel):
    routes: list[RouteItem]


class PresetCreate(BaseModel):
    name: str
    routes: dict[str, str | None] | None = Field(
        None, description="output id/name -> source. Omit to snapshot current routes.")


class PresetUpdate(BaseModel):
    name: str | None = None
    routes: dict[str, str | None] | None = None
    snapshot: bool = Field(False, description="Replace routes with the current routing")


class Credentials(BaseModel):
    username: str
    password: str


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


class PasswordSet(BaseModel):
    password: str


class KeyCreate(BaseModel):
    name: str = Field(..., examples=["Companion"])


def _same_origin(headers) -> bool:
    """CSRF / cross-site WebSocket guard for cookie-authenticated requests.
    Browsers always send Origin on cross-origin and WebSocket requests."""
    origin = headers.get("origin")
    if not origin:
        return True
    host = headers.get("x-forwarded-host") or headers.get("host") or ""
    return urlsplit(origin).netloc.lower() == host.split(",")[0].strip().lower()


_key_header = APIKeyHeader(name="X-API-Key", auto_error=False,
                           description="API key created in the web UI (Settings → API keys)")
_bearer = HTTPBearer(auto_error=False, description="API key as a Bearer token")


# ------------------------------------------------------------------ app -- #
def create_app(engine: Engine, auth: AuthStore) -> FastAPI:
    clients: set[asyncio.Queue] = set()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        loop = asyncio.get_running_loop()

        def on_event(msg: dict) -> None:
            def push():
                for q in list(clients):
                    if q.qsize() > 200:  # slow client: drop it, it will resync on reconnect
                        clients.discard(q)
                        q.put_nowait(None)
                    else:
                        q.put_nowait(msg)
            loop.call_soon_threadsafe(push)

        engine.add_listener(on_event)
        engine.start()
        try:
            yield
        finally:
            engine.remove_listener(on_event)
            for q in list(clients):
                q.put_nowait(None)
            await asyncio.to_thread(engine.stop)

    app = FastAPI(
        title="Patchbay",
        version=__version__,
        description="Patchbay is a headless router for NDI® sources, built on the NDI SDK "
                    "routing API. Outputs are virtual NDI "
                    "sources that redirect receivers to the selected source; no video passes "
                    "through the server. Authenticate with an API key created in the web UI "
                    "(Settings → API keys), sent as `Authorization: Bearer <key>` or "
                    "`X-API-Key: <key>`. User and API-key management requires a web UI login.\n\n"
                    "NDI® is a registered trademark of Vizrt NDI AB. Learn about NDI at "
                    "[ndi.video](https://ndi.video/). Patchbay is not affiliated with or "
                    "endorsed by Vizrt NDI AB.",
        lifespan=lifespan,
    )

    limiter = LoginLimiter()

    def _unauth(msg: str = "not authenticated") -> HTTPException:
        return HTTPException(status.HTTP_401_UNAUTHORIZED, msg, headers={"WWW-Authenticate": "Bearer"})

    def principal(
        request: Request,
        key: str | None = Depends(_key_header),
        bearer: HTTPAuthorizationCredentials | None = Depends(_bearer),
    ) -> Principal:
        token = key or (bearer.credentials if bearer else None)
        if token:
            p = auth.check_key(token)
            if p is None:
                raise _unauth("invalid API key")
            return p
        user = auth.session_user(request.cookies.get(COOKIE))
        if user is None:
            raise _unauth()
        if request.method not in ("GET", "HEAD", "OPTIONS") and not _same_origin(request.headers):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "cross-origin request rejected")
        return Principal("session", user)

    def require_user(p: Principal = Depends(principal)) -> Principal:
        if p.kind != "session":
            raise HTTPException(status.HTTP_403_FORBIDDEN,
                                "API keys cannot manage users or keys; log in to the web UI")
        return p

    def _set_cookie(request: Request, response: Response, token: str) -> None:
        response.set_cookie(COOKIE, token, max_age=auth.session_ttl_s, httponly=True,
                            samesite="strict", secure=request.url.scheme == "https", path="/")

    @app.exception_handler(AuthError)
    async def _authinv(_, exc: AuthError):
        return JSONResponse({"detail": str(exc)}, status_code=422)

    @app.exception_handler(AuthNotFound)
    async def _authnf(_, exc: AuthNotFound):
        return JSONResponse({"detail": str(exc).strip("'\"")}, status_code=404)

    @app.exception_handler(NotFound)
    async def _nf(_, exc: NotFound):
        return JSONResponse({"detail": str(exc).strip("'\"")}, status_code=404)

    @app.exception_handler(Invalid)
    async def _inv(_, exc: Invalid):
        return JSONResponse({"detail": str(exc)}, status_code=422)

    deps = [Depends(principal)]

    # -------------------------------------------------------------- UI -- #
    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})

    # ---------------------------------------------------------- health -- #
    @app.get("/api/health", tags=["system"])
    def health():
        return {
            "status": "ok",
            "version": __version__,
            "ndi_runtime": getattr(engine.backend, "version", "unknown"),
            "uptime_s": round(time.time() - engine.started_at),
            "setup_required": auth.setup_required(),
        }

    # ------------------------------------------------------------ auth -- #
    @app.get("/api/auth/me", tags=["auth"])
    def me(request: Request):
        """Current web UI login (null if not logged in) and whether first-run setup is needed."""
        return {"user": auth.session_user(request.cookies.get(COOKIE)),
                "setup_required": auth.setup_required()}

    @app.post("/api/auth/setup", tags=["auth"], status_code=201)
    def setup(body: Credentials, request: Request, response: Response):
        """Create the first user account. Only possible while no users exist."""
        if not _same_origin(request.headers):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "cross-origin request rejected")
        try:
            u = auth.setup(body.username, body.password)
        except PermissionError:
            raise HTTPException(status.HTTP_409_CONFLICT, "setup already completed")
        _set_cookie(request, response, auth.create_session(u["username"]))
        return {"user": u["username"]}

    @app.post("/api/auth/login", tags=["auth"])
    def login(body: Credentials, request: Request, response: Response):
        ip = request.client.host if request.client else "?"
        if not _same_origin(request.headers):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "cross-origin request rejected")
        if limiter.blocked(ip):
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                                "too many failed logins; try again in a few minutes")
        user = auth.check_login(body.username, body.password)
        if user is None:
            limiter.fail(ip)
            log.warning("Failed login for %r from %s", body.username, ip)
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid username or password")
        limiter.reset(ip)
        log.info("Login: %s from %s", user, ip)
        _set_cookie(request, response, auth.create_session(user))
        return {"user": user}

    @app.post("/api/auth/logout", tags=["auth"], status_code=204)
    def logout(request: Request, response: Response):
        auth.end_session(request.cookies.get(COOKIE))
        response.delete_cookie(COOKIE, path="/")

    @app.post("/api/auth/password", tags=["auth"], status_code=204)
    def change_password(body: PasswordChange, request: Request, p: Principal = Depends(require_user)):
        """Change your own password. Logs out your other sessions."""
        if auth.check_login(p.name, body.current_password) is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "current password is wrong")
        auth.set_password(p.name, body.new_password, keep_session=request.cookies.get(COOKIE))

    # ----------------------------------------------------------- users -- #
    @app.get("/api/users", tags=["users"], dependencies=[Depends(require_user)])
    def users():
        return auth.list_users()

    @app.post("/api/users", tags=["users"], dependencies=[Depends(require_user)], status_code=201)
    def create_user(body: Credentials):
        return auth.create_user(body.username, body.password)

    @app.put("/api/users/{username}/password", tags=["users"], status_code=204,
             dependencies=[Depends(require_user)])
    def reset_password(username: str, body: PasswordSet):
        """Set another user's password (logs that user out everywhere)."""
        auth.set_password(username, body.password)

    @app.delete("/api/users/{username}", tags=["users"], status_code=204)
    def delete_user(username: str, p: Principal = Depends(require_user)):
        if username.lower() == p.name.lower():
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "you cannot delete your own account")
        auth.delete_user(username)

    # -------------------------------------------------------- API keys -- #
    @app.get("/api/keys", tags=["api keys"], dependencies=[Depends(require_user)])
    def keys():
        return auth.list_keys()

    @app.post("/api/keys", tags=["api keys"], status_code=201)
    def create_key(body: KeyCreate, p: Principal = Depends(require_user)):
        """Create an API key. The `key` value is returned only in this response."""
        return auth.create_key(body.name, p.name)

    @app.delete("/api/keys/{key_id}", tags=["api keys"], status_code=204,
                dependencies=[Depends(require_user)])
    def delete_key(key_id: str):
        auth.delete_key(key_id)

    # --------------------------------------------------------- sources -- #
    @app.get("/api/sources", tags=["sources"], dependencies=deps)
    def sources():
        return engine.list_sources()

    # --------------------------------------------------------- outputs -- #
    @app.get("/api/outputs", tags=["outputs"], dependencies=deps)
    def outputs():
        return engine.list_outputs()

    @app.post("/api/outputs", tags=["outputs"], dependencies=deps, status_code=201)
    def create_output(body: OutputCreate):
        return engine.create_output(body.name, body.groups, body.source)

    @app.get("/api/outputs/{ref}", tags=["outputs"], dependencies=deps)
    def get_output(ref: str):
        return engine.get_output(ref)

    @app.patch("/api/outputs/{ref}", tags=["outputs"], dependencies=deps)
    def update_output(ref: str, body: OutputUpdate):
        fields = body.model_fields_set
        return engine.update_output(
            ref,
            name=body.name if "name" in fields else None,
            groups=body.groups if "groups" in fields else ...,
        )

    @app.delete("/api/outputs/{ref}", tags=["outputs"], dependencies=deps, status_code=204)
    def delete_output(ref: str):
        engine.delete_output(ref)

    @app.put("/api/outputs/{ref}/route", tags=["routing"], dependencies=deps)
    def route(ref: str, body: RouteBody):
        return engine.route(ref, body.source)

    @app.delete("/api/outputs/{ref}/route", tags=["routing"], dependencies=deps)
    def clear_route(ref: str):
        return engine.route(ref, None)

    @app.post("/api/routes", tags=["routing"], dependencies=deps)
    def route_many(body: RoutesBody):
        """Apply several routes at once (a "take" / salvo). All-or-nothing validation."""
        return engine.route_many([(r.output, r.source) for r in body.routes])

    # --------------------------------------------------------- presets -- #
    @app.get("/api/presets", tags=["presets"], dependencies=deps)
    def presets():
        return engine.list_presets()

    @app.post("/api/presets", tags=["presets"], dependencies=deps, status_code=201)
    def create_preset(body: PresetCreate):
        return engine.create_preset(body.name, body.routes)

    @app.get("/api/presets/{ref}", tags=["presets"], dependencies=deps)
    def get_preset(ref: str):
        return engine.get_preset(ref)

    @app.put("/api/presets/{ref}", tags=["presets"], dependencies=deps)
    def update_preset(ref: str, body: PresetUpdate):
        return engine.update_preset(ref, body.name, body.routes, body.snapshot)

    @app.delete("/api/presets/{ref}", tags=["presets"], dependencies=deps, status_code=204)
    def delete_preset(ref: str):
        engine.delete_preset(ref)

    @app.post("/api/presets/{ref}/recall", tags=["presets"], dependencies=deps)
    def recall_preset(ref: str):
        return engine.recall_preset(ref)

    # ------------------------------------------------------- websocket -- #
    @app.websocket("/api/ws")
    async def ws(websocket: WebSocket):
        token = websocket.query_params.get("token") or websocket.headers.get("x-api-key")
        if token:
            ok = auth.check_key(token) is not None
        else:
            ok = (auth.session_user(websocket.cookies.get(COOKIE)) is not None
                  and _same_origin(websocket.headers))
        if not ok:
            await websocket.close(code=4401, reason="unauthorized")
            return
        await websocket.accept()
        q: asyncio.Queue = asyncio.Queue()
        clients.add(q)
        try:
            await websocket.send_json(await asyncio.to_thread(engine.snapshot))

            async def drain_incoming():
                while True:  # ignore client messages; detect disconnect
                    await websocket.receive_text()

            reader = asyncio.create_task(drain_incoming())
            try:
                while True:
                    getter = asyncio.create_task(q.get())
                    done, _ = await asyncio.wait({getter, reader}, timeout=25,
                                                 return_when=asyncio.FIRST_COMPLETED)
                    if reader in done:
                        getter.cancel()
                        break
                    if getter in done:
                        msg = getter.result()
                        if msg is None:
                            break
                        await websocket.send_json(msg)
                    else:
                        getter.cancel()
                        await websocket.send_json({"type": "ping"})
            finally:
                reader.cancel()
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            clients.discard(q)
            try:
                await websocket.close()
            except RuntimeError:
                pass

    return app
