from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import (CandidateCase, CandidateCaseMerge, CandidateCaseNote, CandidateCasePost,
                      CandidateIdentifier, CandidateIdentityExclusion, PetPost, SurveyorEvent)
from .identity import case_output, choose_primary_post, extract_identifiers, merge_candidate_cases, reverse_case_merge

router = APIRouter(prefix="/api/candidate-cases", tags=["candidate-cases"])


class CandidateCaseNoteIn(BaseModel):
    body: str = Field(min_length=1, max_length=10000)


class CandidateCaseMergeIn(BaseModel):
    other_case_id: int
    reason: str = Field(default="", max_length=2000)


class CandidateCaseSplitIn(BaseModel):
    post_ids: list[int] = Field(min_length=1, max_length=100)
    reason: str = Field(default="", max_length=2000)


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
    merges = list(db.scalars(select(CandidateCaseMerge).where(
        (CandidateCaseMerge.survivor_case_id == case_id) | (CandidateCaseMerge.absorbed_case_id == case_id))))
    items.extend({"kind": "identity", "id": row.id,
        "label": "Case merge reversed" if row.reversed_at else "Cases merged",
        "occurred_at": row.reversed_at or row.created_at,
        "reason": row.reason,
        "merge_id": row.id,
    } for row in merges)
    items.sort(key=_sort_time, reverse=True)
    return items


@router.post("/{case_id}/merge", status_code=201)
def merge_case(case_id: int, payload: CandidateCaseMergeIn, db: Session = Depends(get_db)):
    try:
        merge = merge_candidate_cases(db, case_id, payload.other_case_id, payload.reason)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    db.add(SurveyorEvent(event_type="candidate_cases_merged", entity_type="candidate_case",
        entity_id=str(case_id), action=f"Merged case #{payload.other_case_id}",
        after_json=f'{{"merge_id": {merge.id}, "absorbed_case_id": {payload.other_case_id}}}', notes=payload.reason))
    db.commit()
    return {"merge_id": merge.id, "survivor_case_id": case_id, "absorbed_case_id": payload.other_case_id}


@router.post("/{case_id}/split", status_code=201)
def split_case(case_id: int, payload: CandidateCaseSplitIn, db: Session = Depends(get_db)):
    case = _case_or_404(db, case_id)
    selected_ids = set(payload.post_ids)
    members = list(db.scalars(select(CandidateCasePost).where(CandidateCasePost.case_id == case_id)))
    existing_ids = {member.post_id for member in members}
    if not selected_ids or not selected_ids.issubset(existing_ids) or selected_ids == existing_ids:
        raise HTTPException(400, "Choose one or more source records, but leave at least one in the current case")
    selected_posts = [db.get(PetPost, post_id) for post_id in selected_ids]
    selected_posts = [post for post in selected_posts if post]
    remaining_posts = [db.get(PetPost, member.post_id) for member in members if member.post_id not in selected_ids]
    remaining_posts = [post for post in remaining_posts if post]
    new_case = CandidateCase(review_state=case.review_state)
    db.add(new_case)
    db.flush()
    for member in members:
        if member.post_id in selected_ids:
            member.case_id = new_case.id
            member.match_method = "manual"

    selected_keys = {key for post in selected_posts for key in extract_identifiers(post)}
    remaining_keys = {key[:2] for post in remaining_posts for key in extract_identifiers(post)}
    for namespace, value, _, _, identity_key in selected_keys:
        if not identity_key:
            continue
        if (namespace, value) in remaining_keys:
            for post in selected_posts:
                exclusion = db.scalar(select(CandidateIdentityExclusion).where(
                    CandidateIdentityExclusion.post_id == post.id,
                    CandidateIdentityExclusion.namespace == namespace,
                    CandidateIdentityExclusion.value == value))
                if exclusion is None:
                    db.add(CandidateIdentityExclusion(post_id=post.id, namespace=namespace,
                        value=value, reason=payload.reason or "Manual case split"))
        else:
            identifier = db.scalar(select(CandidateIdentifier).where(
                CandidateIdentifier.case_id == case_id,
                CandidateIdentifier.namespace == namespace,
                CandidateIdentifier.value == value))
            if identifier:
                identifier.case_id = new_case.id

    case.primary_post_id = choose_primary_post(remaining_posts, db).id
    new_case.primary_post_id = choose_primary_post(selected_posts, db).id
    db.add(SurveyorEvent(event_type="candidate_case_split", entity_type="candidate_case",
        entity_id=str(case_id), action=f"Split into case #{new_case.id}",
        after_json=f'{{"new_case_id": {new_case.id}, "post_ids": {sorted(selected_ids)}}}', notes=payload.reason))
    db.commit()
    return {"original_case_id": case_id, "new_case_id": new_case.id,
            "moved_post_ids": sorted(selected_ids)}


@router.get("/{case_id}/merges")
def list_case_merges(case_id: int, db: Session = Depends(get_db)):
    _case_or_404(db, case_id)
    rows = db.scalars(select(CandidateCaseMerge).where(
        (CandidateCaseMerge.survivor_case_id == case_id) | (CandidateCaseMerge.absorbed_case_id == case_id)
    ).order_by(CandidateCaseMerge.created_at.desc()))
    return [{"id": row.id, "survivor_case_id": row.survivor_case_id,
             "absorbed_case_id": row.absorbed_case_id, "reason": row.reason,
             "created_at": row.created_at, "reversed_at": row.reversed_at} for row in rows]


@router.post("/{case_id}/merges/{merge_id}/reverse")
def reverse_merge(case_id: int, merge_id: int, db: Session = Depends(get_db)):
    merge = db.get(CandidateCaseMerge, merge_id)
    if not merge or case_id not in {merge.survivor_case_id, merge.absorbed_case_id}:
        raise HTTPException(404, "Case merge not found")
    if merge.reversed_at:
        raise HTTPException(409, "Case merge was already reversed")
    try:
        reverse_case_merge(db, merge)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    db.add(SurveyorEvent(event_type="candidate_case_merge_reversed", entity_type="candidate_case",
        entity_id=str(merge.survivor_case_id), action=f"Reversed merge with case #{merge.absorbed_case_id}",
        after_json=f'{{"merge_id": {merge.id}, "restored_case_id": {merge.absorbed_case_id}}}'))
    db.commit()
    return {"merge_id": merge.id, "reversed": True, "restored_case_id": merge.absorbed_case_id}
