from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


ReviewState = Literal["new", "possible", "dismissed", "confirmed", "needs_review"]


class PetPostIn(BaseModel):
    source: str
    source_id: str
    source_url: str | None = None
    status: str = "unknown"
    species: str = "cat"
    name: str | None = None
    sex: str = "unknown"
    altered_status: str = "unknown"
    description: str = ""
    location_text: str = ""
    latitude: float | None = None
    longitude: float | None = None
    image_url: str | None = None
    reported_at: datetime | None = None
    raw: dict = Field(default_factory=dict)


class FacebookBridgeIn(BaseModel):
    source_id: str
    source_url: str | None = None
    status: str = "unknown"
    species: str = "cat"
    name: str | None = None
    sex: str = "unknown"
    altered_status: str = "unknown"
    description: str = ""
    location_text: str = ""
    latitude: float | None = None
    longitude: float | None = None
    image_url: str | None = None
    reported_at: datetime | None = None


class PetPostOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    source_id: str
    source_url: str | None
    status: str
    species: str
    name: str | None
    sex: str
    altered_status: str
    description: str
    location_text: str
    latitude: float | None
    longitude: float | None
    map_latitude: float | None = None
    map_longitude: float | None = None
    location_precision: str | None = None
    approximate_place: str | None = None
    distance_from_home_miles: float | None = None
    distance_is_approximate: bool = False
    image_url: str | None
    reported_at: datetime | None
    posted_at: datetime | None = None
    first_seen_at: datetime
    last_seen_at: datetime
    match_score: float
    match_reasons: str
    review_state: str
    photo_similarity: float | None = None
    duplicate_of_post_id: int | None = None
    vision_status: str | None = None
    nearest_landmark: str | None = None
    finder_message: str | None = None
    contact_info: str | None = None
    contact_url: str | None = None
    parsed_traits: dict = Field(default_factory=dict)
    archie_trait_matches: list[str] = Field(default_factory=list)
    archie_trait_conflicts: list[str] = Field(default_factory=list)


class ProfileIn(BaseModel):
    species: str = "cat"
    sex: str = "male"
    altered_status: str = "neutered"
    trait_keywords: str = ""
    anchor_latitude: float | None = None
    anchor_longitude: float | None = None
    notes: str = ""


