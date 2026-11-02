"""Settings, read from environment variables (systemd loads them from an
EnvironmentFile such as /etc/patchbay.env)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(name)
    return v if v not in (None, "") else default


@dataclass
class Settings:
    host: str = field(default_factory=lambda: _env("HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(_env("PORT", "8080")))
    # Deprecated: if set, it is imported once as a managed API key.
    api_key: str | None = field(default_factory=lambda: _env("API_KEY"))
    state_file: str = field(
        default_factory=lambda: _env("STATE_FILE", "/var/lib/patchbay/state.json")
    )
    # Users, sessions and API keys (hashed). Defaults to auth.json next to STATE_FILE.
    auth_file: str | None = field(default_factory=lambda: _env("AUTH_FILE"))
    session_days: int = field(default_factory=lambda: int(_env("SESSION_DAYS", "30")))

    def auth_path(self, state_file: str | None = None) -> str:
        from pathlib import Path
        return self.auth_file or str(Path(state_file or self.state_file).parent / "auth.json")
    ndi_lib_path: str | None = field(default_factory=lambda: _env("NDI_LIB_PATH"))
    ndi_groups: str | None = field(default_factory=lambda: _env("NDI_GROUPS"))
    ndi_extra_ips: str | None = field(default_factory=lambda: _env("NDI_EXTRA_IPS"))
    ndi_discovery_server: str | None = field(
        default_factory=lambda: _env("NDI_DISCOVERY_SERVER")
    )
    output_prefix: str = field(default_factory=lambda: _env("OUTPUT_PREFIX", "") or "")
    log_level: str = field(default_factory=lambda: _env("LOG_LEVEL", "info"))
