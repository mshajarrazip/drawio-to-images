"""`drawio-export doctor` — check the environment for a working render backend."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

from .backends import DEFAULT_IMAGE
from .backends.docker import DockerBackend
from .backends.local import LocalBackend


def _line(status: str, label: str, detail: str = "") -> None:
    print(f"  [{status:4}] {label}" + (f" — {detail}" if detail else ""))


def run_doctor() -> int:
    print("drawio-export doctor\n")
    print(f"python      {sys.version.split()[0]}  ({sys.platform})")
    if hasattr(os, "getuid"):
        print(f"uid:gid     {os.getuid()}:{os.getgid()}")
    print()

    docker = DockerBackend()
    print("docker backend")
    if not shutil.which("docker"):
        _line("MISS", "docker binary", "not on PATH")
    else:
        _line("OK", "docker binary", shutil.which("docker") or "")
        if docker.available():
            _line("OK", "docker daemon", "reachable")
            present = docker.image_present()
            _line(
                "OK" if present else "WARN",
                f"image {DEFAULT_IMAGE}",
                "present" if present else "not pulled yet (first render pulls it)",
            )
        else:
            _line("FAIL", "docker daemon", "not reachable — start Docker")
    print()

    local = LocalBackend()
    print("local backend")
    if not local.drawio:
        _line("MISS", "drawio binary", "not on PATH")
    else:
        version = ""
        try:
            version = subprocess.run(
                [local.drawio, "--version"],
                capture_output=True,
                text=True,
                timeout=15,
            ).stdout.strip()
        except (subprocess.SubprocessError, OSError):
            pass
        _line("OK", "drawio binary", f"{local.drawio} {version}".strip())
        if local.needs_xvfb():
            _line(
                "OK" if local.xvfb_run else "WARN",
                "xvfb-run",
                local.xvfb_run or "missing (needed on headless Linux)",
            )
    print()

    usable = []
    if docker.available():
        usable.append("docker")
    if local.available():
        usable.append("local")
    if usable:
        auto = "local" if local.available() else "docker"
        print(f"result: usable backends: {', '.join(usable)}  (auto picks: {auto})")
        return 0
    print(
        "result: NO usable backend. Install Docker and start it, or put 'drawio' on PATH."
    )
    return 1
