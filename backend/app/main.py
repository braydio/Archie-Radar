from __future__ import annotations

import asyncio
import base64
import binascii
import json
import logging
import re
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import delete, desc, func, or_, select
from sqlalchemy.orm import Session

from .connectors.orange_county import OrangeCountyFoundCatsConnector
from .connectors.pawboost import PawBoostConnector
from .connectors.regional_24petconnect import Regional24PetConnectConnector
from .connectors.aps_durham import APSDurhamFoundPetsConnector
from .connectors.wake_county import WakeCountyLostFoundConnector
from .connectors.pet911 import Pet911Connector
from .connectors.petkey import PetkeyConnector
from .db import Base, SessionLocal, engine, get_db
from .geocoder import NominatimGeocoder, geocode_posts
from .image_service import analyze_post_ids
from .models import ArchieProfile, ArchieReferencePhoto, PetPost, PostVision, SurveyorMapObject
from .schemas import (
    FacebookBridgeIn,
    PetPostIn,
    PetPostOut,
    ProfileIn,
    ProfileOut,
    ReferencePhotoIn,
    ReferencePhotoOut,
    ReviewIn,
    SearchConfigOut,
    SurveyorObjectIn,
    SurveyorObjectOut,
    SurveyorObjectPatch,
)
from .service import (
    get_or_create_profile,
    post_output,
    recompute_vision_matches,
    rescore_all,
    upsert_posts,
)
from .settings import get_settings
from .vision import fingerprint_image
from .traits import ARCHIE_TRAITS, is_archie_compatible


settings = get_settings()
logger = logging.getLogger("archie-radar")
media_dir = Path(settings.media_dir).resolve()
reference_dir = media_dir / "reference"
reference_dir.mkdir(parents=True, exist_ok=True)
geocoder = NominatimGeocoder(settings.geocode_user_agent, settings.geocode_base_url, settings.geocode_min_delay_seconds)


def _set_home_anchor(db: Session) -> ArchieProfile:
    profile = get_or_create_profile(db)
    profile.anchor_latitude = settings.home_latitude
    profile.anchor_longitude = settings.home_longitude
    db.commit()
    db.refresh(profile)
    return profile


async def _prepare_and_store(db: Session, posts: list[PetPostIn]) -> dict:
    # Ingestion stays fast. A separate rate-limited worker geocodes missing locations
    # in the background, then upsert_posts rescoring picks up the distance signal.
    result = upsert_posts(db, posts)
    if settings.analyze_images:
        result["vision"] = await analyze_post_ids(
            db,
            result.get("post_ids", []),
            max_bytes=settings.max_image_bytes,
        )
    return result


async def _ingest_pawboost_once() -> dict:
    connector = PawBoostConnector(settings.pawboost_area_list, settings.pawboost_pages)
    posts = await connector.fetch_listings()

    # Detail-page requests are reserved for new/incomplete rows. PawBoost listing
    # cards occasionally omit the actual image even though the landing page has it.
    # This keeps the automatic 30-minute scan useful without re-fetching every detail
    # page forever.
    with SessionLocal() as db:
        existing_rows = list(db.scalars(select(PetPost).where(PetPost.source == "pawboost")))
        existing = {row.source_id: row for row in existing_rows}
        visions = {
            v.post_id: v for v in db.scalars(
                select(PostVision).join(PetPost, PetPost.id == PostVision.post_id).where(PetPost.source == "pawboost")
            )
        }
        enrich_ids: set[str] = set()
        for post in posts:
            row = existing.get(post.source_id)
            if row is None:
                enrich_ids.add(post.source_id)
                continue
            try:
                raw = json.loads(row.raw_json or "{}")
            except json.JSONDecodeError:
                raw = {}
            vision = visions.get(row.id)
            if (
                not raw.get("posted_metadata_checked")
                or (
                    not raw.get("detail_page_enriched")
                    and (
                        not row.image_url
                        or row.reported_at is None
                        or (vision is not None and vision.status in {"error", "no_photo"})
                        or (vision is not None and vision.duplicate_of_post_id is not None)
                    )
                )
            ):
                enrich_ids.add(post.source_id)

    posts = await connector.enrich_posts(posts, enrich_ids)
    with SessionLocal() as db:
        return await _prepare_and_store(db, posts)


