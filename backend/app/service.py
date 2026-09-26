from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .matcher import haversine_miles, score_candidate
from .local_places import approximate_coordinates
from .traits import archie_trait_assessment, extract_traits
from .models import ArchieProfile, ArchieReferencePhoto, PetPost, PostVision
from .schemas import PetPostIn
from .vision import compare_fingerprints


def get_or_create_profile(db: Session) -> ArchieProfile:
    profile = db.get(ArchieProfile, 1)
    default_keywords = "orange, ginger, striped, tabby, white chest, short hair, shorthair, no collar, not microchipped"
    default_notes = (
        "Archie: approximately 8-year-old neutered male orange striped/tabby shorthaired cat; "
        "white chest, no white on belly; not microchipped; no collar when lost; missing since late June 2026."
    )
    if profile is None:
        profile = ArchieProfile(
            id=1, species="cat", sex="male", altered_status="neutered",
            trait_keywords=default_keywords, notes=default_notes,
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)
    else:
        changed = False
        if not (profile.trait_keywords or "").strip():
            profile.trait_keywords = default_keywords
            changed = True
        if not (profile.notes or "").strip():
            profile.notes = default_notes
            changed = True
        if changed:
            db.commit()
            db.refresh(profile)
    return profile


def post_as_input(row: PetPost) -> PetPostIn:
    return PetPostIn(
        source=row.source,
        source_id=row.source_id,
        source_url=row.source_url,
        status=row.status,
        species=row.species,
        name=row.name,
        sex=row.sex,
        altered_status=row.altered_status,
        description=row.description,
        location_text=row.location_text,
        latitude=row.latitude,
        longitude=row.longitude,
        image_url=row.image_url,
        reported_at=row.reported_at,
    )


def upsert_posts(db: Session, posts: list[PetPostIn]) -> dict:
    profile = get_or_create_profile(db)
    created = updated = 0
    now = datetime.now(timezone.utc)
    post_ids: list[int] = []

    for incoming in posts:
        existing = db.scalar(
            select(PetPost).where(
                PetPost.source == incoming.source,
                PetPost.source_id == incoming.source_id,
            )
        )
        photo_similarity = None
        if existing:
            vision = db.scalar(select(PostVision).where(PostVision.post_id == existing.id))
            photo_similarity = vision.photo_similarity if vision else None
        score, reasons = score_candidate(incoming, profile, photo_similarity)
        values = dict(
            source_url=incoming.source_url,
            status=incoming.status,
            species=incoming.species,
            name=incoming.name,
            sex=incoming.sex,
            altered_status=incoming.altered_status,
            description=incoming.description,
            location_text=incoming.location_text,
            latitude=incoming.latitude,
            longitude=incoming.longitude,
            image_url=incoming.image_url,
            reported_at=incoming.reported_at,
            last_seen_at=now,
            match_score=score,
            match_reasons=json.dumps(reasons),
            raw_json=json.dumps(incoming.raw),
        )
        if existing:
            old_image = existing.image_url
            # Listing pages are often less complete than detail pages. A later scan
            # must not erase richer data we already captured simply because a card
            # omitted it this time.
            if (incoming.raw or {}).get("image_confirmed_missing"):
                # A detail page is authoritative enough to clear a stale listing
                # placeholder left by older Archie Radar versions.
                values["image_url"] = None
            elif not incoming.image_url and existing.image_url:
                values["image_url"] = existing.image_url
            if incoming.reported_at is None and existing.reported_at is not None:
                values["reported_at"] = existing.reported_at
            if not incoming.description and existing.description:
                values["description"] = existing.description
            if not incoming.location_text and existing.location_text:
                values["location_text"] = existing.location_text
            try:
                previous_raw = json.loads(existing.raw_json or "{}")
            except (TypeError, json.JSONDecodeError):
                previous_raw = {}
            merged_raw = dict(previous_raw)
            merged_raw.update(incoming.raw or {})
            values["raw_json"] = json.dumps(merged_raw)

            for key, value in values.items():
                setattr(existing, key, value)
            if old_image != values.get("image_url"):
                vision = db.scalar(select(PostVision).where(PostVision.post_id == existing.id))
                if vision:
                    db.delete(vision)
            updated += 1
            db.flush()
            post_ids.append(existing.id)
        else:
            row = PetPost(source=incoming.source, source_id=incoming.source_id, **values)
            db.add(row)
            db.flush()
            created += 1
            post_ids.append(row.id)

    db.commit()
    # Keep the additive case index current as new source records arrive. This is
    # intentionally identifier-driven; image similarity never merges identities.
    from .candidates.identity import ensure_candidate_cases
    ensure_candidate_cases(db)
    return {"created": created, "updated": updated, "total": len(posts), "post_ids": post_ids}


def rescore_post(db: Session, row: PetPost, photo_similarity: float | None = None) -> None:
    profile = get_or_create_profile(db)
    score, reasons = score_candidate(post_as_input(row), profile, photo_similarity)
    row.match_score = score
    row.match_reasons = json.dumps(reasons)


