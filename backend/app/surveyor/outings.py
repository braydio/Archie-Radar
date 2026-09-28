from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import (CandidateCase, SurveyorMapObject, SurveyorOutingDependency,
    SurveyorOutingItem, SurveyorOutingPlan, SurveyorSearchSession, SurveyorTask)

router = APIRouter(prefix="/api/surveyor/outings", tags=["surveyor-outings"])
Section = Literal["prep", "packing", "gameplan"]
ItemStatus = Literal["pending", "completed", "skipped"]
PlanStatus = Literal["draft", "ready", "active", "completed", "abandoned"]


class PlanIn(BaseModel):
    title: str = Field(default="Tonight's plan", min_length=1, max_length=180)
    objective: str = Field(default="", max_length=500)
    method: str = Field(default="walking", max_length=50)


class PlanPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=180)
    objective: str | None = Field(default=None, max_length=500)
    method: str | None = Field(default=None, max_length=50)
    status: PlanStatus | None = None
    search_session_id: int | None = None


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


def _plan_or_404(db: Session, plan_id: int) -> SurveyorOutingPlan:
    plan = db.get(SurveyorOutingPlan, plan_id)
    if plan is None:
        raise HTTPException(404, "Outing plan not found")
    return plan


def _validate_refs(db: Session, values: dict) -> None:
    for key, model in (("map_object_id", SurveyorMapObject), ("surveyor_task_id", SurveyorTask), ("candidate_case_id", CandidateCase)):
        value = values.get(key)
        if value is not None and db.get(model, value) is None:
            raise HTTPException(422, f"Referenced {key} does not exist")


def _readiness(items: list[SurveyorOutingItem]) -> dict:
    remaining = [item for item in items if item.required and item.status != "completed"]
    prep = sum(item.section == "prep" for item in remaining)
    packing = sum(item.section == "packing" for item in remaining)
    gameplan = [item for item in items if item.section == "gameplan" and item.status == "pending"]
    packed = sum(item.section == "packing" and item.status == "completed" for item in items)
    ready = prep == 0 and packing == 0
    return {"ready": ready, "setup_blockers": prep, "unpacked_items": packing,
        "remaining_gameplan_items": len(gameplan), "packed_items": packed,
        "stop_count": len(gameplan)}


def output_plan(db: Session, plan: SurveyorOutingPlan) -> dict:
    items = list(db.scalars(select(SurveyorOutingItem).where(
        SurveyorOutingItem.plan_id == plan.id).order_by(SurveyorOutingItem.position, SurveyorOutingItem.id)))
    section_order = {"prep": 0, "packing": 1, "gameplan": 2}
    items.sort(key=lambda item: (section_order[item.section], item.position, item.id))
    item_ids = [item.id for item in items]
    dependencies = list(db.scalars(select(SurveyorOutingDependency).where(
        SurveyorOutingDependency.dependent_item_id.in_(item_ids)))) if item_ids else []
    prep_by_id = {item.id: item for item in items if item.section == "prep"}
    dependents: dict[int, list[int]] = {}
    for dependency in dependencies:
        if dependency.prep_item_id in prep_by_id:
            dependents.setdefault(dependency.dependent_item_id, []).append(dependency.prep_item_id)
    item_data = [{"id": item.id, "plan_id": item.plan_id, "section": item.section,
        "title": item.title, "note": item.note, "position": item.position, "required": item.required,
        "status": item.status, "completed_at": item.completed_at, "map_object_id": item.map_object_id,
        "surveyor_task_id": item.surveyor_task_id, "candidate_case_id": item.candidate_case_id,
        "time_hint": item.time_hint, "depends_on_prep_ids": sorted(dependents.get(item.id, [])),
        "created_at": item.created_at, "updated_at": item.updated_at} for item in items]
    return {"id": plan.id, "title": plan.title, "objective": plan.objective,
        "status": plan.status, "method": plan.method, "search_session_id": plan.search_session_id,
        "created_at": plan.created_at, "updated_at": plan.updated_at, "completed_at": plan.completed_at,
        "items": item_data, "readiness": _readiness(items)}


def _refresh_readiness_status(db: Session, plan: SurveyorOutingPlan) -> None:
    if plan.status in {"active", "completed", "abandoned"}:
        return
    items = list(db.scalars(select(SurveyorOutingItem).where(SurveyorOutingItem.plan_id == plan.id)))
    plan.status = "ready" if _readiness(items)["ready"] else "draft"


