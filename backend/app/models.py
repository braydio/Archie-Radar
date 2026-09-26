from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PetPost(Base):
    __tablename__ = "pet_posts"
    __table_args__ = (UniqueConstraint("source", "source_id", name="uq_pet_posts_source_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(40), index=True)
    source_id: Mapped[str] = mapped_column(String(180))
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(String(30), default="unknown", index=True)
    species: Mapped[str] = mapped_column(String(30), default="cat", index=True)
    name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    sex: Mapped[str] = mapped_column(String(20), default="unknown")
    altered_status: Mapped[str] = mapped_column(String(20), default="unknown")
    description: Mapped[str] = mapped_column(Text, default="")
    location_text: Mapped[str] = mapped_column(Text, default="")
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    reported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    match_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    match_reasons: Mapped[str] = mapped_column(Text, default="[]")
    review_state: Mapped[str] = mapped_column(String(30), default="new", index=True)
    raw_json: Mapped[str] = mapped_column(Text, default="{}")


class ArchieProfile(Base):
    __tablename__ = "archie_profile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    species: Mapped[str] = mapped_column(String(30), default="cat")
    sex: Mapped[str] = mapped_column(String(20), default="male")
    altered_status: Mapped[str] = mapped_column(String(20), default="neutered")
    trait_keywords: Mapped[str] = mapped_column(Text, default="")
    anchor_latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    anchor_longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")


class ArchieReferencePhoto(Base):
    __tablename__ = "archie_reference_photos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    label: Mapped[str] = mapped_column(String(160), default="Archie reference")
    filename: Mapped[str] = mapped_column(String(240))
    media_url: Mapped[str] = mapped_column(Text)
    perceptual_hash: Mapped[str] = mapped_column(String(32), index=True)
    color_histogram: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PostVision(Base):
    __tablename__ = "post_vision"
    __table_args__ = (UniqueConstraint("post_id", name="uq_post_vision_post_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("pet_posts.id", ondelete="CASCADE"), index=True)
    perceptual_hash: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    color_histogram: Mapped[str] = mapped_column(Text, default="[]")
    photo_similarity: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    duplicate_of_post_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    error: Mapped[str] = mapped_column(Text, default="")
    analyzed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SurveyorMapObject(Base):
    __tablename__ = "surveyor_map_objects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    object_type: Mapped[str] = mapped_column(String(40), index=True)
    subtype: Mapped[str | None] = mapped_column(String(60), nullable=True, index=True)
    name: Mapped[str | None] = mapped_column(String(180), nullable=True)
    geometry_geojson: Mapped[str] = mapped_column(Text)
    style_json: Mapped[str] = mapped_column(Text, default="{}")
    properties_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    confidence: Mapped[str | None] = mapped_column(String(30), nullable=True)
    epistemic_state: Mapped[str | None] = mapped_column(String(30), nullable=True)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    centroid_lat: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    centroid_lon: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    bbox_west: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    bbox_south: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    bbox_east: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    bbox_north: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
