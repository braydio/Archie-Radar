from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import CandidateCase, CandidateCaseNote, SurveyorEvent
from .identity import case_output

router = APIRouter(prefix="/api/candidate-cases", tags=["candidate-cases"])


class CandidateCaseNoteIn(BaseModel):
    body: str = Field(min_length=1, max_length=10000)


def _case_or_404(db: Session, case_id: int) -> CandidateCase:
    case = db.get(CandidateCase, case_id)
    if not case:
        raise HTTPException(404, "Candidate case not found")
    return case


def _sort_time(item: dict) -> float:
    value = item.get("occurred_at")
    if value is None:
        return 0.0
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.timestamp()


@router.get("/{case_id}")
def get_candidate_case(case_id: int, db: Session = Depends(get_db)):
    case = _case_or_404(db, case_id)
    return case_output(db, case)


@router.get("/{case_id}/notes")
def list_candidate_case_notes(case_id: int, db: Session = Depends(get_db)):
    _case_or_404(db, case_id)
    rows = db.scalars(select(CandidateCaseNote).where(CandidateCaseNote.case_id == case_id)
                      .order_by(CandidateCaseNote.created_at.desc(), CandidateCaseNote.id.desc()))
    return [{"id": row.id, "case_id": row.case_id, "body": row.body, "created_at": row.created_at} for row in rows]


@router.post("/{case_id}/notes", status_code=201)
def create_candidate_case_note(case_id: int, payload: CandidateCaseNoteIn, db: Session = Depends(get_db)):
    _case_or_404(db, case_id)
    note = CandidateCaseNote(case_id=case_id, body=payload.body.strip())
    if not note.body:
        raise HTTPException(422, "Note cannot be blank")
    db.add(note)
    db.flush()
    db.add(SurveyorEvent(event_type="candidate_case_note_added", entity_type="candidate_case",
        entity_id=str(case_id), action="Case note added", occurred_at=datetime.now(timezone.utc),
        after_json=f'{{"note_id": {note.id}}}'))
    db.commit()
    db.refresh(note)
    return {"id": note.id, "case_id": note.case_id, "body": note.body, "created_at": note.created_at}


@router.get("/{case_id}/timeline")
def candidate_case_timeline(case_id: int, db: Session = Depends(get_db)):
    case = _case_or_404(db, case_id)
    events = list(db.scalars(select(SurveyorEvent).where(
        SurveyorEvent.entity_type == "candidate_case", SurveyorEvent.entity_id == str(case_id))))
    notes = list(db.scalars(select(CandidateCaseNote).where(CandidateCaseNote.case_id == case_id)))
    items = [{"kind": "event", "id": row.id, "label": row.action, "event_type": row.event_type,
              "occurred_at": row.occurred_at, "notes": row.notes} for row in events]
    items.extend({"kind": "note", "id": row.id, "label": "Case note", "body": row.body,
                  "occurred_at": row.created_at} for row in notes)
    items.extend({"kind": "source_record", "id": record["post_id"],
                  "label": f'{record.get("custody_label") or record.get("status") or "Source record"} · {record.get("source_label")}',
                  "occurred_at": record.get("last_seen_at") or record.get("first_seen_at"),
                  "source_record": record} for record in case_output(db, case).get("source_records", []))
    items.sort(key=_sort_time, reverse=True)
    return items
