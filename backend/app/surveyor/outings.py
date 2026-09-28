import json
import math
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import (CandidateCase, CandidateIdentifier, SurveyorEvent, SurveyorMapObject,
    SurveyorOutingDependency, SurveyorOutingItem, SurveyorOutingPlan, SurveyorSearchSession,
    SurveyorTask, utcnow)
from .helpers import event

router = APIRouter(prefix="/api/surveyor/outings", tags=["surveyor-outings"])
Section = Literal["prep", "packing", "gameplan"]
ItemStatus = Literal["pending", "completed", "skipped"]
PlanStatus = Literal["draft", "active", "completed", "abandoned"]


class PlanIn(BaseModel):
    title: str = Field(default="Tonight's plan", min_length=1, max_length=180)
    objective: str = Field(default="", max_length=500)
    method: str = Field(default="walking", max_length=50)


class PlanPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, min_length=1, max_length=180)
    objective: str | None = Field(default=None, max_length=500)
    method: str | None = Field(default=None, max_length=50)


class ItemIn(BaseModel):
    section: Section
    title: str = Field(min_length=1, max_length=240)
    note: str = Field(default="", max_length=20000)
    position: int | None = Field(default=None, ge=0)
    required: bool = True
    map_object_id: int | None = None
    surveyor_task_id: int | None = None
    candidate_case_id: int | None = None
    time_hint: str | None = Field(default=None, max_length=40)
    depends_on_prep_ids: list[int] = Field(default_factory=list)


class ItemPatch(BaseModel):
    section: Section | None = None
    title: str | None = Field(default=None, min_length=1, max_length=240)
    note: str | None = Field(default=None, max_length=20000)
    position: int | None = Field(default=None, ge=0)
    required: bool | None = None
    status: ItemStatus | None = None
    map_object_id: int | None = None
    surveyor_task_id: int | None = None
    candidate_case_id: int | None = None
    time_hint: str | None = Field(default=None, max_length=40)


class DependenciesIn(BaseModel):
    prep_item_ids: list[int] = Field(default_factory=list, max_length=30)


class StartIn(BaseModel):
    method: str = Field(default="walking", max_length=50)
    start_with_blockers: bool = False


class PrepDependencyIn(BaseModel):
    title: str = Field(min_length=1, max_length=240)


class ReorderIn(BaseModel):
    section: Section
    ordered_item_ids: list[int]


def normalize_legacy_ready_statuses(db: Session) -> int:
    """Idempotently remove the old persisted readiness lifecycle value."""
    result = db.query(SurveyorOutingPlan).filter(SurveyorOutingPlan.status == "ready").update(
        {SurveyorOutingPlan.status: "draft"}, synchronize_session=False)
    if result:
        db.commit()
    return int(result or 0)


def _plan_or_404(db: Session, plan_id: int) -> SurveyorOutingPlan:
    plan = db.get(SurveyorOutingPlan, plan_id)
    if plan is None:
        raise HTTPException(404, "Outing plan not found")
    if plan.status == "ready":
        plan.status = "draft"
        db.flush()
    return plan


def _validate_refs(db: Session, values: dict) -> None:
    for key, model in (("map_object_id", SurveyorMapObject), ("surveyor_task_id", SurveyorTask), ("candidate_case_id", CandidateCase)):
        value = values.get(key)
        if value is not None and db.get(model, value) is None:
            raise HTTPException(422, f"Referenced {key} does not exist")


