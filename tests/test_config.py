import argparse
import textwrap

from drawio_export.config import find_project_root, load_config, resolve_options


def _ns(**kw):
    base = dict(
        src=None, out=None, formats=None, scale=None, width=None, height=None,
        border=None, transparent=None, quality=None, page_index=None, backend=None,
        docker_image=None, pull=None, timeout=None, jobs=None, flatten=None,
        include=None, exclude=None, cache_dir=None, no_cache=None,
    )
    base.update(kw)
    return argparse.Namespace(**base)


def test_pyproject_config_is_read(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        textwrap.dedent(
            """
            [tool.drawio-export]
            src = "d"
            out = "o"
            format = ["svg", "png"]
            scale = 2
            timeout = "45s"
            """
        )
    )
    cfg = load_config(tmp_path)
    opts = resolve_options(_ns(), cfg, tmp_path)
    assert opts.src == (tmp_path / "d").resolve()
    assert opts.out == (tmp_path / "o").resolve()
    assert opts.formats == ["svg", "png"]
    assert opts.scale == 2.0
    assert opts.timeout == 45.0


def test_standalone_toml_wins_over_pyproject(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[tool.drawio-export]\nout = "from_pyproject"\n')
    (tmp_path / "drawio-export.toml").write_text('out = "from_toml"\n')
    assert load_config(tmp_path)["out"] == "from_toml"


def test_cli_overrides_config(tmp_path):
    (tmp_path / "drawio-export.toml").write_text("scale = 2\n")
    opts = resolve_options(_ns(scale=4.0), load_config(tmp_path), tmp_path)
    assert opts.scale == 4.0


def test_defaults_when_no_config(tmp_path):
    opts = resolve_options(_ns(), {}, tmp_path)
    assert opts.formats == ["svg"]
    assert opts.backend == "auto"
    assert opts.timeout == 30.0
    assert opts.use_cache is True
    assert opts.cache_dir == (tmp_path / ".drawio-export").resolve()


def test_find_project_root(tmp_path):
    (tmp_path / "pyproject.toml").write_text("")
    sub = tmp_path / "a" / "b"
    sub.mkdir(parents=True)
    assert find_project_root(sub) == tmp_path
