import json
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.candidates.identity import case_output
from app.db import Base
from app.models import ArchieProfile, CandidateCase, CandidateCasePost, PetPost


def test_case_projection_keeps_current_location_and_distance_with_same_record():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            profile = ArchieProfile(anchor_latitude=35.9, anchor_longitude=-79.0)
            older = PetPost(
                source="regional_24petconnect", source_id="A123", status="shelter_intake",
                name="Found cat", location_text="Shelter, 12 miles away", latitude=36.0,
                longitude=-79.0, image_url="https://example.test/older.jpg",
                reported_at=datetime(2026, 9, 20, tzinfo=timezone.utc), match_score=62,
                raw_json=json.dumps({"holding_entity": "County Shelter", "custody_type": "shelter",
                                    "custody_label": "At shelter", "image_meta": {"width": 1600, "height": 1200}}),
            )
            newer = PetPost(
                source="chatham_24petconnect", source_id="A123", status="found_with_finder",
                name="Found cat", location_text="Finder, 4 miles away", latitude=35.94,
                longitude=-79.0, image_url=None,
                reported_at=datetime(2026, 9, 26, tzinfo=timezone.utc), match_score=71,
                raw_json=json.dumps({"custody_type": "finder", "custody_label": "With finder"}),
            )
            case = CandidateCase(review_state="new")
            db.add_all([profile, older, newer, case])
            db.flush()
            case.primary_post_id = older.id
            db.add_all([
                CandidateCasePost(case_id=case.id, post_id=older.id),
                CandidateCasePost(case_id=case.id, post_id=newer.id),
            ])
            db.commit()

            result = case_output(db, case, profile)

            assert result["primary_image"]["source_post_id"] == older.id
            assert result["current_record_id"] == newer.id
            assert result["current_location"]["record_id"] == newer.id
            assert result["location_text"] == "Finder, 4 miles away"
            assert result["distance_from_home_miles"] == result["current_location"]["distance_from_home_miles"]
            assert result["distance_from_home_miles"] < 4
            assert result["current_custody"]["record_id"] == newer.id
            assert result["custody_label"] == "With finder"
            assert result["match_record_id"] == newer.id
    finally:
        engine.dispose()