async def _ingest_orange_once() -> dict:
    if not settings.orange_county_enabled:
        return {"enabled": False, "created": 0, "updated": 0, "total": 0}
    connector = OrangeCountyFoundCatsConnector()
    posts = await connector.fetch()
    with SessionLocal() as db:
        return await _prepare_and_store(db, posts)




async def _ingest_regional_24petconnect_once() -> dict:
    if not settings.regional_24petconnect_enabled or not settings.regional_24petconnect_url:
        return {"enabled": False, "created": 0, "updated": 0, "total": 0}
    connector = Regional24PetConnectConnector(settings.regional_24petconnect_url)
    posts = await connector.fetch()
    with SessionLocal() as db:
        return await _prepare_and_store(db, posts)


async def _ingest_aps_durham_once() -> dict:
    if not settings.aps_durham_enabled:
        return {"enabled": False, "created": 0, "updated": 0, "total": 0}
    connector = APSDurhamFoundPetsConnector()
    posts = await connector.fetch()
    with SessionLocal() as db:
        return await _prepare_and_store(db, posts)


async def _ingest_wake_once() -> dict:
    if not settings.wake_county_enabled:
        return {"enabled": False, "created": 0, "updated": 0, "total": 0}
    connector = WakeCountyLostFoundConnector()
    posts = await connector.fetch()
    with SessionLocal() as db:
        return await _prepare_and_store(db, posts)


async def _ingest_pet911_once() -> dict:
    if not settings.pet911_enabled:
        return {"enabled": False, "created": 0, "updated": 0, "total": 0}
    connector = Pet911Connector(settings.pet911_place_list)
    posts = await connector.fetch()
    with SessionLocal() as db:
        return await _prepare_and_store(db, posts)


async def _ingest_petkey_once() -> dict:
    if not settings.petkey_enabled:
        return {"enabled": False, "created": 0, "updated": 0, "total": 0}
    connector = PetkeyConnector(settings.petkey_place_list)
    posts = await connector.fetch()
    with SessionLocal() as db:
        return await _prepare_and_store(db, posts)


async def _ingest_all_once() -> dict:
    scanners = (
        ("pawboost", _ingest_pawboost_once),
        ("orange_county_found", _ingest_orange_once),
        ("regional_24petconnect", _ingest_regional_24petconnect_once),
        ("aps_durham_found", _ingest_aps_durham_once),
        ("wake_county_lostfound", _ingest_wake_once),
        ("pet911", _ingest_pet911_once),
        ("petkey", _ingest_petkey_once),
    )

    async def run_one(name, fn):
        try:
            return name, await fn()
        except Exception as exc:
            logger.exception("%s scan failed", name)
            return name, {"error": str(exc)}

    pairs = await asyncio.gather(*(run_one(name, fn) for name, fn in scanners))
    return dict(pairs)


async def _backfill_geocodes_once(limit: int | None = None) -> dict:
    if not settings.geocode_enabled:
        return {"enabled": False, "total": 0}
    limit = limit or settings.geocode_backfill_limit
    with SessionLocal() as db:
        rows = list(
            db.scalars(
                select(PetPost)
                .where(PetPost.latitude.is_(None), PetPost.location_text != "")
                .order_by(desc(PetPost.first_seen_at))
                .limit(limit)
            )
        )
        posts: list[PetPostIn] = []
        for row in rows:
            try:
                raw = json.loads(row.raw_json or "{}")
            except json.JSONDecodeError:
                raw = {}
            posts.append(
                PetPostIn(
                    source=row.source,
                    source_id=row.source_id,
                    source_url=row.source_url,
                    status=row.status,
                    species=row.species,
                    name=row.name,
                    sex=row.sex,
                    altered_status=row.altered_status,
                    description=row.description,
                    location_text=row.location_text,
                    image_url=row.image_url,
                    reported_at=row.reported_at,
                    raw=raw,
                )
            )
        if not posts:
            return {"total": 0, "geocoding": {"cache_hits": 0, "looked_up": 0, "resolved": 0, "failed": 0}}
        geocoded, stats = await geocode_posts(db, posts, geocoder)
        stored = upsert_posts(db, geocoded)
        return {"total": len(posts), "geocoding": stats, "stored": stored}


