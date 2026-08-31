from __future__ import annotations

from pathlib import Path

TEMPLATE = """\
# drawio-export configuration. Every key is optional; CLI flags override these.

src = "diagrams"          # where .drawio files live
out = "imgs"              # where images are written (sub-dirs of src are mirrored)
formats = ["svg"]         # any of: svg, png, pdf, jpg

# scale = 2
# border = 8
# transparent = true      # png only
# quality = 90            # jpg only
# page-index = 0          # export only this page (0-based)

# backend = "auto"        # auto | docker | local
# docker-image = "rlespinasse/drawio-desktop-headless:v1.61.0"
# pull = false
# timeout = "30s"
# jobs = 4
# flatten = false
# include = ["**/*.drawio"]
# exclude = ["**/wip/**", "**/_archive/**"]
# cache-dir = ".drawio-export"
"""


def write_config(dest: Path, force: bool = False) -> bool:
    if dest.exists() and not force:
        return False
    dest.write_text(TEMPLATE, encoding="utf-8")
    return True
