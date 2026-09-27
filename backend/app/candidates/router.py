from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import (CandidateCase, CandidateCaseMerge, CandidateCaseNote, CandidateCasePost,
                      CandidateIdentifier, CandidateIdentityExclusion, PetPost, SurveyorAttachment,
                      SurveyorAttachmentLink, SurveyorEvent, SurveyorMapObject, SurveyorTask)
from ..surveyor_media import attachment_metadata, contained_path
from ..settings import get_settings
from .identity import case_output, choose_primary_post, extract_identifiers, merge_candidate_cases, reverse_case_merge

router = APIRouter(prefix="/api/candidate-cases", tags=["candidate-cases"])
settings = get_settings()
media_root = Path(settings.media_dir).resolve()


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
    output = case_output(db, case)
    field_objects = []
    for obj in db.scalars(select(SurveyorMapObject)):
        properties = _properties(obj.id, db)
        if properties.get("candidate_case_id") != case_id:
            continue
        field_objects.append({"id": obj.id, "object_type": obj.object_type, "subtype": obj.subtype,
            "name": obj.name, "geometry": json.loads(obj.geometry_json), "status": obj.status,
            "occurred_at": obj.occurred_at, "created_at": obj.created_at})
    output["field_objects"] = field_objects
    return output


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
    objects = list(db.scalars(select(SurveyorMapObject)))
    case_object_ids = set()
    for obj in objects:
        if _properties(obj.id, db).get("candidate_case_id") == case_id:
            case_object_ids.add(obj.id)
    case_objects = [obj for obj in objects if obj.id in case_object_ids]
    for obj in case_objects:
        items.append({"kind": "field_object", "id": obj.id,
            "label": obj.name or f"{obj.subtype or obj.object_type.replace('_', ' ')} recorded",
            "event_type": obj.subtype or obj.object_type,
            "occurred_at": obj.occurred_at or obj.created_at})
    if case_object_ids:
        linked_events = db.scalars(select(SurveyorEvent).where(
            SurveyorEvent.entity_type == "map_object",
            SurveyorEvent.entity_id.in_([str(value) for value in case_object_ids])))
        items.extend({"kind": "event", "id": row.id, "label": row.action,
            "event_type": row.event_type, "occurred_at": row.occurred_at, "notes": row.notes}
            for row in linked_events)
        tasks = db.scalars(select(SurveyorTask).where(SurveyorTask.map_object_id.in_(case_object_ids)))
        items.extend({"kind": "task", "id": task.id,
            "label": f"Follow-up {task.status}", "body": task.title,
            "priority": task.priority, "occurred_at": task.completed_at or task.created_at}
            for task in tasks)
    attachment_ids = {row.attachment_id for row in db.scalars(select(SurveyorAttachmentLink).where(
        SurveyorAttachmentLink.entity_type == "candidate_case", SurveyorAttachmentLink.entity_id == str(case_id)))}
    if case_object_ids:
        attachment_ids.update(row.id for row in db.scalars(select(SurveyorAttachment).where(
            SurveyorAttachment.map_object_id.in_(case_object_ids))))
    for attachment in db.scalars(select(SurveyorAttachment).where(SurveyorAttachment.id.in_(attachment_ids))) if attachment_ids else []:
        items.append({"kind": "media", "id": attachment.id,
            "label": f"{attachment.attachment_type.title()} added",
            "body": attachment.caption,
            "occurred_at": attachment.observed_at or attachment.created_at})
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


