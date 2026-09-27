from __future__ import annotations

import asyncio
import base64
import binascii
import csv
import io
import json
import logging
import os
import re
import tempfile
import uuid
import zipfile
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import delete, desc, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from shapely.geometry import shape as shape_geojson
from shapely.geometry import mapping as mapping_geojson
from shapely.ops import transform as transform_geometry
from pyproj import Transformer
from PIL import Image

from .connectors.orange_county import OrangeCountyFoundCatsConnector
from .connectors.pawboost import PawBoostConnector
from .connectors.regional_24petconnect import Regional24PetConnectConnector
from .connectors.aps_durham import APSDurhamFoundPetsConnector
from .connectors.wake_county import WakeCountyLostFoundConnector
from .connectors.pet911 import Pet911Connector
from .connectors.petkey import PetkeyConnector
from .candidates.identity import case_output, ensure_candidate_cases
from .db import Base, SessionLocal, engine, get_db
from .geocoder import NominatimGeocoder, geocode_posts
from .image_service import analyze_post_ids
from .models import ArchieProfile, ArchieReferencePhoto, CandidateCase, CandidateCasePost, CandidateIdentifier, PetPost, PostVision, SurveyorMapObject, SurveyorTrailCamera, SurveyorCameraPlacement, SurveyorSearchSession, SurveyorEvent, SurveyorAttachment, SurveyorObjectLink, SurveyorTask, utcnow
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
    SurveyorCameraIn,
    SurveyorCameraUpdate,
    SurveyorCameraOut,
    SurveyorSessionIn,
    SurveyorSessionOut,
    SurveyorSessionUpdate,
    SurveyorSessionCheckpoint,
    SurveyorCoverageIn,
    SurveyorEventOut,
    SurveyorAttachmentOut,
    SurveyorMediaExportIn,
    SurveyorLinkIn,
    SurveyorLinkPatch,
    SurveyorLinkOut,
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
from .surveyor_media import PublicMediaFiles, attachment_metadata, classify_media, contained_path, delete_attachment_files, store_upload
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
        ensure_candidate_cases(db)
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
from .places import router as places_router
from .surveyor.access import router as surveyor_access_router
from .surveyor.tasks import router as surveyor_tasks_router
app.include_router(surveyor_access_router)
app.include_router(surveyor_tasks_router)
app.include_router(places_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if "*" in settings.cors_origin_list else settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/media", PublicMediaFiles(directory=str(media_dir)), name="media")


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
    visit(geometry.get("coordinates"))
    if geometry["type"] == "GeometryCollection":
        for item in geometry.get("geometries", []):
            _geometry_stats(item)
            visit(item.get("coordinates"))
    if not coords:
        raise HTTPException(status_code=422, detail="GeoJSON geometry has no coordinates")
    try:
        geometry_shape = shape_geojson(geometry)
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Malformed GeoJSON geometry") from exc
    if geometry_shape.is_empty or not geometry_shape.is_valid:
        raise HTTPException(status_code=422, detail="GeoJSON geometry is empty or invalid")
    west, south, east, north = geometry_shape.bounds
    centroid = geometry_shape.centroid
    return centroid.y, centroid.x, west, south, east, north


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


def _camera_output(db: Session, camera: SurveyorTrailCamera) -> SurveyorCameraOut:
    placements = list(db.scalars(select(SurveyorCameraPlacement).where(
        SurveyorCameraPlacement.camera_id == camera.id
    ).order_by(SurveyorCameraPlacement.installed_at.desc())))
    def placement_dict(row):
        return {"id": row.id, "latitude": row.latitude, "longitude": row.longitude,
                "heading_degrees": row.heading_degrees, "fov_degrees": row.fov_degrees,
                "range_meters": row.range_meters, "installed_at": row.installed_at,
                "removed_at": row.removed_at, "notes": row.notes}
    active = next((item for item in placements if item.removed_at is None), None)
    return SurveyorCameraOut(id=camera.id, map_object_id=camera.map_object_id, name=camera.name,
        camera_model=camera.camera_model, power_type=camera.power_type, notes=camera.notes,
        retired_at=camera.retired_at, placement=placement_dict(active) if active else None,
        history=[placement_dict(item) for item in placements])


def _record_surveyor_event(db: Session, event_type: str, entity_type: str, entity_id: int | str, action: str,
                           before: dict | None = None, after: dict | None = None, reversible: bool = False, notes: str = ""):
    db.add(SurveyorEvent(event_type=event_type, entity_type=entity_type, entity_id=str(entity_id), action=action,
        before_json=json.dumps(before, default=str) if before is not None else None,
        after_json=json.dumps(after, default=str) if after is not None else None, reversible=reversible, notes=notes))


def _event_output(row: SurveyorEvent) -> SurveyorEventOut:
    return SurveyorEventOut(id=row.id, event_type=row.event_type, entity_type=row.entity_type, entity_id=row.entity_id,
        action=row.action, before=json.loads(row.before_json) if row.before_json else None,
        after=json.loads(row.after_json) if row.after_json else None, occurred_at=row.occurred_at,
        created_at=row.created_at, reversible=row.reversible, notes=row.notes)


def _session_output(row: SurveyorSearchSession) -> SurveyorSessionOut:
    return SurveyorSessionOut(id=row.id, method=row.method, started_at=row.started_at, ended_at=row.ended_at,
        track_geojson=json.loads(row.track_geojson) if row.track_geojson else None,
        distance_meters=row.distance_meters, notes=row.notes, result_summary=row.result_summary, created_at=row.created_at)


def _attachment_output(row: SurveyorAttachment) -> SurveyorAttachmentOut:
    metadata = attachment_metadata(row)
    kind = metadata.get("media_type") or ("document" if row.attachment_type == "file" else row.attachment_type)
    preview = f"/api/surveyor/attachments/{row.id}/preview" if row.storage_path else None
    thumbnail = f"/api/surveyor/attachments/{row.id}/thumbnail" if row.storage_path else None
    return SurveyorAttachmentOut(id=row.id, map_object_id=row.map_object_id, search_session_id=row.search_session_id,
        attachment_type=kind, original_filename=metadata.get("original_filename") or metadata.get("source_filename") or Path(row.storage_path or "field-media").name,
        mime_type=metadata.get("mime_type") or metadata.get("content_type") or "application/octet-stream",
        duration_seconds=metadata.get("duration_seconds"), width=metadata.get("width"), height=metadata.get("height"),
        aspect_ratio=metadata.get("aspect_ratio"),
        file_size_bytes=int(metadata.get("file_size_bytes") or metadata.get("size_bytes") or 0),
        latitude=metadata.get("latitude"), longitude=metadata.get("longitude"),
        media_url=preview, preview_url=preview, thumbnail_url=thumbnail,
        download_url=f"/api/surveyor/attachments/{row.id}/download" if row.storage_path else None,
        external_url=row.external_url, caption=row.caption or metadata.get("caption", ""), notes=metadata.get("notes", ""),
        observed_at=row.observed_at, source=row.source, metadata=metadata, created_at=row.created_at)


def _link_output(db: Session, row: SurveyorObjectLink) -> SurveyorLinkOut:
    source = db.get(SurveyorMapObject, row.source_object_id)
    target = db.get(SurveyorMapObject, row.target_object_id)
    if source is None or target is None:
        raise HTTPException(status_code=409, detail="A linked object no longer exists")
    coordinates = [[source.centroid_lon, source.centroid_lat]]
    if row.vertices_geojson:
        coordinates.extend(json.loads(row.vertices_geojson))
    coordinates.append([target.centroid_lon, target.centroid_lat])
    geometry = {"type": "LineString", "coordinates": coordinates}
    return SurveyorLinkOut(id=row.id, source_object_id=row.source_object_id, target_object_id=row.target_object_id,
        link_type=row.link_type, line_style=row.line_style, label=row.label, notes=row.notes, geometry=geometry,
        created_at=row.created_at, updated_at=row.updated_at)


@app.get("/api/surveyor/cameras", response_model=list[SurveyorCameraOut])
def list_surveyor_cameras(db: Session = Depends(get_db)):
    cameras = db.scalars(select(SurveyorTrailCamera).where(SurveyorTrailCamera.retired_at.is_(None)).order_by(SurveyorTrailCamera.name))
    return [_camera_output(db, camera) for camera in cameras]


@app.post("/api/surveyor/cameras", response_model=SurveyorCameraOut, status_code=201)
def create_surveyor_camera(payload: SurveyorCameraIn, db: Session = Depends(get_db)):
    map_object = SurveyorMapObject(object_type="trail_camera", subtype="camera", name=payload.name,
        style_json="{}", properties_json="{}", status="active", epistemic_state="observed", notes=payload.notes)
    _save_surveyor_geometry(map_object, {"type": "Point", "coordinates": [payload.longitude, payload.latitude]})
    db.add(map_object); db.flush()
    camera = SurveyorTrailCamera(map_object_id=map_object.id, name=payload.name,
        camera_model=payload.camera_model, power_type=payload.power_type, notes=payload.notes)
    db.add(camera); db.flush()
    placement = SurveyorCameraPlacement(camera_id=camera.id, latitude=payload.latitude, longitude=payload.longitude,
        heading_degrees=payload.heading_degrees % 360, fov_degrees=payload.fov_degrees,
        range_meters=payload.range_meters, installed_at=payload.installed_at or utcnow(), notes=payload.notes)
    db.add(placement); db.commit(); db.refresh(camera)
    _record_surveyor_event(db, "camera_created", "trail_camera", camera.id, f"Installed {camera.name}",
        after=_camera_output(db, camera).model_dump(mode="json"))
    db.commit()
    return _camera_output(db, camera)


@app.get("/api/surveyor/cameras/{camera_id}", response_model=SurveyorCameraOut)
def get_surveyor_camera(camera_id: int, db: Session = Depends(get_db)):
    camera = db.get(SurveyorTrailCamera, camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail="Trail camera not found")
    return _camera_output(db, camera)


@app.patch("/api/surveyor/cameras/{camera_id}", response_model=SurveyorCameraOut)
def update_surveyor_camera(camera_id: int, payload: SurveyorCameraUpdate, db: Session = Depends(get_db)):
    camera = db.get(SurveyorTrailCamera, camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail="Trail camera not found")
    before = _camera_output(db, camera).model_dump(mode="json")
    values = payload.model_dump(exclude_unset=True)
    save_as_new = values.pop("save_as_new_placement", False)
    camera_fields = {key: values.pop(key) for key in list(values) if key in {"name", "camera_model", "power_type", "notes"}}
    for key, value in camera_fields.items():
        setattr(camera, key, value)
    map_object = db.get(SurveyorMapObject, camera.map_object_id)
    if "name" in camera_fields:
        map_object.name = camera_fields["name"]
    if "notes" in camera_fields:
        map_object.notes = camera_fields["notes"]
    placement = db.scalar(select(SurveyorCameraPlacement).where(
        SurveyorCameraPlacement.camera_id == camera.id, SurveyorCameraPlacement.removed_at.is_(None)
    ))
    placement_keys = {"latitude", "longitude", "heading_degrees", "fov_degrees", "range_meters"}
    placement_updates = {key: value for key, value in values.items() if key in placement_keys and value is not None
        and (placement is None or value != getattr(placement, key))}
    position_changed = any(key in placement_updates for key in {"latitude", "longitude"})
    aim_updates = {key: value for key, value in placement_updates.items()
        if key in {"heading_degrees", "fov_degrees", "range_meters"}}
    if position_changed or save_as_new:
        if placement is None:
            raise HTTPException(status_code=409, detail="Camera has no active placement")
        next_values = {key: getattr(placement, key) for key in placement_keys}
        next_values.update(placement_updates)
        placement.removed_at = utcnow()
        db.add(SurveyorCameraPlacement(camera_id=camera.id, **next_values, installed_at=utcnow(), notes=placement.notes))
        if position_changed:
            _save_surveyor_geometry(map_object, {"type": "Point", "coordinates": [next_values["longitude"], next_values["latitude"]]})
    elif aim_updates:
        for key, value in aim_updates.items():
            setattr(placement, key, value)
    db.flush()
    if position_changed or save_as_new or aim_updates:
        action = "camera_moved" if position_changed else "camera_placement_saved" if save_as_new else "camera_aimed"
        _record_surveyor_event(db, action, "trail_camera", camera.id,
            f"{'Moved' if position_changed else 'Saved placement for' if save_as_new else 'Re-aimed'} {camera.name}", before=before,
            after=_camera_output(db, camera).model_dump(mode="json"), reversible=True)
    db.commit(); db.refresh(camera)
    return _camera_output(db, camera)


@app.get("/api/surveyor/cameras/{camera_id}/placements")
def list_surveyor_camera_placements(camera_id: int, db: Session = Depends(get_db)):
    if db.get(SurveyorTrailCamera, camera_id) is None:
        raise HTTPException(status_code=404, detail="Trail camera not found")
    placements = db.scalars(select(SurveyorCameraPlacement).where(
        SurveyorCameraPlacement.camera_id == camera_id
    ).order_by(SurveyorCameraPlacement.installed_at.desc()))
    return [{
        "id": item.id, "camera_id": item.camera_id, "latitude": item.latitude, "longitude": item.longitude,
        "heading_degrees": item.heading_degrees, "fov_degrees": item.fov_degrees, "range_meters": item.range_meters,
        "installed_at": item.installed_at, "removed_at": item.removed_at, "notes": item.notes
    } for item in placements]


@app.post("/api/surveyor/cameras/{camera_id}/deactivate", response_model=SurveyorCameraOut)
def deactivate_surveyor_camera(camera_id: int, db: Session = Depends(get_db)):
    camera = db.get(SurveyorTrailCamera, camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail="Trail camera not found")
    now = utcnow(); camera.retired_at = now
    active = db.scalar(select(SurveyorCameraPlacement).where(
        SurveyorCameraPlacement.camera_id == camera.id, SurveyorCameraPlacement.removed_at.is_(None)
    ))
    if active:
        active.removed_at = now
    map_object = db.get(SurveyorMapObject, camera.map_object_id); map_object.status = "inactive"
    _record_surveyor_event(db, "camera_deactivated", "trail_camera", camera.id, f"Deactivated {camera.name}")
    db.commit(); db.refresh(camera)
    return _camera_output(db, camera)


@app.get("/api/surveyor/sessions", response_model=list[SurveyorSessionOut])
def list_surveyor_sessions(from_date: datetime | None = Query(None, alias="from"),
                           to_date: datetime | None = Query(None, alias="to"), db: Session = Depends(get_db)):
    query = select(SurveyorSearchSession)
    if from_date:
        query = query.where(SurveyorSearchSession.started_at >= from_date)
    if to_date:
        query = query.where(SurveyorSearchSession.started_at <= to_date)
    return [_session_output(row) for row in db.scalars(query.order_by(SurveyorSearchSession.started_at.desc()))]


@app.post("/api/surveyor/sessions", response_model=SurveyorSessionOut, status_code=201)
def start_surveyor_session(payload: SurveyorSessionIn, db: Session = Depends(get_db)):
    row = SurveyorSearchSession(method=payload.method, started_at=payload.started_at or utcnow(), notes=payload.notes)
    db.add(row); db.flush()
    _record_surveyor_event(db, "search_started", "search_session", row.id, f"Started {row.method} search", after=_session_output(row).model_dump(mode="json"))
    db.commit(); db.refresh(row)
    return _session_output(row)


@app.patch("/api/surveyor/sessions/{session_id}", response_model=SurveyorSessionOut)
def finish_surveyor_session(session_id: int, payload: SurveyorSessionUpdate, db: Session = Depends(get_db)):
    row = db.get(SurveyorSearchSession, session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Search session not found")
    if row.ended_at is not None:
        raise HTTPException(status_code=409, detail="Search session is already complete")
    if payload.track_geojson is not None:
        _geometry_stats(payload.track_geojson)
        row.track_geojson = json.dumps(payload.track_geojson, separators=(",", ":"))
    if payload.distance_meters is not None:
        row.distance_meters = payload.distance_meters
    if payload.notes is not None:
        row.notes = payload.notes
    if payload.result_summary is not None:
        row.result_summary = payload.result_summary
    row.ended_at = payload.ended_at or utcnow()
    _record_surveyor_event(db, "search_completed", "search_session", row.id, f"Completed {row.method} search",
        after=_session_output(row).model_dump(mode="json"), reversible=False)
    db.commit(); db.refresh(row)
    return _session_output(row)


@app.put("/api/surveyor/sessions/{session_id}/checkpoint", response_model=SurveyorSessionOut)
def checkpoint_surveyor_session(session_id: int, payload: SurveyorSessionCheckpoint, db: Session = Depends(get_db)):
    row = db.get(SurveyorSearchSession, session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Search session not found")
    if row.ended_at is not None:
        raise HTTPException(status_code=409, detail="Search session is already complete")
    _geometry_stats(payload.track_geojson)
    row.track_geojson = json.dumps(payload.track_geojson, separators=(",", ":"))
    row.distance_meters = payload.distance_meters
    db.commit(); db.refresh(row)
    return _session_output(row)


@app.post("/api/surveyor/sessions/{session_id}/coverage", response_model=SurveyorObjectOut, status_code=201)
def create_session_coverage(session_id: int, payload: SurveyorCoverageIn, db: Session = Depends(get_db)):
    session = db.get(SurveyorSearchSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Search session not found")
    if session.ended_at is None:
        raise HTTPException(status_code=409, detail="Finish the search session before creating coverage")
    try:
        route_geojson = json.loads(session.track_geojson or "null")
        route = shape_geojson(route_geojson)
        if route.geom_type != "LineString" or route.is_empty or len(route.coords) < 2:
            raise ValueError("A LineString with at least two route points is required")
        lon, lat = route.centroid.x, route.centroid.y
        zone_number = max(1, min(60, int((lon + 180) // 6) + 1))
        epsg = (32600 if lat >= 0 else 32700) + zone_number
        forward = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True).transform
        reverse = Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True).transform
        projected = transform_geometry(forward, route)
        buffered = projected.buffer(payload.buffer_meters, cap_style="round", join_style="round")
        polygon = transform_geometry(reverse, buffered)
        geometry = mapping_geojson(polygon)
        _geometry_stats(geometry)
    except (TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=422, detail=f"Session route cannot produce coverage: {exc}") from exc
    searched_at = session.ended_at or utcnow()
    row = SurveyorMapObject(object_type="zone", subtype="searched", name=payload.name,
        geometry_geojson=json.dumps(geometry, separators=(",", ":")), style_json="{}",
        properties_json=json.dumps({"searched_at": searched_at.isoformat(), "search_session_id": session.id,
            "search_method": session.method, "buffer_meters": payload.buffer_meters, "generated_from_route": True}),
        status="searched", confidence="strong", epistemic_state="observed", occurred_at=searched_at,
        notes=payload.notes)
    _save_surveyor_geometry(row, geometry)
    db.add(row); db.flush()
    _record_surveyor_event(db, "search_coverage_created", "map_object", row.id, "Created searched coverage from route",
        after={"search_session_id": session.id, "buffer_meters": payload.buffer_meters, "search_method": session.method})
    db.commit(); db.refresh(row)
    return _surveyor_out(row)


@app.get("/api/surveyor/sessions/{session_id}/summary")
def surveyor_session_summary(session_id: int, db: Session = Depends(get_db)):
    session = db.get(SurveyorSearchSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Search session not found")
    linked = [obj for obj in db.scalars(select(SurveyorMapObject))
        if json.loads(obj.properties_json or "{}").get("search_session_id") == session_id]
    object_ids = [obj.id for obj in linked]
    event_conditions = [(SurveyorEvent.entity_type == "search_session") & (SurveyorEvent.entity_id == str(session_id))]
    attachment_conditions = [SurveyorAttachment.search_session_id == session_id]
    task_conditions = [SurveyorTask.search_session_id == session_id]
    if object_ids:
        ids = [str(item) for item in object_ids]
        event_conditions.append((SurveyorEvent.entity_type == "map_object") & SurveyorEvent.entity_id.in_(ids))
        attachment_conditions.append(SurveyorAttachment.map_object_id.in_(object_ids))
        task_conditions.append(SurveyorTask.map_object_id.in_(object_ids))
    events = list(db.scalars(select(SurveyorEvent).where(or_(*event_conditions)).order_by(SurveyorEvent.occurred_at.asc())))
    attachments = list(db.scalars(select(SurveyorAttachment).where(or_(*attachment_conditions))))
    tasks = list(db.scalars(select(SurveyorTask).where(or_(*task_conditions))))
    by_type = {}
    for obj in linked: by_type[obj.object_type] = by_type.get(obj.object_type, 0) + 1
    coverage = [obj.id for obj in linked if obj.object_type == "zone" and json.loads(obj.properties_json or "{}").get("generated_from_route")]
    return {"session": _session_output(session), "object_count": len(linked), "objects_by_type": by_type,
        "attachment_count": len(attachments), "events": [_event_output(item) for item in events],
        "coverage_objects": coverage, "tasks_created": len(tasks), "objects": [_surveyor_out(item) for item in linked]}


@app.get("/api/surveyor/events", response_model=list[SurveyorEventOut])
def list_surveyor_events(event_type: str | None = None, from_date: datetime | None = Query(None, alias="from"),
                         to_date: datetime | None = Query(None, alias="to"), limit: int = Query(500, ge=1, le=2000),
                         db: Session = Depends(get_db)):
    query = select(SurveyorEvent)
    if event_type:
        query = query.where(SurveyorEvent.event_type == event_type)
    if from_date:
        query = query.where(SurveyorEvent.occurred_at >= from_date)
    if to_date:
        query = query.where(SurveyorEvent.occurred_at <= to_date)
    return [_event_output(row) for row in db.scalars(query.order_by(SurveyorEvent.occurred_at.desc()).limit(limit))]


@app.get("/api/surveyor/brief")
def surveyor_brief(db: Session = Depends(get_db)):
    now = utcnow(); today = now.date()
    tasks = list(db.scalars(select(SurveyorTask).where(SurveyorTask.status == "open")))
    due_today = overdue = 0
    for task in tasks:
        if task.due_at is None: continue
        due_date = task.due_at.date()
        due_today += due_date == today
        overdue += due_date < today
    objects = list(db.scalars(select(SurveyorMapObject).where(or_(SurveyorMapObject.status.is_(None), SurveyorMapObject.status != "archived"))))
    needs_search = sum(obj.object_type == "zone" and obj.subtype == "needs_search" for obj in objects)
    needs_recheck = sum(obj.object_type == "zone" and obj.subtype == "needs_recheck" for obj in objects)
    stale = 0
    for obj in objects:
        if obj.object_type != "zone" or obj.subtype != "searched": continue
        try:
            searched = datetime.fromisoformat(json.loads(obj.properties_json).get("searched_at", ""))
            if searched.tzinfo is None: searched = searched.replace(tzinfo=timezone.utc)
            stale += (now - searched).days > 30
        except (TypeError, ValueError):
            continue
    unresolved = sum(obj.object_type == "evidence" and json.loads(obj.properties_json).get("resolution", "unresolved") == "unresolved" for obj in objects)
    active_session = db.scalar(select(SurveyorSearchSession).where(SurveyorSearchSession.ended_at.is_(None)).order_by(SurveyorSearchSession.started_at.desc()).limit(1))
    recent = db.scalar(select(func.count(SurveyorMapObject.id)).where(SurveyorMapObject.occurred_at >= now - timedelta(hours=24), SurveyorMapObject.object_type.in_(["pin", "evidence"]))) or 0
    return {"open_tasks": len(tasks), "due_today": due_today, "overdue_tasks": overdue,
        "needs_search_zones": needs_search, "needs_recheck_zones": needs_recheck,
        "stale_search_zones": stale, "unresolved_evidence": unresolved,
        "active_cameras": db.scalar(select(func.count(SurveyorTrailCamera.id)).where(SurveyorTrailCamera.retired_at.is_(None))) or 0,
        "active_search_session": _session_output(active_session).model_dump(mode="json") if active_session else None,
        "recent_observations_24h": recent}


@app.get("/api/surveyor/objects/{object_id}/attachments", response_model=list[SurveyorAttachmentOut])
def list_object_attachments(object_id: int, db: Session = Depends(get_db)):
    if db.get(SurveyorMapObject, object_id) is None:
        raise HTTPException(status_code=404, detail="Surveyor object not found")
    rows = db.scalars(select(SurveyorAttachment).where(SurveyorAttachment.map_object_id == object_id).order_by(SurveyorAttachment.created_at.desc()))
    return [_attachment_output(row) for row in rows]


@app.post("/api/surveyor/objects/{object_id}/attachments", response_model=SurveyorAttachmentOut, status_code=201)
async def upload_surveyor_attachment(object_id: int, file: UploadFile = File(...), caption: str = Form(""),
                                    observed_at: datetime | None = Form(None), notes: str = Form(""),
                                    latitude: float | None = Form(None), longitude: float | None = Form(None),
                                    duration_seconds: float | None = Form(None), width: int | None = Form(None), height: int | None = Form(None),
                                    source: str = Form("user capture"), db: Session = Depends(get_db)):
    map_object = db.get(SurveyorMapObject, object_id)
    if map_object is None:
        raise HTTPException(status_code=404, detail="Surveyor object not found")
    kind, _ = classify_media(file.content_type, file.filename)
    limit = settings.max_image_bytes if kind == "image" else settings.surveyor_max_video_mb * 1024 * 1024 if kind == "video" else settings.surveyor_max_audio_mb * 1024 * 1024 if kind == "audio" else settings.surveyor_max_document_mb * 1024 * 1024
    storage_path, metadata = await store_upload(file, media_dir, caption=caption, notes=notes, observed_at=observed_at,
        latitude=latitude, longitude=longitude, duration_seconds=duration_seconds, width=width, height=height, max_bytes=limit)
    metadata.pop("caption", None)
    row = SurveyorAttachment(map_object_id=object_id, attachment_type=kind, storage_path=storage_path,
        caption=caption, observed_at=observed_at, source=source[:120], metadata_json=json.dumps(metadata))
    db.add(row); db.flush()
    _record_surveyor_event(db, "evidence_added", "map_object", object_id, "Added evidence attachment",
        after={"attachment_id": row.id, "attachment_type": kind, "caption": caption})
    db.commit(); db.refresh(row)
    return _attachment_output(row)


@app.get("/api/surveyor/sessions/{session_id}/attachments", response_model=list[SurveyorAttachmentOut])
def list_session_attachments(session_id: int, db: Session = Depends(get_db)):
    if db.get(SurveyorSearchSession, session_id) is None:
        raise HTTPException(status_code=404, detail="Search session not found")
    rows = db.scalars(select(SurveyorAttachment).where(SurveyorAttachment.search_session_id == session_id).order_by(SurveyorAttachment.created_at.desc()))
    return [_attachment_output(row) for row in rows]


@app.post("/api/surveyor/sessions/{session_id}/attachments", response_model=SurveyorAttachmentOut, status_code=201)
async def upload_session_attachment(session_id: int, file: UploadFile = File(...), caption: str = Form(""),
                                    observed_at: datetime | None = Form(None), notes: str = Form(""),
                                    latitude: float | None = Form(None), longitude: float | None = Form(None),
                                    duration_seconds: float | None = Form(None), width: int | None = Form(None), height: int | None = Form(None),
                                    source: str = Form("user capture"), db: Session = Depends(get_db)):
    session = db.get(SurveyorSearchSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Search session not found")
    kind, _ = classify_media(file.content_type, file.filename)
    limit = settings.max_image_bytes if kind == "image" else settings.surveyor_max_video_mb * 1024 * 1024 if kind == "video" else settings.surveyor_max_audio_mb * 1024 * 1024 if kind == "audio" else settings.surveyor_max_document_mb * 1024 * 1024
    storage_path, metadata = await store_upload(file, media_dir, caption=caption, notes=notes, observed_at=observed_at,
        latitude=latitude, longitude=longitude, duration_seconds=duration_seconds, width=width, height=height, max_bytes=limit)
    metadata.pop("caption", None)
    row = SurveyorAttachment(search_session_id=session_id, attachment_type=kind, storage_path=storage_path,
        caption=caption, observed_at=observed_at, source=source[:120], metadata_json=json.dumps(metadata))
    db.add(row); db.flush()
    _record_surveyor_event(db, "evidence_added", "search_session", session_id, "Added session evidence attachment",
        after={"attachment_id": row.id, "attachment_type": kind, "caption": caption})
    db.commit(); db.refresh(row)
    return _attachment_output(row)


@app.delete("/api/surveyor/attachments/{attachment_id}", status_code=204)
def delete_surveyor_attachment(attachment_id: int, db: Session = Depends(get_db)):
    row = db.get(SurveyorAttachment, attachment_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Attachment not found")
    if row.storage_path:
        delete_attachment_files(row, media_dir)
    owner_type = "map_object" if row.map_object_id is not None else "search_session"
    owner_id = row.map_object_id if row.map_object_id is not None else row.search_session_id
    _record_surveyor_event(db, "attachment_deleted", owner_type, owner_id, "Deleted evidence attachment",
        before={"attachment_id": row.id, "attachment_type": row.attachment_type, "caption": row.caption})
    db.delete(row); db.commit()
    return None


def _attachment_original_path(row: SurveyorAttachment) -> Path:
    if not row.storage_path:
        raise HTTPException(status_code=404, detail="This attachment has no stored original")
    path = contained_path(media_dir, row.storage_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Stored media file is missing")
    return path


def _attachment_derivative_path(row: SurveyorAttachment, key: str) -> Path | None:
    metadata = attachment_metadata(row)
    relative = (metadata.get("derivatives") or {}).get(key)
    if not relative:
        return None
    path = contained_path(media_dir, (Path("surveyor") / relative).as_posix())
    return path if path.is_file() else None


@app.get("/api/surveyor/attachments/{attachment_id}/download")
def download_surveyor_attachment(attachment_id: int, db: Session = Depends(get_db)):
    row = db.get(SurveyorAttachment, attachment_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Attachment not found")
    metadata = attachment_metadata(row)
    return FileResponse(_attachment_original_path(row), media_type=metadata.get("mime_type", "application/octet-stream"),
        filename=metadata.get("original_filename") or Path(row.storage_path or "field-media").name)


@app.get("/api/surveyor/attachments/{attachment_id}/preview")
def preview_surveyor_attachment(attachment_id: int, db: Session = Depends(get_db)):
    row = db.get(SurveyorAttachment, attachment_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Attachment not found")
    metadata = attachment_metadata(row)
    preview = _attachment_derivative_path(row, "preview")
    path = preview or _attachment_original_path(row)
    mime_type = "image/jpeg" if preview else metadata.get("mime_type", "application/octet-stream")
    return FileResponse(path, media_type=mime_type, headers={"Cache-Control": "private, max-age=3600"})


@app.get("/api/surveyor/attachments/{attachment_id}/thumbnail")
def thumbnail_surveyor_attachment(attachment_id: int, db: Session = Depends(get_db)):
    row = db.get(SurveyorAttachment, attachment_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Attachment not found")
    metadata = attachment_metadata(row)
    key = "poster" if metadata.get("media_type") == "video" or row.attachment_type == "video" else "thumbnail"
    path = _attachment_derivative_path(row, key)
    if path is None:
        if metadata.get("media_type") == "image" or row.attachment_type == "image":
            path = _attachment_original_path(row)
        else:
            raise HTTPException(status_code=404, detail="No thumbnail is available")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})


@app.get("/api/surveyor/media", response_model=list[SurveyorAttachmentOut])
def list_surveyor_media(
    media_type: str | None = Query(None, pattern="^(image|video|audio|document)$"),
    observed_from: datetime | None = None,
    observed_to: datetime | None = None,
    search_session_id: int | None = None,
    map_object_id: int | None = None,
    camera_id: int | None = None,
    candidate_case_id: int | None = None,
    limit: int = Query(500, ge=1, le=2000),
    db: Session = Depends(get_db),
):
    rows = list(db.scalars(select(SurveyorAttachment).order_by(desc(SurveyorAttachment.observed_at), desc(SurveyorAttachment.created_at))))
    result = []
    for row in rows:
        metadata = attachment_metadata(row)
        kind = metadata.get("media_type") or ("document" if row.attachment_type == "file" else row.attachment_type)
        if media_type and kind != media_type:
            continue
        if search_session_id is not None and row.search_session_id != search_session_id:
            continue
        if map_object_id is not None and row.map_object_id != map_object_id:
            continue
        if camera_id is not None:
            camera = db.get(SurveyorTrailCamera, camera_id)
            if not camera or row.map_object_id != camera.map_object_id:
                continue
            metadata["camera_id"] = camera.id
            metadata["camera_name"] = camera.name
        if candidate_case_id is not None:
            obj = db.get(SurveyorMapObject, row.map_object_id) if row.map_object_id else None
            props = json.loads(obj.properties_json or "{}") if obj else {}
            if props.get("candidate_case_id") != candidate_case_id:
                continue
        moment = row.observed_at or row.created_at
        if observed_from and moment < observed_from:
            continue
        if observed_to and moment > observed_to:
            continue
        output = _attachment_output(row)
        obj = db.get(SurveyorMapObject, row.map_object_id) if row.map_object_id else None
        session = db.get(SurveyorSearchSession, row.search_session_id) if row.search_session_id else None
        camera = db.scalar(select(SurveyorTrailCamera).where(SurveyorTrailCamera.map_object_id == obj.id)) if obj else None
        candidate_case_id = None
        if obj:
            object_properties = json.loads(obj.properties_json or "{}")
            candidate_case_id = object_properties.get("candidate_case_id")
        output = output.model_copy(update={
            "map_object_name": obj.name if obj else None,
            "camera_name": camera.name if camera else None,
            "session_label": f"Search #{session.id}" if session else None,
            "candidate_case_id": candidate_case_id,
            "map_object_type": obj.object_type if obj else None,
            "map_object_id": obj.id if obj else None,
            "camera_id": camera.id if camera else None,
        })
        result.append(output)
        if len(result) >= limit:
            break
    return result


@app.get("/api/surveyor/media/config")
def surveyor_media_config():
    return {"max_video_mb": settings.surveyor_max_video_mb, "max_audio_mb": settings.surveyor_max_audio_mb,
            "max_document_mb": settings.surveyor_max_document_mb, "max_image_mb": round(settings.max_image_bytes / (1024 * 1024), 1)}


def _slug(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9]+", "-", (value or "field-media")).strip("-").lower()
    return (value[:48] or "field-media")


def _export_timestamp(value: datetime | None) -> datetime:
    value = value or utcnow()
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _remove_temp_export(path: str):
    Path(path).unlink(missing_ok=True)


@app.post("/api/surveyor/media/export")
def export_surveyor_media(payload: SurveyorMediaExportIn, db: Session = Depends(get_db)):
    requested_ids = list(dict.fromkeys(payload.attachment_ids))
    rows = list(db.scalars(select(SurveyorAttachment).where(SurveyorAttachment.id.in_(requested_ids))))
    by_id = {row.id: row for row in rows}
    if len(by_id) != len(requested_ids):
        raise HTTPException(status_code=404, detail="One or more selected media items were not found")
    rows.sort(key=lambda row: _export_timestamp(row.observed_at or row.created_at))

    created_at = utcnow()
    manifest_items = []
    context_objects: dict[int, dict] = {}
    context_sessions: dict[int, dict] = {}
    context_evidence: dict[int, dict] = {}
    csv_rows = []
    sequences: dict[tuple[str, str, str], int] = {}
    files: list[tuple[Path, str]] = []

    for row in rows:
        metadata = attachment_metadata(row)
        moment = _export_timestamp(row.observed_at or row.created_at)
        media_type = metadata.get("media_type") or ("document" if row.attachment_type == "file" else row.attachment_type)
        object_row = db.get(SurveyorMapObject, row.map_object_id) if row.map_object_id else None
        session = db.get(SurveyorSearchSession, row.search_session_id) if row.search_session_id else None
        object_props = json.loads(object_row.properties_json or "{}") if object_row else {}
        camera = db.scalar(select(SurveyorTrailCamera).where(SurveyorTrailCamera.map_object_id == object_row.id)) if object_row else None
        if camera:
            context_name = camera.name
        elif object_row and object_row.name:
            context_name = object_row.name
        elif session:
            context_name = f"session-{session.id}"
        else:
            context_name = "field-media"
        timestamp_slug = moment.strftime("%Y-%m-%d_%H%M%S")
        extension = Path(metadata.get("original_filename") or row.storage_path or "media.bin").suffix.lower()
        if not re.fullmatch(r"\.[a-z0-9]{1,10}", extension):
            extension = ".bin"
        sequence_key = (timestamp_slug, _slug(context_name), media_type)
        sequences[sequence_key] = sequences.get(sequence_key, 0) + 1
        export_filename = f"{timestamp_slug}_{sequence_key[1]}_{media_type}_{sequences[sequence_key]:03d}{extension}"

        item = {
            "attachment_id": row.id,
            "export_filename": export_filename,
            "original_filename": metadata.get("original_filename") or Path(row.storage_path or "field-media").name,
            "media_type": media_type,
            "mime_type": metadata.get("mime_type", "application/octet-stream"),
            "file_size_bytes": metadata.get("file_size_bytes", 0),
            "observed_at": row.observed_at.isoformat() if row.observed_at else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "caption": row.caption,
            "notes": metadata.get("notes", ""),
            "source": row.source,
        }
        if metadata.get("duration_seconds") is not None:
            item["duration_seconds"] = metadata["duration_seconds"]
        if metadata.get("width") and metadata.get("height"):
            item["width"], item["height"] = metadata["width"], metadata["height"]
        if payload.include_exact_coordinates:
            if metadata.get("latitude") is not None and metadata.get("longitude") is not None:
                item["latitude"], item["longitude"] = metadata["latitude"], metadata["longitude"]
        if object_row:
            object_context = {"id": object_row.id, "type": object_row.object_type, "subtype": object_row.subtype,
                              "name": object_row.name}
            if payload.include_exact_coordinates and object_row.centroid_lat is not None and object_row.centroid_lon is not None:
                object_context["centroid"] = {"latitude": object_row.centroid_lat, "longitude": object_row.centroid_lon}
            item["map_object"] = object_context
            context_objects[object_row.id] = object_context
            if object_row.object_type == "evidence":
                evidence = {**object_context, "occurred_at": object_row.occurred_at.isoformat() if object_row.occurred_at else None,
                            "confidence": object_row.confidence, "epistemic_state": object_row.epistemic_state,
                            "notes": object_row.notes, "properties": {key: value for key, value in object_props.items()
                                if key not in {"contact_name", "contact_method", "contact_notes", "phone", "email"}}}
                context_evidence[object_row.id] = evidence
        if session:
            item["search_session"] = {"id": session.id, "method": session.method,
                                       "started_at": session.started_at.isoformat(),
                                       "ended_at": session.ended_at.isoformat() if session.ended_at else None}
            context_sessions[session.id] = item["search_session"]
        case_id = object_props.get("candidate_case_id")
        if case_id is not None:
            item["candidate_case_id"] = case_id
            candidate_case = db.get(CandidateCase, int(case_id))
            if candidate_case:
                item["candidate_case"] = {"id": candidate_case.id, "display_name": candidate_case.display_name,
                                           "holding_entity": candidate_case.holding_entity, "review_state": candidate_case.review_state}
        if camera:
            placements = list(db.scalars(select(SurveyorCameraPlacement).where(SurveyorCameraPlacement.camera_id == camera.id)
                .order_by(SurveyorCameraPlacement.installed_at.desc())))
            item["camera"] = {"id": camera.id, "name": camera.name, "placements": [
                {"id": place.id, "installed_at": place.installed_at.isoformat(),
                 "removed_at": place.removed_at.isoformat() if place.removed_at else None,
                 "heading_degrees": place.heading_degrees, "fov_degrees": place.fov_degrees,
                 "range_meters": place.range_meters} for place in placements]}
        manifest_items.append(item)
        csv_rows.append({
            "attachment_id": row.id, "export_filename": export_filename,
            "original_filename": item["original_filename"], "media_type": media_type, "mime_type": item["mime_type"],
            "observed_at": item["observed_at"] or item["created_at"], "caption": row.caption,
            "latitude": item.get("latitude"), "longitude": item.get("longitude"),
            "object_id": object_row.id if object_row else None,
            "object_type": object_row.object_type if object_row else None,
            "object_name": object_row.name if object_row else None,
            "session_id": session.id if session else None,
            "candidate_case_id": case_id,
            "evidence_resolution": object_props.get("resolution") if object_row and object_row.object_type == "evidence" else None,
        })
        if payload.include_originals:
            files.append((_attachment_original_path(row), f"media/{export_filename}"))

    export_name = f"archie-radar-export-{created_at.strftime('%Y-%m-%d')}"
    manifest = {"export_created_at": created_at.isoformat(), "file_count": len(rows), "originals_included": payload.include_originals,
                "items": manifest_items}
    descriptor, temp_name = tempfile.mkstemp(prefix="archie-radar-export-", suffix=".zip")
    os.close(descriptor)
    try:
        with zipfile.ZipFile(temp_name, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
            archive.writestr(f"{export_name}/README.txt",
                f"Archie Radar media export\nCreated: {created_at.isoformat()}\nFiles: {len(rows)}\n"
                f"Originals included: {'yes' if payload.include_originals else 'no'}\n"
                "manifest.json contains full media and field context.\nmanifest.csv is a flat review summary.\n")
            if payload.include_manifest_json:
                archive.writestr(f"{export_name}/manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
            if payload.include_manifest_csv:
                stream = io.StringIO(newline="")
                fields = ["attachment_id", "export_filename", "original_filename", "media_type", "mime_type", "observed_at",
                          "caption", "latitude", "longitude", "object_id", "object_type", "object_name", "session_id",
                          "candidate_case_id", "evidence_resolution"]
                writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
                writer.writeheader(); writer.writerows(csv_rows)
                archive.writestr(f"{export_name}/manifest.csv", stream.getvalue())
            if payload.include_context:
                archive.writestr(f"{export_name}/context/map_objects.json", json.dumps(list(context_objects.values()), indent=2))
                archive.writestr(f"{export_name}/context/sessions.json", json.dumps(list(context_sessions.values()), indent=2))
                archive.writestr(f"{export_name}/context/evidence.json", json.dumps(list(context_evidence.values()), indent=2))
            for source_path, archive_path in files:
                archive.write(source_path, f"{export_name}/{archive_path}")
    except Exception:
        Path(temp_name).unlink(missing_ok=True)
        raise
    return FileResponse(temp_name, media_type="application/zip", filename=f"{export_name}.zip",
                        background=BackgroundTask(_remove_temp_export, temp_name))


@app.get("/api/surveyor/links", response_model=list[SurveyorLinkOut])
def list_surveyor_links(db: Session = Depends(get_db)):
    return [_link_output(db, row) for row in db.scalars(select(SurveyorObjectLink).order_by(SurveyorObjectLink.created_at.desc()))]


@app.post("/api/surveyor/links", response_model=SurveyorLinkOut, status_code=201)
def create_surveyor_link(payload: SurveyorLinkIn, db: Session = Depends(get_db)):
    if payload.source_object_id == payload.target_object_id:
        raise HTTPException(status_code=422, detail="A link needs two different objects")
    source = db.get(SurveyorMapObject, payload.source_object_id)
    target = db.get(SurveyorMapObject, payload.target_object_id)
    if source is None or target is None:
        raise HTTPException(status_code=404, detail="Linked map object not found")
    coordinates = [[source.centroid_lon, source.centroid_lat], *payload.vertices, [target.centroid_lon, target.centroid_lat]]
    _geometry_stats({"type": "LineString", "coordinates": coordinates})
    row = SurveyorObjectLink(source_object_id=source.id, target_object_id=target.id, link_type=payload.link_type,
        line_style=payload.line_style, label=payload.label, notes=payload.notes,
        vertices_geojson=json.dumps(payload.vertices))
    db.add(row)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="This object link already exists") from exc
    _record_surveyor_event(db, "object_link_created", "object_link", row.id, f"Linked {source.name or source.object_type} to {target.name or target.object_type}",
        after={"source_object_id": source.id, "target_object_id": target.id, "link_type": row.link_type})
    db.commit(); db.refresh(row)
    return _link_output(db, row)


@app.patch("/api/surveyor/links/{link_id}", response_model=SurveyorLinkOut)
def update_surveyor_link(link_id: int, payload: SurveyorLinkPatch, db: Session = Depends(get_db)):
    row = db.get(SurveyorObjectLink, link_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Object link not found")
    before = _link_output(db, row).model_dump(mode="json")
    values = payload.model_dump(exclude_unset=True)
    if "vertices" in values:
        source = db.get(SurveyorMapObject, row.source_object_id); target = db.get(SurveyorMapObject, row.target_object_id)
        _geometry_stats({"type": "LineString", "coordinates": [[source.centroid_lon, source.centroid_lat], *values["vertices"], [target.centroid_lon, target.centroid_lat]]})
        row.vertices_geojson = json.dumps(values.pop("vertices"))
    for key, value in values.items():
        setattr(row, key, value)
    db.flush()
    _record_surveyor_event(db, "object_link_updated", "object_link", row.id, "Updated object link", before=before,
        after=_link_output(db, row).model_dump(mode="json"), reversible=True)
    db.commit(); db.refresh(row)
    return _link_output(db, row)


@app.delete("/api/surveyor/links/{link_id}", status_code=204)
def delete_surveyor_link(link_id: int, db: Session = Depends(get_db)):
    row = db.get(SurveyorObjectLink, link_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Object link not found")
    before = _link_output(db, row).model_dump(mode="json")
    _record_surveyor_event(db, "object_link_deleted", "object_link", row.id, "Deleted object link", before=before)
    db.delete(row); db.commit()
    return None


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
    query = select(SurveyorMapObject).where(or_(SurveyorMapObject.status.is_(None), SurveyorMapObject.status != "archived"))
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
    db.add(row); db.flush()
    _record_surveyor_event(db, "object_created", "map_object", row.id, f"Created {row.object_type}", after=_surveyor_out(row).model_dump(mode="json"), reversible=True)
    db.commit(); db.refresh(row)
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
    before = _surveyor_out(row).model_dump(mode="json")
    old_resolution = before.get("properties", {}).get("resolution")
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
    _record_surveyor_event(db, "object_updated", "map_object", row.id, f"Updated {row.object_type}", before=before,
        after=_surveyor_out(row).model_dump(mode="json"), reversible=True)
    if row.object_type == "zone" and row.subtype == "searched" and "properties" in values:
        old_searched_at = before.get("properties", {}).get("searched_at")
        new_searched_at = json.loads(row.properties_json).get("searched_at")
        if new_searched_at and new_searched_at != old_searched_at:
            _record_surveyor_event(db, "zone_researched", "map_object", row.id, "Searched area again",
                before={"searched_at": old_searched_at}, after={"searched_at": new_searched_at})
    if row.object_type == "evidence" and "properties" in values:
        new_resolution = json.loads(row.properties_json).get("resolution", "unresolved")
        if new_resolution != old_resolution:
            event_type = "evidence_reopened" if new_resolution == "unresolved" else "evidence_resolved"
            _record_surveyor_event(db, event_type, "map_object", row.id, f"Evidence {new_resolution.replace('_', ' ')}",
                before={"resolution": old_resolution or "unresolved"}, after={"resolution": new_resolution})
    db.commit(); db.refresh(row)
    return _surveyor_out(row)


@app.delete("/api/surveyor/objects/{object_id}", status_code=204)
def delete_surveyor_object(object_id: int, db: Session = Depends(get_db)):
    row = db.get(SurveyorMapObject, object_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Surveyor object not found")
    before = _surveyor_out(row).model_dump(mode="json")
    _record_surveyor_event(db, "object_deleted", "map_object", row.id, f"Deleted {row.object_type}", before=before)
    row.status = "archived"
    db.commit()
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
    limit: int = Query(100, ge=1, le=2000),
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


@app.get("/api/candidate-cases")
def list_candidate_cases(
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
    limit: int = Query(100, ge=1, le=2000),
    db: Session = Depends(get_db),
):
    """Return one row per animal case while matching filters against member records."""
    ensure_candidate_cases(db)
    profile = get_or_create_profile(db)
    cases = list(db.scalars(select(CandidateCase).where(
        CandidateCase.review_state == review_state if review_state else True
    )))
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=reported_within_days) if reported_within_days else None
    if not_before is not None:
        requested_cutoff = not_before if not_before.tzinfo else not_before.replace(tzinfo=timezone.utc)
        cutoff = max(cutoff, requested_cutoff) if cutoff else requested_cutoff

    results = []
    for case in cases:
        memberships = list(db.scalars(select(CandidateCasePost).where(CandidateCasePost.case_id == case.id)))
        members = []
        for membership in memberships:
            row = db.get(PetPost, membership.post_id)
            if not row:
                continue
            vision = db.scalar(select(PostVision).where(PostVision.post_id == row.id))
            output = post_output(row, vision, profile)
            if row.match_score < min_score:
                continue
            if source and row.source != source:
                continue
            if status and row.status != status:
                continue
            if sex and row.sex != sex:
                continue
            if cutoff and (row.reported_at or row.first_seen_at) < cutoff:
                continue
            if has_photo is True and (not output.get("image_url")):
                continue
            if has_photo is False and output.get("image_url"):
                continue
            if not include_duplicates and output.get("duplicate_of_post_id"):
                continue
            if max_distance_miles is not None and output.get("distance_from_home_miles") is not None and output["distance_from_home_miles"] > max_distance_miles:
                continue
            traits = output.get("parsed_traits") or {}
            if color and color not in (traits.get("colors") or []):
                continue
            if pattern and pattern not in (traits.get("patterns") or []):
                continue
            if coat and traits.get("coat") != coat:
                continue
            if collar and traits.get("collar") != collar:
                continue
            if microchip and traits.get("microchip") != microchip:
                continue
            if altered and traits.get("altered_status") != altered:
                continue
            if white_chest is not None and traits.get("white_chest") is not white_chest:
                continue
            if white_belly is not None and traits.get("white_belly") is not white_belly:
                continue
            if white_paws is not None and traits.get("white_paws") is not white_paws:
                continue
            if white_face is not None and traits.get("white_face") is not white_face:
                continue
            if age_compatible and (traits.get("age_years") is None or abs(float(traits["age_years"]) - float(ARCHIE_TRAITS["age_years"])) > 2.5):
                continue
            if archie_compatible and not is_archie_compatible(traits, row.sex):
                continue
            members.append((row, vision, output))
        if not members:
            continue
        result = case_output(db, case, profile)
        eligible_scores = [float(member[0].match_score or 0) for member in members]
        result["match_score"] = max(eligible_scores)
        results.append((result, members))

    if sort == "newest":
        results.sort(key=lambda item: max(((row.reported_at or row.first_seen_at) for row, _, _ in item[1]), default=datetime.min.replace(tzinfo=timezone.utc)), reverse=True)
    elif sort == "closest":
        results.sort(key=lambda item: (item[0].get("distance_from_home_miles") is None,
            item[0].get("distance_from_home_miles") if item[0].get("distance_from_home_miles") is not None else 9999))
    else:
        results.sort(key=lambda item: (item[0].get("match_score", 0), max((row.reported_at or row.first_seen_at for row, _, _ in item[1]), default=datetime.min.replace(tzinfo=timezone.utc))), reverse=True)
    return [result for result, _ in results[:limit]]


@app.patch("/api/candidate-cases/{case_id}/review")
def review_candidate_case(case_id: int, payload: ReviewIn, db: Session = Depends(get_db)):
    case = db.get(CandidateCase, case_id)
    if not case:
        raise HTTPException(404, "Candidate case not found")
    previous = case.review_state
    case.review_state = payload.review_state
    members = list(db.scalars(select(CandidateCasePost).where(CandidateCasePost.case_id == case.id)))
    for membership in members:
        post = db.get(PetPost, membership.post_id)
        if post:
            post.review_state = payload.review_state
    _record_surveyor_event(db, "candidate_reviewed", "candidate_case", case.id,
        f"Candidate case #{case.id} marked {payload.review_state}",
        before={"case_id": case.id, "review_state": previous}, after={"case_id": case.id, "review_state": payload.review_state})
    db.commit()
    return case_output(db, case)


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
    ensure_candidate_cases(db)
    cutoff = (not_before if not_before.tzinfo else not_before.replace(tzinfo=timezone.utc)) if not_before else None
    grouped = {state: 0 for state in ("new", "possible", "needs_review", "dismissed", "confirmed")}
    high_new = with_photo = 0
    for case in db.scalars(select(CandidateCase)):
        members = list(db.scalars(select(PetPost).join(CandidateCasePost, CandidateCasePost.post_id == PetPost.id)
                                   .where(CandidateCasePost.case_id == case.id)))
        recent = [row for row in members if not cutoff or (row.reported_at or row.first_seen_at) >= cutoff]
        if not recent:
            continue
        grouped[case.review_state] = grouped.get(case.review_state, 0) + 1
        if case.review_state == "new" and max((row.match_score for row in recent), default=0) >= 65:
            high_new += 1
        if case.review_state == "new" and any(row.image_url for row in recent):
            with_photo += 1
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
    previous_state = row.review_state
    row.review_state = payload.review_state
    membership = db.scalar(select(CandidateCasePost).where(CandidateCasePost.post_id == post_id))
    if membership:
        case = db.get(CandidateCase, membership.case_id)
        if case:
            case.review_state = payload.review_state
            for member in db.scalars(select(CandidateCasePost).where(CandidateCasePost.case_id == case.id)):
                related = db.get(PetPost, member.post_id)
                if related:
                    related.review_state = payload.review_state
    _record_surveyor_event(db, "candidate_reviewed", "candidate_post", post_id,
        f"Candidate #{post_id} marked {payload.review_state}",
        before={"candidate_id": post_id, "review_state": previous_state, "source": row.source},
        after={"candidate_id": post_id, "review_state": payload.review_state, "source": row.source})
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
