"""Bounded, viewport-scoped public geography for Surveyor."""
from __future__ import annotations

import asyncio
import math
import time
from datetime import date
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/api/surveyor/environment", tags=["surveyor-environment"])
WILDLIFE_TAXA = {
    "coyote": ("Canis latrans", "Coyote"), "red_fox": ("Vulpes vulpes", "Red fox"),
    "gray_fox": ("Urocyon cinereoargenteus", "Gray fox"), "bobcat": ("Lynx rufus", "Bobcat"),
    "raccoon": ("Procyon lotor", "Raccoon"), "deer": ("Odocoileus virginianus", "White-tailed deer"),
}
_cache: dict[tuple[Any, ...], tuple[float, Any]] = {}
_BUCKET = 0.02


def _bounds(west: float, south: float, east: float, north: float) -> tuple[float, float, float, float]:
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise HTTPException(400, "Invalid WGS84 viewport bounds")
    if east - west > 2 or north - south > 2:
        raise HTTPException(400, "Viewport width and height must not exceed 2 degrees")
    return west, south, east, north


def _expanded_bounds(bounds: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    west, south, east, north = bounds
    return (math.floor(west / _BUCKET) * _BUCKET, math.floor(south / _BUCKET) * _BUCKET,
            math.ceil(east / _BUCKET) * _BUCKET, math.ceil(north / _BUCKET) * _BUCKET)


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
    raise RuntimeError("Environmental provider unavailable") from error


async def _hydro_layer(layer: int, bounds: tuple[float, ...], kind: str):
    west, south, east, north = bounds
    url = f"https://services.nconemap.gov/secure/rest/services/NC1Map_Hydrography/FeatureServer/{layer}/query"
    features, truncated = [], False
    for offset in (0, 2000, 4000):
        payload = await _get_json(url, {
            "where": "1=1", "geometry": f"{west},{south},{east},{north}",
            "geometryType": "esriGeometryEnvelope", "inSR": 4326, "outSR": 4326,
            "spatialRel": "esriSpatialRelIntersects", "outFields": "STREAM_NAM,WATERBODY" if layer == 2 else "STREAM_NAM",
            "returnGeometry": "true", "resultRecordCount": 2000, "resultOffset": offset, "f": "geojson",
        })
        page = payload.get("features", [])
        for feature in page:
            props = feature.get("properties") or {}
            name = (props.get("WATERBODY") if layer == 2 else None) or props.get("STREAM_NAM") or ""
            feature["properties"] = {"provider": "NC OneMap", "feature_type": kind, "name": name}
        features.extend(page)
        has_more = payload.get("exceededTransferLimit", len(page) >= 2000)
        if len(page) < 2000 or not has_more:
            break
        if offset == 4000:
            truncated = True
    return {"type": "FeatureCollection", "features": features}, truncated


@router.get("/status")
def status():
    return {key: {"provider": provider, "available": True} for key, provider in (
        ("hydrography", "NC OneMap"), ("wetlands", "USFWS NWI"),
        ("boundaries", "US Census TIGERweb"), ("wildlife", "iNaturalist"))}


@router.get("/hydrography")
async def hydrography(west: float = Query(...), south: float = Query(...), east: float = Query(...), north: float = Query(...), force: bool = False):
    bounds = _expanded_bounds(_bounds(west, south, east, north))
    key = ("hydro", *bounds)
    cached = None if force else _cache_get(key, 86400)
    if cached is not None:
        return cached
    outcomes = await asyncio.gather(_hydro_layer(1, bounds, "stream"), _hydro_layer(2, bounds, "waterbody"), return_exceptions=True)
    streams_result, water_result = outcomes
    if isinstance(streams_result, Exception) and isinstance(water_result, Exception):
        raise HTTPException(502, "NC OneMap hydrography unavailable")
    streams = streams_result[0] if not isinstance(streams_result, Exception) else {"type": "FeatureCollection", "features": []}
    waterbodies = water_result[0] if not isinstance(water_result, Exception) else {"type": "FeatureCollection", "features": []}
    result = {"provider": "NC OneMap", "streams": streams, "waterbodies": waterbodies,
              "truncated": any(outcome[1] for outcome in outcomes if not isinstance(outcome, Exception)),
              "degraded_layers": [name for name, outcome in (("streams", streams_result), ("waterbodies", water_result)) if isinstance(outcome, Exception)]}
    _cache_put(key, result, 86400)
    return result


@router.get("/wildlife")
async def wildlife(west: float = Query(...), south: float = Query(...), east: float = Query(...), north: float = Query(...),
                   from_date: str = Query(...), to_date: str = Query(...), species: list[str] = Query(...), force: bool = False):
    bounds = _expanded_bounds(_bounds(west, south, east, north))
    try:
        start, end = date.fromisoformat(from_date), date.fromisoformat(to_date)
        if start.isoformat() != from_date or end.isoformat() != to_date or end < start:
            raise ValueError
    except ValueError as exc:
        raise HTTPException(400, "Dates must use YYYY-MM-DD and be in chronological order") from exc
    selected = sorted(set(species))
    if not selected or len(selected) > 6 or any(item not in WILDLIFE_TAXA for item in selected):
        raise HTTPException(400, "Choose one or more supported wildlife species")
    key = ("wildlife", *bounds, tuple(selected), start.isoformat(), end.isoformat())
    cached = None if force else _cache_get(key, 900)
    if cached is not None:
        return cached

    async def one(species_key: str):
        scientific, common = WILDLIFE_TAXA[species_key]
        records, truncated = [], False
        for page in (1, 2):
            payload = await _get_json("https://api.inaturalist.org/v1/observations", {
                "taxon_name": scientific, "swlat": bounds[1], "swlng": bounds[0], "nelat": bounds[3], "nelng": bounds[2],
                "d1": start.isoformat(), "d2": end.isoformat(), "quality_grade": "research", "per_page": 200,
                "page": page, "order_by": "observed_on", "order": "desc",
            })
            results = payload.get("results", [])
            for observation in results:
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
                    "properties": {"provider": "iNaturalist", "provider_record_id": observation.get("id"), "species_key": species_key,
                        "scientific_name": scientific, "common_name": taxon.get("preferred_common_name") or common,
                        "observed_at": observation.get("time_observed_at") or observation.get("observed_on"), "added_at": observation.get("created_at"),
                        "quality_grade": observation.get("quality_grade"), "geoprivacy": observation.get("geoprivacy"),
                        "coordinate_accuracy_m": observation.get("positional_accuracy"), "latitude": latitude, "longitude": longitude,
                        "url": f"https://www.inaturalist.org/observations/{observation.get('id')}"}})
            total = payload.get("total_results")
            if len(results) < 200 or (total is not None and page * 200 >= total):
                break
            if page == 2:
                truncated = total is None or total > 400
        return records, truncated

    groups = await asyncio.gather(*(one(item) for item in selected))
    result = {"provider": "iNaturalist", "type": "FeatureCollection", "features": [feature for group, _ in groups for feature in group],
              "truncated": any(truncated for _, truncated in groups)}
    _cache_put(key, result, 900)
    return result
