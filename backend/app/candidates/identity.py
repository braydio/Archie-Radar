from __future__ import annotations

import json
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import CandidateCase, CandidateCasePost, CandidateIdentifier, PetPost, PostVision
from ..service import get_or_create_profile, post_output
from ..vision import compare_fingerprints

P24_SOURCES = {
    "regional_24petconnect", "chatham_24petconnect", "orange_county_24petconnect",
    "durham_24petconnect", "wake_24petconnect", "burlington_24petconnect", "orange_county_found",
}
REVIEW_PRECEDENCE = ("confirmed", "possible", "needs_review", "new", "dismissed")


def normalize_external_id(source: str, source_id: str, raw: dict | None = None):
    source, value, raw = (source or "").strip().lower(), str(source_id or "").strip(), raw or {}
    if not value:
        return None
    if source in P24_SOURCES:
        # Only strip/normalize the optional A prefix in this known numeric format.
        if re.fullmatch(r"(?i)A?\d+", value):
            value = "A" + value.lstrip("aA")
        return "24petconnect.animal_id", value.upper(), "animal_id", "Animal ID", True
    if source == "wake_county_lostfound":
        return "wake_county.animal_id", value.casefold(), "animal_id", "Wake ID", True
    if source in {"pawboost", "pet911", "petkey"}:
        return f"{source}.listing_id", value, "listing_id", f"{source.title()} ID", False
    if source == "facebook_bridge":
        return "facebook.post_id", value, "report_id", "Facebook post ID", False
    animal_id = raw.get("animal_id") or raw.get("shelter_animal_id")
    shelter = raw.get("shelter_namespace") or raw.get("shelter_name")
    if animal_id and shelter:
        return f"shelter.{str(shelter).strip().casefold()}.animal_id", str(animal_id).strip(), "animal_id", "Animal ID", True
    return None


def _raw(post: PetPost) -> dict:
    try:
        return json.loads(post.raw_json or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}


def _image_meta(post: PetPost) -> dict:
    value = _raw(post).get("image_meta")
    return value if isinstance(value, dict) else {}


def _image_size(post: PetPost) -> tuple[int, int]:
    meta = _image_meta(post)
    try:
        width, height = int(meta.get("width") or 0), int(meta.get("height") or 0)
        return (width, height) if width > 0 and height > 0 else (0, 0)
    except (TypeError, ValueError):
        return 0, 0


def choose_primary_case_image(posts: list[PetPost], visions: dict[int, PostVision], primary_post_id: int | None = None) -> PetPost | None:
    """Choose the most useful distinct case photo without favoring aspect ratio."""
    usable = [post for post in posts if post.image_url and not (visions.get(post.id) and visions[post.id].status == "no_photo")]
    if not usable:
        return None

    def key(post: PetPost):
        vision = visions.get(post.id)
        width, height = _image_size(post)
        short_edge = min(width, height)
        pixel_area = width * height
        return (bool(vision and vision.status == "ok"), short_edge > 0, short_edge, pixel_area,
                post.id == primary_post_id,
                post.last_seen_at.timestamp() if post.last_seen_at else 0)

    return max(usable, key=key)


def _case_images(posts: list[PetPost], visions: dict[int, PostVision]) -> list[dict]:
    """Return distinct usable images; repeated mirrors should not become gallery slides."""
    candidates = [post for post in posts if post.image_url and not (visions.get(post.id) and visions[post.id].status == "no_photo")]
    candidates.sort(key=lambda post: (
        bool(visions.get(post.id) and visions[post.id].status == "ok"),
        min(_image_size(post)) > 0,
        min(_image_size(post)),
        _image_size(post)[0] * _image_size(post)[1],
        post.last_seen_at.timestamp() if post.last_seen_at else 0,
    ), reverse=True)
    distinct: list[PetPost] = []
    for post in candidates:
        vision = visions.get(post.id)
        repeated = False
        for prior in distinct:
            prior_vision = visions.get(prior.id)
            if post.image_url == prior.image_url:
                repeated = True
                break
            if (vision and prior_vision and vision.status == prior_vision.status == "ok"
                    and vision.perceptual_hash and prior_vision.perceptual_hash):
                exact_fingerprint = vision.perceptual_hash == prior_vision.perceptual_hash
                near_fingerprint = compare_fingerprints(
                    vision.perceptual_hash, vision.color_histogram,
                    prior_vision.perceptual_hash, prior_vision.color_histogram,
                ) >= 0.94
                if exact_fingerprint or near_fingerprint:
                    repeated = True
                    break
        if not repeated:
            distinct.append(post)

    output = []
    for post in distinct:
        meta = _image_meta(post)
        try:
            width, height = int(meta["width"]), int(meta["height"])
        except (KeyError, TypeError, ValueError):
            width = height = None
        output.append({
            "url": post.image_url,
            "width": width,
            "height": height,
            "aspect_ratio": round(width / height, 6) if width and height else None,
            "pixel_area": width * height if width and height else None,
            "source_post_id": post.id,
            "source_platform": _raw(post).get("source_platform") or post.source.replace("_", " ").title(),
            "holding_entity": _raw(post).get("holding_entity"),
            "photo_similarity": visions.get(post.id).photo_similarity if visions.get(post.id) else None,
            "vision_status": visions.get(post.id).status if visions.get(post.id) else None,
        })
    return output


