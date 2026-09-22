# -*- coding: utf-8 -*-
import json
from unittest.mock import MagicMock, patch


def test_offline_skips_network():
    from app.update_checker import check_for_updates

    r = check_for_updates(offline=True)
    assert r["error"] == "offline"
    assert r["update_available"] is False
    assert r["source"] == "offline"


def test_fetch_invalid_scheme():
    from app.update_checker import fetch_manifest

    data, err = fetch_manifest("ftp://evil.example/x")
    assert data is None
    assert "scheme" in err


def test_check_for_updates_mocked():
    from app.release_manifest import example_manifest
    from app.update_checker import check_for_updates

    body = json.dumps(example_manifest(version="99.0.0")).encode("utf-8")

    class Resp:
        def read(self, n=-1):
            return body

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

    with patch("app.update_checker.urlopen", return_value=Resp()):
        r = check_for_updates(url="https://example.com/release.json", offline=False)
    assert r["manifest_ok"] is True
    assert r["update_available"] is True
    assert r["latest"] == "99.0.0"
    assert r["source"] == "network"


def test_format_notice():
    from app.update_checker import format_update_notice

    assert format_update_notice({"update_available": False}) == ""
    text = format_update_notice({
        "update_available": True,
        "manifest_ok": True,
        "latest": "0.10.1",
        "notes": "fixes",
    })
    assert "0.10.1" in text
    assert "Обновить" in text


def test_http_error_fail_closed():
    from app.update_checker import fetch_manifest
    from urllib.error import HTTPError

    with patch(
        "app.update_checker.urlopen",
        side_effect=HTTPError("https://x", 404, "no", hdrs=None, fp=None),
    ):
        data, err = fetch_manifest("https://example.com/release.json")
    assert data is None
    assert err.startswith("http:")
