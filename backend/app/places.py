from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import DateTime, Integer, String, Text, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from .db import Base, get_db
from .geocoder import NominatimGeocoder, utcnow
from .settings import get_settings

router = APIRouter(prefix="/api/places", tags=["places"])
settings = get_settings()
geocoder = NominatimGeocoder(settings.geocode_user_agent, settings.geocode_base_url, settings.geocode_min_delay_seconds)


class PlaceLookupCache(Base):
    __tablename__ = "place_lookup_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    query: Mapped[str] = mapped_column(String(500), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="ok")
    results_json: Mapped[str] = mapped_column(Text, default="[]")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ResolvePlaceIn(BaseModel):
    query: str = Field(min_length=3, max_length=400)


def distance_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    from math import asin, cos, radians, sin, sqrt
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    value = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 3958.7613 * 2 * asin(min(1, sqrt(value)))


def bearing_degrees(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    from math import atan2, cos, radians, sin
    a, b = radians(lat1), radians(lat2)
    dlon = radians(lon2 - lon1)
    y = sin(dlon) * cos(b)
    x = cos(a) * sin(b) - sin(a) * cos(b) * cos(dlon)
    return (atan2(y, x) * 180 / 3.141592653589793 + 360) % 360


def compass_label(bearing: float) -> str:
    return ("N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW")[round(bearing / 22.5) % 16]


def _precision(hit: dict) -> str:
    kind = str(hit.get("addresstype") or "").lower()
    if kind in {"house", "building", "house_number", "apartments"}:
        return "address"
    if kind in {"road", "street", "residential", "highway"}:
        return "street"
    if kind in {"neighbourhood", "suburb", "quarter", "hamlet"}:
        return "neighborhood"
    if kind in {"city", "town", "village", "municipality", "county", "state"}:
        return "city"
    return "place" if hit.get("name") or hit.get("type") else "approximate"


def _normalized_hit(hit: dict) -> dict:
    return {
        "latitude": float(hit["latitude"]),
        "longitude": float(hit["longitude"]),
        "display_name": str(hit.get("display_name") or ""),
        "addresstype": str(hit.get("addresstype") or ""),
        "type": str(hit.get("type") or ""),
        "class": str(hit.get("class") or ""),
        "name": str(hit.get("name") or ""),
    }


@router.post("/resolve")
async def resolve_address(payload: ResolvePlaceIn, db: Session = Depends(get_db)):
    if not settings.geocode_enabled:
        raise HTTPException(503, "Address lookup is disabled in Archie Radar settings")
    query = " ".join(payload.query.split()).strip()
    lookup_query = query if any(term in query.casefold() for term in ("north carolina", " nc", "united states", ", us")) else f"{query}, North Carolina, USA"
    cached = db.scalar(select(PlaceLookupCache).where(PlaceLookupCache.query == lookup_query))
    hits = None
    if cached and cached.status == "ok":
        try:
            hits = [_normalized_hit(item) for item in json.loads(cached.results_json or "[]")][:5]
        except (TypeError, ValueError, KeyError, json.JSONDecodeError):
            hits = None
    elif cached and cached.status == "miss":
        cached_at = cached.updated_at if cached.updated_at.tzinfo else cached.updated_at.replace(tzinfo=timezone.utc)
        if utcnow() - cached_at < timedelta(days=7):
            hits = []
    else:
        cached = None

    if hits is None:
        try:
            hits = await geocoder.lookup_many(lookup_query, limit=5)
        except Exception as exc:
            raise HTTPException(502, "Address service is temporarily unavailable") from exc
        now = utcnow()
        if cached is None:
            cached = PlaceLookupCache(query=lookup_query)
            db.add(cached)
        cached.updated_at = now
        if hits:
            hits = [_normalized_hit(hit) for hit in hits[:5]]
            cached.results_json, cached.status = json.dumps(hits), "ok"
        else:
            cached.results_json, cached.status = "[]", "miss"
        db.commit()
    home_lat, home_lon = settings.home_latitude, settings.home_longitude
    matches = []
    for hit in hits[:5]:
        distance = distance_miles(home_lat, home_lon, hit["latitude"], hit["longitude"])
        bearing = bearing_degrees(home_lat, home_lon, hit["latitude"], hit["longitude"])
        matches.append({"display_name": hit["display_name"], "latitude": hit["latitude"], "longitude": hit["longitude"],
            "precision": _precision(hit), "distance_miles": round(distance, 2), "bearing_degrees": round(bearing, 1),
            "bearing_label": compass_label(bearing), "source_type": hit.get("type"), "address_type": hit.get("addresstype")})
    return {"query": query, "home": {"latitude": home_lat, "longitude": home_lon}, "matches": matches}
