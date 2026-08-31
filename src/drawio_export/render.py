"""Turn discovered sources + options into render work, then run it."""

from __future__ import annotations

import os
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from .backends import RenderRequest, select_backend
from .cache import Cache
from .config import Options
from .errors import RenderError
from .outputs import output_path


@dataclass
class Plan:
    source: Path
    outputs: list[Path]
    signature: str
    fresh: bool = False


@dataclass
class Outcome:
    source: Path
    outputs: list[Path]
    status: str  # "rendered" | "skipped" | "failed"
    error: str | None = None


def build_plans(sources, opts: Options, cache: Cache, root: Path) -> list[Plan]:
    plans: list[Plan] = []
    sig = opts.render_signature()
    for s in sources:
        outs = [
            output_path(
                s, opts.src, opts.out, fmt, flatten=opts.flatten, page=opts.page_index
            )
            for fmt in opts.formats
        ]
        plans.append(
            Plan(
                source=s,
                outputs=outs,
                signature=sig,
                fresh=cache.is_fresh(s, root, sig, outs),
            )
        )
    return plans


def _requests(plan: Plan, opts: Options) -> list[RenderRequest]:
    return [
        RenderRequest(
            source=plan.source,
            output=out,
            fmt=fmt,
            scale=opts.scale,
            width=opts.width,
            height=opts.height,
            border=opts.border,
            transparent=opts.transparent,
            quality=opts.quality,
            page_index=opts.page_index,
            timeout=opts.timeout,
        )
        for fmt, out in zip(opts.formats, plan.outputs)
    ]


def _mount_root(plans: list[Plan], opts: Options) -> Path:
    paths = [str(opts.src), str(opts.out)]
    for p in plans:
        paths.append(str(p.source.parent))
        paths.extend(str(o.parent) for o in p.outputs)
    m = Path(os.path.commonpath(paths))
    if str(m) == m.anchor:
        raise RenderError(
            "sources and outputs share no directory close enough for a docker bind-mount; "
            "run with --backend local, or move --out under the project root"
        )
    return m


def execute(
    plans: list[Plan], opts: Options, cache: Cache, root: Path, *, force: bool
) -> list[Outcome]:
    todo = [p for p in plans if force or not p.fresh]
    outcomes = [
        Outcome(p.source, p.outputs, "skipped") for p in plans if not (force or not p.fresh)
    ]
    if not todo:
        return outcomes

    backend = select_backend(
        opts.backend, image=opts.docker_image, pull=opts.pull, mount_root=None
    )
    if backend.name == "docker":
        backend.mount_root = _mount_root(plans, opts)
    print(f"drawio-export: backend = {backend.describe()}", file=sys.stderr)
    backend.prepare()

    def _one(plan: Plan) -> Outcome:
        try:
            for req in _requests(plan, opts):
                backend.render(req)
            return Outcome(plan.source, plan.outputs, "rendered")
        except RenderError as e:
            return Outcome(plan.source, plan.outputs, "failed", str(e))

    if opts.jobs <= 1 or len(todo) == 1:
        results = [_one(p) for p in todo]
    else:
        with ThreadPoolExecutor(max_workers=opts.jobs) as pool:
            results = list(pool.map(_one, todo))

    for r in results:
        if r.status == "rendered":
            cache.update(r.source, root, opts.render_signature(), r.outputs)
    cache.save()

    return outcomes + results
