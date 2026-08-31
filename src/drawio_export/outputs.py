"""Map a source .drawio file to its output image path(s)."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from .errors import CliError

# Accepted format spellings -> canonical extension.
EXT = {"svg": "svg", "png": "png", "pdf": "pdf", "jpg": "jpg", "jpeg": "jpg"}


def normalize_formats(value: str | Iterable[str]) -> list[str]:
    items = value.split(",") if isinstance(value, str) else [str(v) for v in value]
    out: list[str] = []
    for raw in items:
        name = raw.strip().lower()
        if not name:
            continue
        if name not in EXT:
            raise CliError(f"unsupported format: {raw!r} (choose from svg, png, pdf, jpg)")
        ext = EXT[name]
        if ext not in out:
            out.append(ext)
    if not out:
        raise CliError("no output formats given")
    return out


def output_path(
    source: Path,
    src_root: Path,
    out_root: Path,
    ext: str,
    *,
    flatten: bool = False,
    page: int | None = None,
) -> Path:
    rel = source.resolve().relative_to(src_root.resolve())
    stem = source.stem if page is None else f"{source.stem}.page-{page}"
    name = f"{stem}.{ext}"
    if flatten:
        return (out_root / name).resolve()
    return (out_root / rel.parent / name).resolve()
