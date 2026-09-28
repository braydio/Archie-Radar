import json
from pathlib import Path

import pytest

from app.facebook import session


def test_session_handoff_writes_playwright_state(tmp_path, monkeypatch):
    path = tmp_path / "facebook" / "storage-state.json"
    monkeypatch.setattr(session, "_state_path", lambda: path)
    monkeypatch.setattr(session, "_meta_path", lambda: path.with_name("storage-state.meta.json"))

    result = session.save_chrome_cookies([
        {
            "name": "c_user", "value": "123", "domain": ".facebook.com", "path": "/",
            "expirationDate": 1900000000, "httpOnly": False, "secure": True, "sameSite": "no_restriction",
        },
        {
            "name": "xs", "value": "secret", "domain": ".facebook.com", "path": "/",
            "expirationDate": 1900000000, "httpOnly": True, "secure": True, "sameSite": "no_restriction",
        },
        {
            "name": "ignored", "value": "x", "domain": ".example.com", "path": "/",
        },
    ])

    assert result["ready"] is True
    assert result["cookie_count"] == 2
    assert session.session_ready() is True
    payload = json.loads(path.read_text())
    assert {item["name"] for item in payload["cookies"]} == {"c_user", "xs"}
    assert path.stat().st_mode & 0o077 == 0


def test_session_handoff_requires_authenticated_facebook_cookies(tmp_path, monkeypatch):
    path = tmp_path / "storage-state.json"
    monkeypatch.setattr(session, "_state_path", lambda: path)
    monkeypatch.setattr(session, "_meta_path", lambda: tmp_path / "storage-state.meta.json")

    with pytest.raises(ValueError, match="not logged in"):
        session.save_chrome_cookies([
            {"name": "datr", "value": "x", "domain": ".facebook.com", "path": "/"}
        ])

    assert not path.exists()


def test_clear_session(tmp_path, monkeypatch):
    path = tmp_path / "storage-state.json"
    meta = tmp_path / "storage-state.meta.json"
    path.write_text('{"cookies":[],"origins":[]}')
    meta.write_text('{"auth_state":"ready"}')
    monkeypatch.setattr(session, "_state_path", lambda: path)
    monkeypatch.setattr(session, "_meta_path", lambda: meta)

    session.clear_session()

    assert not path.exists()
    assert not meta.exists()
