"""Per-project render cache: skip a diagram when nothing that affects its output changed."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path


def hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


class Cache:
    def __init__(self, path: Path, enabled: bool = True) -> None:
        self.path = path
        self.enabled = enabled
        self._data: dict = {"version": 1, "entries": {}}
        if enabled and path.is_file():
            try:
                loaded = json.loads(path.read_text("utf-8"))
                if isinstance(loaded, dict) and isinstance(loaded.get("entries"), dict):
                    self._data = loaded
            except (json.JSONDecodeError, OSError):
                pass

    def _key(self, source: Path, root: Path) -> str:
        try:
            return source.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            return source.resolve().as_posix()

    def is_fresh(
        self, source: Path, root: Path, signature: str, outputs: list[Path]
    ) -> bool:
        if not self.enabled:
            return False
        entry = self._data["entries"].get(self._key(source, root))
        if not entry:
            return False
        if entry.get("signature") != signature:
            return False
        if entry.get("hash") != hash_file(source):
            return False
        return all(Path(o).exists() for o in outputs)

    def update(
        self, source: Path, root: Path, signature: str, outputs: list[Path]
    ) -> None:
        if not self.enabled:
            return
        self._data["entries"][self._key(source, root)] = {
            "hash": hash_file(source),
            "signature": signature,
            "outputs": [str(o) for o in outputs],
            "rendered_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

    def save(self) -> None:
        if not self.enabled:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._data, indent=2, sort_keys=True) + "\n", "utf-8"
        )

    def entries(self) -> dict:
        return dict(self._data["entries"])
