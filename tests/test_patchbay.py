import time

import pytest
from fastapi.testclient import TestClient

from patchbay.api import create_app
from patchbay.engine import Engine, Invalid, NotFound
from patchbay.ndi import FakeBackend, Source
from patchbay.store import Store

CAM1 = Source("CAM-PC (Cam 1)", "fake://1")
CAM2 = Source("CAM-PC (Cam 2)", "fake://2")


def wait_for(cond, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.02)
    raise AssertionError("condition not met")


@pytest.fixture
def setup(tmp_path):
    be = FakeBackend([CAM1, CAM2])
    store = Store(tmp_path / "state.json")
    eng = Engine(be, store, poll_interval=0.05)
    eng.start()
    wait_for(lambda: len(eng.list_sources()) == 2)
    yield be, eng, store
    eng.stop()


def test_route_and_clear(setup):
    be, eng, _ = setup
    o = eng.create_output("Program")
    assert o["status"] == "idle"
    assert o["ndi_name"] == "ROUTER (Program)"
    eng.route("program", CAM1.name)  # lookup by name, case-insensitive
    inst = be.outputs["Program"]
    assert inst.target == CAM1
    assert eng.get_output(o["id"])["status"] == "live"
    eng.route(o["id"], None)
    assert inst.target is None
    assert eng.get_output(o["id"])["status"] == "idle"


def test_offline_source_is_pending_then_applied(setup):
    be, eng, _ = setup
    o = eng.create_output("Aux")
    eng.route(o["id"], "LATE (Cam 9)")
    assert eng.get_output(o["id"])["status"] == "pending"
    # routed by name only until discovered
    assert be.outputs["Aux"].target == Source("LATE (Cam 9)", None)
    be.set_sources([CAM1, CAM2, Source("LATE (Cam 9)", "fake://9")])
    wait_for(lambda: eng.get_output(o["id"])["status"] == "live")
    assert be.outputs["Aux"].target.url == "fake://9"


def test_router_outputs_flagged_and_loops_rejected(setup):
    be, eng, _ = setup
    a = eng.create_output("A")
    b = eng.create_output("B")
    wait_for(lambda: any(s["router_output"] for s in eng.list_sources()))
    with pytest.raises(Invalid):
        eng.route(a["id"], "ROUTER (A)")
    eng.route(b["id"], "ROUTER (A)")
    with pytest.raises(Invalid):
        eng.route(a["id"], "ROUTER (B)")


def test_duplicate_and_missing(setup):
    _, eng, _ = setup
    eng.create_output("X")
    with pytest.raises(Invalid):
        eng.create_output("x")
    with pytest.raises(NotFound):
        eng.route("nope", None)


def test_rename_recreates_instance(setup):
    be, eng, _ = setup
    o = eng.create_output("Old", source=CAM1.name)
    eng.update_output(o["id"], name="New")
    assert "Old" not in be.outputs
    assert be.outputs["New"].target == CAM1


def test_presets_and_salvo(setup):
    be, eng, _ = setup
    a = eng.create_output("A", source=CAM1.name)
    b = eng.create_output("B", source=CAM2.name)
    p = eng.create_preset("Normal")
    eng.route_many([(a["id"], CAM2.name), (b["id"], None)])
    assert be.outputs["A"].target == CAM2 and be.outputs["B"].target is None
    eng.recall_preset("normal")
    assert be.outputs["A"].target == CAM1 and be.outputs["B"].target == CAM2
    eng.delete_output(b["id"])
    assert list(eng.get_preset(p["id"])["routes"]) == [a["id"]]


def test_salvo_validation_is_all_or_nothing(setup):
    _, eng, _ = setup
    a = eng.create_output("A", source=CAM1.name)
    with pytest.raises(NotFound):
        eng.route_many([(a["id"], CAM2.name), ("missing", CAM1.name)])
    assert eng.get_output(a["id"])["source"] == CAM1.name


def test_persistence_round_trip(tmp_path):
    store = Store(tmp_path / "s.json")
    be = FakeBackend([CAM1])
    eng = Engine(be, store)
    eng.start()
    o = eng.create_output("Program", source=CAM1.name)
    eng.create_preset("P1")
    eng.stop()

    be2 = FakeBackend([CAM1])
    eng2 = Engine(be2, store)
    eng2.start()
    try:
        assert eng2.get_output(o["id"])["source"] == CAM1.name
        assert be2.outputs["Program"].target is not None
        assert eng2.list_presets()[0]["name"] == "P1"
    finally:
        eng2.stop()