async def _poll_all_forever():
    await asyncio.sleep(3)
    while True:
        try:
            result = await _ingest_all_once()
            logger.info("Regional scan complete: %s", result)
        except Exception:
            logger.exception("Regional background scan failed")
        await asyncio.sleep(max(5, settings.scan_minutes) * 60)


async def _geocode_worker_forever():
    # One serial worker. NominatimGeocoder itself enforces the public-service
    # periodic-use ceiling (>=15 s between network requests) and results are cached.
    await asyncio.sleep(5)
    while True:
        try:
            result = await _backfill_geocodes_once(limit=1)
            if result.get("total", 0) == 0:
                await asyncio.sleep(30)
            else:
                # Cache hits can drain quickly; real lookups are throttled inside geocoder.
                await asyncio.sleep(0.1)
        except Exception:
            logger.exception("Geocode worker failed")
            await asyncio.sleep(30)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Importing geocoder above registers its cache table with SQLAlchemy metadata.
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        _set_home_anchor(db)
        rescore_all(db)
    tasks = []
    if settings.auto_scan:
        tasks.append(asyncio.create_task(_poll_all_forever()))
    if settings.geocode_enabled:
        tasks.append(asyncio.create_task(_geocode_worker_forever()))
    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass


app = FastAPI(title="Archie Radar API", version="0.9.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if "*" in settings.cors_origin_list else settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/media", StaticFiles(directory=str(media_dir)), name="media")


def _geometry_stats(geometry: dict) -> tuple[float, float, float, float, float, float]:
    if not isinstance(geometry, dict) or geometry.get("type") not in {
        "Point", "MultiPoint", "LineString", "MultiLineString", "Polygon", "MultiPolygon", "GeometryCollection"
    }:
        raise HTTPException(status_code=422, detail="Unsupported GeoJSON geometry")
    coords = []
    def visit(value):
        if isinstance(value, (list, tuple)) and len(value) >= 2 and all(isinstance(v, (int, float)) for v in value[:2]):
            lon, lat = float(value[0]), float(value[1])
            if not (-180 <= lon <= 180 and -90 <= lat <= 90):
                raise HTTPException(status_code=422, detail="GeoJSON coordinate out of range")
            coords.append((lon, lat))
        elif isinstance(value, (list, tuple)):
            for item in value:
                visit(item)
    if geometry["type"] == "GeometryCollection":
        for item in geometry.get("geometries", []):
            _geometry_stats(item)
            visit(item.get("coordinates", []))
    else:
        visit(geometry.get("coordinates"))
    if not coords:
        raise HTTPException(status_code=422, detail="GeoJSON geometry has no coordinates")
    west = min(x for x, _ in coords); east = max(x for x, _ in coords)
    south = min(y for _, y in coords); north = max(y for _, y in coords)
    return sum(y for _, y in coords) / len(coords), sum(x for x, _ in coords) / len(coords), west, south, east, north


def _surveyor_out(row: SurveyorMapObject) -> SurveyorObjectOut:
    return SurveyorObjectOut(
        id=row.id, object_type=row.object_type, subtype=row.subtype, name=row.name,
        geometry=json.loads(row.geometry_geojson), style=json.loads(row.style_json or "{}"),
        properties=json.loads(row.properties_json or "{}"), status=row.status, confidence=row.confidence,
        epistemic_state=row.epistemic_state, occurred_at=row.occurred_at, valid_from=row.valid_from,
        valid_to=row.valid_to, notes=row.notes, centroid_lat=row.centroid_lat, centroid_lon=row.centroid_lon,
        bbox=[row.bbox_west, row.bbox_south, row.bbox_east, row.bbox_north],
        created_at=row.created_at, updated_at=row.updated_at,
    )


def _save_surveyor_geometry(row: SurveyorMapObject, geometry: dict):
    lat, lon, west, south, east, north = _geometry_stats(geometry)
    row.geometry_geojson = json.dumps(geometry, separators=(",", ":"))
    row.centroid_lat, row.centroid_lon = lat, lon
    row.bbox_west, row.bbox_south, row.bbox_east, row.bbox_north = west, south, east, north


