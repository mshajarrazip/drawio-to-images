from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from ..errors import BackendUnavailable, RenderError
from .base import Backend, RenderRequest, export_args

DEFAULT_IMAGE = "rlespinasse/drawio-desktop-headless:v1.61.0"


class DockerBackend(Backend):
    name = "docker"

    def __init__(
        self,
        image: str = DEFAULT_IMAGE,
        pull: bool = False,
        mount_root: Path | None = None,
    ) -> None:
        self.image = image
        self.pull = pull
        self.mount_root = Path(mount_root).resolve() if mount_root else None

    def available(self) -> bool:
        if not shutil.which("docker"):
            return False
        try:
            subprocess.run(
                ["docker", "info"], capture_output=True, timeout=20, check=True
            )
        except (subprocess.SubprocessError, OSError):
            return False
        return True

    def describe(self) -> str:
        return f"docker ({self.image})"

    def image_present(self) -> bool:
        return (
            subprocess.run(
                ["docker", "image", "inspect", self.image], capture_output=True
            ).returncode
            == 0
        )

    def prepare(self) -> None:
        if self.pull or not self.image_present():
            print(f"drawio-export: pulling {self.image} ...", file=sys.stderr)
            if subprocess.run(["docker", "pull", self.image]).returncode != 0:
                raise BackendUnavailable(f"failed to pull docker image {self.image}")

    def _mount_for(self, req: RenderRequest) -> Path:
        if self.mount_root:
            return self.mount_root
        return Path(
            os.path.commonpath(
                [str(req.source.resolve().parent), str(req.output.resolve().parent)]
            )
        )

    def command(self, req: RenderRequest) -> list[str]:
        mount = self._mount_for(req)
        rel_in = req.source.resolve().relative_to(mount).as_posix()
        rel_out = req.output.resolve().relative_to(mount).as_posix()
        cmd = [
            "docker", "run", "--rm",
            "-e", "HOME=/tmp",
            "-e", f"DRAWIO_DESKTOP_COMMAND_TIMEOUT={max(1, int(req.timeout))}s",
            "-v", f"{mount}:/data",
            "-w", "/data",
        ]
        if sys.platform.startswith("linux") and hasattr(os, "getuid"):
            cmd += ["--user", f"{os.getuid()}:{os.getgid()}"]
        cmd.append(self.image)
        cmd += export_args(req, rel_in, rel_out)
        return cmd

    def render(self, req: RenderRequest) -> None:
        mount = self._mount_for(req)
        for p in (req.source, req.output):
            try:
                p.resolve().relative_to(mount)
            except ValueError:
                raise RenderError(
                    f"{p} is outside the docker mount root {mount}; use --backend local "
                    "or keep sources and outputs under one directory tree"
                )
        req.output.parent.mkdir(parents=True, exist_ok=True)
        try:
            proc = subprocess.run(
                self.command(req), capture_output=True, text=True, timeout=req.timeout + 30
            )
        except subprocess.TimeoutExpired:
            raise RenderError(f"docker render timed out after {req.timeout + 30:.0f}s")
        if proc.returncode != 0 or not req.output.exists():
            raise RenderError(_tail(proc.stderr or proc.stdout) or f"exit {proc.returncode}")


def _tail(text: str, limit: int = 1500) -> str:
    return (text or "").strip()[-limit:]
