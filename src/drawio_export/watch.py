"""`drawio-export watch` — re-render on change. Needs the `watch` extra (watchfiles)."""

from __future__ import annotations

import sys
from pathlib import Path

from .cache import Cache
from .config import Options
from .discovery import SUFFIX, discover
from .errors import CliError
from .render import build_plans, execute


def watch_loop(root: Path, opts: Options) -> int:
    try:
        from watchfiles import watch
    except ImportError:
        raise CliError(
            "watch needs the 'watch' extra: "
            "uv tool install 'drawio-to-images[watch] @ git+https://github.com/mshajarrazip/drawio-to-images'"
        )
    if not opts.src.is_dir():
        raise CliError(f"source directory not found: {opts.src}")

    def render_all() -> None:
        sources = discover(opts.src, opts.include, opts.exclude)
        if not sources:
            return
        cache = Cache(opts.cache_dir / "cache.json", enabled=opts.use_cache)
        outcomes = execute(
            build_plans(sources, opts, cache, root), opts, cache, root, force=False
        )
        rendered = sum(o.status == "rendered" for o in outcomes)
        failed = sum(o.status == "failed" for o in outcomes)
        print(
            f"drawio-export: {rendered} rendered, {failed} failed", file=sys.stderr
        )

    print(f"drawio-export: watching {opts.src} (Ctrl+C to stop)", file=sys.stderr)
    render_all()
    try:
        for changes in watch(str(opts.src)):
            if any(p.endswith(SUFFIX) for _, p in changes):
                print("drawio-export: change detected, re-rendering", file=sys.stderr)
                render_all()
    except KeyboardInterrupt:
        pass
    return 0
