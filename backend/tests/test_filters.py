from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.main import list_posts
from app.models import ArchieProfile, PetPost, PostVision


def test_hide_duplicates_keeps_records_without_images_or_vision_rows():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        no_image = PetPost(
            source="pawboost",
            source_id="no-photo",
            status="found",
            species="cat",
            sex="male",
            image_url=None,
            match_score=50,
        )
        original = PetPost(
            source="pawboost",
            source_id="original",
            status="found",
            species="cat",
            sex="male",
            image_url="https://img.example/cat.jpg",
            match_score=50,
        )
        duplicate = PetPost(
            source="pawboost",
            source_id="duplicate",
            status="found",
            species="cat",
            sex="male",
            image_url="https://img.example/cat-copy.jpg",
            match_score=50,
        )
        db.add_all([no_image, original, duplicate])
        db.flush()
        db.add(PostVision(post_id=original.id, status="ok", perceptual_hash="0" * 16))
        db.add(PostVision(post_id=duplicate.id, status="ok", perceptual_hash="0" * 16, duplicate_of_post_id=original.id))
        db.commit()

        rows = list_posts(
            review_state=None,
            min_score=0,
            source=None,
            status=None,
            sex=None,
            has_photo=None,
            reported_within_days=None,
            include_duplicates=False,
            max_distance_miles=None,
            sort="smart",
            limit=100,
            db=db,
        )
        ids = {row["source_id"] for row in rows}
        assert "no-photo" in ids
        assert "original" in ids
        assert "duplicate" not in ids


def test_trait_filter_and_city_map_fallback():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(ArchieProfile(id=1, species="cat", sex="male", altered_status="neutered", anchor_latitude=35.845701, anchor_longitude=-79.117282))
        db.add_all([
            PetPost(
                source="pawboost", source_id="orange", status="found", species="cat", sex="male",
                description="Orange striped tabby shorthaired cat with white chest", location_text="Sanford, NC 27332",
                match_score=70,
            ),
            PetPost(
                source="pawboost", source_id="black", status="found", species="cat", sex="male",
                description="Black longhaired cat", location_text="Sanford, NC 27332", match_score=30,
            ),
        ])
        db.commit()
        rows = list_posts(
            review_state=None,
            min_score=0,
            source=None,
            status=None,
            sex=None,
            has_photo=None,
            color="orange",
            reported_within_days=None,
            include_duplicates=True,
            max_distance_miles=None,
            sort="smart",
            limit=100,
            db=db,
        )
        assert [row["source_id"] for row in rows] == ["orange"]
        assert rows[0]["map_latitude"] is not None
        assert rows[0]["location_precision"] == "city"
        assert rows[0]["distance_is_approximate"] is True


def test_not_before_hides_pre_june_reports_by_default_window_logic():
    from datetime import datetime, timezone

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all([
            PetPost(
                source="pawboost", source_id="may", status="found", species="cat", sex="male",
                reported_at=datetime(2026, 5, 31, 23, 59, tzinfo=timezone.utc), match_score=50,
            ),
            PetPost(
                source="pawboost", source_id="june", status="found", species="cat", sex="male",
                reported_at=datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc), match_score=50,
            ),
        ])
        db.commit()
        rows = list_posts(
            review_state=None,
            min_score=0,
            source=None,
            status=None,
            sex=None,
            has_photo=None,
            reported_within_days=None,
            not_before=datetime(2026, 6, 1, tzinfo=timezone.utc),
            include_duplicates=True,
            max_distance_miles=None,
            sort="smart",
            limit=100,
            db=db,
        )
        assert [row["source_id"] for row in rows] == ["june"]