def extract_identifiers(post: PetPost):
    item = normalize_external_id(post.source, post.source_id, _raw(post))
    return [item] if item else []


def choose_primary_post(posts: list[PetPost], db: Session | None = None) -> PetPost:
    def quality(post: PetPost):
        raw = _raw(post)
        richness = sum(bool(v) for v in (post.name, post.description, post.location_text, post.source_url, raw.get("status_text")))
        vision = db.scalar(select(PostVision).where(PostVision.post_id == post.id)) if db is not None else None
        usable_image = bool(post.image_url) and not (vision and vision.status == "no_photo")
        return (usable_image, post.latitude is not None and post.longitude is not None,
                richness, bool(raw.get("holding_entity")), post.reported_at.timestamp() if post.reported_at else 0,
                len(post.description or ""), post.last_seen_at.timestamp())
    return max(posts, key=quality)


def _lifecycle_state(post: PetPost) -> str:
    value = _raw(post).get("listing_state")
    return value if value in {"active", "inactive"} else "unknown"


def _timestamp(post: PetPost):
    from datetime import timezone
    values = [value for value in (post.reported_at, post.last_seen_at, post.first_seen_at) if value is not None]
    normalized = []
    for value in values:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        normalized.append(value.timestamp())
    return max(normalized, default=0.0)


def choose_current_record(posts: list[PetPost]) -> PetPost | None:
    """Choose the freshest source record, preferring records explicitly still active."""
    active = [post for post in posts if _lifecycle_state(post) == "active"]
    pool = active or [post for post in posts if _lifecycle_state(post) != "inactive"] or posts
    return max(pool, key=lambda post: (_timestamp(post), bool(post.description), bool(post.location_text)), default=None)


def choose_current_location_record(posts: list[PetPost], outputs: dict[int, dict]) -> PetPost | None:
    candidates = [post for post in posts if _lifecycle_state(post) != "inactive" and
                  (outputs[post.id].get("map_latitude") is not None or post.location_text)]
    return max(candidates, key=lambda post: (_timestamp(post), bool(post.latitude is not None and post.longitude is not None)), default=None)


def choose_current_custody_record(posts: list[PetPost]) -> PetPost | None:
    candidates = []
    for post in posts:
        if _lifecycle_state(post) == "inactive":
            continue
        raw = _raw(post)
        if raw.get("holding_entity") or raw.get("custody_type") or raw.get("custody_label"):
            candidates.append(post)
    return max(candidates, key=_timestamp, default=None)


def choose_best_match_record(posts: list[PetPost]) -> PetPost | None:
    return max(posts, key=lambda post: (float(post.match_score or 0), _timestamp(post)), default=None)


def _merge_case_ids(db: Session, case_ids: set[int]) -> int:
    cases = list(db.scalars(select(CandidateCase).where(CandidateCase.id.in_(case_ids))))
    if not cases:
        raise ValueError("Candidate case disappeared during identity merge")
    keep = min(cases, key=lambda row: row.id)
    states = {row.review_state for row in cases}
    keep.review_state = next((state for state in REVIEW_PRECEDENCE if state in states), "new")
    for case in cases:
        if case.id == keep.id:
            continue
        for member in db.scalars(select(CandidateCasePost).where(CandidateCasePost.case_id == case.id)):
            member.case_id = keep.id
            member.match_method = "stable_animal_id"
        duplicates = []
        for identifier in db.scalars(select(CandidateIdentifier).where(CandidateIdentifier.case_id == case.id)):
            existing = db.scalar(select(CandidateIdentifier).where(
                CandidateIdentifier.case_id == keep.id,
                CandidateIdentifier.namespace == identifier.namespace,
                CandidateIdentifier.value == identifier.value,
            ))
            if existing:
                duplicates.append(identifier)
            else:
                identifier.case_id = keep.id
        for duplicate in duplicates:
            db.delete(duplicate)
        db.flush()
        db.delete(case)
    db.flush()
    return keep.id


