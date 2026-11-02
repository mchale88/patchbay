"""JSON state persistence with atomic writes."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)

EMPTY = {"version": 1, "outputs": [], "presets": []}


class Store:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self) -> dict:
        try:
            data = json.loads(self.path.read_text())
        except FileNotFoundError:
            return json.loads(json.dumps(EMPTY))
        except (OSError, ValueError) as e:
            log.error("Could not read state file %s: %s (starting empty)", self.path, e)
            bad = self.path.with_suffix(self.path.suffix + ".corrupt")
            try:
                self.path.replace(bad)
                log.error("Moved unreadable state to %s", bad)
            except OSError:
                pass
            return json.loads(json.dumps(EMPTY))
        data.setdefault("outputs", [])
        data.setdefault("presets", [])
        return data

    def save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".state-", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
