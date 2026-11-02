"""User accounts, login sessions and API keys.

- Users log in to the web UI with username + password (scrypt hashes) and get
  an HttpOnly session cookie.
- API keys are created/revoked from the web UI and are meant for REST/WebSocket
  control (Companion, Stream Deck, scripts). Only a SHA-256 of each key and
  session token is stored, so the auth file never holds usable secrets.

Persisted to a JSON file (mode 0600) next to the router state.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

KEY_PREFIX = "ndr_"
USERNAME_RE = re.compile(r"^[A-Za-z0-9._@-]{1,64}$")
MIN_PASSWORD = 8
_SCRYPT = {"n": 2**14, "r": 8, "p": 1, "dklen": 32}
_LAST_USED_PERSIST_S = 60


class AuthError(ValueError):
    """Invalid input for an auth operation (maps to HTTP 422)."""


class AuthNotFound(LookupError):
    pass


@dataclass(frozen=True)
class Principal:
    kind: str  # "session" | "key"
    name: str  # username, or API key name
    key_id: str | None = None


def _sha(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return f"scrypt${_SCRYPT['n']}${_SCRYPT['r']}${_SCRYPT['p']}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt, dk = stored.split("$")
        if algo != "scrypt":
            return False
        got = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt),
                             n=int(n), r=int(r), p=int(p), dklen=len(dk) // 2)
        return hmac.compare_digest(got.hex(), dk)
    except (ValueError, TypeError):
        return False


# A real hash to compare against when the username does not exist, so login
# timing does not reveal which usernames are valid.
_DUMMY_HASH = hash_password(secrets.token_hex(8))


class AuthStore:
    def __init__(self, path: str | Path, session_ttl_s: int = 30 * 86400):
        self.path = Path(path)
        self.session_ttl_s = session_ttl_s
        self._lock = threading.RLock()
        self._data = self._load()
        self._purge_expired()

    # ------------------------------------------------------------ io -- #
    def _load(self) -> dict:
        try:
            data = json.loads(self.path.read_text())
        except FileNotFoundError:
            data = {}
        except (OSError, ValueError) as e:
            # Do not silently start empty: that would re-open first-run setup.
            raise RuntimeError(f"Could not read auth file {self.path}: {e}") from e
        data.setdefault("version", 1)
        data.setdefault("users", {})
        data.setdefault("sessions", {})
        data.setdefault("keys", {})
        return data

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".auth-", dir=self.path.parent)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w") as f:
                json.dump(self._data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def _purge_expired(self) -> None:
        now = time.time()
        with self._lock:
            dead = [h for h, s in self._data["sessions"].items() if s["expires"] < now]
            for h in dead:
                del self._data["sessions"][h]
            if dead:
                self._save()

    # --------------------------------------------------------- users -- #
    def setup_required(self) -> bool:
        with self._lock:
            return not self._data["users"]

    def _find_user(self, username: str) -> str | None:
        low = username.lower()
        for u in self._data["users"]:
            if u.lower() == low:
                return u
        return None

    @staticmethod
    def _check_password(password: str) -> None:
        if len(password or "") < MIN_PASSWORD:
            raise AuthError(f"password must be at least {MIN_PASSWORD} characters")

    def list_users(self) -> list[dict]:
        with self._lock:
            return [{"username": u, "created_at": v["created_at"]}
                    for u, v in sorted(self._data["users"].items(), key=lambda kv: kv[0].lower())]

    def create_user(self, username: str, password: str) -> dict:
        username = (username or "").strip()
        if not USERNAME_RE.match(username):
            raise AuthError("username must be 1-64 characters: letters, digits, . _ @ -")
        self._check_password(password)
        with self._lock:
            if self._find_user(username):
                raise AuthError(f"user {username!r} already exists")
            self._data["users"][username] = {"password": hash_password(password),
                                             "created_at": time.time()}
            self._save()
        log.info("User created: %s", username)
        return {"username": username}

    def setup(self, username: str, password: str) -> dict:
        """Create the first user. Only allowed while no users exist."""
        with self._lock:
            if not self.setup_required():
                raise PermissionError("setup already completed")
            return self.create_user(username, password)

    def delete_user(self, username: str) -> None:
        with self._lock:
            u = self._find_user(username)
            if not u:
                raise AuthNotFound(f"user {username!r} not found")
            if len(self._data["users"]) == 1:
                raise AuthError("cannot delete the last user")
            del self._data["users"][u]
            self._drop_sessions(u)
            self._save()
        log.info("User deleted: %s", u)

    def set_password(self, username: str, password: str, *, keep_session: str | None = None) -> None:
        self._check_password(password)
        with self._lock:
            u = self._find_user(username)
            if not u:
                raise AuthNotFound(f"user {username!r} not found")
            self._data["users"][u]["password"] = hash_password(password)
            # Log out everywhere else.
            self._drop_sessions(u, keep=_sha(keep_session) if keep_session else None)
            self._save()
        log.info("Password changed for %s", u)

    def check_login(self, username: str, password: str) -> str | None:
        """Return the canonical username if the credentials are valid."""
        with self._lock:
            u = self._find_user((username or "").strip())
            stored = self._data["users"][u]["password"] if u else _DUMMY_HASH
        ok = verify_password(password or "", stored)
        return u if (u and ok) else None

    # ------------------------------------------------------ sessions -- #
    def create_session(self, username: str) -> str:
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._data["sessions"][_sha(token)] = {
                "user": username, "created_at": time.time(),
                "expires": time.time() + self.session_ttl_s,
            }
            self._save()
        return token

    def session_user(self, token: str | None) -> str | None:
        if not token:
            return None
        with self._lock:
            s = self._data["sessions"].get(_sha(token))
            if not s:
                return None
            if s["expires"] < time.time() or s["user"] not in self._data["users"]:
                del self._data["sessions"][_sha(token)]
                self._save()
                return None
            return s["user"]

    def end_session(self, token: str | None) -> None:
        if not token:
            return
        with self._lock:
            if self._data["sessions"].pop(_sha(token), None) is not None:
                self._save()

    def _drop_sessions(self, username: str, keep: str | None = None) -> None:
        for h in [h for h, s in self._data["sessions"].items()
                  if s["user"] == username and h != keep]:
            del self._data["sessions"][h]

    # ------------------------------------------------------ API keys -- #
    def _key_dict(self, kid: str, k: dict) -> dict:
        return {"id": kid, "name": k["name"], "hint": k["hint"], "created_at": k["created_at"],
                "created_by": k.get("created_by"), "last_used_at": k.get("last_used_at")}

    def list_keys(self) -> list[dict]:
        with self._lock:
            return sorted((self._key_dict(i, k) for i, k in self._data["keys"].items()),
                          key=lambda d: d["created_at"])

    def create_key(self, name: str, created_by: str | None, token: str | None = None) -> dict:
        """Create an API key. Returns its metadata plus the plaintext `key`,
        which is never retrievable again."""
        name = (name or "").strip()
        if not name or len(name) > 100:
            raise AuthError("key name must be 1-100 characters")
        token = token or KEY_PREFIX + secrets.token_urlsafe(32)
        kid = uuid.uuid4().hex[:8]
        with self._lock:
            if any(k["name"].lower() == name.lower() for k in self._data["keys"].values()):
                raise AuthError(f"an API key named {name!r} already exists")
            h = _sha(token)
            if any(k["hash"] == h for k in self._data["keys"].values()):
                raise AuthError("this key already exists")
            self._data["keys"][kid] = {
                "name": name, "hash": h, "hint": token[:8] + "…",
                "created_at": time.time(), "created_by": created_by, "last_used_at": None,
            }
            self._save()
            out = self._key_dict(kid, self._data["keys"][kid])
        log.info("API key created: %s (by %s)", name, created_by)
        out["key"] = token
        return out

    def delete_key(self, kid: str) -> None:
        with self._lock:
            k = self._data["keys"].pop(kid, None)
            if k is None:
                raise AuthNotFound(f"API key {kid!r} not found")
            self._save()
        log.info("API key revoked: %s", k["name"])

    def check_key(self, token: str | None) -> Principal | None:
        if not token:
            return None
        h = _sha(token)
        with self._lock:
            for kid, k in self._data["keys"].items():
                if hmac.compare_digest(k["hash"], h):
                    now = time.time()
                    if (k.get("last_used_at") or 0) < now - _LAST_USED_PERSIST_S:
                        k["last_used_at"] = now
                        self._save()
                    return Principal("key", k["name"], kid)
        return None

    def import_legacy_key(self, token: str) -> None:
        """Keep a pre-existing API_KEY env value working as a managed key."""
        with self._lock:
            if any(k["hash"] == _sha(token) for k in self._data["keys"].values()):
                return
            name = "Imported from API_KEY"
            while any(k["name"] == name for k in self._data["keys"].values()):
                name += "'"
            self.create_key(name, None, token=token)
        log.warning("Imported API_KEY from the environment as API key %r. Manage it in the "
                    "web UI and remove API_KEY from the config file.", name)


class LoginLimiter:
    """Per-client brute-force protection: after `limit` failures within
    `window_s`, further attempts are refused until the window passes."""

    def __init__(self, limit: int = 10, window_s: float = 300):
        self.limit, self.window_s = limit, window_s
        self._fails: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, ip: str, now: float) -> list[float]:
        lst = [t for t in self._fails.get(ip, []) if t > now - self.window_s]
        if lst:
            self._fails[ip] = lst
        else:
            self._fails.pop(ip, None)
        return lst

    def blocked(self, ip: str) -> bool:
        with self._lock:
            return len(self._recent(ip, time.time())) >= self.limit

    def fail(self, ip: str) -> None:
        with self._lock:
            now = time.time()
            self._fails[ip] = self._recent(ip, now) + [now]

    def reset(self, ip: str) -> None:
        with self._lock:
            self._fails.pop(ip, None)