def test_corrupt_state_starts_empty(tmp_path):
    p = tmp_path / "s.json"
    p.write_text("{not json")
    assert Store(p).load()["outputs"] == []
    assert (tmp_path / "s.json.corrupt").exists()


# ------------------------------------------------------------------ API -- #
from patchbay.auth import AuthStore


@pytest.fixture
def env(tmp_path):
    be = FakeBackend([CAM1, CAM2])
    eng = Engine(be, Store(tmp_path / "state.json"), poll_interval=0.05)
    auth = AuthStore(tmp_path / "auth.json")
    app = create_app(eng, auth)
    with TestClient(app) as c:
        wait_for(lambda: len(eng.list_sources()) == 2)
        yield c, auth


@pytest.fixture
def client(env):
    """Logged-in web client plus an API key in H."""
    c, auth = env
    assert c.post("/api/auth/setup", json={"username": "admin", "password": "password1"}).status_code == 201
    key = c.post("/api/keys", json={"name": "test"}).json()["key"]
    H.clear()
    H["Authorization"] = "Bearer " + key
    return c


H: dict = {}


def test_first_run_setup(env):
    c, auth = env
    assert c.get("/api/health").json()["setup_required"] is True
    assert c.get("/api/auth/me").json() == {"user": None, "setup_required": True}
    assert c.get("/api/outputs").status_code == 401
    assert c.post("/api/auth/setup", json={"username": "admin", "password": "short"}).status_code == 422
    assert c.post("/api/auth/setup", json={"username": "admin", "password": "password1"}).status_code == 201
    assert c.get("/api/auth/me").json()["user"] == "admin"
    assert c.get("/api/outputs").status_code == 200
    # setup only once, even for a fresh client
    c.cookies.clear()
    assert c.post("/api/auth/setup", json={"username": "evil", "password": "password1"}).status_code == 409
    assert auth.setup_required() is False


def test_login_logout_and_rate_limit(client):
    client.post("/api/auth/logout")
    assert client.get("/api/outputs").status_code == 401
    assert client.post("/api/auth/login", json={"username": "admin", "password": "nope"}).status_code == 401
    assert client.post("/api/auth/login", json={"username": "ADMIN", "password": "password1"}).status_code == 200
    assert client.get("/api/outputs").status_code == 200
    client.post("/api/auth/logout")
    for _ in range(10):
        client.post("/api/auth/login", json={"username": "admin", "password": "nope"})
    r = client.post("/api/auth/login", json={"username": "admin", "password": "password1"})
    assert r.status_code == 429


def test_api_keys(client):
    client.cookies.clear()  # key-only from here
    assert client.get("/api/outputs").status_code == 401
    assert client.get("/api/outputs", headers={"X-API-Key": "wrong"}).status_code == 401
    assert client.get("/api/outputs", headers={"X-API-Key": H["Authorization"][7:]}).status_code == 200
    assert client.get("/api/outputs", headers=H).status_code == 200
    # keys cannot manage users or keys
    assert client.get("/api/keys", headers=H).status_code == 403
    assert client.post("/api/users", json={"username": "x", "password": "password1"}, headers=H).status_code == 403
    # revoke
    client.post("/api/auth/login", json={"username": "admin", "password": "password1"})
    keys = client.get("/api/keys").json()
    assert len(keys) == 1 and "hash" not in keys[0] and "key" not in keys[0] and keys[0]["last_used_at"]
    assert client.delete(f"/api/keys/{keys[0]['id']}").status_code == 204
    client.cookies.clear()
    assert client.get("/api/outputs", headers=H).status_code == 401


def test_users_and_passwords(client):
    assert client.post("/api/users", json={"username": "op", "password": "password2"}).status_code == 201
    assert client.post("/api/users", json={"username": "OP", "password": "password2"}).status_code == 422
    assert [u["username"] for u in client.get("/api/users").json()] == ["admin", "op"]
    assert client.delete("/api/users/admin").status_code == 422  # self
    # change own password: wrong current, then right
    assert client.post("/api/auth/password", json={"current_password": "x", "new_password": "password3"}).status_code == 403
    assert client.post("/api/auth/password", json={"current_password": "password1", "new_password": "password3"}).status_code == 204
    assert client.get("/api/users").status_code == 200  # this session survives
    client.cookies.clear()
    assert client.post("/api/auth/login", json={"username": "admin", "password": "password1"}).status_code == 401
    assert client.post("/api/auth/login", json={"username": "op", "password": "password2"}).status_code == 200
    assert client.delete("/api/users/admin").status_code == 204
    assert client.delete("/api/users/op").status_code == 422  # self / last user


