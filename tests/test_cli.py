import pytest

from drawio_export.cli import main


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pyproject.toml").write_text("")
    return tmp_path


def test_version(capsys):
    with pytest.raises(SystemExit) as ei:
        main(["--version"])
    assert ei.value.code == 0
    assert "drawio-export" in capsys.readouterr().out


def test_list_on_empty_project(project):
    assert main(["list"]) == 0


def test_check_reports_stale_and_exits_1(project, capsys):
    d = project / "diagrams"
    d.mkdir()
    (d / "x.drawio").write_text("<mxfile/>")
    assert main(["check"]) == 1
    assert "stale" in capsys.readouterr().out


def test_render_with_no_sources_is_ok(project):
    (project / "diagrams").mkdir()
    assert main(["render"]) == 0


def test_dry_run_prints_plan(project, capsys):
    d = project / "diagrams"
    d.mkdir()
    (d / "x.drawio").write_text("<mxfile/>")
    assert main(["--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "render" in out and "x.svg" in out


def test_unknown_target_lists_available(project, capsys):
    d = project / "diagrams"
    d.mkdir()
    (d / "known.drawio").write_text("<mxfile/>")
    assert main(["render", "unknown"]) == 2
    err = capsys.readouterr().err
    assert "known" in err


def test_init_writes_config_once(project):
    assert main(["init"]) == 0
    assert (project / "drawio-export.toml").is_file()
    assert main(["init"]) == 1


def test_bad_backend_choice(project):
    # argparse rejects the value before we run anything
    with pytest.raises(SystemExit):
        main(["render", "--backend", "nonsense"])
