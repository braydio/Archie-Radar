from __future__ import annotations

import asyncio
import hashlib
import re
from datetime import timezone
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from dateutil import parser as dtparser

from ..schemas import PetPostIn
from .base import Connector


class PetkeyConnector(Connector):
    source_name = "petkey"

    def __init__(self, places: list[str]):
        self.places = places

    async def fetch(self) -> list[PetPostIn]:
        headers = {"User-Agent": "ArchieRadar/0.7 (+lost-pet-reunion-project)"}
        posts: list[PetPostIn] = []
        async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=25) as client:
            for place in self.places:
                url = f"https://petkey.org/lost-and-found/{place}"
                try:
                    response = await client.get(url)
                    if response.status_code == 404:
                        continue
                    response.raise_for_status()
                    posts.extend(self.parse_listing(response.text, str(response.url)))
                except httpx.HTTPError:
                    continue
                await asyncio.sleep(0.25)
        return list({(p.source, p.source_id): p for p in posts}.values())

    @staticmethod
    def parse_listing(html: str, source_url: str) -> list[PetPostIn]:
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text("\n", strip=True)
        # Petkey cards expose name then Breed/Gender/Age/Other Id/Color and Lost/Found date.
        event_matches = list(re.finditer(r"\b(Found|Lost)\s+(\d{1,2}/\d{1,2}/\d{4})", text, re.I))
        records: list[PetPostIn] = []
        for i, event in enumerate(event_matches):
            # Each card ends at its Lost/Found date. Start immediately after the
            # previous card's date so neighboring records cannot bleed together.
            start = event_matches[i - 1].end() if i > 0 else 0
            end = event.end()
            chunk = text[start:end]
            if event.group(1).lower() != "found":
                continue

            breed_m = re.search(r"Breed:\s*([^\n]+)", chunk, re.I)
            breed_value = breed_m.group(1).strip() if breed_m else ""
            if breed_value and not re.search(r"\b(?:cat|domestic short hair|domestic shorthair|domestic long hair|domestic longhair|american shorthair|siamese|tabby|balinese|maine coon)\b", breed_value, re.I):
                continue
            if not breed_value and not re.search(r"\bcat\b", chunk, re.I):
                continue
            gender_m = re.search(r"Gender:\s*(Male|Female|Unknown)", chunk, re.I)
            other_m = re.search(r"Other Id:\s*([^\n]+)", chunk, re.I)
            color_m = re.search(r"Color:\s*([^\n]+)", chunk, re.I)
            lines = [x.strip() for x in chunk.splitlines() if x.strip()]
            name = "Found cat"
            if "Breed:" in chunk:
                breed_index = next((idx for idx, x in enumerate(lines) if x.startswith("Breed:")), None)
                if breed_index and breed_index > 0:
                    name = lines[breed_index - 1][:120]

            source_id = other_m.group(1).strip() if other_m and other_m.group(1).strip() else hashlib.sha1(f"{name}|{event.group(2)}|{chunk}".encode()).hexdigest()[:16]
            reported_at = None
            try:
                reported_at = dtparser.parse(event.group(2)).replace(tzinfo=timezone.utc)
            except Exception:
                pass
            sex = gender_m.group(1).lower() if gender_m else "unknown"
            breed = breed_value or "Cat"
            color = color_m.group(1).strip() if color_m else ""

            # Avoid storing microchip values even though some public cards display them.
            description = f"Breed: {breed}." + (f" Color: {color}." if color else "")
            records.append(PetPostIn(
                source="petkey",
                source_id=source_id,
                source_url=source_url,
                status="found",
                species="cat",
                name=None if name == "Found cat" else name,
                sex=sex,
                description=description,
                location_text="",
                image_url=None,
                reported_at=reported_at,
                raw={"listing_url": source_url, "breed": breed, "color": color},
            ))
        return records
