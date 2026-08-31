from __future__ import annotations

import os
import shutil
import subprocess
import sys

from ..errors import RenderError
from .base import Backend, RenderRequest, export_args


class LocalBackend(Backend):
    name = "local"

    def __init__(self) -> None:
        self.drawio = shutil.which("drawio") or shutil.which("draw.io")
        self.xvfb_run = shutil.which("xvfb-run")

    def available(self) -> bool:
        return self.drawio is not None

    def describe(self) -> str:
        return f"local ({self.drawio or 'drawio not found'})"

    def needs_xvfb(self) -> bool:
        return sys.platform.startswith("linux") and not os.environ.get("DISPLAY")

    def command(self, req: RenderRequest) -> list[str]:
        base = [self.drawio or "drawio", "--no-sandbox"]
        base += export_args(req, str(req.source.resolve()), str(req.output.resolve()))
        if self.needs_xvfb() and self.xvfb_run:
            return [self.xvfb_run, "-a", *base]
        return base

    def render(self, req: RenderRequest) -> None:
        if not self.drawio:
            raise RenderError("no 'drawio' binary on PATH")
        if self.needs_xvfb() and not self.xvfb_run:
            raise RenderError(
                "headless Linux (no DISPLAY) and 'xvfb-run' not found; install xvfb"
            )
        req.output.parent.mkdir(parents=True, exist_ok=True)
        try:
            proc = subprocess.run(
                self.command(req), capture_output=True, text=True, timeout=req.timeout + 30
            )
        except subprocess.TimeoutExpired:
            raise RenderError(f"drawio render timed out after {req.timeout + 30:.0f}s")
        if proc.returncode != 0 or not req.output.exists():
            raise RenderError(
                (proc.stderr or proc.stdout or "").strip()[-1500:] or f"exit {proc.returncode}"
            )
