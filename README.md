# drawio-to-images

A `uvx`-installable CLI that renders `.drawio` files to images (SVG / PNG / PDF / JPG),
with source-change tracking so it only re-renders what actually changed.

> **Status: PLAN / not yet implemented.** This README is the design spec for the tool.
> Nothing under `src/` exists yet. See [Implementation plan](#implementation-plan) for the
> build order.

---

## Why this exists

The [`MLNG-DigitalLAP-Design-2`](../MLNG-DigitalLAP-Design-2) repo has a working diagram
export pipeline, but it is **vendored into that repo** and can't be reused elsewhere without
copy-paste:

- `compose.yml` defines an `export` service.
- `drawio-exporter/Dockerfile` builds a local image `FROM rlespinasse/drawio-desktop-headless:v1.61.0`
  purely to swap in a custom entrypoint.
- `drawio-exporter/entrypoint.sh` (~130 lines of bash) does the real work: start Xvfb, parse
  `--force` + target labels, resolve a bare label / relative path / full path to a `.drawio`
  file, walk `diagrams/**/*.drawio` when no target is given, `sha256` each source against a
  cache under `tmp/.drawio-exporter/`, and call the drawio runner (`-x -f svg -o <out> <in>`)
  under a `timeout` — writing the hash file only on success. Output mirrors the source tree:
  `diagrams/foo.drawio` → `imgs/foo.svg`.

To use that in a new project today you must copy three files, commit a Dockerfile, and carry
the pipeline's rough edges with you. Those rough edges (all documented in the sibling repo's
own troubleshooting section):

