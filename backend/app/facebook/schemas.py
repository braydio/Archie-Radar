from datetime import datetime, timezone
from pydantic import BaseModel, Field, HttpUrl


class GroupIn(BaseModel):
    group_url: HttpUrl
    facebook_group_id: str | None = Field(default=None, max_length=120)
    group_name: str = Field(default="Facebook group", min_length=1, max_length=240)
    enabled: bool = True
    initial_sync_cutoff: datetime = Field(default_factory=lambda: datetime(2026, 6, 1, tzinfo=timezone.utc))


class GroupPatch(BaseModel):
    group_url: HttpUrl | None = None
    facebook_group_id: str | None = Field(default=None, max_length=120)
    group_name: str | None = Field(default=None, min_length=1, max_length=240)
    enabled: bool | None = None
    initial_sync_cutoff: datetime | None = None


class CapturedImage(BaseModel):
    url: HttpUrl
    sha256: str | None = Field(default=None, pattern=r"^[a-fA-F0-9]{64}$")
    width: int | None = Field(default=None, ge=1, le=20000)
    height: int | None = Field(default=None, ge=1, le=20000)


class CapturedPost(BaseModel):
    facebook_post_id: str | None = Field(default=None, max_length=180)
    canonical_url: HttpUrl | None = None
    text: str = Field(default="", max_length=30000)
    author_name: str | None = Field(default=None, max_length=240)
    posted_at: datetime | None = None
    images: list[CapturedImage] = Field(default_factory=list, max_length=12)
    video_present: bool = False
    captured_at: datetime | None = None


class BatchIn(BaseModel):
    sync_run_id: int
    group_subscription_id: int
    scanned: int = Field(ge=0, le=2000)
    parser_warning: str = Field(default="", max_length=1000)
    posts: list[CapturedPost] = Field(max_length=500)


class GroupReceiptIn(BaseModel):
    scanned: int = Field(ge=0, le=2000)
    parser_warning: str = Field(default="", max_length=1000)
    error: str = Field(default="", max_length=2000)


class SyncCompleteIn(BaseModel):
    error_summary: str = Field(default="", max_length=4000)
