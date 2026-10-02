"""Bounded, viewport-scoped public geography for Surveyor."""
from __future__ import annotations

import asyncio
import time
from datetime import date
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/api/surveyor/environment", tags=["surveyor-environment"])
WILDLIFE_TAXA = {
    "coyote": ("Canis latrans", "Coyote"),
    "red_fox": ("Vulpes vulpes", "Red fox"),
    "gray_fox": ("Urocyon cinereoargenteus", "Gray fox"),
    "bobcat": ("Lynx rufus", "Bobcat"),
    "raccoon": ("Procyon lotor", "Raccoon"),
    "deer": ("Odocoileus virginianus", "White-tailed deer"),
}
_cache: dict[tuple[Any, ...], tuple[float, Any]] = {}


def _bounds(west: float, south: float, east: float, north: float) -> tuple[float, float, float, float]:
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise HTTPException(400, "Invalid WGS84 viewport bounds")
    if east - west > 2 or north - south > 2:
        raise HTTPException(400, "Viewport width and height must not exceed 2 degrees")
    return west, south, east, north


def _key_bounds(bounds: tuple[float, float, float, float]) -> tuple[float, ...]:
    return tuple(round(value / 0.02) * 0.02 for value in bounds)


def _cache_get(key: tuple[Any, ...], ttl: int):
    item = _cache.get(key)
    if item and item[0] > time.monotonic():
        return item[1]
    _cache.pop(key, None)
    return None


def _cache_put(key: tuple[Any, ...], value: Any, ttl: int):
    now = time.monotonic()
    for old_key, (expires, _) in list(_cache.items()):
        if expires <= now:
            _cache.pop(old_key, None)
    while len(_cache) >= 128:
        _cache.pop(next(iter(_cache)))
    _cache[key] = (now + ttl, value)


async def _get_json(url: str, params: dict[str, Any]) -> dict[str, Any]:
    error = None
    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=4, headers={"User-Agent": "ArchieRadar/0.9"}) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict) or payload.get("error"):
                    raise ValueError("Invalid provider response")
                return payload
        except (httpx.HTTPError, ValueError) as exc:
            error = exc
            if attempt == 0:
                await asyncio.sleep(0)
    raise HTTPException(502, "Environmental provider unavailable") from error


async def _hydro_layer(layer: int, bounds: tuple[float, ...], kind: str):
    west, south, east, north = bounds
    url = f"https://services.nconemap.gov/secure/rest/services/NC1Map_Hydrography/FeatureServer/{layer}/query"
    payload = await _get_json(url, {
        "where": "1=1", "geometry": f"{west},{south},{east},{north}",
        "geometryType": "esriGeometryEnvelope", "inSR": 4326, "outSR": 4326,
        "spatialRel": "esriSpatialRelIntersects", "outFields": "STREAM_NAM",
        "returnGeometry": "true", "resultRecordCount": 2000, "f": "geojson",
    })
    features = []
    for feature in payload.get("features", []):
        props = feature.get("properties") or {}
        feature["properties"] = {"provider": "NC OneMap", "feature_type": kind, "name": props.get("STREAM_NAM") or ""}
        features.append(feature)
    return {"type": "FeatureCollection", "features": features}


@router.get("/status")
def status():
    return {key: {"provider": provider, "available": True} for key, provider in (
        ("hydrography", "NC OneMap"), ("wetlands", "USFWS NWI"),
        ("boundaries", "US Census TIGERweb"), ("wildlife", "iNaturalist"))}


@router.get("/hydrography")
async def hydrography(west: float = Query(...), south: float = Query(...), east: float = Query(...), north: float = Query(...)):
    bounds = _bounds(west, south, east, north)
    key = ("hydro", *_key_bounds(bounds))
    cached = _cache_get(key, 86400)
    if cached is not None:
        return cached
    streams, waterbodies = await asyncio.gather(_hydro_layer(1, bounds, "stream"), _hydro_layer(2, bounds, "waterbody"))
    result = {"provider": "NC OneMap", "streams": streams, "waterbodies": waterbodies}
    _cache_put(key, result, 86400)
    return result


@router.get("/wildlife")
async def wildlife(west: float = Query(...), south: float = Query(...), east: float = Query(...), north: float = Query(...),
                   from_date: str = Query(...), to_date: str = Query(...), species: list[str] = Query(...)):
    bounds = _bounds(west, south, east, north)
    try:
        start, end = date.fromisoformat(from_date), date.fromisoformat(to_date)
        if start.isoformat() != from_date or end.isoformat() != to_date:
            raise ValueError
        if end < start:
            raise ValueError
    except ValueError as exc:
        raise HTTPException(400, "Dates must use YYYY-MM-DD and be in chronological order") from exc
    selected = sorted(set(species))
    if not selected or len(selected) > 6 or any(item not in WILDLIFE_TAXA for item in selected):
        raise HTTPException(400, "Choose one or more supported wildlife species")
    key = ("wildlife", *_key_bounds(bounds), tuple(selected), start.isoformat(), end.isoformat())
    cached = _cache_get(key, 900)
    if cached is not None:
        return cached

    async def one(species_key: str):
        scientific, common = WILDLIFE_TAXA[species_key]
        payload = await _get_json("https://api.inaturalist.org/v1/observations", {
            "taxon_name": scientific, "swlat": bounds[1], "swlng": bounds[0],
            "nelat": bounds[3], "nelng": bounds[2], "d1": start.isoformat(), "d2": end.isoformat(),
            "quality_grade": "research", "per_page": 200, "order_by": "observed_on", "order": "desc",
        })
        records = []
        for observation in payload.get("results", []):
            location = observation.get("location")
            if not location or observation.get("geoprivacy") == "private":
                continue
            try:
                latitude, longitude = map(float, location.split(","))
            except (ValueError, AttributeError):
                continue
            if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                continue
            taxon = observation.get("taxon") or {}
            records.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [longitude, latitude]},
                "properties": {"provider": "iNaturalist", "provider_record_id": observation.get("id"),
                    "species_key": species_key, "scientific_name": scientific,
                    "common_name": taxon.get("preferred_common_name") or common,
                    "observed_at": observation.get("observed_on"), "added_at": observation.get("created_at"),
                    "quality_grade": observation.get("quality_grade"),
                    "geoprivacy": observation.get("geoprivacy"),
                    "coordinate_accuracy_m": observation.get("positional_accuracy"),
                    "latitude": latitude, "longitude": longitude,
                    "url": f"https://www.inaturalist.org/observations/{observation.get('id')}"}})
        return records

    lists = await asyncio.gather(*(one(item) for item in selected))
    result = {"provider": "iNaturalist", "type": "FeatureCollection", "features": [f for group in lists for f in group]}
    _cache_put(key, result, 900)
    return result
