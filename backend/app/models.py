from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
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


class CandidateCase(Base):
    __tablename__ = "candidate_cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    review_state: Mapped[str] = mapped_column(String(30), default="new", index=True)
    display_name: Mapped[str | None] = mapped_column(String(180), nullable=True)
    holding_entity: Mapped[str | None] = mapped_column(String(240), nullable=True)
    custody_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    primary_post_id: Mapped[int | None] = mapped_column(ForeignKey("pet_posts.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class CandidateCasePost(Base):
    __tablename__ = "candidate_case_posts"
    __table_args__ = (UniqueConstraint("post_id", name="uq_candidate_case_posts_post_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("candidate_cases.id", ondelete="CASCADE"), index=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("pet_posts.id", ondelete="CASCADE"), index=True)
    match_method: Mapped[str] = mapped_column(String(40), default="source_record")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CandidateIdentifier(Base):
    __tablename__ = "candidate_identifiers"
    __table_args__ = (UniqueConstraint("namespace", "value", name="uq_candidate_identifiers_namespace_value"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("candidate_cases.id", ondelete="CASCADE"), index=True)
    namespace: Mapped[str] = mapped_column(String(120), index=True)
    value: Mapped[str] = mapped_column(String(240))
    identifier_kind: Mapped[str] = mapped_column(String(40), default="other")
    display_label: Mapped[str] = mapped_column(String(100), default="Identifier")
    source_post_id: Mapped[int | None] = mapped_column(ForeignKey("pet_posts.id", ondelete="SET NULL"), nullable=True)
    is_identity_key: Mapped[bool] = mapped_column(default=False, index=True)


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


class SurveyorTrailCamera(Base):
    __tablename__ = "surveyor_trail_cameras"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    map_object_id: Mapped[int] = mapped_column(ForeignKey("surveyor_map_objects.id", ondelete="CASCADE"), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(180))
    camera_model: Mapped[str] = mapped_column(String(120), default="")
    power_type: Mapped[str] = mapped_column(String(60), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SurveyorCameraPlacement(Base):
    __tablename__ = "surveyor_camera_placements"
    __table_args__ = (Index("uq_surveyor_camera_active_placement", "camera_id", unique=True, sqlite_where=text("removed_at IS NULL")),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    camera_id: Mapped[int] = mapped_column(ForeignKey("surveyor_trail_cameras.id", ondelete="CASCADE"), index=True)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    heading_degrees: Mapped[float] = mapped_column(Float, default=0)
    fov_degrees: Mapped[float] = mapped_column(Float, default=60)
    range_meters: Mapped[float] = mapped_column(Float, default=15)
    installed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SurveyorSearchSession(Base):
    __tablename__ = "surveyor_search_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    method: Mapped[str] = mapped_column(String(50), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    track_geojson: Mapped[str | None] = mapped_column(Text, nullable=True)
    distance_meters: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    result_summary: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SurveyorEvent(Base):
    __tablename__ = "surveyor_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_type: Mapped[str] = mapped_column(String(60), index=True)
    entity_type: Mapped[str] = mapped_column(String(50), index=True)
    entity_id: Mapped[str] = mapped_column(String(100), index=True)
    action: Mapped[str] = mapped_column(String(120))
    before_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    after_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    reversible: Mapped[bool] = mapped_column(default=False)
    notes: Mapped[str] = mapped_column(Text, default="")


class SurveyorAttachment(Base):
    __tablename__ = "surveyor_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    map_object_id: Mapped[int | None] = mapped_column(ForeignKey("surveyor_map_objects.id", ondelete="CASCADE"), nullable=True, index=True)
    search_session_id: Mapped[int | None] = mapped_column(ForeignKey("surveyor_search_sessions.id", ondelete="CASCADE"), nullable=True, index=True)
    attachment_type: Mapped[str] = mapped_column(String(30))
    storage_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    caption: Mapped[str] = mapped_column(Text, default="")
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source: Mapped[str] = mapped_column(String(120), default="user upload")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SurveyorAttachmentLink(Base):
    __tablename__ = "surveyor_attachment_links"
    __table_args__ = (UniqueConstraint("attachment_id", "entity_type", "entity_id", "relationship", name="uq_surveyor_attachment_link"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    attachment_id: Mapped[int] = mapped_column(ForeignKey("surveyor_attachments.id", ondelete="CASCADE"), index=True)
    entity_type: Mapped[str] = mapped_column(String(40), index=True)
    entity_id: Mapped[int] = mapped_column(Integer, index=True)
    relationship: Mapped[str] = mapped_column(String(40), default="related")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SurveyorObjectLink(Base):
    __tablename__ = "surveyor_object_links"
    __table_args__ = (UniqueConstraint("source_object_id", "target_object_id", "link_type", name="uq_surveyor_object_link"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_object_id: Mapped[int] = mapped_column(ForeignKey("surveyor_map_objects.id", ondelete="CASCADE"), index=True)
    target_object_id: Mapped[int] = mapped_column(ForeignKey("surveyor_map_objects.id", ondelete="CASCADE"), index=True)
    link_type: Mapped[str] = mapped_column(String(50), default="association", index=True)
    line_style: Mapped[str] = mapped_column(String(30), default="dotted")
    label: Mapped[str] = mapped_column(String(180), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    vertices_geojson: Mapped[str | None] = mapped_column(Text, nullable=True)
    properties_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class SurveyorAccessRecord(Base):
    __tablename__ = "surveyor_access_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    map_object_id: Mapped[int] = mapped_column(ForeignKey("surveyor_map_objects.id", ondelete="CASCADE"), unique=True, index=True)
    access_status: Mapped[str] = mapped_column(String(40), default="unknown", index=True)
    dog_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    outdoor_cat_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    camera_permission: Mapped[str] = mapped_column(String(30), default="unknown")
    trap_permission: Mapped[str] = mapped_column(String(30), default="unknown")
    search_permission: Mapped[str] = mapped_column(String(30), default="unknown")
    contact_name: Mapped[str] = mapped_column(String(180), default="")
    contact_method: Mapped[str] = mapped_column(String(80), default="")
    last_contact_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    next_followup_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    contact_notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class SurveyorTask(Base):
    __tablename__ = "surveyor_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(240))
    task_type: Mapped[str] = mapped_column(String(40), default="other", index=True)
    status: Mapped[str] = mapped_column(String(30), default="open", index=True)
    priority: Mapped[str] = mapped_column(String(30), default="normal", index=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    map_object_id: Mapped[int | None] = mapped_column(ForeignKey("surveyor_map_objects.id", ondelete="SET NULL"), nullable=True, index=True)
    search_session_id: Mapped[int | None] = mapped_column(ForeignKey("surveyor_search_sessions.id", ondelete="SET NULL"), nullable=True, index=True)
    candidate_post_id: Mapped[int | None] = mapped_column(ForeignKey("pet_posts.id", ondelete="SET NULL"), nullable=True, index=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