def find_or_create_case(db: Session, post: PetPost) -> CandidateCase:
    member = db.scalar(select(CandidateCasePost).where(CandidateCasePost.post_id == post.id))
    keys = extract_identifiers(post)
    case_ids = {member.case_id} if member else set()
    for namespace, value, *_ in keys:
        identifier = db.scalar(select(CandidateIdentifier).where(
            CandidateIdentifier.namespace == namespace, CandidateIdentifier.value == value))
        if identifier:
            case_ids.add(identifier.case_id)
    if case_ids:
        case = db.get(CandidateCase, _merge_case_ids(db, case_ids))
        if member:
            member.case_id = case.id
        else:
            db.add(CandidateCasePost(case_id=case.id, post_id=post.id,
                match_method="stable_animal_id" if any(item[4] for item in keys) else "source_record"))
    else:
        case = CandidateCase(review_state=post.review_state)
        db.add(case)
        db.flush()
        db.add(CandidateCasePost(case_id=case.id, post_id=post.id,
            match_method="stable_animal_id" if any(item[4] for item in keys) else "source_record"))
    for namespace, value, kind, label, identity in keys:
        identifier = db.scalar(select(CandidateIdentifier).where(
            CandidateIdentifier.namespace == namespace, CandidateIdentifier.value == value))
        if identifier:
            identifier.case_id = case.id
        else:
            db.add(CandidateIdentifier(case_id=case.id, namespace=namespace, value=value,
                identifier_kind=kind, display_label=label, source_post_id=post.id, is_identity_key=identity))
    db.flush()
    return case


def ensure_candidate_cases(db: Session) -> int:
    posts = list(db.scalars(select(PetPost).order_by(PetPost.id)))
    for post in posts:
        find_or_create_case(db, post)
    cases = list(db.scalars(select(CandidateCase)))
    for case in cases:
        members = list(db.scalars(select(PetPost).join(CandidateCasePost, CandidateCasePost.post_id == PetPost.id)
                                   .where(CandidateCasePost.case_id == case.id)))
        if not members:
            continue
        states = {post.review_state for post in members}
        case.review_state = next((state for state in REVIEW_PRECEDENCE if state in states), "new")
        primary = choose_primary_post(members, db)
        case.primary_post_id = primary.id
        raw = _raw(primary)
        case.display_name = primary.name
        case.holding_entity = raw.get("holding_entity")
    db.commit()
    return len(cases)