def _readiness(items: list[SurveyorOutingItem], dependencies: list[SurveyorOutingDependency] | None = None) -> dict:
    dependencies = dependencies or []
    by_id = {item.id: item for item in items}
    pending_prep = {item.id for item in items if item.section == "prep" and item.required and item.status == "pending"}
    pending_packing = sum(item.section == "packing" and item.required and item.status == "pending" for item in items)
    skipped_required = sum(item.required and item.status == "skipped" for item in items)
    waived = sum(1 for dep in dependencies if dep.prep_item_id in by_id and by_id[dep.prep_item_id].status == "skipped")
    pending_gameplan = [item for item in items if item.section == "gameplan" and item.status == "pending"]
    packed = sum(item.section == "packing" and item.status == "completed" for item in items)
    return {
        "ready_to_leave": not pending_prep and pending_packing == 0,
        "prep_remaining": len(pending_prep),
        "packing_remaining": pending_packing,
        # A shared setup task is one blocker even when several stops depend on it.
        "dependency_blockers": len({dep.prep_item_id for dep in dependencies if dep.prep_item_id in pending_prep}),
        "skipped_required": skipped_required,
        "waived_dependency_count": waived,
        "gameplan_total": sum(item.section == "gameplan" for item in items),
        "gameplan_remaining": len(pending_gameplan),
        "packed_items": packed,
        "blocking_prep_item_ids": sorted(pending_prep),
        # Temporary aliases keep old clients working while the UI migrates.
        "ready": not pending_prep and pending_packing == 0,
        "setup_blockers": len(pending_prep),
        "unpacked_items": pending_packing,
        "remaining_gameplan_items": len(pending_gameplan),
        "stop_count": sum(item.section == "gameplan" for item in items),
    }


def _context(db: Session, item: SurveyorOutingItem) -> dict | None:
    if item.map_object_id:
        obj = db.get(SurveyorMapObject, item.map_object_id)
        if obj:
            kind = "trail_camera" if obj.object_type == "trail_camera" else "map_object"
            prefix = "Trail camera" if kind == "trail_camera" else (obj.subtype or obj.object_type.replace("_", " ")).replace("_", " ").title()
            focus = _object_focus(obj)
            return {"kind": kind, "label": f"{prefix} · {obj.name}" if obj.name else prefix,
                "focusable": focus is not None, "focus_coordinates": focus}
    if item.surveyor_task_id:
        task = db.get(SurveyorTask, item.surveyor_task_id)
        if task:
            if task.map_object_id:
                obj = db.get(SurveyorMapObject, task.map_object_id)
                if obj:
                    focus = _object_focus(obj)
                    return {"kind": "task", "label": f"Follow-up · {obj.name or task.title}",
                        "focusable": focus is not None, "focus_coordinates": focus, "map_object_id": obj.id}
            return {"kind": "task", "label": f"Follow-up · {task.title}", "focusable": False}
    if item.candidate_case_id:
        case = db.get(CandidateCase, item.candidate_case_id)
        if case:
            identifier = db.scalar(select(CandidateIdentifier).where(
                CandidateIdentifier.case_id == case.id, CandidateIdentifier.is_identity_key.is_(True)
            ).order_by(CandidateIdentifier.id).limit(1))
            label = f"Candidate · {identifier.display_label} {identifier.value}" if identifier else "Candidate case"
            from ..candidates.identity import case_output
            projected = case_output(db, case)
            location = projected.get("current_location") or {}
            longitude, latitude = location.get("map_longitude"), location.get("map_latitude")
            focus = [float(longitude), float(latitude)] if _valid_lon_lat(longitude, latitude) else None
            return {"kind": "candidate", "label": label, "focusable": focus is not None,
                "focus_coordinates": focus, "location_text": location.get("location_text")}
    return None


def _valid_lon_lat(longitude, latitude) -> bool:
    try:
        return (longitude is not None and latitude is not None and
            math.isfinite(float(longitude)) and math.isfinite(float(latitude)) and
            -180 <= float(longitude) <= 180 and -90 <= float(latitude) <= 90)
    except (TypeError, ValueError):
        return False


def _geometry_focus(geometry: dict, centroid_lon=None, centroid_lat=None):
    if not isinstance(geometry, dict):
        return None
    if geometry.get("type") == "Point":
        coordinates = geometry.get("coordinates")
        if isinstance(coordinates, list) and len(coordinates) >= 2 and _valid_lon_lat(coordinates[0], coordinates[1]):
            return [float(coordinates[0]), float(coordinates[1])]
        return None
    if _valid_lon_lat(centroid_lon, centroid_lat):
        return [float(centroid_lon), float(centroid_lat)]
    return None


