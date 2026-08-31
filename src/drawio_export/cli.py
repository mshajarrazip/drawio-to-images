from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import __version__
from .backends import DEFAULT_IMAGE, RenderRequest, select_backend
from .cache import Cache
from .config import find_project_root, load_config, resolve_options
from .discovery import SUFFIX, discover, resolve_target, resolve_targets
from .doctor import run_doctor
from .errors import CliError, DrawioExportError, TargetNotFound
from .outputs import EXT, output_path
from .render import build_plans, execute
from .scaffold import write_config

SUBCOMMANDS = {"render", "check", "list", "prune", "doctor", "init", "watch"}


# --------------------------------------------------------------------------- args


def _add_render_opts(p: argparse.ArgumentParser) -> None:
    p.add_argument("targets", nargs="*", help="diagram labels / paths; empty = all under --src")
    p.add_argument("--src", help="source root (default: ./diagrams if present, else .)")
    p.add_argument("--out", help="output root (default: ./imgs)")
    p.add_argument("--format", dest="formats", help="comma list: svg,png,pdf,jpg (default: svg)")
    p.add_argument("-o", "--output", help="single-file mode: write ONE source to this exact path")
    p.add_argument("-f", "--force", action="store_true", default=None, help="re-render even if unchanged")
    p.add_argument("--jobs", type=int, help="parallel renders (default: min(CPU, 4))")
    p.add_argument("--backend", choices=["auto", "docker", "local"], help="rendering backend (default: auto)")
    p.add_argument("--docker-image", dest="docker_image", help=f"(default: {DEFAULT_IMAGE})")
    p.add_argument("--pull", action="store_true", default=None, help="docker pull before rendering")
    p.add_argument("--timeout", help="per-diagram timeout, e.g. 30s, 2m (default: 30s)")
    p.add_argument("--scale", type=float)
    p.add_argument("--width", type=int)
    p.add_argument("--height", type=int)
    p.add_argument("--border", type=int, help="padding in px around the diagram")
    p.add_argument("--transparent", action="store_true", default=None, help="PNG transparent background")
    p.add_argument("--quality", type=int, help="JPG quality 0-100")
    p.add_argument("--page-index", dest="page_index", type=int, help="export only this page (0-based)")
    p.add_argument("--flatten", action="store_true", default=None, help="do not mirror sub-dirs into --out")
    p.add_argument("--include", action="append", help="glob relative to --src (repeatable)")
    p.add_argument("--exclude", action="append", help="glob relative to --src (repeatable)")
    p.add_argument("--cache-dir", dest="cache_dir", help="(default: <project>/.drawio-export)")
    p.add_argument("--no-cache", dest="no_cache", action="store_true", default=None,
                   help="ignore and do not write the change-tracking cache")
    p.add_argument("--json", action="store_true", help="machine-readable output on stdout")
    p.add_argument("--dry-run", action="store_true", help="print the plan, render nothing")


def _add_query_opts(p: argparse.ArgumentParser) -> None:
    p.add_argument("--src", help="source root (default: ./diagrams if present, else .)")
    p.add_argument("--out", help="output root (default: ./imgs)")
    p.add_argument("--format", dest="formats", help="comma list: svg,png,pdf,jpg (default: svg)")
    p.add_argument("--flatten", action="store_true", default=None)
    p.add_argument("--include", action="append")
    p.add_argument("--exclude", action="append")
    p.add_argument("--cache-dir", dest="cache_dir")
    p.add_argument("--no-cache", dest="no_cache", action="store_true", default=None)
    p.add_argument("--json", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="drawio-export",
        description="Render .drawio files to SVG/PNG/PDF/JPG via a headless drawio backend.",
    )
    p.add_argument("--version", action="version", version=f"drawio-export {__version__}")
    sub = p.add_subparsers(dest="command")

    _add_render_opts(sub.add_parser("render", help="render diagrams (this is the default)"))
    _add_render_opts(sub.add_parser("check", help="report stale/missing outputs; exit 1 if any"))
    _add_render_opts(sub.add_parser("watch", help="re-render on change (needs the 'watch' extra)"))
    _add_query_opts(sub.add_parser("list", help="list discovered diagrams and their status"))

    pr = sub.add_parser("prune", help="delete outputs whose source no longer exists")
    _add_query_opts(pr)
    pr.add_argument("--dry-run", action="store_true")

    sub.add_parser("doctor", help="check the environment for a working backend")

    it = sub.add_parser("init", help="write a starter drawio-export.toml")
    it.add_argument("--force", action="store_true", help="overwrite an existing config")
    return p


