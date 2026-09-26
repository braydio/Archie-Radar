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
    object_type: str = Field(min_length=1, max_length=40)
    subtype: str | None = Field(default=None, max_length=60)
    name: str | None = Field(default=None, max_length=180)
    geometry: dict
    style: dict = Field(default_factory=dict)
    properties: dict = Field(default_factory=dict)
    status: str | None = None
    confidence: str | None = None
    epistemic_state: str | None = None
    occurred_at: datetime | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    notes: str = ""


class SurveyorObjectPatch(BaseModel):
    object_type: str | None = Field(default=None, min_length=1, max_length=40)
    subtype: str | None = Field(default=None, max_length=60)
    name: str | None = Field(default=None, max_length=180)
    geometry: dict | None = None
    style: dict | None = None
    properties: dict | None = None
    status: str | None = None
    confidence: str | None = None
    epistemic_state: str | None = None
    occurred_at: datetime | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    notes: str | None = None


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
