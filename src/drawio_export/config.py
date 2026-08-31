"""Load `[tool.drawio-export]` / `drawio-export.toml` and merge it with CLI flags."""

from __future__ import annotations

import argparse
import json
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from .backends import DEFAULT_IMAGE
from .discovery import default_src
from .duration import parse_duration
from .errors import CliError
from .outputs import normalize_formats

_KEYS = {
    "src", "out", "formats", "scale", "width", "height", "border", "transparent",
    "quality", "backend", "docker_image", "pull", "timeout", "jobs", "flatten",
    "include", "exclude", "page_index", "cache_dir", "no_cache",
}


def find_project_root(start: Path) -> Path:
    start = start.resolve()
    for d in (start, *start.parents):
        if (
            (d / "drawio-export.toml").is_file()
            or (d / "pyproject.toml").is_file()
            or (d / ".git").exists()
        ):
            return d
    return start


def load_config(root: Path) -> dict:
    toml_path = root / "drawio-export.toml"
    if toml_path.is_file():
        raw = tomllib.loads(toml_path.read_text("utf-8"))
    else:
        pp = root / "pyproject.toml"
        raw = {}
        if pp.is_file():
            raw = tomllib.loads(pp.read_text("utf-8")).get("tool", {}).get(
                "drawio-export", {}
            )
    cfg: dict = {}
    for key, value in raw.items():
        norm = key.replace("-", "_")
        if norm == "format":
            norm = "formats"
        if norm in _KEYS:
            cfg[norm] = value
    return cfg


@dataclass
class Options:
    src: Path
    out: Path
    formats: list[str]
    scale: float | None
    width: int | None
    height: int | None
    border: int | None
    transparent: bool
    quality: int | None
    page_index: int | None
    backend: str
    docker_image: str
    pull: bool
    timeout: float
    jobs: int
    flatten: bool
    include: list[str]
    exclude: list[str]
    cache_dir: Path
    use_cache: bool

    def render_signature(self) -> str:
        """Stable string of every option that changes an output file's bytes."""
        return json.dumps(
            {
                "formats": sorted(self.formats),
                "scale": self.scale,
                "width": self.width,
                "height": self.height,
                "border": self.border,
                "transparent": self.transparent,
                "quality": self.quality,
                "page_index": self.page_index,
                "flatten": self.flatten,
            },
            sort_keys=True,
        )


def resolve_options(args: argparse.Namespace, cfg: dict, root: Path) -> Options:
    def pick(name: str, default):
        val = getattr(args, name, None)
        if val is not None:
            return val
        return cfg.get(name, default)

    def as_path(value: str | Path) -> Path:
        p = Path(value)
        return p if p.is_absolute() else (root / p)

    def as_int(name: str) -> int | None:
        val = pick(name, None)
        return None if val is None else int(val)

    backend = str(pick("backend", "auto")).lower()
    if backend not in {"auto", "docker", "local"}:
        raise CliError(f"unknown backend: {backend!r} (choose auto, docker, or local)")

    src = as_path(pick("src", None) or default_src(root)).resolve()
    out = as_path(pick("out", "imgs")).resolve()
    cache_dir = as_path(pick("cache_dir", ".drawio-export")).resolve()
    scale = pick("scale", None)

    return Options(
        src=src,
        out=out,
        formats=normalize_formats(pick("formats", ["svg"])),
        scale=None if scale is None else float(scale),
        width=as_int("width"),
        height=as_int("height"),
        border=as_int("border"),
        transparent=bool(pick("transparent", False)),
        quality=as_int("quality"),
        page_index=as_int("page_index"),
        backend=backend,
        docker_image=str(pick("docker_image", DEFAULT_IMAGE)),
        pull=bool(pick("pull", False)),
        timeout=parse_duration(pick("timeout", "30s")),
        jobs=max(1, int(pick("jobs", min(os.cpu_count() or 1, 4)))),
        flatten=bool(pick("flatten", False)),
        include=list(pick("include", []) or []),
        exclude=list(pick("exclude", []) or []),
        cache_dir=cache_dir,
        use_cache=not bool(pick("no_cache", False)),
    )