def _object_focus(obj: SurveyorMapObject):
    try:
        geometry = json.loads(obj.geometry_geojson)
    except (TypeError, ValueError):
        return None
    return _geometry_focus(geometry, obj.centroid_lon, obj.centroid_lat)


def output_plan(db: Session, plan: SurveyorOutingPlan) -> dict:
    items = list(db.scalars(select(SurveyorOutingItem).where(
        SurveyorOutingItem.plan_id == plan.id).order_by(SurveyorOutingItem.position, SurveyorOutingItem.id)))
    items.sort(key=lambda item: ({"prep": 0, "packing": 1, "gameplan": 2}[item.section], item.position, item.id))
    item_ids = [item.id for item in items]
    dependencies = list(db.scalars(select(SurveyorOutingDependency).where(
        SurveyorOutingDependency.dependent_item_id.in_(item_ids)))) if item_ids else []
    prep_by_id = {item.id: item for item in items if item.section == "prep"}
    dependents: dict[int, list[int]] = {}
    for dep in dependencies:
        if dep.prep_item_id in prep_by_id:
            dependents.setdefault(dep.dependent_item_id, []).append(dep.prep_item_id)
    item_data = [{"id": item.id, "plan_id": item.plan_id, "section": item.section,
        "title": item.title, "note": item.note, "position": item.position, "required": item.required,
        "status": item.status, "completed_at": item.completed_at, "map_object_id": item.map_object_id,
        "surveyor_task_id": item.surveyor_task_id, "candidate_case_id": item.candidate_case_id,
        "time_hint": item.time_hint, "depends_on_prep_ids": sorted(dependents.get(item.id, [])),
        "linked_context": _context(db, item), "created_at": item.created_at, "updated_at": item.updated_at} for item in items]
    return {"id": plan.id, "title": plan.title, "objective": plan.objective,
        "status": "draft" if plan.status == "ready" else plan.status, "method": plan.method,
        "search_session_id": plan.search_session_id, "created_at": plan.created_at,
        "updated_at": plan.updated_at, "completed_at": plan.completed_at,
        "items": item_data, "readiness": _readiness(items, dependencies)}


def _touch(plan: SurveyorOutingPlan) -> None:
    plan.updated_at = utcnow()


def _event_plan(db: Session, event_type: str, plan: SurveyorOutingPlan, action: str, before=None):
    event(db, event_type, "outing_plan", plan.id, action, before=before, after={"id": plan.id, "status": plan.status})


def _set_dependencies(db: Session, item: SurveyorOutingItem, prep_item_ids: list[int]) -> None:
    if item.section not in {"packing", "gameplan"} and prep_item_ids:
        raise HTTPException(422, "Only Packing and Gameplan items can depend on setup")
    if len(set(prep_item_ids)) != len(prep_item_ids):
        raise HTTPException(422, "Duplicate setup dependency")
    prep_items = []
    for prep_id in prep_item_ids:
        prep = db.get(SurveyorOutingItem, prep_id)
        if prep is None or prep.plan_id != item.plan_id or prep.section != "prep":
            raise HTTPException(422, "Dependencies must reference Prep / Setup items in the same outing")
        prep_items.append(prep)
    db.query(SurveyorOutingDependency).filter(SurveyorOutingDependency.dependent_item_id == item.id).delete(synchronize_session=False)
    for prep in prep_items:
        db.add(SurveyorOutingDependency(prep_item_id=prep.id, dependent_item_id=item.id))