def rescore_all(db: Session) -> int:
    rows = list(db.scalars(select(PetPost)))
    for row in rows:
        vision = db.scalar(select(PostVision).where(PostVision.post_id == row.id))
        rescore_post(db, row, vision.photo_similarity if vision else None)
    db.commit()
    return len(rows)


def best_reference_similarity(db: Session, vision: PostVision) -> float | None:
    if not vision.perceptual_hash:
        return None
    refs = list(db.scalars(select(ArchieReferencePhoto)))
    if not refs:
        return None
    values = [
        compare_fingerprints(
            vision.perceptual_hash,
            vision.color_histogram,
            ref.perceptual_hash,
            ref.color_histogram,
        )
        for ref in refs
    ]
    return max(values) if values else None


def recompute_vision_matches(db: Session) -> int:
    """Recompare stored candidate fingerprints after reference photos change."""
    visions = list(db.scalars(select(PostVision).where(PostVision.status == "ok")))
    for vision in visions:
        vision.photo_similarity = best_reference_similarity(db, vision)
        row = db.get(PetPost, vision.post_id)
        if row:
            rescore_post(db, row, vision.photo_similarity)
    db.commit()
    return len(visions)


def post_output(row: PetPost, vision: PostVision | None = None, profile: ArchieProfile | None = None) -> dict:
    precise = row.latitude is not None and row.longitude is not None
    map_latitude = row.latitude
    map_longitude = row.longitude
    location_precision = "exact" if precise else None
    approximate_place = None
    if not precise:
        approx = approximate_coordinates(row.location_text)
        if approx:
            map_latitude, map_longitude, approximate_place = approx
            location_precision = "city"

    distance = None
    if (
        profile is not None
        and profile.anchor_latitude is not None
        and profile.anchor_longitude is not None
        and map_latitude is not None
        and map_longitude is not None
    ):
        distance = round(
            haversine_miles(profile.anchor_latitude, profile.anchor_longitude, map_latitude, map_longitude),
            2,
        )

    try:
        raw = json.loads(row.raw_json or "{}")
    except (TypeError, json.JSONDecodeError):
        raw = {}

    nearest_landmark = (raw.get("nearest_landmark") or "").strip() or None
    finder_message = (raw.get("finder_message") or "").strip() or None
    contact_info = (raw.get("contact_info") or "").strip() or None
    contact_url = (raw.get("contact_url") or "").strip() or None
    if raw.get("contact_available") and not contact_url:
        contact_url = row.source_url
        if not contact_info:
            contact_info = "Contact the finder through the original listing"
    elif row.status == "found_with_finder" and row.source_url and not contact_url:
        contact_url = row.source_url
        contact_info = contact_info or "Finder contact details are on the original listing"

    # A source placeholder may still be stored in the database from an older scan.
    # Once vision classifies it as no-photo, never show it or treat it as a photo.
    display_image_url = None if vision and vision.status == "no_photo" else row.image_url

    trait_text = " ".join(filter(None, [row.name or "", row.description, str(raw.get("breed") or ""), str(raw.get("listing_text") or "")]))
    parsed_traits = extract_traits(trait_text, row.altered_status)
    trait_assessment = archie_trait_assessment(parsed_traits, row.sex)

    # Prefer a true source-posted timestamp when a connector captured one separately.
    posted_at = raw.get("posted_at") or raw.get("source_posted_at")
    if posted_at:
        try:
            if isinstance(posted_at, str):
                posted_at = datetime.fromisoformat(posted_at.replace("Z", "+00:00"))
        except Exception:
            posted_at = None
    return {
        "id": row.id,
        "source": row.source,
        "source_id": row.source_id,
        "source_url": row.source_url,
        "status": row.status,
        "species": row.species,
        "name": row.name,
        "sex": row.sex,
        "altered_status": row.altered_status,
        "description": row.description,
        "location_text": row.location_text,
        "latitude": row.latitude,
        "longitude": row.longitude,
        "map_latitude": map_latitude,
        "map_longitude": map_longitude,
        "location_precision": location_precision,
        "approximate_place": approximate_place,
        "distance_from_home_miles": distance,
        "distance_is_approximate": bool(distance is not None and location_precision == "city"),
        "image_url": display_image_url,
        "reported_at": row.reported_at,
        "posted_at": posted_at,
        "first_seen_at": row.first_seen_at,
        "last_seen_at": row.last_seen_at,
        "match_score": row.match_score,
        "match_reasons": row.match_reasons,
        "review_state": row.review_state,
        "photo_similarity": vision.photo_similarity if vision and vision.status == "ok" else None,
        "duplicate_of_post_id": vision.duplicate_of_post_id if vision and vision.status == "ok" else None,
        "vision_status": vision.status if vision else None,
        "nearest_landmark": nearest_landmark,
        "finder_message": finder_message,
        "contact_info": contact_info,
        "contact_url": contact_url,
        "parsed_traits": parsed_traits,
        "archie_trait_matches": trait_assessment["matches"],
        "archie_trait_conflicts": trait_assessment["conflicts"],
    }
