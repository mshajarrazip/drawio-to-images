from drawio_export.cache import Cache


def test_cache_roundtrip_and_invalidation(tmp_path):
    root = tmp_path
    src = tmp_path / "a.drawio"
    src.write_text("one")
    out = tmp_path / "a.svg"
    cpath = tmp_path / ".drawio-export" / "cache.json"

    c = Cache(cpath, enabled=True)
    assert c.is_fresh(src, root, "sig", [out]) is False  # no entry yet

    out.write_text("<svg/>")
    c.update(src, root, "sig", [out])
    c.save()

    reloaded = Cache(cpath, enabled=True)
    assert reloaded.is_fresh(src, root, "sig", [out]) is True
    assert reloaded.is_fresh(src, root, "other", [out]) is False  # signature changed

    src.write_text("two")
    assert reloaded.is_fresh(src, root, "sig", [out]) is False  # source changed

    src.write_text("one")
    out.unlink()
    assert reloaded.is_fresh(src, root, "sig", [out]) is False  # output missing


def test_disabled_cache_writes_nothing_and_is_never_fresh(tmp_path):
    cpath = tmp_path / "cache.json"
    c = Cache(cpath, enabled=False)
    src = tmp_path / "a.drawio"
    src.write_text("x")
    c.update(src, tmp_path, "sig", [])
    c.save()
    assert not cpath.exists()
    assert c.is_fresh(src, tmp_path, "sig", []) is False


def test_corrupt_cache_file_is_ignored(tmp_path):
    cpath = tmp_path / "cache.json"
    cpath.write_text("not json{{{")
    c = Cache(cpath, enabled=True)
    assert c.entries() == {}