def test_cookie_csrf_guard(client):
    evil = {"Origin": "http://evil.example"}
    assert client.post("/api/outputs", json={"name": "X"}, headers=evil).status_code == 403
    assert client.post("/api/outputs", json={"name": "X"}, headers={"Origin": "http://testserver"}).status_code == 201


def test_auth_file_has_no_secrets(client, tmp_path):
    import json
    raw = (tmp_path / "auth.json").read_text()
    assert "password1" not in raw and H["Authorization"][7:] not in raw
    assert oct((tmp_path / "auth.json").stat().st_mode)[-3:] == "600"
    assert json.loads(raw)["users"]["admin"]["password"].startswith("scrypt$")


def test_legacy_key_import(tmp_path):
    a = AuthStore(tmp_path / "auth.json")
    a.import_legacy_key("oldsecret")
    a.import_legacy_key("oldsecret")  # idempotent across restarts
    assert len(a.list_keys()) == 1
    assert a.check_key("oldsecret").name == "Imported from API_KEY"


def test_api_flow(client):
    r = client.post("/api/outputs", json={"name": "Program"}, headers=H)
    assert r.status_code == 201
    oid = r.json()["id"]
    r = client.put("/api/outputs/Program/route", json={"source": CAM1.name}, headers=H)
    assert r.json()["status"] == "live"
    assert client.post("/api/presets", json={"name": "Show"}, headers=H).status_code == 201
    client.delete(f"/api/outputs/{oid}/route", headers=H)
    r = client.post("/api/presets/Show/recall", headers=H)
    assert r.json()[0]["source"] == CAM1.name
    assert client.post("/api/outputs", json={"name": "program"}, headers=H).status_code == 422
    assert client.get("/api/outputs/nope", headers=H).status_code == 404
    r = client.post("/api/routes", json={"routes": [{"output": oid, "source": CAM2.name}]}, headers=H)
    assert r.json()[0]["source"] == CAM2.name
    assert client.delete(f"/api/outputs/{oid}", headers=H).status_code == 204


def test_websocket(client):
    from starlette.websockets import WebSocketDisconnect

    key = H["Authorization"][7:]
    with client.websocket_connect("/api/ws") as ws:  # session cookie
        assert ws.receive_json()["type"] == "snapshot"
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/api/ws", headers={"Origin": "http://evil.example"}) as ws:
            ws.receive_json()
    client.cookies.clear()
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/api/ws") as ws:
            ws.receive_json()
    with client.websocket_connect(f"/api/ws?token={key}") as ws:
        snap = ws.receive_json()
        assert snap["type"] == "snapshot" and len(snap["sources"]) == 2
        client.post("/api/outputs", json={"name": "Live"}, headers=H)
        for _ in range(10):
            m = ws.receive_json()
            if m["type"] == "outputs" and m["outputs"]:
                assert m["outputs"][0]["name"] == "Live"
                break
        else:
            raise AssertionError("no outputs event")


def test_failed_output_is_flagged_and_retried(tmp_path):
    """routing_create can fail if avahi-daemon is not ready yet at startup;
    the output must be reported as an error and recreated once possible."""
    from patchbay.ndi import NDIError

    class FlakyBackend(FakeBackend):
        fail = True

        def create_output(self, ndi_name, groups):
            if self.fail:
                raise NDIError(f"NDIlib_routing_create failed for {ndi_name!r}")
            return super().create_output(ndi_name, groups)

    be = FlakyBackend([CAM1], host="ROUTER")
    eng = Engine(be, Store(tmp_path / "s.json"), poll_interval=0.05)
    eng.start()
    try:
        o = eng.create_output("PGM", source=CAM1.name)
        assert o["status"] == "error" and o["advertised"] is False
        be.fail = False
        wait_for(lambda: eng.get_output(o["id"])["status"] == "live")
        assert eng.get_output(o["id"])["advertised"] is True
        assert be.outputs["PGM"].target == CAM1
    finally:
        eng.stop()
