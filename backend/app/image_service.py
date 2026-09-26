from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import PetPost, PostVision
from .service import best_reference_similarity, rescore_post
from .vision import compare_fingerprints, fingerprint_image, looks_like_placeholder_image


def _obvious_placeholder_url(url: str) -> bool:
    value = (url or "").lower()
    path = urlparse(value).path
    bad_tokens = (
        "placeholder", "no-photo", "no_photo", "nophoto", "default-pet",
        "default_pet", "pawboost-white-dog-hero", "logo", "avatar-default",
    )
    return any(token in path for token in bad_tokens)


async def analyze_post_image(
    db: Session,
    post_id: int,
    max_bytes: int = 8_000_000,
) -> PostVision | None:
    post = db.get(PetPost, post_id)
    if not post or not post.image_url:
        return None

    vision = db.scalar(select(PostVision).where(PostVision.post_id == post_id))
    if vision and vision.status in {"ok", "no_photo"}:
        return vision
    if vision is None:
        vision = PostVision(post_id=post_id, status="pending")
        db.add(vision)
        db.flush()

    try:
        if _obvious_placeholder_url(post.image_url):
            vision.status = "no_photo"
            vision.error = "Source image appears to be placeholder artwork"
            vision.perceptual_hash = None
            vision.color_histogram = "[]"
            vision.photo_similarity = None
            vision.duplicate_of_post_id = None
            vision.analyzed_at = datetime.now(timezone.utc)
            rescore_post(db, post, None)
            db.commit()
            return vision

        headers = {"User-Agent": "ArchieRadar/0.7 (+lost-pet-reunion-project)"}
        async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=20) as client:
            async with client.stream("GET", post.image_url) as response:
                response.raise_for_status()
                content_type = response.headers.get("content-type", "")
                if content_type and not content_type.lower().startswith("image/"):
                    raise ValueError(f"Not an image response ({content_type})")
                chunks: list[bytes] = []
                total = 0
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > max_bytes:
                        raise ValueError("Candidate image exceeds configured size limit")
                    chunks.append(chunk)
        image_bytes = b"".join(chunks)

        # Critical dedupe guard: a source's generic no-photo artwork must never
        # cause every imageless animal to be marked as a repost of candidate #1.
        if looks_like_placeholder_image(image_bytes):
            vision.status = "no_photo"
            vision.error = "Low-information source placeholder ignored"
            vision.perceptual_hash = None
            vision.color_histogram = "[]"
            vision.photo_similarity = None
            vision.duplicate_of_post_id = None
            vision.analyzed_at = datetime.now(timezone.utc)
            rescore_post(db, post, None)
            db.commit()
            db.refresh(vision)
            return vision

        fp = fingerprint_image(image_bytes)
        vision.perceptual_hash = fp.dhash
        vision.color_histogram = fp.histogram_json()
        vision.status = "ok"
        vision.error = ""
        vision.analyzed_at = datetime.now(timezone.utc)

        # Find near-identical reused photos from an earlier post. This is for
        # deduplication, not identity matching. Only real, successfully analyzed
        # images participate.
        older = list(
            db.scalars(
                select(PostVision).where(
                    PostVision.post_id != post_id,
                    PostVision.status == "ok",
                    PostVision.perceptual_hash.is_not(None),
                )
            )
        )
        best_dup: tuple[float, int] | None = None
        for other in older:
            sim = compare_fingerprints(
                vision.perceptual_hash,
                vision.color_histogram,
                other.perceptual_hash or "",
                other.color_histogram,
            )
            if sim >= 0.94 and (best_dup is None or sim > best_dup[0]):
                best_dup = (sim, other.post_id)
        vision.duplicate_of_post_id = best_dup[1] if best_dup else None
        vision.photo_similarity = best_reference_similarity(db, vision)
        rescore_post(db, post, vision.photo_similarity)
        db.commit()
        db.refresh(vision)
        return vision
    except Exception as exc:
        vision.status = "error"
        vision.error = str(exc)[:1000]
        vision.analyzed_at = datetime.now(timezone.utc)
        db.commit()
        return vision


async def analyze_post_ids(db: Session, post_ids: list[int], max_bytes: int = 8_000_000) -> dict[str, int]:
    ok = errors = skipped = no_photo = 0
    for post_id in post_ids:
        post = db.get(PetPost, post_id)
        if not post or not post.image_url:
            skipped += 1
            continue
        result = await analyze_post_image(db, post_id, max_bytes=max_bytes)
        if result and result.status == "ok":
            ok += 1
        elif result and result.status == "no_photo":
            no_photo += 1
        else:
            errors += 1
    return {"ok": ok, "no_photo": no_photo, "errors": errors, "skipped": skipped}
