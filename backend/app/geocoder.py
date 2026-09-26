from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import DateTime, Float, Integer, String, Text, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from .db import Base
from .schemas import PetPostIn


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class GeocodeCache(Base):
    __tablename__ = "geocode_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    query: Mapped[str] = mapped_column(Text, unique=True, index=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    display_name: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="ok")
    provider: Mapped[str] = mapped_column(String(30), default="nominatim")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


@dataclass(slots=True)
class GeocodeResult:
    latitude: float
    longitude: float
    display_name: str = ""


class NominatimGeocoder:
    """Small, cached geocoder with intentionally conservative request pacing."""

    def __init__(self, user_agent: str, base_url: str = "https://nominatim.openstreetmap.org", min_delay_seconds: float = 15.1):
        self.user_agent = user_agent
        self.base_url = base_url.rstrip("/")
        self.min_delay_seconds = max(15.0, min_delay_seconds)
        self._lock = asyncio.Lock()
        self._last_request_monotonic = 0.0

    async def lookup(self, query: str) -> GeocodeResult | None:
        query = " ".join(query.split()).strip()
        if not query:
            return None
        async with self._lock:
            loop = asyncio.get_running_loop()
            elapsed = loop.time() - self._last_request_monotonic
            if elapsed < self.min_delay_seconds:
                await asyncio.sleep(self.min_delay_seconds - elapsed)
            headers = {"User-Agent": self.user_agent}
            params = {"q": query, "format": "jsonv2", "limit": 1, "countrycodes": "us"}
            async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=20) as client:
                response = await client.get(f"{self.base_url}/search", params=params)
                response.raise_for_status()
                self._last_request_monotonic = loop.time()
                data = response.json()
            if not data:
                return None
            hit = data[0]
            return GeocodeResult(float(hit["lat"]), float(hit["lon"]), hit.get("display_name", ""))


def build_query(post: PetPostIn) -> str:
    location = " ".join((post.location_text or "").split()).strip()
    if not location:
        return ""
    context = str(post.raw.get("geocode_context", "")).strip()
    lowered = location.lower()
    if context and context.lower() not in lowered:
        return f"{location}, {context}"
    if " nc" not in lowered and "north carolina" not in lowered:
        return f"{location}, North Carolina, USA"
    return location


async def geocode_posts(
    db: Session,
    posts: list[PetPostIn],
    geocoder: NominatimGeocoder,
    *,
    failed_cache_days: int = 7,
) -> tuple[list[PetPostIn], dict]:
    output: list[PetPostIn] = []
    cache_hits = looked_up = resolved = failed = 0
    now = utcnow()

    for post in posts:
        if post.latitude is not None and post.longitude is not None:
            output.append(post)
            continue
        query = build_query(post)
        if not query:
            output.append(post)
            continue

        cached = db.scalar(select(GeocodeCache).where(GeocodeCache.query == query))
        result: GeocodeResult | None = None
        if cached and cached.status == "ok" and cached.latitude is not None and cached.longitude is not None:
            cache_hits += 1
            result = GeocodeResult(cached.latitude, cached.longitude, cached.display_name)
        elif cached and cached.status == "miss" and cached.updated_at:
            cached_dt = cached.updated_at
            if cached_dt.tzinfo is None:
                cached_dt = cached_dt.replace(tzinfo=timezone.utc)
            if now - cached_dt < timedelta(days=failed_cache_days):
                cache_hits += 1
        else:
            looked_up += 1
            try:
                result = await geocoder.lookup(query)
            except Exception:
                result = None
            if cached is None:
                cached = GeocodeCache(query=query)
                db.add(cached)
            cached.updated_at = now
            if result:
                cached.status = "ok"
                cached.latitude = result.latitude
                cached.longitude = result.longitude
                cached.display_name = result.display_name
            else:
                cached.status = "miss"
                cached.latitude = None
                cached.longitude = None
                cached.display_name = ""
            db.flush()

        if result:
            resolved += 1
            raw = dict(post.raw)
            raw["geocode_query"] = query
            raw["geocode_display_name"] = result.display_name
            post = post.model_copy(update={"latitude": result.latitude, "longitude": result.longitude, "raw": raw})
        else:
            failed += 1
        output.append(post)

    db.commit()
    return output, {
        "cache_hits": cache_hits,
        "looked_up": looked_up,
        "resolved": resolved,
        "failed": failed,
    }
