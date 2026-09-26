from __future__ import annotations

import asyncio
import hashlib
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from ..schemas import PetPostIn
from .base import Connector


class Regional24PetConnectConnector(Connector):
    """Parse a public 24PetConnect search-results page covering the local region.

    The site creates saved search URLs such as /ViewAnimals/<request-id>. The URL is
    configurable because 24PetConnect owns the search/session lifecycle.
    """

    source_name = "regional_24petconnect"

    def __init__(self, url: str):
        self.url = url.strip()

    async def fetch(self) -> list[PetPostIn]:
        if not self.url:
            return []
        headers = {"User-Agent": "ArchieRadar/0.9 (+lost-pet-reunion-project)"}
        async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=25) as client:
            response = await client.get(self.url)
            response.raise_for_status()
            rows = self.parse_listing(response.text, str(response.url))

            async def active(row: PetPostIn) -> PetPostIn | None:
                if not row.source_url or row.source_url == str(response.url):
                    return row
                try:
                    detail = await client.get(row.source_url, timeout=12)
                    detail.raise_for_status()
                    text = BeautifulSoup(detail.text, "html.parser").get_text(" ", strip=True).lower()
                    inactive = bool(re.search(r"\b(?:inactive|reunited|adopted)\b|no longer (?:active|available)|listing (?:is )?closed|animal (?:is )?no longer available", text, re.I))
                    if inactive:
                        return None
                except Exception:
                    # A failed detail check must not erase a valid search-result row.
                    pass
                return row

            checked = await asyncio.gather(*(active(row) for row in rows))
            return [row for row in checked if row is not None]

    @staticmethod
    def _source_for_status(status_text: str) -> str:
        value = status_text.lower()
        if "animal protection society of durham" in value:
            return "durham_24petconnect"
        if "burlington animal services" in value:
            return "burlington_24petconnect"
        if "chatham" in value and ("animal" in value or "shelter" in value):
            return "chatham_24petconnect"
        if "orange county" in value:
            return "orange_county_24petconnect"
        if "wake county" in value:
            return "wake_24petconnect"
        return "regional_24petconnect"

    @staticmethod
    def parse_listing(html: str, source_url: str) -> list[PetPostIn]:
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text("\n", strip=True)
        matches = list(re.finditer(r"Animal id:\s*([^\s]+)", text, re.I))
        records: list[PetPostIn] = []

        for i, match in enumerate(matches):
            animal_id = match.group(1).strip()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            chunk = text[match.end():end]
            if not chunk.strip():
                continue

            gender_m = re.search(r"Gender\s*:\s*(?:Unknown Gender|Unknown|Male|Female)(?:\s*\((Spayed|Neutered)\))?", chunk, re.I)
            gender_full = gender_m.group(0) if gender_m else ""
            if re.search(r"\bMale\b", gender_full, re.I):
                sex = "male"
            elif re.search(r"\bFemale\b", gender_full, re.I):
                sex = "female"
            else:
                sex = "unknown"
            altered = "unknown"
            if re.search(r"\bNeutered\b", gender_full, re.I):
                altered = "neutered"
            elif re.search(r"\bSpayed\b", gender_full, re.I):
                altered = "spayed"

            status_m = re.search(r"Status\s*:\s*([^\n]+)", chunk, re.I)
            status_text = status_m.group(1).strip() if status_m else "Found report"
            location_m = re.search(r"Location Found\s*:\s*([^\n]+)", chunk, re.I)
            location = location_m.group(1).strip() if location_m else ""
            breed_m = re.search(r"Breed\s*:\s*([^\n]+)", chunk, re.I)
            breed = breed_m.group(1).strip() if breed_m else "Cat"

            days_m = re.search(r"Days (?:At Shelter|Since Found)\s*:\s*(\d+)", chunk, re.I)
            days = int(days_m.group(1)) if days_m else None
            reported_at = datetime.now(timezone.utc) - timedelta(days=days) if days is not None else None

            # 24PetConnect result pages carry linked animal images. Prefer a matching
            # alt/title if present; otherwise leave blank rather than fabricating a URL.
            image_url = None
            detail_url = source_url
            for img in soup.find_all("img"):
                label = " ".join(filter(None, [img.get("alt"), img.get("title")]))
                if animal_id.lower() in label.lower():
                    src = img.get("src") or img.get("data-src") or img.get("data-lazy-src")
                    if src:
                        image_url = urljoin(source_url, src)
                    parent_link = img.find_parent("a", href=True)
                    if parent_link:
                        detail_url = urljoin(source_url, parent_link["href"])
                    break
            if detail_url == source_url:
                link = soup.find("a", href=re.compile(re.escape(animal_id), re.I))
                if link and link.get("href"):
                    detail_url = urljoin(source_url, link["href"])

            source = Regional24PetConnectConnector._source_for_status(status_text)
            status = "found"
            if "finder's home" in status_text.lower() or "finders home" in status_text.lower():
                status = "found_with_finder"
            elif "shelter" in status_text.lower():
                status = "shelter_intake"

            raw_hash = hashlib.sha1(f"{animal_id}|{status_text}|{location}".encode()).hexdigest()[:12]
            records.append(
                PetPostIn(
                    source=source,
                    source_id=animal_id or raw_hash,
                    source_url=detail_url,
                    status=status,
                    species="cat",
                    sex=sex,
                    altered_status=altered,
                    description=f"{status_text}. Breed: {breed}.",
                    location_text=location,
                    image_url=image_url,
                    reported_at=reported_at,
                    raw={
                        "listing_url": source_url,
                        "status_text": status_text,
                        "breed": breed,
                        "days_since_event": days,
                        "geocode_context": "North Carolina, USA",
                    },
                )
            )

        # If a page contains mixed species, the 24PetConnect cat search text normally
        # says Domestic Shorthair/Longhair/etc. Keep records with feline-looking breeds,
        # but also keep unknown breeds because some shelters omit the field.
        out = []
        feline_terms = ("cat", "domestic", "siamese", "tabby", "maine coon", "persian", "shorthair", "longhair")
        for row in records:
            breed = str(row.raw.get("breed", "")).lower()
            if not breed or any(term in breed for term in feline_terms):
                out.append(row)
        return out