@router.post("/{case_id}/export")
def export_candidate_case(case_id: int, db: Session = Depends(get_db)):
    case = _case_or_404(db, case_id)
    projection = case_output(db, case)
    source_records = projection.get("source_records", [])
    notes = list(db.scalars(select(CandidateCaseNote).where(CandidateCaseNote.case_id == case_id)
                            .order_by(CandidateCaseNote.created_at)))
    linked_ids = {row.attachment_id for row in db.scalars(select(SurveyorAttachmentLink).where(
        SurveyorAttachmentLink.entity_type == "candidate_case",
        SurveyorAttachmentLink.entity_id == str(case_id)))}
    linked_ids.update(row.id for row in db.scalars(select(SurveyorAttachment).join(
        SurveyorMapObject, SurveyorMapObject.id == SurveyorAttachment.map_object_id))
        if (properties := _properties(row.map_object_id, db)).get("candidate_case_id") == case_id)

    attachments = [db.get(SurveyorAttachment, attachment_id) for attachment_id in linked_ids]
    attachments = [row for row in attachments if row]
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    safe = re.sub(r"[^A-Za-z0-9]+", "-", projection.get("display_name") or f"case-{case_id}").strip("-").lower()
    root = f"archie-radar-case-{case_id}-{safe[:40]}-{stamp}"
    summary = {
        "case_id": case_id,
        "review_state": projection.get("review_state"),
        "display_name": projection.get("display_name"),
        "current_record_id": projection.get("current_record_id"),
        "current_location": projection.get("current_location"),
        "current_custody": projection.get("current_custody"),
        "external_ids": projection.get("external_ids", []),
        "record_count": projection.get("record_count", 0),
        "source_records": source_records,
    }
    manifest = []
    archive_data = io.BytesIO()
    with zipfile.ZipFile(archive_data, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f"{root}/README.txt", f"Archie Radar case export created {stamp}.\nLocal originals included: {len(attachments)}.\ncase.json is the structured case summary; manifest.csv lists included local media.\n")
        archive.writestr(f"{root}/case.json", json.dumps(summary, default=str, indent=2))
        archive.writestr(f"{root}/case-notes.json", json.dumps([
            {"id": note.id, "body": note.body, "created_at": note.created_at} for note in notes
        ], default=str, indent=2))
        for index, attachment in enumerate(attachments, start=1):
            if not attachment.storage_path:
                continue
            try:
                path = contained_path(media_root, attachment.storage_path)
            except HTTPException:
                continue
            if not path.is_file():
                continue
            metadata = attachment_metadata(attachment)
            observed = attachment.observed_at or attachment.created_at
            timestamp = observed.astimezone(timezone.utc).strftime("%Y-%m-%d_%H%M%S") if observed.tzinfo else observed.strftime("%Y-%m-%d_%H%M%S")
            original_name = Path(metadata.get("original_filename") or path.name).name
            extension = Path(original_name).suffix[:12]
            media_type = metadata.get("media_type") or attachment.attachment_type
            slug = re.sub(r"[^A-Za-z0-9]+", "-", (attachment.caption or Path(original_name).stem)).strip("-").lower()[:40] or "field-media"
            export_name = f"{timestamp}_{slug}_{media_type}_{index:03d}{extension}"
            archive.writestr(f"{root}/media/{export_name}", path.read_bytes())
            manifest.append({"attachment_id": attachment.id, "export_filename": export_name,
                "original_filename": original_name, "media_type": media_type,
                "mime_type": metadata.get("mime_type"), "file_size_bytes": metadata.get("file_size_bytes"),
                "observed_at": attachment.observed_at, "created_at": attachment.created_at,
                "caption": attachment.caption, "latitude": metadata.get("latitude"), "longitude": metadata.get("longitude")})
        archive.writestr(f"{root}/media-manifest.json", json.dumps(manifest, default=str, indent=2))
        table = io.StringIO(newline="")
        writer = csv.DictWriter(table, fieldnames=["attachment_id", "export_filename", "original_filename", "media_type", "mime_type", "observed_at", "caption"], extrasaction="ignore")
        writer.writeheader()
        for row in manifest:
            writer.writerow(row)
        archive.writestr(f"{root}/manifest.csv", table.getvalue())
    archive_data.seek(0)
    return StreamingResponse(archive_data, media_type="application/zip", headers={
        "Content-Disposition": f'attachment; filename="{root}.zip"'})


def _properties(object_id: int | None, db: Session) -> dict:
    if object_id is None:
        return {}
    obj = db.get(SurveyorMapObject, object_id)
    try:
        value = json.loads(obj.properties_json or "{}") if obj else {}
        return value if isinstance(value, dict) else {}
    except (TypeError, json.JSONDecodeError):
        return {}


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
