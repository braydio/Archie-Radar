from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import (CandidateCasePost, FacebookBridgeToken, FacebookGroupSubscription,
                      FacebookGroupSyncReceipt, FacebookGroupSyncRun, FacebookPostFingerprint,
                      PetPost, utcnow)
from ..schemas import PetPostIn
from ..service import upsert_posts
from ..settings import get_settings
from ..candidates.identity import merge_candidate_cases
from .classifier import candidate_status, is_cat_related
from .dedupe import likely_crosspost, text_fingerprint
from .schemas import BatchIn, GroupIn, GroupPatch, GroupReceiptIn, SessionImportIn, SyncCompleteIn
from .session import clear_session, save_chrome_cookies, session_ready, session_status

router = APIRouter(prefix="/api/facebook", tags=["facebook-collector"])
settings = get_settings()


def _token_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def require_bridge_token(
    x_archie_facebook_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> FacebookBridgeToken:
    if not x_archie_facebook_token:
        raise HTTPException(401, "Facebook browser is not paired")
    row = db.scalar(select(FacebookBridgeToken).where(
        FacebookBridgeToken.token_digest == _token_hash(x_archie_facebook_token),
        FacebookBridgeToken.revoked_at.is_(None),
    ))
    if row is None:
        raise HTTPException(401, "Facebook browser pairing is invalid or revoked")
    row.last_seen_at = utcnow()
    db.commit()
    return row


def _group_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "https" or parsed.hostname not in {"facebook.com", "www.facebook.com", "m.facebook.com"}:
        raise HTTPException(422, "Use an https://www.facebook.com/groups/... URL")
    if not parsed.path.startswith("/groups/"):
        raise HTTPException(422, "URL must point to a Facebook group")
    return f"https://www.facebook.com{parsed.path.rstrip('/')}"


def _group_id_from_url(value: str) -> str | None:
    path = urlparse(value).path
    parts = [part for part in path.split("/") if part]
    if len(parts) >= 2 and parts[0] == "groups" and parts[1].isdigit():
        return parts[1]
    return None


def _group_out(row: FacebookGroupSubscription) -> dict:
    return {
        "id": row.id, "group_url": row.group_url, "facebook_group_id": row.facebook_group_id,
        "group_name": row.group_name, "enabled": row.enabled, "initial_sync_cutoff": row.initial_sync_cutoff, "added_at": row.added_at,
        "last_sync_started_at": row.last_sync_started_at, "last_sync_completed_at": row.last_sync_completed_at,
        "last_success_at": row.last_success_at, "newest_seen_post_at": row.newest_seen_post_at,
        "newest_seen_post_id": row.newest_seen_post_id, "last_error": row.last_error,
        "parser_warning": row.parser_warning,
    }


def _run_out(db: Session, row: FacebookGroupSyncRun) -> dict:
    receipts = list(db.scalars(select(FacebookGroupSyncReceipt).where(
        FacebookGroupSyncReceipt.sync_run_id == row.id
    ).order_by(FacebookGroupSyncReceipt.id)))
    groups = {item.id: item for item in db.scalars(select(FacebookGroupSubscription).where(
        FacebookGroupSubscription.id.in_([receipt.group_subscription_id for receipt in receipts] or [-1])
    ))}
    return {
        "id": row.id, "started_at": row.started_at, "completed_at": row.completed_at,
        "requested_group_count": row.requested_group_count, "successful_group_count": row.successful_group_count,
        "posts_seen": row.posts_seen, "posts_new": row.posts_new, "posts_updated": row.posts_updated,
        "posts_filtered": row.posts_filtered, "exact_duplicates": row.exact_duplicates,
        "crossposts_combined": row.crossposts_combined, "status": row.status,
        "error_summary": row.error_summary,
        "groups": [{"group": _group_out(groups[receipt.group_subscription_id]),
                    "scanned": receipt.scanned, "cat_related": receipt.cat_related,
                    "posts_new": receipt.posts_new, "already_known": receipt.already_known,
                    "crossposts_combined": receipt.crossposts_combined, "status": receipt.status,
                    "parser_warning": receipt.parser_warning, "error": receipt.error}
                   for receipt in receipts if receipt.group_subscription_id in groups],
    }


@router.post("/pair")
def pair_browser(db: Session = Depends(get_db)):
    """Mint one narrow, revocable collector credential; the secret is shown once."""
    db.query(FacebookBridgeToken).filter(FacebookBridgeToken.revoked_at.is_(None)).update(
        {FacebookBridgeToken.revoked_at: utcnow()}, synchronize_session=False)
    secret = secrets.token_urlsafe(36)
    db.add(FacebookBridgeToken(token_digest=_token_hash(secret)))
    db.commit()
    return {"paired": True, "token": secret, "header": "X-Archie-Facebook-Token"}


@router.get("/bridge/status")
def bridge_status(_token: FacebookBridgeToken = Depends(require_bridge_token)):
    return {"paired": True, "device_name": _token.device_name, "last_seen_at": _token.last_seen_at}


@router.get("/status")
def collector_status(db: Session = Depends(get_db)):
    token = db.scalar(select(FacebookBridgeToken).where(
        FacebookBridgeToken.revoked_at.is_(None)
    ).order_by(FacebookBridgeToken.created_at.desc()))
    latest_run = db.scalar(select(FacebookGroupSyncRun).order_by(
        FacebookGroupSyncRun.started_at.desc(), FacebookGroupSyncRun.id.desc()
    ).limit(1))
    server_state = session_status()
    server_mode = bool(settings.facebook_server_collector_enabled)
    return {
        "paired": server_state["ready"] if server_mode else token is not None,
        "collector_mode": "server" if server_mode else "extension",
        "server_collector_enabled": server_mode,
        "server_session_ready": server_state["ready"],
        "server_session": server_state,
        "extension_paired": token is not None,
        "last_seen_at": token.last_seen_at if token else None,
        "automatic_sync_minutes": int(settings.facebook_sync_minutes) if server_mode else None,
        "last_sync": _run_out(db, latest_run) if latest_run else None,
    }


@router.post("/session/import")
def import_server_session(
    payload: SessionImportIn,
    _token: FacebookBridgeToken = Depends(require_bridge_token),
):
    try:
        result = save_chrome_cookies([cookie.model_dump() for cookie in payload.cookies])
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {
        "connected": True,
        "collector_mode": "server",
        "cookie_count": result["cookie_count"],
        "message": "Server Facebook session ready. This browser no longer needs to stay open for scans.",
    }


@router.get("/session/status")
def get_server_session_status():
    return session_status()


@router.delete("/session")
def delete_server_session():
    clear_session()
    return {"connected": False}


@router.get("/groups")
def list_groups(db: Session = Depends(get_db)):
    return [_group_out(row) for row in db.scalars(select(FacebookGroupSubscription).order_by(FacebookGroupSubscription.added_at.desc()))]


@router.post("/groups", status_code=201)
def add_group(payload: GroupIn, db: Session = Depends(get_db)):
    url = _group_url(str(payload.group_url))
    row = db.scalar(select(FacebookGroupSubscription).where(FacebookGroupSubscription.group_url == url))
    if row:
        row.group_name = payload.group_name.strip()
        row.facebook_group_id = payload.facebook_group_id or row.facebook_group_id or _group_id_from_url(url)
        row.enabled = payload.enabled
        row.initial_sync_cutoff = payload.initial_sync_cutoff
    else:
        row = FacebookGroupSubscription(group_url=url, facebook_group_id=payload.facebook_group_id or _group_id_from_url(url),
            group_name=payload.group_name.strip(), enabled=payload.enabled, initial_sync_cutoff=payload.initial_sync_cutoff)
        db.add(row)
    db.commit(); db.refresh(row)
    return _group_out(row)


@router.patch("/groups/{group_id:int}")
def update_group(group_id: int, payload: GroupPatch, db: Session = Depends(get_db)):
    row = db.get(FacebookGroupSubscription, group_id)
    if row is None:
        raise HTTPException(404, "Facebook group not found")
    changes = payload.model_dump(exclude_unset=True)
    if "group_url" in changes and changes["group_url"] is not None:
        row.group_url = _group_url(str(changes["group_url"]))
    for key in ("facebook_group_id", "group_name", "enabled", "initial_sync_cutoff"):
        if key in changes and changes[key] is not None:
            setattr(row, key, changes[key])
    db.commit(); db.refresh(row)
    return _group_out(row)


@router.delete("/groups/{group_id:int}")
def disable_group(group_id: int, db: Session = Depends(get_db)):
    row = db.get(FacebookGroupSubscription, group_id)
    if row is None:
        raise HTTPException(404, "Facebook group not found")
    row.enabled = False
    db.commit()
    return {"disabled": True, "id": row.id}


@router.post("/sync")
def create_sync(db: Session = Depends(get_db)):
    if settings.facebook_server_collector_enabled:
        if not session_ready():
            raise HTTPException(409, "Connect Facebook once so the server can scan selected groups independently.")
    elif db.scalar(select(FacebookBridgeToken.id).where(FacebookBridgeToken.revoked_at.is_(None))) is None:
        raise HTTPException(409, "Connect the Facebook browser extension first")
    groups = list(db.scalars(select(FacebookGroupSubscription).where(FacebookGroupSubscription.enabled.is_(True))))
    if not groups:
        raise HTTPException(409, "Select at least one Facebook group")
    active = db.scalar(select(FacebookGroupSyncRun).where(
        FacebookGroupSyncRun.status.in_(["queued", "syncing"])
    ).order_by(FacebookGroupSyncRun.id.desc()).limit(1))
    if active is not None:
        return _run_out(db, active)
    run = FacebookGroupSyncRun(requested_group_count=len(groups), status="queued")
    db.add(run); db.flush()
    for group in groups:
        db.add(FacebookGroupSyncReceipt(sync_run_id=run.id, group_subscription_id=group.id))
    db.commit(); db.refresh(run)
    return _run_out(db, run)


@router.get("/sync/next")
def next_sync(_token: FacebookBridgeToken = Depends(require_bridge_token), db: Session = Depends(get_db)):
    # The extension is only the transport when server-side collection is disabled.
    # In normal server mode, queued runs are claimed by the backend Playwright worker.
    if settings.facebook_server_collector_enabled:
        return {"job": None, "collector_mode": "server"}
    run = db.scalar(select(FacebookGroupSyncRun).where(FacebookGroupSyncRun.status == "queued")
                     .order_by(FacebookGroupSyncRun.started_at, FacebookGroupSyncRun.id).limit(1))
    if run is None:
        return {"job": None}
    run.status = "syncing"
    receipts = list(db.scalars(select(FacebookGroupSyncReceipt).where(FacebookGroupSyncReceipt.sync_run_id == run.id)))
    groups = {item.id: item for item in db.scalars(select(FacebookGroupSubscription).where(
        FacebookGroupSubscription.id.in_([receipt.group_subscription_id for receipt in receipts] or [-1])
    ))}
    now = utcnow()
    result_groups = []
    for receipt in receipts:
        group = groups.get(receipt.group_subscription_id)
        if not group or not group.enabled:
            receipt.status = "disabled"
            receipt.completed_at = now
            continue
        group.last_sync_started_at = now
        receipt.status = "syncing"
        watermark = json.loads(group.watermark_json or "[]")
        result_groups.append({**_group_out(group), "watermark_post_ids": watermark[-30:],
            "first_sync_cutoff": group.initial_sync_cutoff if group.last_success_at is None else None})
    db.commit()
    return {"job": {"id": run.id, "groups": result_groups}}


@router.get("/sync/{sync_id:int}")
def get_sync(sync_id: int, db: Session = Depends(get_db)):
    run = db.get(FacebookGroupSyncRun, sync_id)
    if run is None:
        raise HTTPException(404, "Facebook sync run not found")
    return _run_out(db, run)


def _upsert_facebook_batch(db: Session, payload: BatchIn) -> dict:
    run = db.get(FacebookGroupSyncRun, payload.sync_run_id)
    group = db.get(FacebookGroupSubscription, payload.group_subscription_id)
    if run is None or group is None:
        raise HTTPException(404, "Sync run or group not found")
    receipt = db.scalar(select(FacebookGroupSyncReceipt).where(
        FacebookGroupSyncReceipt.sync_run_id == run.id,
        FacebookGroupSyncReceipt.group_subscription_id == group.id,
    ))
    if receipt is None or run.status not in {"queued", "syncing"}:
        raise HTTPException(409, "This group is not part of an active sync run")

    accepted = []
    filtered = 0
    for captured in payload.posts:
        text = captured.text.strip()
        if not is_cat_related(text):
            filtered += 1
            continue
        url = str(captured.canonical_url) if captured.canonical_url else ""
        post_id = (captured.facebook_post_id or "").strip()
        if not post_id and not url:
            filtered += 1
            continue
        source_id = post_id or hashlib.sha256(url.encode("utf-8")).hexdigest()
        image_url = str(captured.images[0].url) if captured.images else None
        existing = db.scalar(select(PetPost).where(PetPost.source == "facebook_group", PetPost.source_id == source_id))
        appearances = []
        if existing:
            try:
                previous_raw = json.loads(existing.raw_json or "{}")
                appearances = previous_raw.get("facebook_group_appearances", [])
            except (TypeError, json.JSONDecodeError):
                appearances = []
        appearance = {"group_subscription_id": group.id, "group_name": group.group_name,
            "group_url": group.group_url, "seen_at": (captured.captured_at or utcnow()).isoformat(),
            "posted_at": captured.posted_at.isoformat() if captured.posted_at else None}
        appearances = [item for item in appearances if item.get("group_subscription_id") != group.id]
        appearances.append(appearance)
        image_hash = next((item.sha256.lower() for item in captured.images if item.sha256), None)
        normalized_hash, normalized_text = text_fingerprint(text)
        post_time = captured.posted_at or captured.captured_at or utcnow()
        if post_time.tzinfo is None:
            post_time = post_time.replace(tzinfo=timezone.utc)
        raw = {
            "source_platform": "Facebook", "reporting_entity": group.group_name,
            "custody_type": "finder" if re_search_finder(text) else "field_report",
            "custody_label": "With finder" if re_search_finder(text) else "Found report",
            "facebook_group_id": group.facebook_group_id, "facebook_group_name": group.group_name,
            "facebook_group_url": group.group_url, "facebook_group_appearances": appearances,
            "facebook_author_display_name": captured.author_name,
            "facebook_image_urls": [str(image.url) for image in captured.images],
            "facebook_post_id": source_id, "video_present": captured.video_present,
            "captured_at": (captured.captured_at or utcnow()).isoformat(),
            "source_image_sha256": image_hash,
            "image_meta": {"width": captured.images[0].width, "height": captured.images[0].height} if captured.images else {},
            "facebook_normalized_text_hash": normalized_hash,
        }
        accepted.append((source_id, PetPostIn(
            source="facebook_group", source_id=source_id, source_url=url or f"{group.group_url}/posts/{source_id}",
            status=candidate_status(text), species="cat", description=text, image_url=image_url,
            reported_at=captured.posted_at, raw=raw,
        ), text, image_hash, normalized_text, post_time))

    upsert_result = upsert_posts(db, [item[1] for item in accepted]) if accepted else {"created": 0, "updated": 0, "post_ids": []}
    post_ids = upsert_result["post_ids"]
    crossposts = 0
    exact_dupes = int(upsert_result["updated"])
    for item, post_id in zip(accepted, post_ids):
        _, incoming, text, image_hash, normalized_text, post_time = item
        fingerprint = db.scalar(select(FacebookPostFingerprint).where(FacebookPostFingerprint.post_id == post_id))
        if fingerprint is None:
            fingerprint = FacebookPostFingerprint(post_id=post_id, image_sha256=image_hash,
                normalized_text_hash=text_fingerprint(text)[0], normalized_text=normalized_text,
                group_subscription_id=group.id, captured_at=post_time)
            db.add(fingerprint); db.flush()
        else:
            fingerprint.image_sha256 = image_hash or fingerprint.image_sha256
            fingerprint.normalized_text_hash, fingerprint.normalized_text = text_fingerprint(text)
            fingerprint.group_subscription_id = group.id
            fingerprint.captured_at = post_time
        if not image_hash:
            continue
        lower = post_time - timedelta(days=7)
        upper = post_time + timedelta(days=7)
        possible = list(db.scalars(select(FacebookPostFingerprint).where(
            FacebookPostFingerprint.image_sha256 == image_hash,
            FacebookPostFingerprint.post_id != post_id,
            FacebookPostFingerprint.captured_at >= lower,
            FacebookPostFingerprint.captured_at <= upper,
        )))
        for other in possible:
            if not likely_crosspost(other.normalized_text, normalized_text):
                continue
            current_membership = db.scalar(select(CandidateCasePost).where(CandidateCasePost.post_id == post_id))
            other_membership = db.scalar(select(CandidateCasePost).where(CandidateCasePost.post_id == other.post_id))
            if not current_membership or not other_membership or current_membership.case_id == other_membership.case_id:
                continue
            from ..candidates.identity import merge_candidate_cases
            merge_candidate_cases(db, current_membership.case_id, other_membership.case_id,
                reason="Facebook cross-post: exact image hash and highly similar report text", match_method="facebook_crosspost")
            crossposts += 1
            break

    receipt.scanned = payload.scanned
    receipt.cat_related = len(accepted)
    unique_new = max(0, int(upsert_result["created"]) - crossposts)
    receipt.posts_new = unique_new
    receipt.already_known = int(upsert_result["updated"]) + crossposts
    receipt.crossposts_combined = crossposts
    receipt.parser_warning = payload.parser_warning
    receipt.status = "parser_warning" if payload.parser_warning else "success"
    receipt.completed_at = utcnow()
    group.last_sync_completed_at = utcnow()
    group.parser_warning = payload.parser_warning
    group.last_error = payload.parser_warning
    if not payload.parser_warning:
        group.last_success_at = group.last_sync_completed_at
        newest = max((item[5] for item in accepted), default=group.newest_seen_post_at)
        previous_newest = group.newest_seen_post_at
        if newest is not None and newest.tzinfo is None:
            newest = newest.replace(tzinfo=timezone.utc)
        if previous_newest is not None and previous_newest.tzinfo is None:
            previous_newest = previous_newest.replace(tzinfo=timezone.utc)
        if newest and (previous_newest is None or newest > previous_newest):
            group.newest_seen_post_at = newest
        seen_ids = json.loads(group.watermark_json or "[]")
        group.watermark_json = json.dumps(list(dict.fromkeys((seen_ids + [item[0] for item in accepted])))[-30:])
        group.newest_seen_post_id = accepted[-1][0] if accepted else group.newest_seen_post_id
    run.posts_seen += payload.scanned
    run.posts_new += unique_new
    run.posts_updated += int(upsert_result["updated"])
    run.posts_filtered += filtered
    run.exact_duplicates += exact_dupes
    run.crossposts_combined += crossposts
    if receipt.status == "success":
        run.successful_group_count += 1
    db.commit()
    return {"scanned": payload.scanned, "cat_related": len(accepted), "posts_new": unique_new,
        "already_known": int(upsert_result["updated"]) + crossposts, "filtered": filtered,
        "exact_duplicates": exact_dupes, "crossposts_combined": crossposts,
        "per_item": [{"facebook_post_id": item[0], "status": "stored"} for item in accepted]}


def re_search_finder(text: str) -> bool:
    import re
    return bool(re.search(r"\b(with me|at my home|my porch|finder|found this cat)\b", text, re.I))


@router.post("/ingest-batch")
def ingest_batch(payload: BatchIn, _token: FacebookBridgeToken = Depends(require_bridge_token), db: Session = Depends(get_db)):
    return _upsert_facebook_batch(db, payload)


@router.post("/sync/{sync_id:int}/groups/{group_id:int}/fail")
def fail_group_receipt(
    sync_id: int,
    group_id: int,
    payload: GroupReceiptIn,
    _token: FacebookBridgeToken = Depends(require_bridge_token),
    db: Session = Depends(get_db),
):
    run = db.get(FacebookGroupSyncRun, sync_id)
    receipt = db.scalar(select(FacebookGroupSyncReceipt).where(
        FacebookGroupSyncReceipt.sync_run_id == sync_id,
        FacebookGroupSyncReceipt.group_subscription_id == group_id,
    ))
    group = db.get(FacebookGroupSubscription, group_id)
    if run is None or receipt is None or group is None:
        raise HTTPException(404, "Sync run or group receipt not found")
    if run.status not in {"queued", "syncing"} or receipt.status not in {"queued", "syncing"}:
        raise HTTPException(409, "This group is not part of an active sync run")
    now = utcnow()
    receipt.scanned = payload.scanned
    receipt.parser_warning = payload.parser_warning
    receipt.error = payload.error or payload.parser_warning or "Facebook group scan failed"
    receipt.status = "parser_warning" if payload.parser_warning and not payload.error else "failed"
    receipt.completed_at = now
    group.last_sync_completed_at = now
    group.last_error = receipt.error
    group.parser_warning = payload.parser_warning
    db.commit()
    return {"status": receipt.status, "error": receipt.error}


@router.post("/sync/{sync_id:int}/complete")
def complete_sync(sync_id: int, payload: SyncCompleteIn, _token: FacebookBridgeToken = Depends(require_bridge_token), db: Session = Depends(get_db)):
    run = db.get(FacebookGroupSyncRun, sync_id)
    if run is None:
        raise HTTPException(404, "Facebook sync run not found")
    receipts = list(db.scalars(select(FacebookGroupSyncReceipt).where(FacebookGroupSyncReceipt.sync_run_id == sync_id)))
    pending = [item for item in receipts if item.status in {"queued", "syncing"}]
    if pending:
        for item in pending:
            item.status = "failed"
            item.error = payload.error_summary or "Collector ended before this group completed"
            item.completed_at = utcnow()
    run.completed_at = utcnow()
    problems = [item for item in receipts if item.status in {"failed", "parser_warning"}]
    problem_summary = [item.error or item.parser_warning for item in problems if item.error or item.parser_warning]
    summaries = [value for value in (payload.error_summary, *problem_summary) if value]
    run.error_summary = "\n".join(dict.fromkeys(summaries))
    if (run.error_summary or problems) and run.successful_group_count:
        run.status = "partial"
    elif run.error_summary or problems or not run.successful_group_count:
        run.status = "failed"
    else:
        run.status = "complete"
    db.commit()
    return _run_out(db, run)
