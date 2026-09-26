from __future__ import annotations

import re
from datetime import date, datetime


COLOR_TERMS = {
    "orange": ("orange", "ginger", "red tabby", "orange tabby", "buff", "marmalade"),
    "black": ("black",),
    "gray": ("gray", "grey", "blue cat", "russian blue"),
    "white": ("white",),
    "brown": ("brown", "brown tabby"),
    "cream": ("cream", "beige"),
    "calico": ("calico",),
    "tortoiseshell": ("tortoiseshell", "tortie"),
}

PATTERN_TERMS = {
    "striped": ("striped", "stripes", "tabby", "tiger striped", "tiger stripe", "mackerel tabby"),
    "solid": ("solid",),
    "tuxedo": ("tuxedo",),
    "spotted": ("spotted", "spots"),
}

COAT_TERMS = {
    "short": ("short hair", "shorthair", "short-haired", "shorthaired", "domestic short hair", "dsh"),
    "medium": ("medium hair", "mediumhair", "medium-haired", "mediumhaired"),
    "long": ("long hair", "longhair", "long-haired", "longhaired", "domestic long hair", "dlh"),
}


def _contains(text: str, terms: tuple[str, ...], ignore_accessories: bool = False) -> bool:
    for term in terms:
        for match in re.finditer(rf"(?<!\w){re.escape(term)}(?!\w)", text, re.I):
            if ignore_accessories:
                tail = text[match.end(): match.end() + 24]
                if re.match(r"\s+(?:flea\s+)?(?:collar|harness|tag|bandana)\b", tail, re.I):
                    continue
            return True
    return False


def _negated_near(text: str, term_pattern: str) -> bool:
    pattern = rf"\b(?:no|not|without|wasn['’]?t|isn['’]?t|doesn['’]?t|didn['’]?t)\b[^.\n]{{0,28}}\b(?:{term_pattern})\b"
    return bool(re.search(pattern, text, re.I))


