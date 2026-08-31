import pytest

from drawio_export.errors import CliError
from drawio_export.outputs import normalize_formats, output_path


@pytest.fixture
def src_out(tmp_path):
    src = tmp_path / "diagrams"
    out = tmp_path / "imgs"
    (src / "sub").mkdir(parents=True)
    s = src / "sub" / "x.drawio"
    s.write_text("<mxfile/>")
    return s, src, out


def test_output_path_mirrors_tree(src_out):
    s, src, out = src_out
    assert output_path(s, src, out, "svg") == (out / "sub" / "x.svg").resolve()


def test_output_path_flatten(src_out):
    s, src, out = src_out
    assert output_path(s, src, out, "png", flatten=True) == (out / "x.png").resolve()


def test_output_path_page_suffix(src_out):
    s, src, out = src_out
    assert output_path(s, src, out, "svg", page=2).name == "x.page-2.svg"


def test_normalize_formats():
    assert normalize_formats("svg,png") == ["svg", "png"]
    assert normalize_formats(["JPG", "jpeg", "jpg"]) == ["jpg"]
    assert normalize_formats("pdf , svg") == ["pdf", "svg"]


def test_normalize_formats_rejects_unknown():
    with pytest.raises(CliError):
        normalize_formats("gif")
    with pytest.raises(CliError):
        normalize_formats("")
