from __future__ import annotations

import re

# Coarse centroids are a map fallback while exact geocoding catches up. They are
# intentionally city-level, never presented as an exact sighting point.
LOCAL_CENTROIDS: dict[str, tuple[float, float]] = {
    "chapel hill": (35.9132, -79.0558),
    "carrboro": (35.9101, -79.0753),
    "hillsborough": (36.0754, -79.0997),
    "durham": (35.9940, -78.8986),
    "pittsboro": (35.7201, -79.1772),
    "siler city": (35.7235, -79.4622),
    "mebane": (36.09597, -79.26696),
    "burlington": (36.0957, -79.4378),
    "graham": (36.0690, -79.4006),
    "raleigh": (35.7796, -78.6382),
    "cary": (35.7915, -78.7811),
    "apex": (35.7327, -78.8503),
    "morrisville": (35.8235, -78.8256),
    "sanford": (35.4799, -79.1803),
    "lillington": (35.3993, -78.8158),
    "fuquay-varina": (35.5843, -78.8000),
    "wake forest": (35.9799, -78.5097),
    "roxboro": (36.3938, -78.9828),
    "creedmoor": (36.1224, -78.6861),
}


def approximate_coordinates(location_text: str) -> tuple[float, float, str] | None:
    text = (location_text or "").lower()
    if not text:
        return None
    for name in sorted(LOCAL_CENTROIDS, key=len, reverse=True):
        if re.search(rf"(?<!\w){re.escape(name)}(?!\w)", text):
            lat, lon = LOCAL_CENTROIDS[name]
            return lat, lon, name.title()
    return None