def _parse_age_years(text: str) -> float | None:
    patterns = [
        r"\b(?:about|approx(?:imately)?|around|roughly)?\s*(\d{1,2}(?:\.\d)?)\s*(?:years?|yrs?)\s*(?:old)?\b",
        r"\bage\s*[:\-]?\s*(\d{1,2}(?:\.\d)?)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            try:
                value = float(match.group(1))
            except ValueError:
                continue
            if 0 <= value <= 30:
                return value
    return None


def _part_color(lowered: str, part: str) -> bool | None:
    if re.search(rf"\bwhite (?:{part})\b|\b(?:{part}) (?:are|is)?\s*white\b", lowered):
        return True
    if re.search(rf"\bno white (?:on )?(?:the )?{part}\b|\b{part} (?:has )?no white\b", lowered):
        return False
    return None


def extract_traits(text: str, explicit_altered_status: str = "unknown") -> dict:
    source = (text or "").strip()
    lowered = source.lower()

    colors = [name for name, terms in COLOR_TERMS.items() if _contains(lowered, terms, ignore_accessories=True)]
    patterns = [name for name, terms in PATTERN_TERMS.items() if _contains(lowered, terms, ignore_accessories=True)]
    coats = [name for name, terms in COAT_TERMS.items() if _contains(lowered, terms)]

    collar = "unknown"
    if re.search(r"\b(?:no collar|without (?:a )?collar|not wearing (?:a )?collar|collarless)\b", lowered):
        collar = "none"
    elif re.search(r"\b(?:wearing|has|with) (?:a )?(?:\w+\s+){0,2}collar\b|\bcollar\b", lowered):
        collar = "wearing"

    microchip = "unknown"
    if re.search(r"\b(?:not microchipped|not chipped|no microchip|no chip|unmicrochipped)\b", lowered):
        microchip = "none"
    elif re.search(r"\b(?:microchipped|microchip(?:ped)?|chipped)\b", lowered):
        microchip = "yes"

    altered = (explicit_altered_status or "unknown").lower()
    if altered in {"", "unknown", "unsure"}:
        if re.search(r"\b(?:neutered|fixed male|altered male)\b", lowered):
            altered = "neutered"
        elif re.search(r"\b(?:intact male|unneutered|not neutered)\b", lowered):
            altered = "intact"
        elif re.search(r"\bspayed\b", lowered):
            altered = "spayed"
        else:
            altered = "unknown"

    white_chest = None
    if re.search(r"\bwhite (?:chest|bib|chest patch|patch on (?:his|her|the) chest)\b|\bchest (?:is )?white\b", lowered):
        white_chest = True
    elif _negated_near(lowered, r"white (?:chest|bib)|white on (?:the )?chest"):
        white_chest = False

    white_belly = None
    if re.search(r"\b(?:white belly|white stomach|white abdomen|white on (?:his|her|the) belly)\b", lowered):
        white_belly = True
    if re.search(r"\b(?:no white (?:on )?(?:(?:his|her|the) )?belly|belly has no white|no white belly)\b", lowered):
        white_belly = False

    white_paws = _part_color(lowered, r"paws?|feet|mittens")
    white_face = _part_color(lowered, r"face|muzzle|chin")

    age_years = _parse_age_years(lowered)

    return {
        "colors": sorted(set(colors)),
        "patterns": sorted(set(patterns)),
        "coat": coats[0] if coats else None,
        "collar": collar,
        "microchip": microchip,
        "altered_status": altered,
        "white_chest": white_chest,
        "white_belly": white_belly,
        "white_paws": white_paws,
        "white_face": white_face,
        "age_years": age_years,
    }


ARCHIE_TRAITS = {
    "color": "orange",
    "pattern": "striped",
    "coat": "short",
    "sex": "male",
    "altered_status": "neutered",
    "white_chest": True,
    "white_belly": False,
    "collar": "none",
    "microchip": "none",
    "age_years": 8.0,
    "lost_date": "2026-06-28",
}


def archie_trait_assessment(traits: dict, sex: str = "unknown") -> dict:
    matches: list[str] = []
    conflicts: list[str] = []
    unknown: list[str] = []

    candidate_sex = (sex or "unknown").lower()
    if candidate_sex in {"", "unknown", "unsure"}:
        unknown.append("sex")
    elif candidate_sex == ARCHIE_TRAITS["sex"]:
        matches.append("male")
    else:
        conflicts.append(candidate_sex)

    def list_trait(key: str, target: str, label: str):
        values = traits.get(key) or []
        if not values:
            unknown.append(label)
        elif target in values:
            matches.append(label)
        else:
            conflicts.append(f"{label}: {', '.join(values)}")

    list_trait("colors", ARCHIE_TRAITS["color"], "orange")
    list_trait("patterns", ARCHIE_TRAITS["pattern"], "striped/tabby")

    scalar_specs = [
        ("coat", ARCHIE_TRAITS["coat"], "short hair"),
        ("altered_status", ARCHIE_TRAITS["altered_status"], "neutered"),
        ("collar", ARCHIE_TRAITS["collar"], "no collar"),
        ("microchip", ARCHIE_TRAITS["microchip"], "not microchipped"),
    ]
    for key, target, label in scalar_specs:
        value = traits.get(key)
        if value in (None, "", "unknown"):
            unknown.append(label)
        elif value == target:
            matches.append(label)
        else:
            conflicts.append(f"{label}: {value}")

    if traits.get("white_chest") is True:
        matches.append("white chest")
    elif traits.get("white_chest") is None:
        unknown.append("white chest")
    else:
        conflicts.append("white chest")

    # White belly is intentionally soft. We score it, but do not treat it as an absolute conflict.
    if traits.get("white_belly") is False:
        matches.append("no white belly")
    elif traits.get("white_belly") is None:
        unknown.append("no white belly")

    age = traits.get("age_years")
    if age is None:
        unknown.append("age")
    elif abs(float(age) - ARCHIE_TRAITS["age_years"]) <= 2.5:
        matches.append(f"age ~{age:g}")
    else:
        conflicts.append(f"age ~{age:g}")

    return {"matches": matches, "conflicts": conflicts, "unknown": unknown}


def is_archie_compatible(traits: dict, sex: str = "unknown") -> bool:
    assessment = archie_trait_assessment(traits, sex)
    return len(assessment["conflicts"]) == 0


def date_is_before_archie_missing(value: datetime | date | None) -> bool:
    if value is None:
        return False
    if isinstance(value, datetime):
        value = value.date()
    lost = date.fromisoformat(ARCHIE_TRAITS["lost_date"])
    return value < lost
