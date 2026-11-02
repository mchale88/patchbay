"""Router engine: source discovery, routing outputs, presets, events.

Thread model: one background monitor thread runs NDI discovery and polls
connection counts. API handlers call the public methods from worker threads.
All state mutations happen under a single RLock. Listeners receive event
dicts; the API layer hands them to asyncio.
"""

from __future__ import annotations

import logging
import socket
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable

from .ndi import NDIError, Source
from .store import Store

log = logging.getLogger(__name__)


class NotFound(LookupError):
    pass


class Invalid(ValueError):
    pass


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


@dataclass
class Output:
    id: str
    name: str
    groups: str | None = None
    source: str | None = None  # desired source name (persisted)
    connections: int = 0
    instance: object | None = field(default=None, repr=False)
    applied: Source | None = field(default=None, repr=False)


@dataclass
class Preset:
    id: str
    name: str
    routes: dict[str, str | None]  # output id -> source name (None = clear)


class Engine:
    def __init__(
        self,
        backend,
        store: Store,
        *,
        groups: str | None = None,
        extra_ips: str | None = None,
        output_prefix: str = "",
        poll_interval: float = 2.0,
    ):
        self.backend = backend
        self.store = store
        self.groups = groups
        self.extra_ips = extra_ips
        self.prefix = output_prefix
        self.poll_interval = poll_interval
        self.local_host = (getattr(backend, "host", None) or socket.gethostname()).split(".")[0]

        self._lock = threading.RLock()
        self._outputs: dict[str, Output] = {}
        self._presets: dict[str, Preset] = {}
        self._sources: dict[str, Source] = {}
        self._listeners: list[Callable[[dict], None]] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._finder = None
        self.started_at = time.time()

    # ------------------------------------------------------------------ #
    # lifecycle
    # ------------------------------------------------------------------ #
    def start(self) -> None:
        data = self.store.load()
        with self._lock:
            for p in data.get("presets", []):
                self._presets[p["id"]] = Preset(p["id"], p["name"], dict(p.get("routes", {})))
            for o in data.get("outputs", []):
                out = Output(o["id"], o["name"], o.get("groups"), o.get("source"))
                self._outputs[out.id] = out
                self._open(out)
        self._finder = self.backend.create_finder(self.groups, self.extra_ips)
        self._thread = threading.Thread(target=self._run, name="ndi-monitor", daemon=True)
        self._thread.start()
        log.info("Engine started with %d outputs, %d presets", len(self._outputs), len(self._presets))

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        with self._lock:
            for out in self._outputs.values():
                self._close(out)
        if self._finder:
            self._finder.close()
        self.backend.shutdown()

    def add_listener(self, fn: Callable[[dict], None]) -> None:
        self._listeners.append(fn)

    def remove_listener(self, fn: Callable[[dict], None]) -> None:
        try:
            self._listeners.remove(fn)
        except ValueError:
            pass

    # ------------------------------------------------------------------ #
    # serialisation
    # ------------------------------------------------------------------ #
    def ndi_name(self, out: Output) -> str:
        return f"{self.prefix}{out.name}"

    def full_ndi_name(self, out: Output) -> str:
        return f"{self.local_host.upper()} ({self.ndi_name(out)})"

    def _local_output_for(self, source_name: str) -> Output | None:
        key = source_name.upper()
        for o in self._outputs.values():
            if self.full_ndi_name(o).upper() == key:
                return o
        return None

    def _output_dict(self, o: Output) -> dict:
        online = o.source is not None and o.source in self._sources
        if o.instance is None:
            # The NDI routing instance could not be created, so nothing is
            # advertised and receivers cannot see this output. Retried in _run.
            status = "error"
        else:
            status = "idle" if o.source is None else ("live" if online else "pending")
        return {
            "id": o.id,
            "name": o.name,
            "ndi_name": self.full_ndi_name(o),
            "groups": o.groups,
            "source": o.source,
            "source_online": online,
            "status": status,
            "connections": o.connections,
            "advertised": o.instance is not None,
        }

    def _source_dict(self, s: Source) -> dict:
        local = self._local_output_for(s.name)
        return {"name": s.name, "url": s.url, "router_output": local.id if local else None}

    def _preset_dict(self, p: Preset) -> dict:
        return {"id": p.id, "name": p.name, "routes": dict(p.routes)}

    def list_sources(self) -> list[dict]:
        with self._lock:
            return [self._source_dict(s) for s in sorted(self._sources.values(), key=lambda s: s.name.lower())]

    def list_outputs(self) -> list[dict]:
        with self._lock:
            return [self._output_dict(o) for o in self._outputs.values()]

    def list_presets(self) -> list[dict]:
        with self._lock:
            return [self._preset_dict(p) for p in self._presets.values()]

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "type": "snapshot",
                "sources": self.list_sources(),
                "outputs": self.list_outputs(),
                "presets": self.list_presets(),
            }

    def _persist(self) -> None:
        data = {
            "version": 1,
            "outputs": [
                {"id": o.id, "name": o.name, "groups": o.groups, "source": o.source}
                for o in self._outputs.values()
            ],
            "presets": [self._preset_dict(p) for p in self._presets.values()],
        }
        try:
            self.store.save(data)
        except OSError as e:
            log.error("Failed to save state: %s", e)

    def _emit(self, kind: str) -> None:
        if kind == "sources":
            msg = {"type": "sources", "sources": self.list_sources()}
        elif kind == "outputs":
            msg = {"type": "outputs", "outputs": self.list_outputs()}
        else:
            msg = {"type": "presets", "presets": self.list_presets()}
        for fn in list(self._listeners):
            try:
                fn(msg)
            except Exception:  # pragma: no cover - listener bugs must not kill engine
                log.exception("listener failed")

    # ------------------------------------------------------------------ #
    # lookup
    # ------------------------------------------------------------------ #
    def _resolve_output(self, ref: str) -> Output:
        if ref in self._outputs:
            return self._outputs[ref]
        low = ref.lower()
        for o in self._outputs.values():
            if o.name.lower() == low or self.full_ndi_name(o).lower() == low:
                return o
        raise NotFound(f"output {ref!r} not found")

    def _resolve_preset(self, ref: str) -> Preset:
        if ref in self._presets:
            return self._presets[ref]
        low = ref.lower()
        for p in self._presets.values():
            if p.name.lower() == low:
                return p
        raise NotFound(f"preset {ref!r} not found")

    def _check_name(self, name: str, exclude: str | None = None) -> str:
        name = (name or "").strip()
        if not name:
            raise Invalid("name must not be empty")
        if len(name) > 100:
            raise Invalid("name too long (max 100)")
        for o in self._outputs.values():
            if o.id != exclude and o.name.lower() == name.lower():
                raise Invalid(f"an output named {name!r} already exists")
        return name

    # ------------------------------------------------------------------ #
    # NDI instance management (call with lock held)
    # ------------------------------------------------------------------ #
    def _open(self, out: Output, *, quiet: bool = False) -> None:
        try:
            out.instance = self.backend.create_output(self.ndi_name(out), out.groups or self.groups)
        except NDIError as e:
            # Typically avahi-daemon is not (yet) running/ready. The monitor
            # thread keeps retrying, see _retry_failed_outputs.
            if not quiet:
                log.error("%s (will retry; is avahi-daemon running?)", e)
            out.instance = None
        out.applied = None
        self._apply(out)

    def _close(self, out: Output) -> None:
        if out.instance is not None:
            out.instance.close()
            out.instance = None
        out.applied = None
        out.connections = 0

    def _apply(self, out: Output) -> None:
        """Push the desired route to the SDK if it differs from what is applied."""
        if out.instance is None:
            return
        if out.source is None:
            if out.applied is not None:
                out.instance.clear()
                out.applied = None
            return
        # Use the discovered URL when we have one; otherwise route by name and
        # let the SDK resolve it. We re-apply once the source is discovered.
        target = self._sources.get(out.source) or Source(out.source, None)
        if out.applied != target:
            if out.instance.change(target):
                out.applied = target
                log.info("Routed %s -> %s", out.name, target.name)
            else:
                log.warning("routing_change failed for %s -> %s", out.name, target.name)

    def _would_loop(self, out: Output, source_name: str) -> bool:
        seen = {out.id}
        cur = self._local_output_for(source_name)
        while cur is not None:
            if cur.id in seen:
                return True
            seen.add(cur.id)
            cur = self._local_output_for(cur.source) if cur.source else None
        return False

    # ------------------------------------------------------------------ #
    # public mutations
    # ------------------------------------------------------------------ #
    def create_output(self, name: str, groups: str | None = None, source: str | None = None) -> dict:
        with self._lock:
            out = Output(_new_id(), self._check_name(name), groups or None)
            self._outputs[out.id] = out
            self._open(out)
            if source:
                self._route(out, source)
            self._persist()
        self._emit("outputs")
        self._emit("sources")
        return self.get_output(out.id)

    def get_output(self, ref: str) -> dict:
        with self._lock:
            return self._output_dict(self._resolve_output(ref))

    def update_output(self, ref: str, name: str | None = None, groups: str | None = ...) -> dict:
        with self._lock:
            out = self._resolve_output(ref)
            new_name = self._check_name(name, exclude=out.id) if name is not None else out.name
            new_groups = out.groups if groups is ... else (groups or None)
            if new_name != out.name or new_groups != out.groups:
                # NDI names/groups are fixed at creation: recreate the instance.
                self._close(out)
                out.name, out.groups = new_name, new_groups
                self._open(out)
                self._persist()
        self._emit("outputs")
        self._emit("sources")
        return self.get_output(out.id)

    def delete_output(self, ref: str) -> None:
        with self._lock:
            out = self._resolve_output(ref)
            self._close(out)
            del self._outputs[out.id]
            for p in self._presets.values():
                p.routes.pop(out.id, None)
            self._persist()
        self._emit("outputs")
        self._emit("presets")
        self._emit("sources")

    def _route(self, out: Output, source: str | None) -> None:
        if source is not None:
            source = source.strip()
            if not source:
                source = None
        if source is not None and self._would_loop(out, source):
            raise Invalid(f"routing {out.name!r} to {source!r} would create a loop")
        out.source = source
        self._apply(out)

    def route(self, ref: str, source: str | None) -> dict:
        with self._lock:
            out = self._resolve_output(ref)
            self._route(out, source)
            self._persist()
        self._emit("outputs")
        return self.get_output(out.id)

    def route_many(self, routes: list[tuple[str, str | None]]) -> list[dict]:
        """Salvo: validate every entry first, then apply all of them."""
        with self._lock:
            resolved = [(self._resolve_output(r), s) for r, s in routes]
            previous = {o.id: o.source for o, _ in resolved}
            try:
                for out, src in resolved:
                    self._route(out, src)
            except Invalid:
                for out, _ in resolved:
                    out.source = previous[out.id]
                    self._apply(out)
                raise
            self._persist()
            result = [self._output_dict(o) for o, _ in resolved]
        self._emit("outputs")
        return result

    # presets ----------------------------------------------------------- #
    def _current_routes(self) -> dict[str, str | None]:
        return {o.id: o.source for o in self._outputs.values()}

    def create_preset(self, name: str, routes: dict[str, str | None] | None = None) -> dict:
        name = (name or "").strip()
        if not name:
            raise Invalid("preset name must not be empty")
        with self._lock:
            if any(p.name.lower() == name.lower() for p in self._presets.values()):
                raise Invalid(f"a preset named {name!r} already exists")
            if routes is None:
                routes = self._current_routes()
            else:
                routes = {self._resolve_output(k).id: v for k, v in routes.items()}
            p = Preset(_new_id(), name, routes)
            self._presets[p.id] = p
            self._persist()
        self._emit("presets")
        return self._preset_dict(p)

    def get_preset(self, ref: str) -> dict:
        with self._lock:
            return self._preset_dict(self._resolve_preset(ref))

    def update_preset(
        self,
        ref: str,
        name: str | None = None,
        routes: dict[str, str | None] | None = None,
        snapshot: bool = False,
    ) -> dict:
        with self._lock:
            p = self._resolve_preset(ref)
            if name is not None:
                name = name.strip()
                if not name:
                    raise Invalid("preset name must not be empty")
                if any(q.id != p.id and q.name.lower() == name.lower() for q in self._presets.values()):
                    raise Invalid(f"a preset named {name!r} already exists")
                p.name = name
            if snapshot:
                p.routes = self._current_routes()
            elif routes is not None:
                p.routes = {self._resolve_output(k).id: v for k, v in routes.items()}
            self._persist()
            result = self._preset_dict(p)
        self._emit("presets")
        return result

    def delete_preset(self, ref: str) -> None:
        with self._lock:
            p = self._resolve_preset(ref)
            del self._presets[p.id]
            self._persist()
        self._emit("presets")

    def recall_preset(self, ref: str) -> list[dict]:
        with self._lock:
            p = self._resolve_preset(ref)
            routes = [(oid, src) for oid, src in p.routes.items() if oid in self._outputs]
        return self.route_many(routes)

    # ------------------------------------------------------------------ #
    # monitor thread
    # ------------------------------------------------------------------ #
    def _run(self) -> None:
        last_poll = 0.0
        first = True
        while not self._stop.is_set():
            try:
                changed = self._finder.wait(1000)
                if changed or first:
                    self._refresh_sources()
                    first = False
                now = time.monotonic()
                if now - last_poll >= self.poll_interval:
                    last_poll = now
                    # Some SDK builds do not signal every change; refresh periodically too.
                    self._refresh_sources()
                    self._retry_failed_outputs()
                    self._poll_connections()
            except Exception:
                log.exception("monitor loop error")
                self._stop.wait(1)

    def _refresh_sources(self) -> None:
        found = {s.name: s for s in self._finder.sources()}
        with self._lock:
            if found == self._sources:
                return
            added = found.keys() - self._sources.keys()
            removed = self._sources.keys() - found.keys()
            self._sources = found
            for n in added:
                log.info("Source online: %s", n)
            for n in removed:
                log.info("Source offline: %s", n)
            for out in self._outputs.values():
                if out.source is not None:
                    self._apply(out)
        self._emit("sources")
        self._emit("outputs")

    def _retry_failed_outputs(self) -> None:
        recovered = False
        with self._lock:
            for out in self._outputs.values():
                if out.instance is None:
                    self._open(out, quiet=True)
                    if out.instance is not None:
                        log.info("NDI output %s is now advertised", self.full_ndi_name(out))
                        recovered = True
        if recovered:
            self._emit("outputs")
            self._emit("sources")

    def _poll_connections(self) -> None:
        changed = False
        with self._lock:
            for out in self._outputs.values():
                if out.instance is None:
                    continue
                n = out.instance.connections()
                if n != out.connections:
                    out.connections = n
                    changed = True
        if changed:
            self._emit("outputs")