@app.get("/api/surveyor/objects", response_model=list[SurveyorObjectOut])
def list_surveyor_objects(
    bbox: str | None = None,
    object_type: str | None = None,
    subtype: str | None = None,
    from_date: datetime | None = Query(None, alias="from"),
    to_date: datetime | None = Query(None, alias="to"),
    status: str | None = None,
    db: Session = Depends(get_db),
):
    query = select(SurveyorMapObject)
    if object_type:
        query = query.where(SurveyorMapObject.object_type == object_type)
    if subtype:
        query = query.where(SurveyorMapObject.subtype == subtype)
    if status:
        query = query.where(SurveyorMapObject.status == status)
    if from_date:
        query = query.where(or_(SurveyorMapObject.occurred_at.is_(None), SurveyorMapObject.occurred_at >= from_date))
    if to_date:
        query = query.where(or_(SurveyorMapObject.occurred_at.is_(None), SurveyorMapObject.occurred_at <= to_date))
    if bbox:
        try:
            west, south, east, north = [float(part) for part in bbox.split(",")]
            if not (-180 <= west <= east <= 180 and -90 <= south <= north <= 90):
                raise ValueError
        except ValueError:
            raise HTTPException(status_code=422, detail="bbox must be west,south,east,north")
        query = query.where(
            SurveyorMapObject.bbox_east >= west, SurveyorMapObject.bbox_west <= east,
            SurveyorMapObject.bbox_north >= south, SurveyorMapObject.bbox_south <= north,
        )
    return [_surveyor_out(row) for row in db.scalars(query.order_by(SurveyorMapObject.created_at.desc()))]


@app.post("/api/surveyor/objects", response_model=SurveyorObjectOut, status_code=201)
def create_surveyor_object(payload: SurveyorObjectIn, db: Session = Depends(get_db)):
    if len(json.dumps(payload.properties)) > 20000 or len(json.dumps(payload.style)) > 5000:
        raise HTTPException(status_code=422, detail="Object metadata is too large")
    row = SurveyorMapObject(
        object_type=payload.object_type, subtype=payload.subtype, name=payload.name,
        style_json=json.dumps(payload.style), properties_json=json.dumps(payload.properties),
        status=payload.status, confidence=payload.confidence, epistemic_state=payload.epistemic_state,
        occurred_at=payload.occurred_at, valid_from=payload.valid_from, valid_to=payload.valid_to, notes=payload.notes,
    )
    _save_surveyor_geometry(row, payload.geometry)
    db.add(row); db.commit(); db.refresh(row)
    return _surveyor_out(row)