- **`UID`/`GID` mapping is broken by design.** `compose.yml` uses `user: "${UID:-1000}:${GID:-1000}"`,
  but `UID` is a read-only bash variable (can't be `export`ed) and `GID` isn't a shell variable
  at all, so it silently falls back to `1000:1000`. Any host user that isn't `1000:1000` gets
  `Permission denied` writing to `imgs/` and `tmp/`, and the fix is a hand-written `.env` file.
- **Stale image reuse.** `docker compose run` reuses a stale built image; you must remember
  `--build` after editing the entrypoint.
- **SVG only.** Format is hard-coded in the entrypoint.
- **Fixed layout.** `diagrams/` → `imgs/`, no configuration.
- **Per-project Docker requirement.** Every consuming repo needs Docker + Compose + the
  vendored files.

**Goal:** extract the rendering *policy* (discovery, change tracking, path mapping, batching)
into a standalone Python CLI that you install once and run in any project, and delegate the
actual rendering to a backend (a stock published Docker image, or a local `drawio` binary).

---

## Feasibility

**Feasible — as an orchestrator, not a renderer.**

There is no faithful pure-Python renderer for arbitrary `.drawio` files; drawio's rendering
engine (mxGraph / Electron) is JavaScript. Any tool that renders real-world `.drawio` files
must drive one of:

1. **A headless drawio-desktop in Docker** — `rlespinasse/drawio-desktop-headless` is
   **already published on Docker Hub** and is designed to be invoked directly as
   `docker run … --export --format svg --output out.svg in.drawio` (it is the image behind
   the `rlespinasse/drawio-export-action` GitHub Action). The sibling repo only *builds* it
   locally to bolt on the hash-cache logic. If our CLI reimplements that logic host-side in
   Python, it can call the **stock image** with `docker run` — **no local Dockerfile, no
   `compose.yml`, no build step**, and the CLI passes `--user $(id -u):$(id -g)` itself, so
   the `UID`/`GID` bug disappears.
2. **A local `drawio` binary** — if the user has drawio-desktop installed (AppImage / deb /
   `.app`), the CLI calls `drawio --export …` directly, no Docker. On headless Linux it wraps
   the call in `xvfb-run` when available.

So the CLI is **pure-Python for packaging purposes** (stdlib + one small dep), ships the
*policy*, and shells out to a backend for pixels. This is a good fit for `uvx` / `uv tool
install` from git.

> One assumption to confirm during implementation: the exact CLI contract of
> `rlespinasse/drawio-desktop-headless:<tag>` when run without the sibling repo's custom
> entrypoint (flag names, page handling). The design intent of that image supports it; it
> will be verified against a pinned tag before the docker backend is called done.

### What is *not* possible / out of scope

- **No zero-dependency rendering.** The CLI always needs *either* Docker *or* a local
  `drawio` binary at run time. With neither, it can discover, diff, and report, but cannot
  render. `drawio-export doctor` makes this explicit.
- **No rendering-fidelity fixes.** Output is exactly what the chosen backend produces; the
  CLI does not patch drawio bugs, font substitution, or layout quirks.
- **No browser/JS runtime bundled.** We don't ship Electron or a Node renderer.
- **Embedded `.drawio.png` / `.drawio.svg`** (diagram XML embedded in an image) — not in the
  first release; see [KIV](#kiv--future-ideas).
- **Not a server / not a watch daemon by default** (watch mode is opt-in and foreground).

---

## What the tool does

### Core behaviour (parity with the sibling pipeline)

- Discover `.drawio` sources under a source dir (default `diagrams/`, or `.` if there is no
  `diagrams/`), recursively.
- Resolve a **target argument** given as a bare label (`data-intake-flow`), a path relative to
  the source dir (`sub/dir/foo`), or a full repo-relative path
  (`diagrams/data-intake-flow.drawio`) — with or without the `.drawio` suffix. An unknown
  target fails and prints the list of available diagrams.
- With no target: process every discovered `.drawio`.
- **Change tracking:** hash each source (and the render options it would be rendered with);
  skip it when the hash matches the cache *and* the expected output files exist. Log each
  decision (`render` / `skip (unchanged)` / `render (source changed)` / `render (output
  missing)` / `render (forced)`).
- Write output mirroring the source tree: `<src>/a/b/foo.drawio` → `<out>/a/b/foo.<ext>`.
- Update the cache only after a successful render.
- Per-diagram timeout.

### Extensions (new in this tool)

| Feature | Detail |
|---|---|
| **Multiple formats** | `--format svg` (default), `png`, `pdf`, `jpg`; comma-list `--format png,svg` renders each. |
| **Render options** | `--scale`, `--width`, `--height`, `--border`, `--transparent` (png), `--quality` (jpg), `--crop`. Options are part of the cache key, so changing `--scale` re-renders. |
| **Multi-page `.drawio`** | `--all-pages` (one output per page, `foo.page-2.svg` …) or `--page-index N`. Bounded by backend capability (PDF handles multi-page best). |
| **Config file** | `[tool.drawio-export]` in `pyproject.toml`, or `drawio-export.toml`. Sets src/out/formats/backend/excludes and **per-diagram overrides**. CLI flags win over config. |
| **Backends** | `--backend auto` (default: local `drawio` if on PATH, else docker) / `docker` / `local`. `--docker-image` override, `--pull` to refresh. |
| **CI mode** | `drawio-export check` — dry run, exits non-zero if any output is stale or missing (like `black --check`). `--json` for machine-readable results. |
| **Parallelism** | `--jobs N` renders diagrams concurrently (default: min(CPU, 4)). |
| **Orphan cleanup** | `drawio-export prune` deletes outputs whose source no longer exists (`--dry-run` to preview). |
| **Watch mode** | `drawio-export watch` re-renders on source change (opt-in extra: `drawio-to-images[watch]`). |
| **Include/exclude** | `--include GLOB` / `--exclude GLOB`, repeatable; also from config. |
| **Output naming** | `--out-pattern '{relpath}/{stem}.{ext}'` (default); tokens `{relpath} {dir} {stem} {ext} {format} {scale} {page}`. |
| **Manifest** | `--manifest [PATH]` writes `index.json` mapping source → outputs → hash → mtime, for docs pipelines. |
| **Diagnostics** | `drawio-export doctor` checks: Docker present & daemon up, image pulled, local `drawio` version, `xvfb-run` presence, writable out/cache dirs, effective uid/gid. Automates the sibling repo's whole troubleshooting section. |
| **Scaffolding** | `drawio-export init` writes a starter config, a `.gitignore` line for the cache dir, and prints a ready-to-paste `.pre-commit-config.yaml` block. |
| **Listing** | `drawio-export list` — every discovered diagram with its current status (fresh / stale / never rendered). |
| **Single-file mode** | `drawio-export path/to/one.drawio -o out.png` bypasses discovery. |
| **pre-commit hook** | Ships `.pre-commit-hooks.yaml` so consumers can wire it as a hook that re-renders changed diagrams. |

### Cache location

Per-project, at the project root (git root, or the dir containing `pyproject.toml` /
`drawio-export.toml`, else CWD):

```
.drawio-export/
  cache.json        # { "<src rel path>": { "hash": "...", "opts": "...", "outputs": [...], "rendered_at": "..." } }
```

A single JSON manifest instead of the sibling's one `.sha256` file per diagram. `--cache-dir`
overrides; `--no-cache` disables read and write. Add `.drawio-export/` to `.gitignore`
(`init` does this).

---

## CLI reference (proposed)

```
drawio-export [TARGETS...] [OPTIONS]        # default action = render
drawio-export render [TARGETS...] [OPTIONS] # explicit alias
drawio-export check  [TARGETS...] [OPTIONS] # dry run; exit 1 if stale  (CI)
drawio-export list   [OPTIONS]              # discovered diagrams + status
drawio-export prune  [OPTIONS]              # remove orphaned outputs
drawio-export watch  [TARGETS...] [OPTIONS] # re-render on change (extra)
drawio-export doctor                        # environment diagnostics
drawio-export init                          # scaffold config + gitignore
```

Common options:

```
  --src DIR                 source root (default: diagrams/ if present, else .)
  --out DIR                 output root (default: imgs/)
  --format LIST             svg | png | pdf | jpg, comma-separated (default: svg)
  -f, --force               re-render even if unchanged
  -n, --check               dry run; non-zero exit if anything is stale
  --jobs N                  parallel renders (default: min(CPU, 4))
  --backend auto|docker|local
  --docker-image NAME:TAG   (default: rlespinasse/drawio-desktop-headless:v1.61.0)
  --pull                    docker pull before rendering
  --timeout DURATION        per diagram (default: 30s)
  --scale N | --width PX | --height PX | --border PX
  --transparent            PNG background transparent
  --quality N              JPG quality 0-100
  --all-pages | --page-index N
  --out-pattern PATTERN     default '{relpath}/{stem}.{ext}'
  --include GLOB            repeatable
  --exclude GLOB            repeatable
  --cache-dir DIR           (default: <project>/.drawio-export)
  --no-cache               ignore and do not write the cache
  --manifest [PATH]         write an index.json manifest
  --json                   machine-readable output on stdout
  -q, --quiet | -v, --verbose
  --version
```

### Usage examples

```bash
# Render every changed diagram in diagrams/ -> imgs/*.svg
drawio-export

# One diagram, by bare label
drawio-export data-intake-flow

# Several, by name
drawio-export schema data-intake-flow

# Force re-render
drawio-export -f data-intake-flow
drawio-export -f

# PNG + SVG at 2x
drawio-export --format png,svg --scale 2

# A non-standard layout
drawio-export --src docs/diagrams --out docs/assets/diagrams --format pdf

# CI: fail the build if any committed image is out of date
drawio-export check

# Diagnose a broken environment
drawio-export doctor
```

---

## Configuration file

`pyproject.toml`:

```toml
[tool.drawio-export]
src = "diagrams"
out = "imgs"
formats = ["svg", "png"]
scale = 2
backend = "auto"
exclude = ["**/wip/**", "**/_archive/**"]
timeout = "45s"

[tool.drawio-export.per-diagram."context-map"]
formats = ["svg", "pdf"]
scale = 1
```

or a standalone `drawio-export.toml` with the same keys minus the `[tool.drawio-export]`
wrapper. Precedence: **CLI flag > config file > built-in default**.

---

## Installation

**Prerequisites**

- `uv` / `uvx` ([install](https://docs.astral.sh/uv/getting-started/installation/)).
- Python ≥ 3.11 (uv fetches it if missing).
- **A rendering backend**, one of:
  - Docker with a running daemon (the CLI pulls `rlespinasse/drawio-desktop-headless` on
    first use — a large, ~1 GB+ image), **or**
  - a local `drawio` desktop binary on `PATH` (plus `xvfb-run` on headless Linux).

**One-off (no install):**

```bash
uvx --from git+https://github.com/mshajarrazip/drawio-to-images drawio-export
```

**Pinned to a tag (recommended for CI / reproducibility):**

```bash
uvx --from git+https://github.com/mshajarrazip/drawio-to-images@v0.1.0 drawio-export check
```

**Persistent install (adds `drawio-export` to your PATH):**

```bash
uv tool install git+https://github.com/mshajarrazip/drawio-to-images
drawio-export --version
```

**As a project dev dependency** (`pyproject.toml`):

```toml
[dependency-groups]
dev = ["drawio-to-images @ git+https://github.com/mshajarrazip/drawio-to-images@v0.1.0"]
```

then `uv run drawio-export`.

**With the watch extra:**

```bash
uv tool install "drawio-to-images[watch] @ git+https://github.com/mshajarrazip/drawio-to-images"
```

**pre-commit** (`.pre-commit-config.yaml`):

```yaml
repos:
  - repo: https://github.com/mshajarrazip/drawio-to-images
    rev: v0.1.0
    hooks:
      - id: drawio-export        # re-renders changed diagrams, stages the images
```

---

## How it works (runtime flow)

```
discover sources (--src, --include/--exclude)
      │
resolve TARGETS  ──►  bare label / rel path / full path, ±.drawio
      │
for each source (--jobs in parallel):
      │
   hash(source bytes + render options)
      │
   compare to .drawio-export/cache.json
      ├─ match AND all expected outputs exist  ──►  skip, log "unchanged"
      └─ otherwise                              ──►  render
                                                       │
                              backend = local drawio? ──► drawio --export …            (xvfb-run if headless)
                              else                    ──► docker run --user $uid:$gid   rlespinasse/drawio-desktop-headless … --export …
                                                       │
                                                on success: write outputs, update cache entry
                                                on timeout/failure: leave cache untouched, mark run failed
      │
(optional) write manifest index.json
      │
exit 0 if all good; non-zero if any render failed (or, for `check`, if anything was stale)
```

---

## Limits & caveats

- **Backend required at render time.** No Docker and no local `drawio` ⇒ discovery/diff/report
  work, rendering does not.
- **First Docker run is slow** — one large image pull.
- **Fidelity is the backend's.** Fonts, shape libraries, and layout match drawio-desktop of
  that image tag; pin the tag for stable output.
- **Headless Linux + `--backend local`** needs `xvfb-run` (the CLI auto-wraps when it's
  present; errors clearly when it isn't).
- **Docker Desktop (macOS/Windows)** ignores `--user`; files are already owned by you there.
  Bind-mount performance is worse than Linux for large trees.
- **Per-diagram timeout** (default 30s) — very large diagrams may need `--timeout`.
- **Multi-page raster export** is limited by the backend; PDF is the reliable multi-page
  format. `--all-pages` for PNG/SVG emits one file per page where the backend supports it.
- **`uvx` from a branch is not reproducible** — always pin `@vX.Y.Z` (or a commit SHA) for CI.
- **Shells out to `docker` / `drawio`.** Those binaries and their trust boundary are the
  user's responsibility; the CLI does not sandbox them.
- **Cache is per-project and local.** It is not committed; a fresh checkout re-renders
  everything once (which is also what `check` expects in CI — commit the images).

---

## Implementation plan

Build order, each step independently testable:

1. **Package skeleton** — `pyproject.toml` (`[project.scripts] drawio-export =
   "drawio_export.cli:main"`, build backend `uv_build` or `hatchling`), `src/drawio_export/`,
   `--version`, `--help`. Confirm `uvx --from git+… drawio-export --help` works from a clean
   machine.
2. **Discovery + target resolution** (`discovery.py`) — port `resolve_target()` and the
   `find … -name '*.drawio'` walk from the sibling entrypoint; add `--include`/`--exclude`.
   Unit-test the resolver against bare label / rel path / full path / missing.
3. **Cache** (`cache.py`) — `cache.json` read/write, hash of source bytes + normalised render
   options, staleness decision incl. "output missing".
4. **Docker backend** (`backends/docker.py`) — `docker run --rm --user $uid:$gid -v
   $src:… -v $out:… <image> --export --format <fmt> --output … <input>`, per-diagram
   `--timeout`. Verify the stock image's real flag contract against the pinned tag; adjust.
5. **Render orchestrator** (`render.py`) — wire discovery → cache → backend, `--jobs`
   parallelism, structured per-diagram result, exit codes. Reach **parity** with the sibling
   pipeline here (svg only, `diagrams/` → `imgs/`, force/skip).
6. **Multi-format + render options** — `--format` list, `--scale/--width/--height/--border/
   --transparent/--quality`, options folded into the cache key, `--out-pattern`.
7. **`check` / `list` / `prune`** subcommands + `--json`.
8. **Config file** (`config.py`) — `[tool.drawio-export]` / `drawio-export.toml`,
   per-diagram overrides, precedence.
9. **Local backend** (`backends/local.py`) — detect `drawio` on PATH, `xvfb-run` wrap,
   `--backend auto` selection.
10. **`doctor`** — environment checks covering every failure mode in the sibling repo's
    troubleshooting section.
11. **`init`** + `.pre-commit-hooks.yaml` + a PEP 723 single-file shim for `uv run`.
12. **`watch`** (`[watch]` extra, `watchfiles`).
13. **`--manifest`**, docs, `v0.1.0` tag.

**Proposed dependencies:** stdlib `argparse` + `rich` (small, pure-Python, for readable
output) as the only core dep; `tomllib` is stdlib on 3.11+. Extras: `[watch]` →
`watchfiles`. Keep the core install light so `uvx` stays fast.

**Proposed layout:**

```
drawio-to-images/
├── pyproject.toml
├── README.md
├── .pre-commit-hooks.yaml
├── src/drawio_export/
│   ├── __init__.py
│   ├── cli.py              # argparse, subcommands, exit codes
│   ├── config.py           # pyproject / drawio-export.toml loader + precedence
│   ├── discovery.py        # source walk + target resolution
│   ├── cache.py            # cache.json, hashing, staleness
│   ├── render.py           # orchestration, --jobs, results
│   ├── outputs.py          # --out-pattern, path mapping
│   ├── manifest.py         # index.json
│   ├── doctor.py           # environment diagnostics
│   └── backends/
│       ├── __init__.py     # backend selection (auto)
│       ├── base.py
│       ├── docker.py
│       └── local.py
└── tests/
```

---

## Migrating `MLNG-DigitalLAP-Design-2` (once this ships)

- Delete `compose.yml`, `drawio-exporter/`, and the README troubleshooting section.
- Replace step 4 of the `create-diagram` skill with
  `uvx --from git+https://github.com/mshajarrazip/drawio-to-images@vX.Y.Z drawio-export <name>`
  (or `uv tool install` once, then `drawio-export <name>`).
- The hash cache moves from `tmp/.drawio-exporter/<name>.sha256` to
  `.drawio-export/cache.json`; add `.drawio-export/` to `.gitignore`.
- Behaviour and CLI surface stay compatible: `drawio-export`, `drawio-export <name>`,
  `drawio-export <a> <b>`, `drawio-export -f [<name>]` all map 1:1 to the old
  `docker compose run --rm export …` forms.

---

## KIV / future ideas

- Embedded `.drawio.png` / `.drawio.svg` input (extract XML, then render).
- `--backend npx` using an npm drawio export package, for Node-only environments.
- Remote/CI cache (share `cache.json` + outputs via an artifact store).
- `vsdx` / `xml` export formats.
- A `--serve` preview mode (local HTTP, live re-render) — explicitly out of the current scope.
- Auto-commit / auto-stage rendered images in the pre-commit hook (currently just renders).
- Per-format option profiles in config (e.g. png always transparent + 2x, pdf always all-pages).
