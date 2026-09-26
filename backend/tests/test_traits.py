from datetime import datetime, timezone

from app.local_places import approximate_coordinates
from app.matcher import score_candidate
from app.models import ArchieProfile
from app.schemas import PetPostIn
from app.traits import extract_traits, is_archie_compatible


def archie_profile():
    return ArchieProfile(id=1, species="cat", sex="male", altered_status="neutered", trait_keywords="")


def test_extracts_archie_traits_from_description():
    traits = extract_traits(
        "Orange striped tabby domestic shorthair male, neutered, white chest, no white on belly, "
        "not microchipped and not wearing a collar. About 8 years old.",
        "neutered",
    )
    assert "orange" in traits["colors"]
    assert "striped" in traits["patterns"]
    assert traits["coat"] == "short"
    assert traits["white_chest"] is True
    assert traits["white_belly"] is False
    assert traits["collar"] == "none"
    assert traits["microchip"] == "none"
    assert traits["age_years"] == 8
    assert is_archie_compatible(traits, "male") is True


def test_explicit_black_longhair_is_not_archie_compatible():
    traits = extract_traits("Black longhaired female cat wearing a red collar")
    assert is_archie_compatible(traits, "female") is False


def test_archie_like_description_raises_priority():
    plain = PetPostIn(source="x", source_id="1", sex="male", description="Friendly cat")
    archie_like = PetPostIn(
        source="x", source_id="2", sex="male", altered_status="neutered",
        description="Orange striped tabby shorthaired cat with a white chest, no collar, not microchipped, about 8 years old",
        reported_at=datetime(2026, 9, 25, tzinfo=timezone.utc),
    )
    plain_score, _ = score_candidate(plain, archie_profile())
    like_score, reasons = score_candidate(archie_like, archie_profile())
    assert like_score > plain_score
    assert any("Orange coloring" in reason for reason in reasons)
    assert any("Striped/tabby" in reason for reason in reasons)


def test_report_before_missing_date_gets_penalty():
    after = PetPostIn(source="x", source_id="1", sex="male", reported_at=datetime(2026, 7, 2, tzinfo=timezone.utc))
    before = PetPostIn(source="x", source_id="2", sex="male", reported_at=datetime(2026, 5, 2, tzinfo=timezone.utc))
    after_score, _ = score_candidate(after, archie_profile())
    before_score, reasons = score_candidate(before, archie_profile())
    assert before_score < after_score
    assert "Report predates Archie going missing" in reasons


def test_city_fallback_coordinates_are_available():
    result = approximate_coordinates("Winding Ridge, Sanford, NC 27332")
    assert result is not None
    lat, lon, place = result
    assert place == "Sanford"
    assert 35 < lat < 36
    assert -80 < lon < -78


def test_accessory_color_does_not_become_cat_color():
    traits = extract_traits("Gray male cat wearing an orange collar")
    assert "orange" not in traits["colors"]
    assert "gray" in traits["colors"]