def case_output(db: Session, case: CandidateCase, profile=None) -> dict:
    memberships = list(db.scalars(select(CandidateCasePost).where(CandidateCasePost.case_id == case.id)))
    posts = [db.get(PetPost, member.post_id) for member in memberships]
    posts = [post for post in posts if post]
    if not posts:
        return {"case_id": case.id, "record_count": 0, "source_records": []}
    primary = next((post for post in posts if post.id == case.primary_post_id), None) or choose_primary_post(posts, db)
    profile = profile or get_or_create_profile(db)
    visions = {row.post_id: row for row in db.scalars(select(PostVision).where(PostVision.post_id.in_([post.id for post in posts])))}
    output_by_id = {post.id: post_output(post, visions.get(post.id), profile) for post in posts}
    primary_output = output_by_id[primary.id]
    records = []
    for post in sorted(posts, key=lambda item: item.last_seen_at, reverse=True):
        raw = _raw(post)
        meta = raw.get("image_meta") if isinstance(raw.get("image_meta"), dict) else {}
        records.append({"post_id": post.id, "source": post.source,
            "source_label": "24PetConnect" if post.source in P24_SOURCES else post.source.replace("_", " ").title(),
            "source_id": post.source_id, "status": post.status, "source_url": post.source_url,
            "first_seen_at": post.first_seen_at, "last_seen_at": post.last_seen_at,
            "holding_entity": raw.get("holding_entity"), "custody_type": raw.get("custody_type"),
            "custody_label": raw.get("custody_label"), "source_platform": raw.get("source_platform"),
            "image_width": meta.get("width"), "image_height": meta.get("height"),
            "image_aspect_ratio": meta.get("aspect_ratio"),
            "listing_state": _lifecycle_state(post),
            "identifier_label": next((item[3] for item in extract_identifiers(post)), "Record ID")})
    identifiers = list(db.scalars(select(CandidateIdentifier).where(
        CandidateIdentifier.case_id == case.id, CandidateIdentifier.is_identity_key.is_(True)).order_by(CandidateIdentifier.identifier_kind, CandidateIdentifier.id)))
    case_images = _case_images(posts, visions)
    image_post = choose_primary_case_image(posts, visions, primary.id)
    primary_image = next((image for image in case_images if image["source_post_id"] == image_post.id), None) if image_post else None
    current = choose_current_record(posts)
    location_record = choose_current_location_record(posts, output_by_id)
    custody_record = choose_current_custody_record(posts)
    match_record = choose_best_match_record(posts)
    photo_score_record = max((post for post in posts if output_by_id[post.id].get("photo_similarity") is not None),
                             key=lambda post: (output_by_id[post.id]["photo_similarity"], _timestamp(post)), default=None)
    current_output = output_by_id[current.id] if current else primary_output
    location_output = output_by_id[location_record.id] if location_record else {}
    custody_raw = _raw(custody_record) if custody_record else {}
    current_location = ({
        "record_id": location_record.id,
        "location_text": location_record.location_text,
        "latitude": location_record.latitude,
        "longitude": location_record.longitude,
        "map_latitude": location_output.get("map_latitude"),
        "map_longitude": location_output.get("map_longitude"),
        "precision": location_output.get("location_precision"),
        "distance_from_home_miles": location_output.get("distance_from_home_miles"),
        "distance_is_approximate": location_output.get("distance_is_approximate", False),
    } if location_record else None)
    current_custody = ({
        "record_id": custody_record.id,
        "holding_entity": custody_raw.get("holding_entity"),
        "custody_type": custody_raw.get("custody_type"),
        "custody_label": custody_raw.get("custody_label"),
        "as_of": custody_record.last_seen_at,
    } if custody_record else None)
    return {**current_output,
        "image_url": primary_image["url"] if primary_image else None,
        "image_width": primary_image["width"] if primary_image else None,
        "image_height": primary_image["height"] if primary_image else None,
        "image_aspect_ratio": primary_image["aspect_ratio"] if primary_image else None,
        "primary_image": primary_image,
        "case_images": case_images,
        "id": case.id, "case_id": case.id, "review_state": case.review_state,
        "display_name": case.display_name or primary.name,
        "holding_entity": current_custody["holding_entity"] if current_custody else "",
        "custody_type": current_custody["custody_type"] if current_custody else None,
        "custody_label": current_custody["custody_label"] if current_custody else "Status unknown",
        "source_platform": _raw(custody_record).get("source_platform") if custody_record else None,
        "current_record_id": current.id if current else None,
        "current_location": current_location,
        "current_custody": current_custody,
        "primary_post_id": primary.id, "primary": primary_output,
        "external_ids": [{"kind": row.identifier_kind, "label": row.display_label, "value": row.value, "namespace": row.namespace} for row in identifiers],
        "record_count": len(posts), "source_records": records, "match_score": float(match_record.match_score or 0) if match_record else 0,
        "match_record_id": match_record.id if match_record else None,
        "photo_similarity": output_by_id[photo_score_record.id]["photo_similarity"] if photo_score_record else None,
        "photo_similarity_record_id": photo_score_record.id if photo_score_record else None,
        "location_record_id": location_record.id if location_record else None,
        "distance_from_home_miles": current_location["distance_from_home_miles"] if current_location else None,
        "map_latitude": current_location["map_latitude"] if current_location else None,
        "map_longitude": current_location["map_longitude"] if current_location else None,
        "location_text": current_location["location_text"] if current_location else "",
        "possible_duplicate_post_ids": sorted({output_by_id[p.id]["duplicate_of_post_id"] for p in posts if output_by_id[p.id].get("duplicate_of_post_id")})}
