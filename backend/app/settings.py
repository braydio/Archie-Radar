from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ARCHIE_", env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./archie_radar.db"
    cors_origins: str = "http://localhost:5173"
    media_dir: str = "./media"

    # Regional search. PawBoost result pages cover roughly 25 miles around each
    # search center, so overlapping centers are intentional and deduplicated by ID.
    pawboost_areas: str = (
        "chapel-hill-nc-27516,durham-nc-27701,mebane-nc-27302,"
        "pittsboro-nc-27312,raleigh-nc-27601,sanford-nc-27330"
    )
    pawboost_pages: int = 2
    scan_minutes: int = 30
    auto_scan: bool = True
    orange_county_enabled: bool = True
    regional_24petconnect_enabled: bool = True
    regional_24petconnect_url: str = "https://24petconnect.com/ViewAnimals/2779667"
    aps_durham_enabled: bool = True
    wake_county_enabled: bool = True
    pet911_enabled: bool = True
    pet911_places: str = "chapel-hill,durham,raleigh"
    petkey_enabled: bool = True
    petkey_places: str = "chapel-hill_nc,durham_nc,raleigh_nc"

    analyze_images: bool = True
    max_image_bytes: int = 8_000_000

    # Home search anchor. Unit does not change the parcel-level coordinate.
    home_address: str = "30 Dollar Road #A, Chapel Hill, NC 27516"
    home_latitude: float = 35.845701
    home_longitude: float = -79.117282
    search_radius_miles: float = 25.0

    geocode_enabled: bool = True
    geocode_user_agent: str = "ArchieRadar/0.7 lost-pet-reunion-project"
    geocode_base_url: str = "https://nominatim.openstreetmap.org"
    # Public Nominatim limits regular/periodic geocoding to 4 requests/minute.
    geocode_min_delay_seconds: float = 15.1
    geocode_backfill_limit: int = 150

    petco_api_key: str = ""
    petco_api_base: str = "https://api.petcolove.org/v2.1"

    @property
    def cors_origin_list(self) -> list[str]:
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]

    @property
    def pawboost_area_list(self) -> list[str]:
        return [x.strip() for x in self.pawboost_areas.split(",") if x.strip()]

    @property
    def pet911_place_list(self) -> list[str]:
        return [x.strip() for x in self.pet911_places.split(",") if x.strip()]

    @property
    def petkey_place_list(self) -> list[str]:
        return [x.strip() for x in self.petkey_places.split(",") if x.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
