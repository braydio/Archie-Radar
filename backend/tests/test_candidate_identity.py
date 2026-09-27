import json

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db import Base
from app.models import CandidateCase, CandidateCasePost, CandidateIdentifier, PetPost, PostVision
from app.candidates.identity import case_output, ensure_candidate_cases, normalize_external_id


def make_post(db: Session, source: str, source_id: str, *, score: float = 30, raw: dict | None = None,
              image_url: str | None = None, review_state: str = "new") -> PetPost:
    post = PetPost(source=source, source_id=source_id, status="found", species="cat", sex="male",
        altered_status="neutered", description="Orange tabby cat", location_text="Chapel Hill",
        match_score=score, match_reasons="[]", review_state=review_state, raw_json=json.dumps(raw or {}), image_url=image_url)
    db.add(post)
    db.flush()
    return post


def with_db(fn):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            fn(db)
    finally:
        engine.dispose()


def test_24pet_aliases_consolidate_and_backfill_is_idempotent():
    def run(db):
        make_post(db, "regional_24petconnect", "12345")
        make_post(db, "chatham_24petconnect", "a12345")
        assert ensure_candidate_cases(db) == 1
        assert ensure_candidate_cases(db) == 1
        assert db.scalar(select(func.count(CandidateCasePost.id))) == 2
        ident = db.scalar(select(CandidateIdentifier))
        assert (ident.namespace, ident.value, ident.is_identity_key) == ("24petconnect.animal_id", "A12345", True)
    with_db(run)


def test_different_animal_ids_and_same_image_do_not_merge():
    def run(db):
        make_post(db, "regional_24petconnect", "A123")
        make_post(db, "chatham_24petconnect", "A124", image_url="same.jpg")
        make_post(db, "durham_24petconnect", "A125", image_url="same.jpg")
        assert ensure_candidate_cases(db) == 3
    with_db(run)


def test_orange_county_found_shares_24pet_animal_namespace():
    def run(db):
        make_post(db, "orange_county_found", "A987")
        make_post(db, "regional_24petconnect", "987")
        assert ensure_candidate_cases(db) == 1
    with_db(run)


def test_case_score_is_max_not_sum_and_output_exposes_id_and_custody():
    def run(db):
        make_post(db, "regional_24petconnect", "A456", score=74,
            raw={"source_platform": "24PetConnect", "holding_entity": "Chatham County · Animal Resources Center",
                 "custody_type": "shelter", "custody_label": "At shelter", "status_text": "At Chatham shelter"})
        make_post(db, "chatham_24petconnect", "456", score=60)
        ensure_candidate_cases(db)
        case = db.scalar(select(CandidateCase))
        output = case_output(db, case)
        assert output["match_score"] == 74
        assert output["record_count"] == 2
        assert output["external_ids"][0]["value"] == "A456"
        assert output["holding_entity"] == "Chatham County · Animal Resources Center"
        assert output["custody_type"] == "shelter"
    with_db(run)


def test_identity_normalization_is_scoped_and_listing_ids_are_not_identity_keys():
    assert normalize_external_id("regional_24petconnect", "123")[:2] == ("24petconnect.animal_id", "A123")
    assert normalize_external_id("pawboost", "123")[4] is False
    assert normalize_external_id("unknown", "123") is None


def test_case_photo_selection_prefers_resolution_and_deduplicates_mirrors():
    def run(db):
        smaller = make_post(db, "regional_24petconnect", "A777", image_url="https://example.test/small.jpg",
            raw={"image_meta": {"width": 400, "height": 300, "pixel_area": 120000}})
        larger = make_post(db, "chatham_24petconnect", "777", image_url="https://example.test/large.jpg",
            raw={"image_meta": {"width": 1200, "height": 900, "pixel_area": 1080000}})
        db.add_all([
            PostVision(post_id=smaller.id, status="ok", perceptual_hash="abcdef0123456789", color_histogram="[1]"),
            PostVision(post_id=larger.id, status="ok", perceptual_hash="abcdef0123456789", color_histogram="[1]"),
        ])
        ensure_candidate_cases(db)
        case = db.scalar(select(CandidateCase))
        output = case_output(db, case)
        assert output["primary_image"]["url"] == larger.image_url
        assert (output["image_width"], output["image_height"]) == (1200, 900)
        assert len(output["case_images"]) == 1
    with_db(run)
