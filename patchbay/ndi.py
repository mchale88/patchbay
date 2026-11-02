"""Minimal ctypes binding to the NDI SDK (v6) find + routing APIs.

Only the pieces a routing-only server needs are bound. No video ever passes
through this process: an NDI "routing" instance is a virtual source that
redirects receivers to whichever real source it currently points at.

A FakeBackend with the same interface is provided for tests and dev mode.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import json
import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Source:
    name: str
    url: str | None = None


class NDIError(RuntimeError):
    pass


# --------------------------------------------------------------------------- #
# C structures (Processing.NDI.Find.h / Processing.NDI.Routing.h)
# --------------------------------------------------------------------------- #
class _Source(ctypes.Structure):
    # p_url_address is a union with the deprecated p_ip_address; same layout.
    _fields_ = [("p_ndi_name", ctypes.c_char_p), ("p_url_address", ctypes.c_char_p)]


class _FindCreate(ctypes.Structure):
    _fields_ = [
        ("show_local_sources", ctypes.c_bool),
        ("p_groups", ctypes.c_char_p),
        ("p_extra_ips", ctypes.c_char_p),
    ]


class _RoutingCreate(ctypes.Structure):
    _fields_ = [("p_ndi_name", ctypes.c_char_p), ("p_groups", ctypes.c_char_p)]


def _enc(s: str | None) -> bytes | None:
    return s.encode("utf-8") if s else None


def _candidate_paths(explicit: str | None) -> list[str]:
    paths: list[str] = []
    if explicit:
        p = Path(explicit)
        paths += [str(p / "libndi.so.6"), str(p / "libndi.so")] if p.is_dir() else [str(p)]
    rt = os.environ.get("NDI_RUNTIME_DIR_V6")
    if rt:
        paths += [str(Path(rt) / "libndi.so.6"), str(Path(rt) / "libndi.so")]
    paths += ["libndi.so.6", "libndi.so"]
    found = ctypes.util.find_library("ndi")
    if found:
        paths.append(found)
    for d in ("/usr/local/lib", "/usr/lib", "/usr/lib/x86_64-linux-gnu", "/opt/ndi/lib"):
        paths += [f"{d}/libndi.so.6", f"{d}/libndi.so"]
    return paths


def write_discovery_config(config_dir: Path, discovery_server: str) -> None:
    """Write ndi-config.v1.json pointing at an NDI Discovery Server and
    export NDI_CONFIG_DIR so the SDK picks it up. Must run before initialize."""
    config_dir.mkdir(parents=True, exist_ok=True)
    cfg = {"ndi": {"networks": {"discovery": discovery_server}}}
    (config_dir / "ndi-config.v1.json").write_text(json.dumps(cfg, indent=2))
    os.environ["NDI_CONFIG_DIR"] = str(config_dir)


# --------------------------------------------------------------------------- #
# Real backend
# --------------------------------------------------------------------------- #
class NDIBackend:
    """Loads libndi and exposes Finder / RoutingOutput factories."""

    def __init__(self, lib_path: str | None = None):
        errors = []
        self.lib = None
        for path in _candidate_paths(lib_path):
            try:
                self.lib = ctypes.CDLL(path)
                self.lib_path = path
                break
            except OSError as e:
                errors.append(f"{path}: {e}")
        if self.lib is None:
            raise NDIError(
                "Could not load the NDI runtime (libndi.so.6). Install the NDI SDK for "
                "Linux from https://ndi.video/for-developers/ndi-sdk/ and set NDI_LIB_PATH "
                "to the library file or its directory.\nTried:\n  " + "\n  ".join(errors[:4])
            )
        self._bind()
        if not self.lib.NDIlib_initialize():
            raise NDIError("NDIlib_initialize() failed (unsupported CPU?)")
        try:
            ver = self.lib.NDIlib_version()
            self.version = ver.decode() if ver else "unknown"
        except AttributeError:
            self.version = "unknown"
        log.info("Loaded NDI runtime %s (%s)", self.version, self.lib_path)

    def _bind(self) -> None:
        L = self.lib
        vp = ctypes.c_void_p
        sig = {
            "NDIlib_initialize": ([], ctypes.c_bool),
            "NDIlib_destroy": ([], None),
            "NDIlib_find_create_v2": ([ctypes.POINTER(_FindCreate)], vp),
            "NDIlib_find_destroy": ([vp], None),
            "NDIlib_find_wait_for_sources": ([vp, ctypes.c_uint32], ctypes.c_bool),
            "NDIlib_find_get_current_sources": (
                [vp, ctypes.POINTER(ctypes.c_uint32)],
                ctypes.POINTER(_Source),
            ),
            "NDIlib_routing_create": ([ctypes.POINTER(_RoutingCreate)], vp),
            "NDIlib_routing_destroy": ([vp], None),
            "NDIlib_routing_change": ([vp, ctypes.POINTER(_Source)], ctypes.c_bool),
            "NDIlib_routing_clear": ([vp], ctypes.c_bool),
            "NDIlib_routing_get_no_connections": ([vp, ctypes.c_uint32], ctypes.c_int),
        }
        for name, (args, res) in sig.items():
            fn = getattr(L, name)
            fn.argtypes = args
            fn.restype = res
        try:
            L.NDIlib_version.argtypes = []
            L.NDIlib_version.restype = ctypes.c_char_p
        except AttributeError:
            pass

    def create_finder(self, groups: str | None, extra_ips: str | None) -> "Finder":
        return Finder(self.lib, groups, extra_ips)

    def create_output(self, ndi_name: str, groups: str | None) -> "RoutingOutput":
        return RoutingOutput(self.lib, ndi_name, groups)

    def shutdown(self) -> None:
        self.lib.NDIlib_destroy()


class Finder:
    def __init__(self, lib, groups: str | None, extra_ips: str | None):
        self._lib = lib
        # Keep encoded strings alive for the instance lifetime.
        self._groups = _enc(groups)
        self._extra = _enc(extra_ips)
        self._cfg = _FindCreate(True, self._groups, self._extra)
        self._inst = lib.NDIlib_find_create_v2(ctypes.byref(self._cfg))
        if not self._inst:
            raise NDIError("NDIlib_find_create_v2 failed")

    def wait(self, timeout_ms: int) -> bool:
        return bool(self._lib.NDIlib_find_wait_for_sources(self._inst, timeout_ms))

    def sources(self) -> list[Source]:
        n = ctypes.c_uint32(0)
        arr = self._lib.NDIlib_find_get_current_sources(self._inst, ctypes.byref(n))
        out = []
        for i in range(n.value):
            s = arr[i]
            if s.p_ndi_name:
                out.append(
                    Source(
                        s.p_ndi_name.decode("utf-8", "replace"),
                        s.p_url_address.decode("utf-8", "replace") if s.p_url_address else None,
                    )
                )
        return out

    def close(self) -> None:
        if self._inst:
            self._lib.NDIlib_find_destroy(self._inst)
            self._inst = None


class RoutingOutput:
    def __init__(self, lib, ndi_name: str, groups: str | None):
        self._lib = lib
        self._name = _enc(ndi_name)
        self._groups = _enc(groups)
        self._cfg = _RoutingCreate(self._name, self._groups)
        self._inst = lib.NDIlib_routing_create(ctypes.byref(self._cfg))
        if not self._inst:
            raise NDIError(f"NDIlib_routing_create failed for {ndi_name!r}")
        self._src_refs: tuple = ()

    def change(self, source: Source) -> bool:
        name, url = _enc(source.name), _enc(source.url)
        self._src_refs = (name, url)
        src = _Source(name, url)
        return bool(self._lib.NDIlib_routing_change(self._inst, ctypes.byref(src)))

    def clear(self) -> bool:
        self._src_refs = ()
        return bool(self._lib.NDIlib_routing_clear(self._inst))

    def connections(self) -> int:
        return max(0, int(self._lib.NDIlib_routing_get_no_connections(self._inst, 0)))

    def close(self) -> None:
        if self._inst:
            self._lib.NDIlib_routing_destroy(self._inst)
            self._inst = None


# --------------------------------------------------------------------------- #
# Fake backend (tests / --fake dev mode)
# --------------------------------------------------------------------------- #
class FakeBackend:
    version = "fake"
    lib_path = "fake"

    def __init__(self, sources: list[Source] | None = None, host: str = "ROUTER"):
        self.host = host
        self._lock = threading.Lock()
        self._sources: list[Source] = list(sources or [])
        self._changed = threading.Event()
        self.outputs: dict[str, FakeOutput] = {}

    # test helpers
    def set_sources(self, sources: list[Source]) -> None:
        with self._lock:
            self._sources = list(sources)
        self._changed.set()

    def visible_sources(self) -> list[Source]:
        with self._lock:
            local = [Source(f"{self.host} ({n})", "fake://local") for n in self.outputs]
            return list(self._sources) + local

    def create_finder(self, groups, extra_ips) -> "FakeFinder":
        return FakeFinder(self)

    def create_output(self, ndi_name: str, groups) -> "FakeOutput":
        o = FakeOutput(self, ndi_name)
        with self._lock:
            self.outputs[ndi_name] = o
        self._changed.set()
        return o

    def shutdown(self) -> None:
        pass


class FakeFinder:
    def __init__(self, be: FakeBackend):
        self.be = be

    def wait(self, timeout_ms: int) -> bool:
        hit = self.be._changed.wait(timeout_ms / 1000)
        self.be._changed.clear()
        return hit

    def sources(self) -> list[Source]:
        return self.be.visible_sources()

    def close(self) -> None:
        pass


class FakeOutput:
    def __init__(self, be: FakeBackend, name: str):
        self.be, self.name = be, name
        self.target: Source | None = None
        self.fake_connections = 0

    def change(self, source: Source) -> bool:
        self.target = source
        return True

    def clear(self) -> bool:
        self.target = None
        return True

    def connections(self) -> int:
        return self.fake_connections

    def close(self) -> None:
        with self.be._lock:
            self.be.outputs.pop(self.name, None)
        self.be._changed.set()
