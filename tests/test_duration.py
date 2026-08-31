import pytest

from drawio_export.duration import parse_duration
from drawio_export.errors import CliError


@pytest.mark.parametrize(
    "value,want",
    [
        ("30s", 30),
        ("45", 45),
        ("2m", 120),
        ("1m30s", 90),
        ("1h", 3600),
        ("1.5h", 5400),
        (15, 15),
        (2.5, 2.5),
    ],
)
def test_parse_ok(value, want):
    assert parse_duration(value) == want


@pytest.mark.parametrize("value", ["", "abc", "10x", "m", "30 s x"])
def test_parse_bad(value):
    with pytest.raises(CliError):
        parse_duration(value)