@router.get("/current")
def current_outing(db: Session = Depends(get_db)):
    # An active field session's own plan always wins over a newer draft.
    active = db.scalar(select(SurveyorOutingPlan).join(SurveyorSearchSession,
        SurveyorOutingPlan.search_session_id == SurveyorSearchSession.id).where(
            SurveyorOutingPlan.status == "active", SurveyorSearchSession.ended_at.is_(None)
        ).order_by(SurveyorSearchSession.started_at.desc(), SurveyorOutingPlan.id.desc()).limit(1))
    plan = active or db.scalar(select(SurveyorOutingPlan).where(SurveyorOutingPlan.status == "draft")
        .order_by(SurveyorOutingPlan.updated_at.desc(), SurveyorOutingPlan.id.desc()).limit(1))
    return output_plan(db, plan) if plan else None


@router.get("/by-session/{session_id}")
def outing_by_session(session_id: int, db: Session = Depends(get_db)):
    plan = db.scalar(select(SurveyorOutingPlan).where(SurveyorOutingPlan.search_session_id == session_id))
    return output_plan(db, plan) if plan else None


@router.get("/last")
def last_outing(db: Session = Depends(get_db)):
    plan = db.scalar(select(SurveyorOutingPlan).where(SurveyorOutingPlan.status == "completed")
        .order_by(SurveyorOutingPlan.completed_at.desc(), SurveyorOutingPlan.id.desc()).limit(1))
    return output_plan(db, plan) if plan else None


@router.post("", status_code=201)
def create_outing(payload: PlanIn, db: Session = Depends(get_db)):
    plan = SurveyorOutingPlan(**payload.model_dump(), status="draft")
    db.add(plan); db.flush()
    _event_plan(db, "outing_created", plan, "Created outing plan")
    db.commit(); db.refresh(plan)
    return output_plan(db, plan)


def _clone_plan(db: Session, previous: SurveyorOutingPlan, items: list[SurveyorOutingItem], *, title: str | None = None) -> SurveyorOutingPlan:
    cloned = SurveyorOutingPlan(title=title or previous.title, objective=previous.objective, status="draft", method=previous.method)
    db.add(cloned); db.flush()
    id_map: dict[int, int] = {}
    selected_ids = {item.id for item in items}
    items = sorted(items, key=lambda row: ({"prep": 0, "packing": 1, "gameplan": 2}[row.section], row.position, row.id))
    positions: dict[str, int] = {"prep": 0, "packing": 0, "gameplan": 0}
    for old in items:
        refs = {"map_object_id": old.map_object_id, "surveyor_task_id": old.surveyor_task_id, "candidate_case_id": old.candidate_case_id}
        for key, model in (("map_object_id", SurveyorMapObject), ("surveyor_task_id", SurveyorTask), ("candidate_case_id", CandidateCase)):
            if refs[key] is not None and db.get(model, refs[key]) is None: refs[key] = None
        copy = SurveyorOutingItem(plan_id=cloned.id, section=old.section, title=old.title, note=old.note,
            position=positions[old.section], required=old.required, status="pending", **refs, time_hint=old.time_hint)
        positions[old.section] += 1
        db.add(copy); db.flush(); id_map[old.id] = copy.id
    deps = list(db.scalars(select(SurveyorOutingDependency).where(
        SurveyorOutingDependency.dependent_item_id.in_(selected_ids)))) if selected_ids else []
    for dep in deps:
        if dep.prep_item_id in id_map and dep.dependent_item_id in id_map:
            db.add(SurveyorOutingDependency(prep_item_id=id_map[dep.prep_item_id], dependent_item_id=id_map[dep.dependent_item_id]))
    return cloned


@router.post("/reuse-last", status_code=201)
def reuse_last_outing(db: Session = Depends(get_db)):
    previous = db.scalar(select(SurveyorOutingPlan).where(SurveyorOutingPlan.status == "completed")
        .order_by(SurveyorOutingPlan.completed_at.desc(), SurveyorOutingPlan.id.desc()).limit(1))
    if previous is None: raise HTTPException(404, "There is no completed outing to reuse")
    originals = list(db.scalars(select(SurveyorOutingItem).where(SurveyorOutingItem.plan_id == previous.id)))
    cloned = _clone_plan(db, previous, originals)
    _event_plan(db, "outing_reused", cloned, f"Reused outing #{previous.id}")
    db.commit(); db.refresh(cloned)
    return output_plan(db, cloned)


