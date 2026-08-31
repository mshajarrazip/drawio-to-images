"""Find .drawio sources and resolve target arguments to concrete files."""

from __future__ import annotations

import fnmatch
from collections.abc import Iterable, Sequence
from pathlib import Path

from .errors import TargetNotFound

SUFFIX = ".drawio"


def default_src(root: Path) -> Path:
    """`<root>/diagrams` when it exists, else `<root>` itself."""
    d = root / "diagrams"
    return d if d.is_dir() else root


def _rel(p: Path, src: Path) -> str:
    try:
        return p.relative_to(src).as_posix()
    except ValueError:
        return p.as_posix()


def discover(
    src: Path,
    include: Sequence[str] = (),
    exclude: Sequence[str] = (),
) -> list[Path]:
    """All `*.drawio` files under `src`, sorted, filtered by globs relative to `src`."""
    out: list[Path] = []
    for p in sorted(src.rglob("*" + SUFFIX)):
        if not p.is_file():
            continue
        rel = _rel(p, src)
        if include and not any(fnmatch.fnmatch(rel, pat) for pat in include):
            continue
        if exclude and any(fnmatch.fnmatch(rel, pat) for pat in exclude):
            continue
        out.append(p)
    return out


def labels(src: Path) -> list[str]:
    """Discovered diagrams as bare labels (relative path without the `.drawio` suffix)."""
    return [_rel(p, src)[: -len(SUFFIX)] for p in discover(src)]


def resolve_target(target: str, src: Path) -> Path:
    """Resolve a bare label / relative path / full path (with or without `.drawio`)."""
    t = target
    cands = [Path(t)]
    if not t.endswith(SUFFIX):
        cands.append(Path(t + SUFFIX))
    cands.append(src / t)
    if not t.endswith(SUFFIX):
        cands.append(src / (t + SUFFIX))
    for c in cands:
        if c.is_file():
            return c.resolve()
    raise TargetNotFound(target, labels(src))


def resolve_targets(targets: Iterable[str], src: Path) -> list[Path]:
    seen: dict[Path, None] = {}
    for t in targets:
        seen.setdefault(resolve_target(t, src), None)
    return list(seen)