# ----------------------------------------------------------------------- helpers


def _prepare(args: argparse.Namespace):
    root = find_project_root(Path.cwd())
    return root, resolve_options(args, load_config(root), root)


def _rel(path: Path, base: Path) -> str:
    try:
        return str(path.resolve().relative_to(base.resolve()))
    except ValueError:
        return str(path)


# ---------------------------------------------------------------------- commands


def cmd_render(args: argparse.Namespace, *, check_only: bool) -> int:
    if getattr(args, "output", None):
        return _render_single(args)

    root, opts = _prepare(args)
    if not opts.src.is_dir():
        raise CliError(f"source directory not found: {opts.src}")
    sources = (
        resolve_targets(args.targets, opts.src)
        if args.targets
        else discover(opts.src, opts.include, opts.exclude)
    )
    if not sources:
        print(f"drawio-export: no {SUFFIX} files under {opts.src}", file=sys.stderr)
        return 0

    cache = Cache(opts.cache_dir / "cache.json", enabled=opts.use_cache)
    plans = build_plans(sources, opts, cache, root)

    if check_only:
        stale = [p for p in plans if not p.fresh]
        for p in plans:
            print(f"{'stale' if p in stale else 'ok':6} {_rel(p.source, opts.src)}")
        if args.json:
            print(json.dumps(
                [{"source": str(p.source), "fresh": p.fresh,
                  "outputs": [str(o) for o in p.outputs]} for p in plans],
                indent=2,
            ))
        if stale:
            print(f"drawio-export: {len(stale)} diagram(s) need rendering", file=sys.stderr)
            return 1
        return 0

    if args.dry_run:
        for p in plans:
            state = "fresh" if p.fresh else "render"
            for o in p.outputs:
                print(f"{state:6} {_rel(p.source, opts.src)} -> {_rel(o, opts.out)}")
        return 0

    outcomes = execute(plans, opts, cache, root, force=bool(getattr(args, "force", None)))
    return _report(outcomes, opts, as_json=args.json)


def _report(outcomes, opts, *, as_json: bool) -> int:
    rendered = [o for o in outcomes if o.status == "rendered"]
    skipped = [o for o in outcomes if o.status == "skipped"]
    failed = [o for o in outcomes if o.status == "failed"]
    for o in outcomes:
        if o.status == "rendered":
            for p in o.outputs:
                print(f"rendered {_rel(p, opts.out)}")
        elif o.status == "failed":
            print(f"FAILED   {_rel(o.source, opts.src)}: {o.error}", file=sys.stderr)
    print(
        f"drawio-export: {len(rendered)} rendered, {len(skipped)} unchanged, "
        f"{len(failed)} failed",
        file=sys.stderr,
    )
    if as_json:
        print(json.dumps(
            [{"source": str(o.source), "status": o.status,
              "outputs": [str(p) for p in o.outputs], "error": o.error}
             for o in outcomes],
            indent=2,
        ))
    return 1 if failed else 0


