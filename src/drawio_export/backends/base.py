from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class RenderRequest:
    source: Path
    output: Path
    fmt: str
    scale: float | None = None
    width: int | None = None
    height: int | None = None
    border: int | None = None
    transparent: bool = False
    quality: int | None = None
    page_index: int | None = None
    timeout: float = 30.0


def export_args(req: RenderRequest, in_path: str, out_path: str) -> list[str]:
    """drawio-desktop CLI arguments common to every backend."""
    a = ["-x", "-f", req.fmt, "-o", out_path]
    if req.scale is not None:
        a += ["-s", str(req.scale)]
    if req.border is not None:
        a += ["-b", str(req.border)]
    if req.width is not None:
        a += ["--width", str(req.width)]
    if req.height is not None:
        a += ["--height", str(req.height)]
    if req.transparent and req.fmt == "png":
        a.append("--transparent")
    if req.quality is not None and req.fmt == "jpg":
        a += ["-q", str(req.quality)]
    if req.page_index is not None:
        a += ["-p", str(req.page_index)]
    a.append(in_path)
    return a


class Backend:
    name = "base"

    def available(self) -> bool:
        raise NotImplementedError

    def describe(self) -> str:
        return self.name

    def prepare(self) -> None:
        """One-time setup before the first render (e.g. `docker pull`)."""

    def command(self, req: RenderRequest) -> list[str]:
        raise NotImplementedError

    def render(self, req: RenderRequest) -> None:
        raise NotImplementedError
