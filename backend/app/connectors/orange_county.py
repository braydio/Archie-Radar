from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from ..schemas import PetPostIn
from .base import Connector


class OrangeCountyFoundCatsConnector(Connector):
    """Orange County's official 24Petconnect found-cat reports held by finders."""

    source_name = "orange_county_found"
    url = "https://24petconnect.com/ORNCFoundReports?at=CAT"

    async def fetch(self) -> list[PetPostIn]:
        headers = {"User-Agent": "ArchieRadar/0.7 (+lost-pet-reunion-project)"}
        async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=20) as client:
            response = await client.get(self.url)
            response.raise_for_status()
            return self.parse_listing(response.text, str(response.url))

    @staticmethod
    def parse_listing(html: str, source_url: str) -> list[PetPostIn]:
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text("\n", strip=True)
        # The 24Petconnect report cards expose stable A-numbers in image alt text.
        ids = list(re.finditer(r"Image_A(\d+)", text, re.I))
        # Some renderings do not include alt text in get_text(); fall back to tags.
        if not ids:
            chunks = []
            for img in soup.find_all("img", alt=re.compile(r"Image_A\d+", re.I)):
                alt = img.get("alt", "")
                m = re.search(r"A(\d+)", alt)
                if not m:
                    continue
                node = img.parent
                for _ in range(5):
                    if node and "Gender:" in node.get_text("\n", strip=True):
                        break
                    node = getattr(node, "parent", None)
                chunks.append((m.group(1), node.get_text("\n", strip=True) if node else "", img))
            return [OrangeCountyFoundCatsConnector._parse_chunk(aid, chunk, img, source_url) for aid, chunk, img in chunks]

        records: list[PetPostIn] = []
        for i, match in enumerate(ids):
            end = ids[i + 1].start() if i + 1 < len(ids) else len(text)
            chunk = text[match.end():end]
            records.append(OrangeCountyFoundCatsConnector._parse_chunk(match.group(1), chunk, None, source_url))
        return [r for r in records if r is not None]

    @staticmethod
    def _parse_chunk(aid: str, chunk: str, img, source_url: str) -> PetPostIn | None:
        if not chunk:
            return None
        gender_m = re.search(r"Gender:\s*(?:Neutered |Spayed )?(Male|Female|Unknown Gender|Unknown)", chunk, re.I)
        sex = gender_m.group(1).lower() if gender_m else "unknown"
        if sex == "unknown gender":
            sex = "unknown"
        days_m = re.search(r"Days Since Found:\s*(\d+)", chunk, re.I)
        days = int(days_m.group(1)) if days_m else None
        status_m = re.search(r"Status:\s*([^\n]+)", chunk, re.I)
        status_text = status_m.group(1).strip() if status_m else "Found report"
        location_m = re.search(r"Location Found:\s*([^\n]+)", chunk, re.I)
        location = location_m.group(1).strip() if location_m else ""
        breed_m = re.search(r"Breed:\s*([^\n]+)", chunk, re.I)
        breed = breed_m.group(1).strip() if breed_m else "Cat"
        reported_at = datetime.now(timezone.utc) - timedelta(days=days) if days is not None else None

        image_url = None
        if img is not None:
            src = img.get("src") or img.get("data-src") or img.get("data-lazy-src")
            image_url = urljoin(source_url, src) if src else None
        if image_url is None:
            # Public 24Petconnect image endpoint accepts the A-number as a useful fallback
            # only on some installations, so omit rather than fabricate an image URL.
            image_url = None

        desc = f"{status_text}. Breed: {breed}."
        return PetPostIn(
            source="orange_county_found",
            source_id=f"A{aid}",
            source_url=source_url,
            status="found",
            species="cat",
            sex=sex,
            description=desc,
            location_text=location,
            image_url=image_url,
            reported_at=reported_at,
            raw={
                "geocode_context": "Orange County, North Carolina, USA",
                "days_since_found": days,
                "status_text": status_text,
                "breed": breed,
            },
        )
