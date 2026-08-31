"""Expected, user-facing errors. Each carries the process exit code to use."""

from __future__ import annotations

from collections.abc import Iterable


class DrawioExportError(Exception):
    exit_code = 1


class CliError(DrawioExportError):
    exit_code = 2


class TargetNotFound(DrawioExportError):
    exit_code = 2

    def __init__(self, target: str, available: Iterable[str]) -> None:
        self.target = target
        self.available = sorted(available)
        super().__init__(f"no diagram found for {target!r}")


class BackendUnavailable(DrawioExportError):
    exit_code = 3


class RenderError(DrawioExportError):
    exit_code = 1
