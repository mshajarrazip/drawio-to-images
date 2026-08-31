from __future__ import annotations

from pathlib import Path

from ..errors import BackendUnavailable
from .base import Backend, RenderRequest, export_args
from .docker import DEFAULT_IMAGE, DockerBackend
from .local import LocalBackend

__all__ = [
    "Backend",
    "RenderRequest",
    "export_args",
    "DockerBackend",
    "LocalBackend",
    "DEFAULT_IMAGE",
    "select_backend",
]


def select_backend(
    name: str,
    *,
    image: str = DEFAULT_IMAGE,
    pull: bool = False,
    mount_root: Path | None = None,
) -> Backend:
    name = (name or "auto").lower()
    if name == "local":
        b = LocalBackend()
        if not b.available():
            raise BackendUnavailable(
                "backend 'local' requested but no 'drawio' binary is on PATH"
            )
        return b
    if name == "docker":
        b = DockerBackend(image=image, pull=pull, mount_root=mount_root)
        if not b.available():
            raise BackendUnavailable(
                "backend 'docker' requested but Docker is not available (is the daemon running?)"
            )
        return b
    if name == "auto":
        local = LocalBackend()
        if local.available():
            return local
        docker = DockerBackend(image=image, pull=pull, mount_root=mount_root)
        if docker.available():
            return docker
        raise BackendUnavailable(
            "no rendering backend available: install Docker and start the daemon, "
            "or put a 'drawio' binary on PATH"
        )
    raise BackendUnavailable(f"unknown backend: {name!r} (choose auto, docker, or local)")