@router.get("/current")
def current_outing(db: Session = Depends(get_db)):
    plan = db.scalar(select(SurveyorOutingPlan).where(
        SurveyorOutingPlan.status.in_(["draft", "ready", "active"])
    ).order_by(SurveyorOutingPlan.updated_at.desc(), SurveyorOutingPlan.id.desc()).limit(1))
    return output_plan(db, plan) if plan else None


@router.get("/last")
def last_outing(db: Session = Depends(get_db)):
    plan = db.scalar(select(SurveyorOutingPlan).where(
        SurveyorOutingPlan.status != "abandoned"
    ).order_by(SurveyorOutingPlan.created_at.desc(), SurveyorOutingPlan.id.desc()).limit(1))
    return output_plan(db, plan) if plan else None


@router.post("", status_code=201)
def create_outing(payload: PlanIn, db: Session = Depends(get_db)):
    plan = SurveyorOutingPlan(**payload.model_dump())
    db.add(plan); db.commit(); db.refresh(plan)
    return output_plan(db, plan)


@router.post("/reuse-last", status_code=201)
def reuse_last_outing(db: Session = Depends(get_db)):
    previous = db.scalar(select(SurveyorOutingPlan).where(
        SurveyorOutingPlan.status != "abandoned"
    ).order_by(SurveyorOutingPlan.created_at.desc(), SurveyorOutingPlan.id.desc()).limit(1))
    if previous is None:
        raise HTTPException(404, "There is no previous outing to reuse")
    cloned = SurveyorOutingPlan(title=previous.title, objective=previous.objective,
        status="draft", method=previous.method)
    db.add(cloned); db.flush()
    originals = list(db.scalars(select(SurveyorOutingItem).where(
        SurveyorOutingItem.plan_id == previous.id).order_by(SurveyorOutingItem.position, SurveyorOutingItem.id)))
    originals.sort(key=lambda item: ({"prep": 0, "packing": 1, "gameplan": 2}[item.section], item.position, item.id))
    id_map: dict[int, int] = {}
    for item in originals:
        copy = SurveyorOutingItem(plan_id=cloned.id, section=item.section, title=item.title, note=item.note,
            position=item.position, required=item.required, status="pending", map_object_id=item.map_object_id,
            surveyor_task_id=item.surveyor_task_id, candidate_case_id=item.candidate_case_id, time_hint=item.time_hint)
        db.add(copy); db.flush(); id_map[item.id] = copy.id
    old_ids = list(id_map)
    if old_ids:
        old_deps = db.scalars(select(SurveyorOutingDependency).where(SurveyorOutingDependency.dependent_item_id.in_(old_ids)))
        for dependency in old_deps:
            if dependency.prep_item_id in id_map and dependency.dependent_item_id in id_map:
                db.add(SurveyorOutingDependency(prep_item_id=id_map[dependency.prep_item_id],
                    dependent_item_id=id_map[dependency.dependent_item_id]))
    _refresh_readiness_status(db, cloned)
    db.commit(); db.refresh(cloned)
    return output_plan(db, cloned)


@router.patch("/{plan_id}")
def patch_outing(plan_id: int, payload: PlanPatch, db: Session = Depends(get_db)):
    plan = _plan_or_404(db, plan_id)
    changes = payload.model_dump(exclude_unset=True)
    for field in ("title", "objective", "method", "status"):
        if field in changes and changes[field] is None:
            raise HTTPException(422, f"{field} cannot be null")
    if changes.get("search_session_id") is not None and db.get(SurveyorSearchSession, changes["search_session_id"]) is None:
        raise HTTPException(422, "Search session does not exist")
    for key, value in changes.items():
        setattr(plan, key, value)
    if changes.get("status") == "completed":
        plan.completed_at = datetime.now(timezone.utc)
    elif changes.get("status") in {"draft", "ready", "active"}:
        plan.completed_at = None
    db.commit(); db.refresh(plan)
    return output_plan(db, plan)


