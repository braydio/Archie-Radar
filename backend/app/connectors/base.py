from __future__ import annotations

import json
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

from bs4 import BeautifulSoup
from dateutil import parser as dtparser

from ..schemas import PetPostIn


class Connector(ABC):
    source_name: str

    @abstractmethod
    async def fetch(self) -> list[PetPostIn]:
        raise NotImplementedError


def _as_utc(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        if not text or len(text) > 120:
            return None
        try:
            dt = dtparser.parse(text)
        except Exception:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def extract_source_posted_at(html: str, soup: BeautifulSoup | None = None) -> datetime | None:
    """Best-effort source publication timestamp from page metadata.

    This deliberately prefers metadata that describes the *web page publication* over
    visible "date found" text. The latter belongs in ``reported_at``. Connectors can
    store the return value as ``raw['source_posted_at']`` so the UI can distinguish
    "Posted" from "Reported".
    """

    soup = soup or BeautifulSoup(html, "html.parser")
    candidates: list[Any] = []

    meta_keys = {
        "article:published_time",
        "og:published_time",
        "article:modified_time",
        "date",
        "datepublished",
        "date_published",
        "publishdate",
        "pubdate",
        "timestamp",
        "dc.date",
        "dc.date.issued",
        "parsely-pub-date",
    }
    for tag in soup.find_all("meta"):
        key = (tag.get("property") or tag.get("name") or tag.get("itemprop") or "").strip().lower()
        if key in meta_keys:
            candidates.append(tag.get("content"))

    for tag in soup.find_all("time"):
        if tag.get("datetime"):
            candidates.append(tag.get("datetime"))

    def walk_json(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if str(key).lower() in {"datepublished", "dateposted", "datecreated", "uploaddate", "pubdate"}:
                    candidates.append(item)
                else:
                    walk_json(item)
        elif isinstance(value, list):
            for item in value:
                walk_json(item)

    for script in soup.find_all("script", type=lambda x: x and "ld+json" in x.lower()):
        payload = script.string or script.get_text(" ", strip=True)
        if not payload:
            continue
        try:
            walk_json(json.loads(payload))
        except Exception:
            continue

    # Prefer the earliest plausible publication timestamp if both published and
    # modified timestamps are present. Ignore obviously ancient/future garbage.
    parsed: list[datetime] = []
    now = datetime.now(timezone.utc)
    for candidate in candidates:
        dt = _as_utc(candidate)
        if dt and datetime(2000, 1, 1, tzinfo=timezone.utc) <= dt <= now.replace(microsecond=0):
            parsed.append(dt)
    return min(parsed) if parsed else None
