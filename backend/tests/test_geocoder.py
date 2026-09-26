import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.geocoder import GeocodeResult, build_query, geocode_posts
from app.schemas import PetPostIn


class FakeGeocoder:
    def __init__(self):
        self.calls = 0

    async def lookup(self, query):
        self.calls += 1
        return GeocodeResult(35.9, -79.1, f"resolved {query}")


@pytest.mark.asyncio
async def test_geocoding_is_cached_and_adds_context():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    fake = FakeGeocoder()
    post = PetPostIn(
        source="orange_county_found",
        source_id="A1",
        location_text="High St, Carrboro",
        raw={"geocode_context": "Orange County, North Carolina, USA"},
    )
    with Session() as db:
        first, stats1 = await geocode_posts(db, [post], fake)
        second, stats2 = await geocode_posts(db, [post], fake)
    assert first[0].latitude == 35.9
    assert second[0].longitude == -79.1
    assert fake.calls == 1
    assert stats1["looked_up"] == 1
    assert stats2["cache_hits"] == 1


def test_build_query_appends_north_carolina_for_bare_location():
    post = PetPostIn(source="x", source_id="1", location_text="Dollar Road")
    assert "North Carolina" in build_query(post)