@router.post("/{plan_id}/continue-unfinished", status_code=201)
def continue_unfinished(plan_id: int, db: Session = Depends(get_db)):
    previous = _plan_or_404(db, plan_id)
    gameplan = list(db.scalars(select(SurveyorOutingItem).where(
        SurveyorOutingItem.plan_id == previous.id, SurveyorOutingItem.section == "gameplan",
        SurveyorOutingItem.status == "pending")))
    if not gameplan: raise HTTPException(409, "There are no unfinished Gameplan stops")
    game_ids = {item.id for item in gameplan}
    deps = list(db.scalars(select(SurveyorOutingDependency).where(SurveyorOutingDependency.dependent_item_id.in_(game_ids))))
    prep_ids = {dep.prep_item_id for dep in deps}
    prep_items = list(db.scalars(select(SurveyorOutingItem).where(
        SurveyorOutingItem.id.in_(prep_ids), SurveyorOutingItem.required.is_(True)))) if prep_ids else []
    new = _clone_plan(db, previous, [*prep_items, *gameplan], title=previous.title)
    _event_plan(db, "outing_continued", new, f"Continued unfinished work from outing #{previous.id}")
    db.commit(); db.refresh(new)
    return output_plan(db, new)


@router.patch("/{plan_id}")
def patch_outing(plan_id: int, payload: PlanPatch, db: Session = Depends(get_db)):
    plan = _plan_or_404(db, plan_id)
    changes = payload.model_dump(exclude_unset=True)
    for field in ("title", "objective", "method"):
        if field in changes and changes[field] is None: raise HTTPException(422, f"{field} cannot be null")
    for key, value in changes.items(): setattr(plan, key, value)
    _touch(plan); db.commit(); db.refresh(plan)
    return output_plan(db, plan)


@router.post("/{plan_id}/start", status_code=201)
def start_outing(plan_id: int, payload: StartIn, db: Session = Depends(get_db)):
    plan = _plan_or_404(db, plan_id)
    if plan.status in {"active", "completed", "abandoned"}: raise HTTPException(409, "This outing cannot be started")
    items = list(db.scalars(select(SurveyorOutingItem).where(SurveyorOutingItem.plan_id == plan.id)))
    deps = list(db.scalars(select(SurveyorOutingDependency).join(SurveyorOutingItem,
        SurveyorOutingDependency.dependent_item_id == SurveyorOutingItem.id).where(SurveyorOutingItem.plan_id == plan.id)))
    readiness = _readiness(items, deps)
    blockers = readiness["prep_remaining"] + readiness["packing_remaining"]
    if blockers and not payload.start_with_blockers:
        raise HTTPException(409, detail={"message": "Outing still has pending setup or packing blockers", "readiness": readiness})
    before = {"status": plan.status, "search_session_id": plan.search_session_id}
    session = SurveyorSearchSession(method=payload.method, started_at=utcnow())
    db.add(session); db.flush()
    plan.status = "active"; plan.method = payload.method; plan.search_session_id = session.id; _touch(plan)
    event(db, "search_started", "search_session", session.id, f"Started {session.method} search", after={"id": session.id, "method": session.method})
    event_type = "outing_started_with_blockers" if blockers else "outing_started"
    _event_plan(db, event_type, plan, "Started outing with setup blockers" if blockers else "Started outing", before=before)
    db.commit(); db.refresh(plan); db.refresh(session)
    return {"plan": output_plan(db, plan), "session": {"id": session.id, "method": session.method,
        "started_at": session.started_at, "ended_at": session.ended_at, "track_geojson": None,
        "distance_meters": session.distance_meters, "notes": session.notes, "result_summary": session.result_summary,
        "created_at": session.created_at}}