@router.post("/{plan_id}/items", status_code=201)
def create_item(plan_id: int, payload: ItemIn, db: Session = Depends(get_db)):
    plan = _plan_or_404(db, plan_id)
    values = payload.model_dump(exclude={"depends_on_prep_ids"})
    _validate_refs(db, values)
    position = values.pop("position")
    if position is None:
        position = int(db.scalar(select(func.coalesce(func.max(SurveyorOutingItem.position), -1)).where(
            SurveyorOutingItem.plan_id == plan.id, SurveyorOutingItem.section == payload.section))) + 1
    item = SurveyorOutingItem(plan_id=plan.id, position=position, **values)
    db.add(item); db.flush()
    if payload.depends_on_prep_ids:
        _set_dependencies(db, item, payload.depends_on_prep_ids)
    _refresh_readiness_status(db, plan)
    db.commit(); db.refresh(item)
    return output_plan(db, plan)


def _item_or_404(db: Session, item_id: int) -> SurveyorOutingItem:
    item = db.get(SurveyorOutingItem, item_id)
    if item is None:
        raise HTTPException(404, "Outing item not found")
    return item


@router.patch("/items/{item_id}")
def patch_item(item_id: int, payload: ItemPatch, db: Session = Depends(get_db)):
    item = _item_or_404(db, item_id)
    plan = _plan_or_404(db, item.plan_id)
    changes = payload.model_dump(exclude_unset=True)
    for field in ("section", "title", "required", "status", "position"):
        if field in changes and changes[field] is None:
            raise HTTPException(422, f"{field} cannot be null")
    if "section" in changes and changes["section"] != item.section:
        if item.section == "prep" and db.scalar(select(SurveyorOutingDependency.id).where(
                SurveyorOutingDependency.prep_item_id == item.id)) is not None:
            raise HTTPException(409, "Remove setup dependencies before moving this item")
        if changes["section"] == "prep" and db.scalar(select(SurveyorOutingDependency.id).where(
                SurveyorOutingDependency.dependent_item_id == item.id)) is not None:
            raise HTTPException(422, "A dependent item cannot be moved into Prep / Setup")
    _validate_refs(db, changes)
    for key, value in changes.items():
        setattr(item, key, value)
    if changes.get("status") == "completed":
        item.completed_at = datetime.now(timezone.utc)
    elif changes.get("status") in {"pending", "skipped"}:
        item.completed_at = None
    plan.updated_at = datetime.now(timezone.utc)
    _refresh_readiness_status(db, plan)
    db.commit(); db.refresh(item)
    result = output_plan(db, plan)
    return next(row for row in result["items"] if row["id"] == item.id)


def _set_dependencies(db: Session, item: SurveyorOutingItem, prep_item_ids: list[int]) -> None:
    if item.section == "prep" and prep_item_ids:
        raise HTTPException(422, "Prep / Setup items cannot depend on other items")
    prep_items = []
    for prep_id in set(prep_item_ids):
        prep = db.get(SurveyorOutingItem, prep_id)
        if prep is None or prep.plan_id != item.plan_id or prep.section != "prep":
            raise HTTPException(422, "Dependencies must reference Prep / Setup items in the same outing")
        prep_items.append(prep)
    db.query(SurveyorOutingDependency).filter(
        SurveyorOutingDependency.dependent_item_id == item.id).delete(synchronize_session=False)
    for prep in prep_items:
        db.add(SurveyorOutingDependency(prep_item_id=prep.id, dependent_item_id=item.id))


@router.put("/items/{item_id}/dependencies")
def set_item_dependencies(item_id: int, payload: DependenciesIn, db: Session = Depends(get_db)):
    item = _item_or_404(db, item_id)
    plan = _plan_or_404(db, item.plan_id)
    _set_dependencies(db, item, payload.prep_item_ids)
    plan.updated_at = datetime.now(timezone.utc)
    db.commit()
    return output_plan(db, plan)


@router.delete("/items/{item_id}", status_code=204)
def delete_item(item_id: int, db: Session = Depends(get_db)):
    item = _item_or_404(db, item_id)
    plan = _plan_or_404(db, item.plan_id)
    db.query(SurveyorOutingDependency).filter(
        (SurveyorOutingDependency.prep_item_id == item.id) |
        (SurveyorOutingDependency.dependent_item_id == item.id)
    ).delete(synchronize_session=False)
    db.delete(item); db.flush()
    _refresh_readiness_status(db, plan)
    db.commit()