@app.get("/api/surveyor/objects/{object_id}", response_model=SurveyorObjectOut)
def get_surveyor_object(object_id: int, db: Session = Depends(get_db)):
    row = db.get(SurveyorMapObject, object_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Surveyor object not found")
    return _surveyor_out(row)


@app.patch("/api/surveyor/objects/{object_id}", response_model=SurveyorObjectOut)
def update_surveyor_object(object_id: int, payload: SurveyorObjectPatch, db: Session = Depends(get_db)):
    row = db.get(SurveyorMapObject, object_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Surveyor object not found")
    values = payload.model_dump(exclude_unset=True)
    if "geometry" in values:
        _save_surveyor_geometry(row, values.pop("geometry"))
    for key, value in values.items():
        if key in {"style", "properties"}:
            if len(json.dumps(value)) > (5000 if key == "style" else 20000):
                raise HTTPException(status_code=422, detail=f"{key} is too large")
            setattr(row, "style_json" if key == "style" else "properties_json", json.dumps(value))
        else:
            setattr(row, key, value)
    db.commit(); db.refresh(row)
    return _surveyor_out(row)


@app.delete("/api/surveyor/objects/{object_id}", status_code=204)
def delete_surveyor_object(object_id: int, db: Session = Depends(get_db)):
    row = db.get(SurveyorMapObject, object_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Surveyor object not found")
    db.delete(row); db.commit()
    return None


@app.get("/health")
def health():
    return {"ok": True, "service": "archie-radar", "version": "0.9.0"}


@app.get("/api/search-config", response_model=SearchConfigOut)
def search_config():
    source_statuses = [
        {"key": "pawboost", "label": "PawBoost", "status": "active", "detail": "Public found/stray listings"},
        {"key": "orange_county", "label": "Orange County", "status": "active" if settings.orange_county_enabled else "disabled"},
        {"key": "regional_24petconnect", "label": "24PetConnect regional", "status": "active" if settings.regional_24petconnect_enabled and settings.regional_24petconnect_url else "setup_required", "detail": "Saved regional search URL. Even if a shelter front-end labels a search inactive, the backend listing endpoint may still return results."},
        {"key": "aps_durham", "label": "APS Durham community", "status": "active" if settings.aps_durham_enabled else "disabled"},
        {"key": "wake_county", "label": "Wake County", "status": "active" if settings.wake_county_enabled else "disabled"},
        {"key": "pet911", "label": "Pet911", "status": "active" if settings.pet911_enabled else "disabled"},
        {"key": "petkey", "label": "Petkey", "status": "active" if settings.petkey_enabled else "disabled"},
        {
            "key": "petco_love",
            "label": "Petco Love Lost",
            "status": "configured_pending_mapping" if settings.petco_api_key else "setup_required",
            "detail": "Approved Partner API key required; set ARCHIE_PETCO_API_KEY in .env" if not settings.petco_api_key else "API key present; endpoint mapping still guarded",
        },
        {
            "key": "facebook_groups",
            "label": "Facebook Groups",
            "status": "manual_bridge",
            "detail": "Use the capture bridge/browser helper; Groups are not scraped automatically",
        },
    ]
    return SearchConfigOut(
        home_address=settings.home_address,
        home_latitude=settings.home_latitude,
        home_longitude=settings.home_longitude,
        search_radius_miles=settings.search_radius_miles,
        pawboost_areas=settings.pawboost_area_list,
        geocoding_enabled=settings.geocode_enabled,
        orange_county_enabled=settings.orange_county_enabled,
        enabled_sources=[item["label"] for item in source_statuses if item["status"] == "active"],
        source_statuses=source_statuses,
        default_not_before=datetime(2026, 6, 1, tzinfo=timezone.utc),
        archie_profile_summary={
            **ARCHIE_TRAITS,
            "description": "Orange striped/tabby shorthaired male; white chest, no white belly; neutered; no collar; not microchipped; about 8 years old; missing since late June 2026.",
        },
    )


@app.get("/api/posts", response_model=list[PetPostOut])
def list_posts(
    review_state: str | None = None,
    min_score: float = Query(0, ge=0, le=100),
    source: str | None = None,
    status: str | None = None,
    sex: str | None = None,
    has_photo: bool | None = None,
    color: str | None = None,
    pattern: str | None = None,
    coat: str | None = None,
    collar: str | None = None,
    microchip: str | None = None,
    altered: str | None = None,
    white_chest: bool | None = None,
    white_belly: bool | None = None,
    white_paws: bool | None = None,
    white_face: bool | None = None,
    age_compatible: bool = False,
    archie_compatible: bool = False,
    reported_within_days: int | None = Query(None, ge=1, le=3650),
    not_before: datetime | None = None,
    include_duplicates: bool = True,
    max_distance_miles: float | None = Query(None, ge=0, le=500),
    sort: str = Query("smart", pattern="^(smart|newest|closest|score)$"),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    stmt = (
        select(PetPost, PostVision)
        .outerjoin(PostVision, PostVision.post_id == PetPost.id)
        .where(PetPost.match_score >= min_score)
    )
    if review_state:
        stmt = stmt.where(PetPost.review_state == review_state)
    if source:
        stmt = stmt.where(PetPost.source == source)
    if status:
        stmt = stmt.where(PetPost.status == status)
    if sex:
        stmt = stmt.where(PetPost.sex == sex)
    effective_event_date = func.coalesce(PetPost.reported_at, PetPost.first_seen_at)
    if reported_within_days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=reported_within_days)
        stmt = stmt.where(effective_event_date >= cutoff)
    if not_before is not None:
        cutoff = not_before if not_before.tzinfo else not_before.replace(tzinfo=timezone.utc)
        stmt = stmt.where(effective_event_date >= cutoff)
    if has_photo is True:
        stmt = stmt.where(
            PetPost.image_url.is_not(None),
            PetPost.image_url != "",
            or_(PostVision.id.is_(None), PostVision.status != "no_photo"),
        )
    elif has_photo is False:
        stmt = stmt.where(
            or_(
                PetPost.image_url.is_(None),
                PetPost.image_url == "",
                PostVision.status == "no_photo",
            )
        )
    if not include_duplicates:
        # Outer-joined rows with no image/vision must remain visible. Only a real
        # analyzed image that explicitly points at another post is filtered out.
        stmt = stmt.where(or_(PostVision.id.is_(None), PostVision.duplicate_of_post_id.is_(None)))

    # Distance sorting/filtering happens after output because distance is computed
    # against the configurable home anchor in Python. Fetch enough rows first.
    needs_python_sort = sort == "closest"
    needs_trait_filter = any([color, pattern, coat, collar, microchip, altered, white_chest is not None, white_belly is not None, white_paws is not None, white_face is not None, age_compatible, archie_compatible])
    fetch_limit = min(3000, max(800, limit * 8)) if (max_distance_miles is not None or needs_python_sort or needs_trait_filter) else limit
    effective_date = effective_event_date
    if sort == "newest":
        stmt = stmt.order_by(desc(effective_date), desc(PetPost.match_score))
    elif sort == "score":
        stmt = stmt.order_by(desc(PetPost.match_score), desc(effective_date))
    else:
        # Smart review order: strongest triage score first, newest evidence breaks ties.
        stmt = stmt.order_by(desc(PetPost.match_score), desc(effective_date))
    stmt = stmt.limit(fetch_limit)

    profile = get_or_create_profile(db)
    output = [post_output(row, vision, profile) for row, vision in db.execute(stmt).all()]

    def trait_match(item: dict) -> bool:
        traits = item.get("parsed_traits") or {}
        if color and color not in (traits.get("colors") or []):
            return False
        if pattern and pattern not in (traits.get("patterns") or []):
            return False
        if coat and traits.get("coat") != coat:
            return False
        if collar and traits.get("collar") != collar:
            return False
        if microchip and traits.get("microchip") != microchip:
            return False
        if altered and traits.get("altered_status") != altered:
            return False
        if white_chest is not None and traits.get("white_chest") is not white_chest:
            return False
        if white_belly is not None and traits.get("white_belly") is not white_belly:
            return False
        if white_paws is not None and traits.get("white_paws") is not white_paws:
            return False
        if white_face is not None and traits.get("white_face") is not white_face:
            return False
        if age_compatible:
            age = traits.get("age_years")
            if age is None or abs(float(age) - float(ARCHIE_TRAITS["age_years"])) > 2.5:
                return False
        if archie_compatible and not is_archie_compatible(traits, item.get("sex") or "unknown"):
            return False
        return True

    if needs_trait_filter:
        output = [item for item in output if trait_match(item)]

    if max_distance_miles is not None:
        output = [
            item for item in output
            if item["distance_from_home_miles"] is None or item["distance_from_home_miles"] <= max_distance_miles
        ]
    if sort == "closest":
        output.sort(key=lambda item: (
            item["distance_from_home_miles"] is None,
            item["distance_from_home_miles"] if item["distance_from_home_miles"] is not None else 9999,
            -float(item["match_score"] or 0),
        ))
    return output[:limit]


@app.get("/api/filter-options")
def filter_options(db: Session = Depends(get_db)):
    sources = [x for x in db.scalars(select(PetPost.source).distinct().order_by(PetPost.source)) if x]
    statuses = [x for x in db.scalars(select(PetPost.status).distinct().order_by(PetPost.status)) if x]
    sexes = [x for x in db.scalars(select(PetPost.sex).distinct().order_by(PetPost.sex)) if x and x != "unknown"]
    return {
        "sources": sources,
        "statuses": statuses,
        "sexes": sexes,
        "colors": ["orange", "black", "gray", "white", "brown", "cream", "calico", "tortoiseshell"],
        "patterns": ["striped", "solid", "tuxedo", "spotted"],
        "coats": ["short", "medium", "long"],
        "collars": ["none", "wearing"],
        "microchips": ["none", "yes"],
        "altered": ["neutered", "intact", "spayed"],
    }


@app.get("/api/queue-stats")
def queue_stats(
    not_before: datetime | None = None,
    db: Session = Depends(get_db),
):
    conditions = []
    if not_before is not None:
        cutoff = not_before if not_before.tzinfo else not_before.replace(tzinfo=timezone.utc)
        conditions.append(func.coalesce(PetPost.reported_at, PetPost.first_seen_at) >= cutoff)

    grouped_stmt = select(PetPost.review_state, func.count(PetPost.id))
    if conditions:
        grouped_stmt = grouped_stmt.where(*conditions)
    grouped = dict(db.execute(grouped_stmt.group_by(PetPost.review_state)).all())

    high_stmt = select(func.count(PetPost.id)).where(PetPost.review_state == "new", PetPost.match_score >= 65)
    photo_stmt = select(func.count(PetPost.id)).where(PetPost.review_state == "new", PetPost.image_url.is_not(None), PetPost.image_url != "")
    if conditions:
        high_stmt = high_stmt.where(*conditions)
        photo_stmt = photo_stmt.where(*conditions)
    high_new = db.scalar(high_stmt) or 0
    with_photo = db.scalar(photo_stmt) or 0
    return {
        "new": grouped.get("new", 0),
        "possible": grouped.get("possible", 0),
        "needs_review": grouped.get("needs_review", 0),
        "dismissed": grouped.get("dismissed", 0),
        "confirmed": grouped.get("confirmed", 0),
        "high_priority_new": high_new,
        "new_with_source_photo": with_photo,
    }


@app.post("/api/posts/{post_id}/review", response_model=PetPostOut)
def review_post(post_id: int, payload: ReviewIn, db: Session = Depends(get_db)):
    row = db.get(PetPost, post_id)
    if not row:
        raise HTTPException(404, "Post not found")
    row.review_state = payload.review_state
    db.commit()
    db.refresh(row)
    vision = db.scalar(select(PostVision).where(PostVision.post_id == post_id))
    return post_output(row, vision, get_or_create_profile(db))


@app.post("/api/posts/{post_id}/reanalyze", response_model=PetPostOut)
async def reanalyze_post(post_id: int, db: Session = Depends(get_db)):
    row = db.get(PetPost, post_id)
    if not row:
        raise HTTPException(404, "Post not found")
    old = db.scalar(select(PostVision).where(PostVision.post_id == post_id))
    if old:
        db.delete(old)
        db.commit()
    await analyze_post_ids(db, [post_id], max_bytes=settings.max_image_bytes)
    db.refresh(row)
    vision = db.scalar(select(PostVision).where(PostVision.post_id == post_id))
    return post_output(row, vision, get_or_create_profile(db))


@app.get("/api/profile", response_model=ProfileOut)
def get_profile(db: Session = Depends(get_db)):
    return get_or_create_profile(db)


@app.put("/api/profile", response_model=ProfileOut)
def set_profile(payload: ProfileIn, db: Session = Depends(get_db)):
    profile = get_or_create_profile(db)
    for key, value in payload.model_dump().items():
        setattr(profile, key, value)
    db.commit()
    db.refresh(profile)
    rescore_all(db)
    return profile


@app.get("/api/reference-photos", response_model=list[ReferencePhotoOut])
def list_reference_photos(db: Session = Depends(get_db)):
    return list(db.scalars(select(ArchieReferencePhoto).order_by(ArchieReferencePhoto.created_at)))


def _decode_data_url(data_url: str, max_bytes: int) -> tuple[bytes, str]:
    match = re.fullmatch(r"data:(image/(?:jpeg|png|webp));base64,(.+)", data_url, re.I | re.S)
    if not match:
        raise HTTPException(400, "Reference photo must be a JPEG, PNG, or WebP data URL")
    mime = match.group(1).lower()
    try:
        data = base64.b64decode(match.group(2), validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(400, "Invalid base64 image data")
    if not data:
        raise HTTPException(400, "Empty image")
    if len(data) > max_bytes:
        raise HTTPException(413, "Reference photo exceeds configured size limit")
    ext = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}[mime]
    return data, ext


@app.post("/api/reference-photos", response_model=ReferencePhotoOut)
def add_reference_photo(payload: ReferencePhotoIn, db: Session = Depends(get_db)):
    data, ext = _decode_data_url(payload.data_url, settings.max_image_bytes)
    try:
        fp = fingerprint_image(data)
    except Exception as exc:
        raise HTTPException(400, f"Could not read image: {exc}")

    stored_name = f"{uuid.uuid4().hex}{ext}"
    path = reference_dir / stored_name
    path.write_bytes(data)
    row = ArchieReferencePhoto(
        label=payload.label.strip() or "Archie reference",
        filename=payload.filename[:240],
        media_url=f"/media/reference/{stored_name}",
        perceptual_hash=fp.dhash,
        color_histogram=fp.histogram_json(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    recompute_vision_matches(db)
    return row


@app.delete("/api/reference-photos/{photo_id}")
def delete_reference_photo(photo_id: int, db: Session = Depends(get_db)):
    row = db.get(ArchieReferencePhoto, photo_id)
    if not row:
        raise HTTPException(404, "Reference photo not found")
    stored_name = Path(row.media_url).name
    db.delete(row)
    db.commit()
    try:
        (reference_dir / stored_name).unlink(missing_ok=True)
    except OSError:
        logger.warning("Could not delete reference image %s", stored_name)
    recompute_vision_matches(db)
    return {"deleted": photo_id}


@app.post("/api/ingest/all")
async def ingest_all():
    return await _ingest_all_once()


@app.post("/api/ingest/pawboost")
async def ingest_pawboost():
    return await _ingest_pawboost_once()


@app.post("/api/ingest/orange-county")
async def ingest_orange_county():
    return await _ingest_orange_once()


@app.post("/api/ingest/24petconnect")
async def ingest_regional_24petconnect():
    return await _ingest_regional_24petconnect_once()


@app.post("/api/ingest/aps-durham")
async def ingest_aps_durham():
    return await _ingest_aps_durham_once()


@app.post("/api/ingest/wake-county")
async def ingest_wake_county():
    return await _ingest_wake_once()


@app.post("/api/ingest/pet911")
async def ingest_pet911():
    return await _ingest_pet911_once()


@app.post("/api/ingest/petkey")
async def ingest_petkey():
    return await _ingest_petkey_once()


@app.post("/api/ingest/{source_key}")
async def ingest_one(source_key: str):
    mapping = {
        "pawboost": _ingest_pawboost_once,
        "orange-county": _ingest_orange_once,
        "24petconnect": _ingest_regional_24petconnect_once,
        "aps-durham": _ingest_aps_durham_once,
        "wake-county": _ingest_wake_once,
        "pet911": _ingest_pet911_once,
        "petkey": _ingest_petkey_once,
    }
    fn = mapping.get(source_key)
    if not fn:
        raise HTTPException(404, "Unknown source")
    return await fn()


@app.post("/api/geocode/backfill")
async def geocode_backfill(limit: int = Query(150, ge=1, le=1000)):
    return await _backfill_geocodes_once(limit)


@app.post("/api/bridge/facebook")
async def facebook_bridge(payload: FacebookBridgeIn, db: Session = Depends(get_db)):
    post = PetPostIn(source="facebook_bridge", **payload.model_dump(), raw={"captured_via": "bridge"})
    posts = [post]
    result = upsert_posts(db, posts)
    if settings.analyze_images:
        result["vision"] = await analyze_post_ids(
            db,
            result.get("post_ids", []),
            max_bytes=settings.max_image_bytes,
        )
    return result


@app.delete("/api/source/{source}")
def delete_source(source: str, db: Session = Depends(get_db)):
    post_ids = list(db.scalars(select(PetPost.id).where(PetPost.source == source)))
    if post_ids:
        db.execute(delete(PostVision).where(PostVision.post_id.in_(post_ids)))
    result = db.execute(delete(PetPost).where(PetPost.source == source))
    db.commit()
    return {"source": source, "deleted": result.rowcount or 0}