@router.post("/{plan_id}/complete")
def complete_outing(plan_id: int, db: Session = Depends(get_db)):
    plan = _plan_or_404(db, plan_id)
    if plan.status == "completed": return output_plan(db, plan)
    if plan.status == "active" and plan.search_session_id:
        session = db.get(SurveyorSearchSession, plan.search_session_id)
        if session and session.ended_at is None:
            raise HTTPException(409, "End the linked search session before completing this outing")
    before = {"status": plan.status, "search_session_id": plan.search_session_id}
    plan.status = "completed"; plan.completed_at = utcnow(); _touch(plan)
    _event_plan(db, "outing_completed", plan, "Completed outing", before=before)
    db.commit(); db.refresh(plan)
    return output_plan(db, plan)


@router.post("/{plan_id}/abandon")
def abandon_outing(plan_id: int, db: Session = Depends(get_db)):
    plan = _plan_or_404(db, plan_id)
    if plan.status == "active":
        raise HTTPException(409, "End the linked search session before abandoning this outing")
    if plan.status in {"completed", "abandoned"}:
        return output_plan(db, plan)
    before = {"status": plan.status}
    plan.status = "abandoned"; _touch(plan)
    _event_plan(db, "outing_abandoned", plan, "Abandoned outing plan", before=before)
    db.commit(); db.refresh(plan)
    return output_plan(db, plan)


@router.post("/{plan_id}/items", status_code=201)
def create_item(plan_id: int, payload: ItemIn, db: Session = Depends(get_db)):
    plan = _plan_or_404(db, plan_id)
    values = payload.model_dump(exclude={"depends_on_prep_ids"}); _validate_refs(db, values)
    position = values.pop("position")
    if position is None:
        position = int(db.scalar(select(func.coalesce(func.max(SurveyorOutingItem.position), -1)).where(
            SurveyorOutingItem.plan_id == plan.id, SurveyorOutingItem.section == payload.section))) + 1
    item = SurveyorOutingItem(plan_id=plan.id, position=position, **values)
    db.add(item); db.flush()
    if payload.depends_on_prep_ids: _set_dependencies(db, item, payload.depends_on_prep_ids)
    _touch(plan); event(db, "outing_item_added", "outing_item", item.id, f"Added {item.section} item", after={"title": item.title, "section": item.section})
    db.commit(); db.refresh(plan)
    return output_plan(db, plan)


def _item_or_404(db: Session, item_id: int) -> SurveyorOutingItem:
    item = db.get(SurveyorOutingItem, item_id)
    if item is None: raise HTTPException(404, "Outing item not found")
    return item


@router.patch("/items/{item_id}")
def patch_item(item_id: int, payload: ItemPatch, db: Session = Depends(get_db)):
    item = _item_or_404(db, item_id); plan = _plan_or_404(db, item.plan_id)
    changes = payload.model_dump(exclude_unset=True)
    for field in ("section", "title", "required", "status", "position"):
        if field in changes and changes[field] is None: raise HTTPException(422, f"{field} cannot be null")
    old_status = item.status
    if "section" in changes and changes["section"] != item.section:
        if db.scalar(select(SurveyorOutingDependency.id).where(
            (SurveyorOutingDependency.prep_item_id == item.id) | (SurveyorOutingDependency.dependent_item_id == item.id))):
            raise HTTPException(409, "Remove setup dependencies before moving this item")
    _validate_refs(db, changes)
    for key, value in changes.items(): setattr(item, key, value)
    now = utcnow()
    if changes.get("status") == "completed": item.completed_at = now
    elif changes.get("status") in {"pending", "skipped"}: item.completed_at = None
    if item.section == "gameplan" and item.surveyor_task_id and item.status == "completed" and old_status != "completed":
        task = db.get(SurveyorTask, item.surveyor_task_id)
        if task and task.status == "open":
            task.status = "completed"; task.completed_at = now; task.updated_at = now
            event(db, "task_completed", "task", task.id, "Completed field follow-up from outing Gameplan", after={"status": task.status, "completed_at": now.isoformat()})
    _touch(plan)
    if changes.get("status") == "completed" and old_status != "completed":
        event(db, "outing_item_completed", "outing_item", item.id, "Completed outing item", after={"title": item.title})
    elif changes.get("status") == "skipped" and old_status != "skipped":
        event(db, "outing_item_skipped", "outing_item", item.id, "Skipped outing item", after={"title": item.title})
    db.commit(); db.refresh(plan)
    return output_plan(db, plan)


