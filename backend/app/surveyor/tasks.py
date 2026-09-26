from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import PetPost, SurveyorMapObject, SurveyorSearchSession, SurveyorTask
from ..schemas import SurveyorTaskIn, SurveyorTaskPatch
from .helpers import event

router = APIRouter(prefix="/api/surveyor/tasks", tags=["surveyor-tasks"])


def output(row):
    return {"id": row.id, "title": row.title, "task_type": row.task_type, "status": row.status,
        "priority": row.priority, "due_at": row.due_at, "map_object_id": row.map_object_id,
        "search_session_id": row.search_session_id, "candidate_post_id": row.candidate_post_id,
        "notes": row.notes, "created_at": row.created_at, "completed_at": row.completed_at,
        "updated_at": row.updated_at}


def validate_refs(db, values):
    for field, model in (("map_object_id", SurveyorMapObject), ("search_session_id", SurveyorSearchSession), ("candidate_post_id", PetPost)):
        if values.get(field) is not None and db.get(model, values[field]) is None:
            raise HTTPException(422, f"Referenced {field} does not exist")


@router.get("")
def list_tasks(status: str | None = None, task_type: str | None = None,
               due_before: datetime | None = None, due_after: datetime | None = None,
               map_object_id: int | None = None, db: Session = Depends(get_db)):
    query = select(SurveyorTask)
    if status: query = query.where(SurveyorTask.status == status)
    if task_type: query = query.where(SurveyorTask.task_type == task_type)
    if due_before: query = query.where(SurveyorTask.due_at <= due_before)
    if due_after: query = query.where(SurveyorTask.due_at >= due_after)
    if map_object_id: query = query.where(SurveyorTask.map_object_id == map_object_id)
    return [output(row) for row in db.scalars(query.order_by(SurveyorTask.due_at.asc().nullslast(), SurveyorTask.created_at.desc()))]


@router.post("", status_code=201)
def create_task(payload: SurveyorTaskIn, db: Session = Depends(get_db)):
    values = payload.model_dump()
    validate_refs(db, values)
    row = SurveyorTask(**values)
    db.add(row); db.flush()
    event(db, "task_created", "task", row.id, "Created field follow-up", after=output(row))
    db.commit(); db.refresh(row)
    return output(row)


@router.patch("/{task_id}")
def patch_task(task_id: int, payload: SurveyorTaskPatch, db: Session = Depends(get_db)):
    row = db.get(SurveyorTask, task_id)
    if row is None: raise HTTPException(404, "Follow-up task not found")
    changes = payload.model_dump(exclude_unset=True)
    validate_refs(db, changes)
    before = output(row)
    old_status = row.status
    for key, value in changes.items(): setattr(row, key, value)
    if changes.get("status") == "completed": row.completed_at = datetime.now(timezone.utc)
    elif changes.get("status") == "open": row.completed_at = None
    new_status = row.status
    event_type = "task_completed" if new_status == "completed" and old_status != new_status else "task_reopened" if new_status == "open" and old_status != new_status else "task_dismissed" if new_status == "dismissed" and old_status != new_status else "task_updated"
    event(db, event_type, "task", row.id, event_type.replace("_", " ").capitalize(), before=before, after=output(row))
    db.commit(); db.refresh(row)
    return output(row)


@router.delete("/{task_id}")
def dismiss_task(task_id: int, db: Session = Depends(get_db)):
    row = db.get(SurveyorTask, task_id)
    if row is None: raise HTTPException(404, "Follow-up task not found")
    before = output(row); row.status = "dismissed"
    event(db, "task_dismissed", "task", row.id, "Dismissed field follow-up", before=before, after=output(row))
    db.commit(); db.refresh(row)
    return output(row)
