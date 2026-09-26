import json

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import SurveyorAccessRecord, SurveyorMapObject
from ..schemas import SurveyorAccessIn, SurveyorAccessPatch
from .helpers import access_out, event, require_access

router = APIRouter(prefix="/api/surveyor/access", tags=["surveyor-access"])


@router.get("")
def list_access(db: Session = Depends(get_db)):
    rows = db.execute(select(SurveyorAccessRecord, SurveyorMapObject)
        .join(SurveyorMapObject, SurveyorMapObject.id == SurveyorAccessRecord.map_object_id)
        .where(SurveyorMapObject.status != "archived")).all()
    return [access_out(row, obj) for row, obj in rows]


@router.post("", status_code=201)
def create_access(payload: SurveyorAccessIn, db: Session = Depends(get_db)):
    values = payload.model_dump()
    name = values.pop("name")
    longitude = values.pop("longitude"); latitude = values.pop("latitude")
    status = values["access_status"]
    obj = SurveyorMapObject(object_type="access", subtype=status, status=status, name=name,
        geometry_geojson=json.dumps({"type": "Point", "coordinates": [longitude, latitude]}),
        style_json="{}", properties_json="{}", epistemic_state="observed", confidence="context",
        centroid_lat=latitude, centroid_lon=longitude, bbox_west=longitude, bbox_east=longitude,
        bbox_south=latitude, bbox_north=latitude)
    db.add(obj); db.flush()
    row = SurveyorAccessRecord(map_object_id=obj.id, **values)
    db.add(row); db.flush()
    event(db, "access_created", "map_object", obj.id, "Created property access record", after={"access_status": status, "name": name})
    db.commit(); db.refresh(row); db.refresh(obj)
    return access_out(row, obj)


@router.get("/{access_id}")
def get_access(access_id: int, db: Session = Depends(get_db)):
    row, obj = require_access(db, access_id)
    return access_out(row, obj)


@router.patch("/{access_id}")
def patch_access(access_id: int, payload: SurveyorAccessPatch, db: Session = Depends(get_db)):
    row, obj = require_access(db, access_id)
    changes = payload.model_dump(exclude_unset=True)
    before = {key: getattr(row, key) for key in changes if hasattr(row, key)}
    for key, value in changes.items():
        if key in {"name", "longitude", "latitude"}:
            continue
        setattr(row, key, value)
    if "name" in changes: obj.name = changes["name"]
    geometry = json.loads(obj.geometry_geojson)
    coordinates = geometry["coordinates"]
    if "longitude" in changes: coordinates[0] = changes["longitude"]
    if "latitude" in changes: coordinates[1] = changes["latitude"]
    if "longitude" in changes or "latitude" in changes:
        lon, lat = coordinates
        obj.geometry_geojson = json.dumps(geometry)
        obj.centroid_lat = obj.bbox_south = obj.bbox_north = lat
        obj.centroid_lon = obj.bbox_west = obj.bbox_east = lon
    if "access_status" in changes:
        obj.subtype = changes["access_status"]; obj.status = changes["access_status"]
    event(db, "access_updated", "map_object", obj.id, "Updated property access record", before=before,
        after={key: value for key, value in changes.items()})
    db.commit(); db.refresh(row); db.refresh(obj)
    return access_out(row, obj)


@router.delete("/{access_id}", status_code=204)
def delete_access(access_id: int, db: Session = Depends(get_db)):
    row, obj = require_access(db, access_id)
    obj.status = "archived"
    event(db, "access_archived", "map_object", obj.id, "Archived property access record",
        before={"access_status": row.access_status})
    db.commit()
    return Response(status_code=204)
