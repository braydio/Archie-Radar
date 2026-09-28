from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..settings import get_settings


def _state_path() -> Path:
    settings = get_settings()
    configured = (settings.facebook_session_state_path or "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path(settings.media_dir).resolve() / "facebook" / "storage-state.json")


def _meta_path() -> Path:
    path = _state_path()
    return path.with_name(f"{path.stem}.meta.json")


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _same_site(value: str | None) -> str:
    normalized = (value or "").strip().lower().replace("-", "_")
    if normalized in {"strict"}:
        return "Strict"
    if normalized in {"lax"}:
        return "Lax"
    return "None"


def save_chrome_cookies(cookies: list[dict[str, Any]]) -> dict[str, Any]:
    """Persist a one-time browser-session handoff as Playwright storage state.

    Archie Radar never receives the Facebook password. The browser extension sends
    only the current facebook.com cookies after an explicit user action. The state
    file is local-only and mode 0600.
    """
    converted: list[dict[str, Any]] = []
    names: set[str] = set()
    for cookie in cookies:
        name = str(cookie.get("name") or "").strip()
        value = str(cookie.get("value") or "")
        domain = str(cookie.get("domain") or "").strip().lower()
        if not name or not domain:
            continue
        normalized_domain = domain.lstrip(".")
        if normalized_domain != "facebook.com" and not normalized_domain.endswith(".facebook.com"):
            continue
        names.add(name)
        expires_raw = cookie.get("expirationDate")
        try:
            expires = float(expires_raw) if expires_raw not in (None, "") else -1
        except (TypeError, ValueError):
            expires = -1
        converted.append({
            "name": name,
            "value": value,
            "domain": domain if domain.startswith(".") else f".{domain}",
            "path": str(cookie.get("path") or "/"),
            "expires": expires,
            "httpOnly": bool(cookie.get("httpOnly")),
            "secure": bool(cookie.get("secure", True)),
            "sameSite": _same_site(cookie.get("sameSite")),
        })

    # These two cookies are the useful minimum signal that the handoff represents an
    # authenticated Facebook session. Do not persist partial anonymous cookie jars.
    missing = {"c_user", "xs"} - names
    if missing:
        raise ValueError("Facebook session is not logged in; sign in first, then hand it off again.")

    state = {"cookies": converted, "origins": []}
    _atomic_json(_state_path(), state)
    update_session_meta("unverified", "")
    return {
        "ready": True,
        "cookie_count": len(converted),
        "path": str(_state_path()),
    }


def session_ready() -> bool:
    path = _state_path()
    if not path.exists() or path.stat().st_size < 20:
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    names = {item.get("name") for item in payload.get("cookies", []) if isinstance(item, dict)}
    return {"c_user", "xs"}.issubset(names)


def storage_state_path() -> Path | None:
    return _state_path() if session_ready() else None


def update_session_meta(auth_state: str, error: str = "") -> None:
    _atomic_json(_meta_path(), {
        "auth_state": auth_state,
        "error": error[:1000],
        "checked_at": datetime.now(timezone.utc).isoformat(),
    })


def session_status() -> dict[str, Any]:
    meta: dict[str, Any] = {}
    try:
        if _meta_path().exists():
            meta = json.loads(_meta_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        meta = {}
    file_ready = session_ready()
    auth_state = meta.get("auth_state") or ("unverified" if file_ready else "missing")
    return {
        "ready": bool(file_ready and auth_state not in {"login_required", "missing", "collector_unavailable"}),
        "auth_state": auth_state,
        "last_checked_at": meta.get("checked_at"),
        "error": meta.get("error") or "",
    }


def clear_session() -> None:
    for path in (_state_path(), _meta_path()):
        try:
            path.unlink()
        except FileNotFoundError:
            pass
