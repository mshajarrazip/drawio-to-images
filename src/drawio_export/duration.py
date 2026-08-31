"""Parse human durations like '30s', '2m', '1m30s' into seconds."""

from __future__ import annotations

import re

from .errors import CliError

_NUM = re.compile(r"^\d+(?:\.\d+)?$")
_PART = re.compile(r"(\d+(?:\.\d+)?)\s*([smh])")
_UNIT = {"s": 1.0, "m": 60.0, "h": 3600.0}


def parse_duration(value: str | float | int) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().lower()
    if not s:
        raise CliError("empty duration")
    if _NUM.match(s):
        return float(s)
    parts = _PART.findall(s)
    if not parts or _PART.sub("", s).strip():
        raise CliError(f"invalid duration: {value!r} (use e.g. '30s', '2m', '1m30s')")
    return sum(float(n) * _UNIT[u] for n, u in parts)