class ProfileOut(ProfileIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class SearchConfigOut(BaseModel):
    home_address: str
    home_latitude: float
    home_longitude: float
    search_radius_miles: float
    pawboost_areas: list[str]
    geocoding_enabled: bool
    orange_county_enabled: bool
    enabled_sources: list[str] = Field(default_factory=list)
    source_statuses: list[dict] = Field(default_factory=list)
    archie_profile_summary: dict = Field(default_factory=dict)
    default_not_before: datetime | None = None


class ReferencePhotoIn(BaseModel):
    label: str = "Archie reference"
    filename: str = "archie.jpg"
    data_url: str


class ReferencePhotoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    label: str
    filename: str
    media_url: str
    created_at: datetime


class ReviewIn(BaseModel):
    review_state: ReviewState


class SurveyorObjectIn(BaseModel):
    object_type: Literal["pin", "note", "zone", "corridor", "trail_camera", "evidence", "access", "search_location"]
    subtype: str | None = Field(default=None, max_length=60)
    name: str | None = Field(default=None, max_length=180)
    geometry: dict
    style: dict = Field(default_factory=dict)
    properties: dict = Field(default_factory=dict)
    status: str | None = None
    confidence: Literal["confirmed", "strong", "possible", "uncertain", "context"] | None = None
    epistemic_state: Literal["observed", "inferred", "hypothesis", "planning"] | None = None
    occurred_at: datetime | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    notes: str = Field(default="", max_length=20000)


class SurveyorObjectPatch(BaseModel):
    object_type: Literal["pin", "note", "zone", "corridor", "trail_camera", "evidence", "access", "search_location"] | None = None
    subtype: str | None = Field(default=None, max_length=60)
    name: str | None = Field(default=None, max_length=180)
    geometry: dict | None = None
    style: dict | None = None
    properties: dict | None = None
    status: str | None = None
    confidence: Literal["confirmed", "strong", "possible", "uncertain", "context"] | None = None
    epistemic_state: Literal["observed", "inferred", "hypothesis", "planning"] | None = None
    occurred_at: datetime | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    notes: str | None = Field(default=None, max_length=20000)


class SurveyorObjectOut(BaseModel):
    id: int
    object_type: str
    subtype: str | None
    name: str | None
    geometry: dict
    style: dict
    properties: dict
    status: str | None
    confidence: str | None
    epistemic_state: str | None
    occurred_at: datetime | None
    valid_from: datetime | None
    valid_to: datetime | None
    notes: str
    centroid_lat: float | None
    centroid_lon: float | None
    bbox: list[float] | None
    created_at: datetime
    updated_at: datetime


class SurveyorCameraIn(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    heading_degrees: float = Field(default=0, ge=0, le=360)
    fov_degrees: float = Field(default=60, ge=1, le=179)
    range_meters: float = Field(default=15, gt=0, le=5000)
    camera_model: str = ""
    power_type: str = ""
    notes: str = ""
    installed_at: datetime | None = None


class SurveyorCameraUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=180)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    heading_degrees: float | None = Field(default=None, ge=0, le=360)
    fov_degrees: float | None = Field(default=None, ge=1, le=179)
    range_meters: float | None = Field(default=None, gt=0, le=5000)
    camera_model: str | None = None
    power_type: str | None = None
    notes: str | None = None
    save_as_new_placement: bool = False


class SurveyorCameraOut(BaseModel):
    id: int
    map_object_id: int
    name: str
    camera_model: str
    power_type: str
    notes: str
    retired_at: datetime | None
    placement: dict | None
    history: list[dict]


class SurveyorSessionIn(BaseModel):
    method: Literal["walking", "bike", "car", "stationary_observation", "camera_maintenance", "flyering", "other"]
    started_at: datetime | None = None
    notes: str = ""


class SurveyorSessionUpdate(BaseModel):
    ended_at: datetime | None = None
    track_geojson: dict | None = None
    distance_meters: float | None = Field(default=None, ge=0)
    notes: str | None = None
    result_summary: str | None = None


class SurveyorSessionCheckpoint(BaseModel):
    track_geojson: dict
    distance_meters: float = Field(ge=0)


class SurveyorSessionOut(BaseModel):
    id: int
    method: str
    started_at: datetime
    ended_at: datetime | None
    track_geojson: dict | None
    distance_meters: float | None
    notes: str
    result_summary: str
    created_at: datetime


class SurveyorCoverageIn(BaseModel):
    buffer_meters: float = Field(ge=2, le=250)
    name: str = Field(default="Searched route", max_length=180)
    notes: str = Field(default="", max_length=20000)


class SurveyorEventOut(BaseModel):
    id: int
    event_type: str
    entity_type: str
    entity_id: str
    action: str
    before: dict | None
    after: dict | None
    occurred_at: datetime
    created_at: datetime
    reversible: bool
    notes: str


class SurveyorAttachmentOut(BaseModel):
    id: int
    map_object_id: int | None
    search_session_id: int | None
    attachment_type: str
    original_filename: str
    mime_type: str
    duration_seconds: float | None
    width: int | None
    height: int | None
    aspect_ratio: float | None = None
    file_size_bytes: int
    latitude: float | None
    longitude: float | None
    media_url: str | None
    preview_url: str | None
    thumbnail_url: str | None
    download_url: str | None
    external_url: str | None
    caption: str
    notes: str
    observed_at: datetime | None
    source: str
    metadata: dict
    created_at: datetime
    map_object_name: str | None = None
    camera_name: str | None = None
    session_label: str | None = None
    candidate_case_id: int | None = None
    map_object_type: str | None = None
    map_object_id: int | None = None
    camera_id: int | None = None
    linked_entities: list[dict] = Field(default_factory=list)


class SurveyorMediaExportIn(BaseModel):
    attachment_ids: list[int] = Field(min_length=1, max_length=2000)
    include_originals: bool = True
    include_manifest_json: bool = True
    include_manifest_csv: bool = True
    include_context: bool = True
    include_exact_coordinates: bool = True


class SurveyorAttachmentLinkIn(BaseModel):
    entity_type: Literal["map_object", "search_session", "camera", "candidate_case"]
    entity_id: int
    relationship: Literal["related", "captured_during", "evidence_for", "camera_capture", "source_media"] = "related"


class SurveyorAttachmentLinkOut(BaseModel):
    id: int
    attachment_id: int
    entity_type: str
    entity_id: int
    relationship: str
    label: str
    created_at: datetime


class SurveyorLinkIn(BaseModel):
    source_object_id: int
    target_object_id: int
    link_type: Literal["observed_movement", "hypothesized_movement", "association", "possible_corridor", "evidence_for", "evidence_against", "custom"] = "association"
    line_style: Literal["solid", "dashed", "dotted", "double_arrow"] = "dotted"
    label: str = ""
    notes: str = ""
    vertices: list[list[float]] = Field(default_factory=list)


class SurveyorLinkPatch(BaseModel):
    link_type: Literal["observed_movement", "hypothesized_movement", "association", "possible_corridor", "evidence_for", "evidence_against", "custom"] | None = None
    line_style: Literal["solid", "dashed", "dotted", "double_arrow"] | None = None
    label: str | None = None
    notes: str | None = None
    vertices: list[list[float]] | None = None


class SurveyorLinkOut(BaseModel):
    id: int
    source_object_id: int
    target_object_id: int
    link_type: str
    line_style: str
    label: str
    notes: str
    geometry: dict
    created_at: datetime
    updated_at: datetime


AccessStatus = Literal["unknown", "no_answer", "permission_granted", "permission_denied", "partial_permission", "do_not_contact"]
PermissionValue = Literal["unknown", "yes", "no"]


class SurveyorAccessFields(BaseModel):
    access_status: AccessStatus = "unknown"
    dog_count: int | None = Field(default=None, ge=0)
    outdoor_cat_count: int | None = Field(default=None, ge=0)
    camera_permission: PermissionValue = "unknown"
    trap_permission: PermissionValue = "unknown"
    search_permission: PermissionValue = "unknown"
    contact_name: str = Field(default="", max_length=180)
    contact_method: str = Field(default="", max_length=80)
    last_contact_at: datetime | None = None
    next_followup_at: datetime | None = None
    contact_notes: str = Field(default="", max_length=20000)


class SurveyorAccessIn(SurveyorAccessFields):
    longitude: float = Field(ge=-180, le=180)
    latitude: float = Field(ge=-90, le=90)
    name: str = Field(default="Property access", max_length=180)


class SurveyorAccessPatch(BaseModel):
    access_status: AccessStatus | None = None
    dog_count: int | None = Field(default=None, ge=0)
    outdoor_cat_count: int | None = Field(default=None, ge=0)
    camera_permission: PermissionValue | None = None
    trap_permission: PermissionValue | None = None
    search_permission: PermissionValue | None = None
    contact_name: str | None = Field(default=None, max_length=180)
    contact_method: str | None = Field(default=None, max_length=80)
    last_contact_at: datetime | None = None
    next_followup_at: datetime | None = None
    contact_notes: str | None = Field(default=None, max_length=20000)
    name: str | None = Field(default=None, max_length=180)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    latitude: float | None = Field(default=None, ge=-90, le=90)


class SurveyorAccessOut(SurveyorAccessFields):
    id: int
    map_object_id: int
    name: str
    longitude: float
    latitude: float
    created_at: datetime
    updated_at: datetime


class SurveyorTaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    task_type: Literal["search", "recheck", "contact", "camera", "trap", "evidence", "flyer", "candidate", "other"] = "other"
    status: Literal["open", "completed", "dismissed"] = "open"
    priority: Literal["low", "normal", "high", "urgent"] = "normal"
    due_at: datetime | None = None
    map_object_id: int | None = None
    search_session_id: int | None = None
    candidate_post_id: int | None = None
    notes: str = Field(default="", max_length=20000)


class SurveyorTaskPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=240)
    task_type: Literal["search", "recheck", "contact", "camera", "trap", "evidence", "flyer", "candidate", "other"] | None = None
    status: Literal["open", "completed", "dismissed"] | None = None
    priority: Literal["low", "normal", "high", "urgent"] | None = None
    due_at: datetime | None = None
    map_object_id: int | None = None
    search_session_id: int | None = None
    candidate_post_id: int | None = None
    notes: str | None = Field(default=None, max_length=20000)


class SurveyorTaskOut(SurveyorTaskIn):
    id: int
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