@router.put("/items/{item_id}/dependencies")
def set_item_dependencies(item_id: int, payload: DependenciesIn, db: Session = Depends(get_db)):
    item = _item_or_404(db, item_id); plan = _plan_or_404(db, item.plan_id)
    before = set(db.scalars(select(SurveyorOutingDependency.prep_item_id).where(SurveyorOutingDependency.dependent_item_id == item.id)))
    _set_dependencies(db, item, payload.prep_item_ids); _touch(plan)
    if set(payload.prep_item_ids) - before: event(db, "outing_dependency_added", "outing_item", item.id, "Added setup dependency")
    db.commit(); db.refresh(plan)
    return output_plan(db, plan)


@router.post("/items/{dependent_item_id}/create-prep-dependency", status_code=201)
def create_prep_dependency(dependent_item_id: int, payload: PrepDependencyIn, db: Session = Depends(get_db)):
    dependent = _item_or_404(db, dependent_item_id); plan = _plan_or_404(db, dependent.plan_id)
    if dependent.section not in {"packing", "gameplan"}: raise HTTPException(422, "Only Packing and Gameplan items can have setup dependencies")
    position = int(db.scalar(select(func.coalesce(func.max(SurveyorOutingItem.position), -1)).where(
        SurveyorOutingItem.plan_id == plan.id, SurveyorOutingItem.section == "prep"))) + 1
    prep = SurveyorOutingItem(plan_id=plan.id, section="prep", title=payload.title, position=position, required=True, status="pending")
    db.add(prep); db.flush(); db.add(SurveyorOutingDependency(prep_item_id=prep.id, dependent_item_id=dependent.id))
    _touch(plan); event(db, "outing_item_added", "outing_item", prep.id, "Added and linked setup item", after={"title": prep.title, "dependent_item_id": dependent.id})
    event(db, "outing_dependency_added", "outing_item", dependent.id, "Added setup dependency", after={"prep_item_id": prep.id})
    db.commit(); db.refresh(plan)
    return output_plan(db, plan)


@router.post("/{plan_id}/reorder")
def reorder_items(plan_id: int, payload: ReorderIn, db: Session = Depends(get_db)):
    plan = _plan_or_404(db, plan_id)
    rows = list(db.scalars(select(SurveyorOutingItem).where(
        SurveyorOutingItem.plan_id == plan.id, SurveyorOutingItem.section == payload.section).order_by(SurveyorOutingItem.position, SurveyorOutingItem.id)))
    ids = [row.id for row in rows]
    if len(set(payload.ordered_item_ids)) != len(payload.ordered_item_ids) or set(payload.ordered_item_ids) != set(ids):
        raise HTTPException(422, "Reorder must include each item in the section exactly once")
    by_id = {row.id: row for row in rows}
    for index, item_id in enumerate(payload.ordered_item_ids): by_id[item_id].position = index
    _touch(plan); db.commit(); db.refresh(plan)
    return output_plan(db, plan)


@router.delete("/items/{item_id}")
def delete_item(item_id: int, db: Session = Depends(get_db)):
    item = _item_or_404(db, item_id); plan = _plan_or_404(db, item.plan_id)
    before = {"title": item.title, "section": item.section}
    db.query(SurveyorOutingDependency).filter((SurveyorOutingDependency.prep_item_id == item.id) |
        (SurveyorOutingDependency.dependent_item_id == item.id)).delete(synchronize_session=False)
    db.delete(item); db.flush(); _touch(plan)
    event(db, "outing_item_removed", "outing_item", item_id, "Removed outing item", before=before)
    db.commit(); db.refresh(plan)
    return output_plan(db, plan)
