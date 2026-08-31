import pytest

from drawio_export.discovery import (
    default_src,
    discover,
    labels,
    resolve_target,
    resolve_targets,
)
from drawio_export.errors import TargetNotFound


@pytest.fixture
def tree(tmp_path):
    d = tmp_path / "diagrams"
    (d / "sub").mkdir(parents=True)
    (d / "a.drawio").write_text("<mxfile/>")
    (d / "sub" / "b.drawio").write_text("<mxfile/>")
    (d / "note.txt").write_text("x")
    return tmp_path


def test_discover_is_sorted_and_ignores_non_drawio(tree):
    src = tree / "diagrams"
    assert [p.relative_to(src).as_posix() for p in discover(src)] == [
        "a.drawio",
        "sub/b.drawio",
    ]


def test_discover_include_exclude(tree):
    src = tree / "diagrams"
    assert discover(src, exclude=["sub/**"]) == [src / "a.drawio"]
    assert discover(src, include=["sub/**"]) == [src / "sub" / "b.drawio"]


def test_default_src(tree):
    assert default_src(tree) == tree / "diagrams"
    assert default_src(tree / "diagrams") == tree / "diagrams"


def test_labels(tree):
    assert labels(tree / "diagrams") == ["a", "sub/b"]


def test_resolve_target_variants(tree):
    src = tree / "diagrams"
    want = (src / "a.drawio").resolve()
    assert resolve_target("a", src) == want
    assert resolve_target("a.drawio", src) == want
    assert resolve_target("sub/b", src) == (src / "sub" / "b.drawio").resolve()


def test_resolve_target_full_path_from_cwd(tree, monkeypatch):
    monkeypatch.chdir(tree)
    src = tree / "diagrams"
    assert resolve_target("diagrams/a.drawio", src) == (src / "a.drawio").resolve()


def test_resolve_target_missing_lists_available(tree):
    with pytest.raises(TargetNotFound) as ei:
        resolve_target("nope", tree / "diagrams")
    assert ei.value.available == ["a", "sub/b"]


def test_resolve_targets_dedupes(tree):
    src = tree / "diagrams"
    assert resolve_targets(["a", "a.drawio"], src) == [(src / "a.drawio").resolve()]
