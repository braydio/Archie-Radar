from app.matcher import score_candidate
from app.models import ArchieProfile
from app.schemas import PetPostIn


def profile():
    return ArchieProfile(
        id=1,
        species="cat",
        sex="male",
        altered_status="neutered",
        trait_keywords="gray, white chest, eye",
    )


def test_matching_male_scores_above_conflicting_female():
    male = PetPostIn(source="x", source_id="1", sex="male", description="gray cat with white chest")
    female = PetPostIn(source="x", source_id="2", sex="female", description="gray cat with white chest")
    male_score, _ = score_candidate(male, profile())
    female_score, _ = score_candidate(female, profile())
    assert male_score > female_score


def test_non_cat_is_zero():
    score, reasons = score_candidate(PetPostIn(source="x", source_id="3", species="dog"), profile())
    assert score == 0
    assert reasons == ["Different species"]
