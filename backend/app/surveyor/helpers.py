import json

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models import SurveyorEvent, utcnow


def event(db: Session, event_type: str, entity_type: str, entity_id: int | str,
          action: str, before=None, after=None):
    db.add(SurveyorEvent(event_type=event_type, entity_type=entity_type, entity_id=str(entity_id),
        action=action, before_json=json.dumps(before, default=str) if before is not None else None,
        after_json=json.dumps(after, default=str) if after is not None else None, occurred_at=utcnow()))


def event_out(row):
    return {"id": row.id, "event_type": row.event_type, "entity_type": row.entity_type,
        "entity_id": row.entity_id, "action": row.action,
        "before": json.loads(row.before_json) if row.before_json else None,
        "after": json.loads(row.after_json) if row.after_json else None,
        "occurred_at": row.occurred_at, "created_at": row.created_at,
        "reversible": row.reversible, "notes": row.notes}


def object_out(row):
    return {"id": row.id, "object_type": row.object_type, "subtype": row.subtype, "name": row.name,
        "geometry": json.loads(row.geometry_geojson), "style": json.loads(row.style_json),
        "properties": json.loads(row.properties_json), "status": row.status,
        "confidence": row.confidence, "epistemic_state": row.epistemic_state,
        "occurred_at": row.occurred_at, "valid_from": row.valid_from, "valid_to": row.valid_to,
        "notes": row.notes, "created_at": row.created_at, "updated_at": row.updated_at}


def access_out(row, obj):
    geometry = json.loads(obj.geometry_geojson)
    return {"id": row.id, "map_object_id": row.map_object_id, "name": obj.name,
        "longitude": geometry["coordinates"][0], "latitude": geometry["coordinates"][1],
        "access_status": row.access_status, "dog_count": row.dog_count,
        "outdoor_cat_count": row.outdoor_cat_count, "camera_permission": row.camera_permission,
        "trap_permission": row.trap_permission, "search_permission": row.search_permission,
        "contact_name": row.contact_name, "contact_method": row.contact_method,
        "last_contact_at": row.last_contact_at, "next_followup_at": row.next_followup_at,
        "contact_notes": row.contact_notes, "created_at": row.created_at, "updated_at": row.updated_at}


def require_access(db, access_id):
    from ..models import SurveyorAccessRecord, SurveyorMapObject
    row = db.get(SurveyorAccessRecord, access_id)
    if row is None:
        raise HTTPException(404, "Access record not found")
    obj = db.get(SurveyorMapObject, row.map_object_id)
    if obj is None:
        raise HTTPException(404, "Access map object not found")
    return row, obj
