from __future__ import annotations

import math
from datetime import datetime, timezone

from .models import ArchieProfile
from .schemas import PetPostIn
from .traits import ARCHIE_TRAITS, date_is_before_archie_missing, extract_traits


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 3958.7613
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _structured_trait_score(post: PetPostIn) -> tuple[float, list[str]]:
    text = f"{post.name or ''} {post.description} {post.location_text}"
    traits = extract_traits(text, post.altered_status)
    score = 0.0
    reasons: list[str] = []

    colors = traits.get("colors") or []
    if colors:
        if ARCHIE_TRAITS["color"] in colors:
            score += 14
            reasons.append("Orange coloring mentioned")
        else:
            score -= 10
            reasons.append("Color description conflicts")

    patterns = traits.get("patterns") or []
    if patterns:
        if ARCHIE_TRAITS["pattern"] in patterns:
            score += 10
            reasons.append("Striped/tabby mentioned")
        else:
            score -= 4
            reasons.append("Pattern description differs")

    coat = traits.get("coat")
    if coat:
        if coat == ARCHIE_TRAITS["coat"]:
            score += 5
            reasons.append("Short hair mentioned")
        else:
            score -= 5
            reasons.append("Coat length conflicts")

    if traits.get("white_chest") is True:
        score += 8
        reasons.append("White chest mentioned")
    elif traits.get("white_chest") is False:
        score -= 5
        reasons.append("White chest conflicts")

    collar = traits.get("collar")
    if collar == "none":
        score += 4
        reasons.append("No collar mentioned")
    elif collar == "wearing":
        score -= 2
        reasons.append("Collar mentioned")

    microchip = traits.get("microchip")
    if microchip == "none":
        score += 4
        reasons.append("Not microchipped mentioned")
    elif microchip == "yes":
        score -= 5
        reasons.append("Microchip conflicts")

    age = traits.get("age_years")
    if age is not None:
        if abs(float(age) - float(ARCHIE_TRAITS["age_years"])) <= 2.5:
            score += 5
            reasons.append(f"Age compatible (~{age:g})")
        else:
            score -= 4
            reasons.append(f"Age differs (~{age:g})")

    return score, reasons


def score_candidate(
    post: PetPostIn,
    profile: ArchieProfile,
    photo_similarity: float | None = None,
) -> tuple[float, list[str]]:
    # This is a review-priority score, never an identity probability.
    reasons: list[str] = []

    if post.species.lower() != profile.species.lower():
        return 0.0, ["Different species"]

    score = 14.0

    sex = post.sex.lower()
    if sex == profile.sex.lower():
        score += 14
        reasons.append("Male")
    elif sex not in {"unknown", "", "unsure"}:
        score -= 14
        reasons.append("Sex conflicts")

    altered = post.altered_status.lower()
    if altered == profile.altered_status.lower():
        score += 10
        reasons.append("Neutered")
    elif altered not in {"unknown", "", "unsure"}:
        score -= 7
        reasons.append("Altered status conflicts")

    structured_score, structured_reasons = _structured_trait_score(post)
    score += structured_score
    reasons.extend(structured_reasons)

    text = f"{post.name or ''} {post.description} {post.location_text}".lower()
    keywords = [k.strip().lower() for k in (profile.trait_keywords or "").split(",") if k.strip()]
    matches = [k for k in keywords if k in text]
    if matches:
        # Keep custom keywords useful without double-counting the structured Archie
        # traits so aggressively that one verbose description dominates the queue.
        bump = min(8, len(matches) * 2)
        score += bump
        reasons.append("Other Archie wording: " + ", ".join(matches[:4]))

    if (
        profile.anchor_latitude is not None
        and profile.anchor_longitude is not None
        and post.latitude is not None
        and post.longitude is not None
    ):
        miles = haversine_miles(
            profile.anchor_latitude,
            profile.anchor_longitude,
            post.latitude,
            post.longitude,
        )
        if miles <= 5:
            score += 20
            reasons.append(f"Very close ({miles:.1f} mi)")
        elif miles <= 15:
            score += 13
            reasons.append(f"Nearby ({miles:.1f} mi)")
        elif miles <= 35:
            score += 6
            reasons.append(f"Regional ({miles:.1f} mi)")
        else:
            reasons.append(f"Farther away ({miles:.1f} mi)")

    if post.reported_at:
        if date_is_before_archie_missing(post.reported_at):
            score -= 45
            reasons.append("Report predates Archie going missing")
        else:
            now = datetime.now(timezone.utc)
            dt = post.reported_at
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            days = max(0, (now - dt).days)
            if days <= 2:
                score += 10
                reasons.append("Very recent")
            elif days <= 14:
                score += 6
                reasons.append("Recent")
            elif days <= 60:
                score += 2

    # Model-free photo comparison is strongest for reused / near-identical images.
    # Never describe this as an identity probability.
    if photo_similarity is not None:
        pct = round(photo_similarity * 100)
        if photo_similarity >= 0.93:
            score += 25
            reasons.append(f"Very strong reference-photo likeness ({pct}% heuristic)")
        elif photo_similarity >= 0.84:
            score += 17
            reasons.append(f"Strong reference-photo likeness ({pct}% heuristic)")
        elif photo_similarity >= 0.74:
            score += 9
            reasons.append(f"Some reference-photo likeness ({pct}% heuristic)")

    # Preserve reason order while removing accidental duplicates from overlapping
    # free-text rules.
    reasons = list(dict.fromkeys(reasons))
    return round(max(0.0, min(100.0, score)), 1), reasons