def _render_single(args: argparse.Namespace) -> int:
    root, opts = _prepare(args)
    if len(args.targets) != 1:
        raise CliError("-o/--output requires exactly one source argument")
    src_file = Path(args.targets[0])
    if not src_file.is_file():
        src_file = resolve_target(args.targets[0], opts.src)
    src_file = src_file.resolve()

    out = Path(args.output)
    if out.is_dir() or args.output.endswith(("/", os.sep)):
        fmt = opts.formats[0]
        out = out / f"{src_file.stem}.{fmt}"
    else:
        fmt = EXT.get(out.suffix.lstrip(".").lower(), opts.formats[0])
    out = out.resolve()

    mount = Path(os.path.commonpath([str(src_file.parent), str(out.parent)]))
    backend = select_backend(
        opts.backend, image=opts.docker_image, pull=opts.pull, mount_root=mount
    )
    print(f"drawio-export: backend = {backend.describe()}", file=sys.stderr)
    backend.prepare()
    backend.render(
        RenderRequest(
            source=src_file, output=out, fmt=fmt, scale=opts.scale, width=opts.width,
            height=opts.height, border=opts.border, transparent=opts.transparent,
            quality=opts.quality, page_index=opts.page_index, timeout=opts.timeout,
        )
    )
    print(f"rendered {out}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    root, opts = _prepare(args)
    if not opts.src.is_dir():
        raise CliError(f"source directory not found: {opts.src}")
    sources = discover(opts.src, opts.include, opts.exclude)
    cache = Cache(opts.cache_dir / "cache.json", enabled=opts.use_cache)
    sig = opts.render_signature()
    rows = []
    for s in sources:
        outs = [
            output_path(s, opts.src, opts.out, fmt, flatten=opts.flatten,
                        page=opts.page_index)
            for fmt in opts.formats
        ]
        rows.append((s, cache.is_fresh(s, root, sig, outs), outs))

    if args.json:
        print(json.dumps(
            [{"source": str(s), "label": _rel(s, opts.src)[: -len(SUFFIX)],
              "fresh": fresh, "outputs": [str(o) for o in outs]}
             for s, fresh, outs in rows],
            indent=2,
        ))
    elif not rows:
        print(f"(no {SUFFIX} files under {opts.src})")
    else:
        for s, fresh, _ in rows:
            print(f"{'fresh' if fresh else 'stale':6} {_rel(s, opts.src)[: -len(SUFFIX)]}")
    return 0


def cmd_prune(args: argparse.Namespace) -> int:
    _, opts = _prepare(args)
    sources = discover(opts.src) if opts.src.is_dir() else []
    expected = {
        output_path(s, opts.src, opts.out, fmt, flatten=opts.flatten, page=opts.page_index)
        for s in sources
        for fmt in opts.formats
    }
    exts = set(opts.formats)
    orphans = []
    if opts.out.is_dir():
        for p in sorted(opts.out.rglob("*")):
            if (
                p.is_file()
                and p.suffix.lstrip(".").lower() in exts
                and p.resolve() not in expected
            ):
                orphans.append(p)

    for p in orphans:
        if args.dry_run:
            print(f"would remove {_rel(p, opts.out)}")
        else:
            p.unlink()
            print(f"removed {_rel(p, opts.out)}")
    if args.json:
        print(json.dumps([str(p) for p in orphans], indent=2))
    if not orphans:
        print("drawio-export: no orphaned outputs", file=sys.stderr)
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    root = find_project_root(Path.cwd())
    dest = root / "drawio-export.toml"
    if write_config(dest, force=args.force):
        print(f"wrote {dest}")
        return 0
    print(f"{dest} already exists (use --force to overwrite)", file=sys.stderr)
    return 1


def cmd_watch(args: argparse.Namespace) -> int:
    from .watch import watch_loop

    root, opts = _prepare(args)
    return watch_loop(root, opts)


# -------------------------------------------------------------------------- main


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        argv = ["render"]
    elif argv[0] not in SUBCOMMANDS and argv[0] not in ("-h", "--help", "--version"):
        argv = ["render", *argv]

    args = build_parser().parse_args(argv)
    try:
        if args.command in (None, "render"):
            return cmd_render(args, check_only=False)
        if args.command == "check":
            return cmd_render(args, check_only=True)
        if args.command == "list":
            return cmd_list(args)
        if args.command == "prune":
            return cmd_prune(args)
        if args.command == "doctor":
            return run_doctor()
        if args.command == "init":
            return cmd_init(args)
        if args.command == "watch":
            return cmd_watch(args)
        raise CliError(f"unknown command: {args.command}")
    except TargetNotFound as e:
        print(f"error: {e}", file=sys.stderr)
        if e.available:
            print("available diagrams:", file=sys.stderr)
            for name in e.available:
                print(f"  {name}", file=sys.stderr)
        return e.exit_code
    except DrawioExportError as e:
        print(f"error: {e}", file=sys.stderr)
        return e.exit_code
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
