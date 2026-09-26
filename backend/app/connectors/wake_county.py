from __future__ import annotations

import asyncio
import re
from datetime import timezone
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from dateutil import parser as dtparser

from ..schemas import PetPostIn
from .base import Connector, extract_source_posted_at


class WakeCountyLostFoundConnector(Connector):
    source_name = "wake_county_lostfound"
    url = "https://pets.wake.gov/lostfound"

    def __init__(self, max_details: int = 50):
        self.max_details = max_details

    async def fetch(self) -> list[PetPostIn]:
        headers = {"User-Agent": "ArchieRadar/0.7 (+lost-pet-reunion-project)"}
        async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=25) as client:
            response = await client.get(self.url)
            response.raise_for_status()
            rows = self.parse_listing(response.text, str(response.url))
            # If the listing only gives IDs, enrich from detail pages and keep cats.
            enriched: list[PetPostIn] = []
            for row in rows[: self.max_details]:
                if row.raw.get("needs_detail"):
                    try:
                        detail = await client.get(row.source_url)
                        detail.raise_for_status()
                        parsed = self.parse_detail(detail.text, str(detail.url), row.source_id)
                        if parsed:
                            row = parsed
                    except httpx.HTTPError:
                        pass
                    await asyncio.sleep(0.15)
                if row.species == "cat":
                    enriched.append(row)
            return enriched

    @staticmethod
    def parse_listing(html: str, source_url: str) -> list[PetPostIn]:
        soup = BeautifulSoup(html, "html.parser")
        records: list[PetPostIn] = []
        seen: set[str] = set()
        for anchor in soup.find_all("a", href=re.compile(r"/lostfound/\d+")):
            href = urljoin(source_url, anchor["href"])
            m = re.search(r"/lostfound/(\d+)", href)
            if not m or m.group(1) in seen:
                continue
            animal_id = m.group(1)
            seen.add(animal_id)
            node = anchor
            chunk = ""
            for _ in range(6):
                node = getattr(node, "parent", None)
                if node is None:
                    break
                chunk = node.get_text("\n", strip=True)
                if re.search(r"Date In Shelter|Age:|Male|Female", chunk, re.I):
                    break
            sex = "male" if re.search(r"\bMale\b", chunk, re.I) else "female" if re.search(r"\bFemale\b", chunk, re.I) else "unknown"
            name = anchor.get_text(" ", strip=True) or None
            image_url = None
            if node is not None:
                img = node.find("img")
                if img:
                    src = img.get("src") or img.get("data-src")
                    if src:
                        image_url = urljoin(source_url, src)
            date_m = re.search(r"Date In Shelter:\s*([^\n]+)", chunk, re.I)
            reported_at = None
            if date_m:
                try:
                    reported_at = dtparser.parse(date_m.group(1).strip()).replace(tzinfo=timezone.utc)
                except Exception:
                    pass
            records.append(PetPostIn(
                source="wake_county_lostfound",
                source_id=animal_id,
                source_url=href,
                status="shelter_intake",
                species="unknown",
                name=name[:120] if name else None,
                sex=sex,
                description="Wake County Animal Center lost/found gallery record.",
                location_text="Wake County Animal Center, Raleigh, NC",
                image_url=image_url,
                reported_at=reported_at,
                raw={"listing_url": source_url, "listing_text": chunk[:1800], "needs_detail": True},
            ))
        return records

    @staticmethod
    def parse_detail(html: str, source_url: str, source_id: str) -> PetPostIn | None:
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text("\n", strip=True)
        if re.search(r"Animal Not Found", text, re.I):
            return None
        breed_m = re.search(r"(?:Breed|Primary Breed):\s*([^\n]+)", text, re.I)
        breed = breed_m.group(1).strip() if breed_m else ""
        lowered = breed.lower()
        feline_terms = ("cat", "domestic", "shorthair", "longhair", "siamese", "tabby", "maine coon", "persian")
        if breed and not any(term in lowered for term in feline_terms):
            return None
        species = "cat" if breed else ("cat" if re.search(r"\bcat\b", text, re.I) else "unknown")
        if species != "cat":
            return None
        sex_m = re.search(r"\b(Male|Female)\b", text, re.I)
        sex = sex_m.group(1).lower() if sex_m else "unknown"
        altered_m = re.search(r"Spayed/Neutered:\s*(Yes|No)", text, re.I)
        altered = "neutered" if altered_m and altered_m.group(1).lower() == "yes" and sex == "male" else "spayed" if altered_m and altered_m.group(1).lower() == "yes" and sex == "female" else "unknown"
        title = soup.find("h1")
        name = title.get_text(" ", strip=True) if title else None
        date_m = re.search(r"Date In Shelter:\s*([^\n]+)", text, re.I)
        reported_at = None
        if date_m:
            try:
                reported_at = dtparser.parse(date_m.group(1).strip()).replace(tzinfo=timezone.utc)
            except Exception:
                pass
        location_m = re.search(r"Location:\s*([^\n]+)", text, re.I)
        location = location_m.group(1).strip() if location_m else "Wake County Animal Center, Raleigh, NC"
        image_url = None
        for img in soup.find_all("img"):
            label = " ".join(filter(None, [img.get("alt"), img.get("title")]))
            if source_id in label or (name and name.lower() in label.lower()):
                src = img.get("src") or img.get("data-src")
                if src:
                    image_url = urljoin(source_url, src)
                    break
        source_posted_at = extract_source_posted_at(html, soup)
        return PetPostIn(
            source="wake_county_lostfound",
            source_id=source_id,
            source_url=source_url,
            status="shelter_intake",
            species="cat",
            name=name[:120] if name else None,
            sex=sex,
            altered_status=altered,
            description=f"Breed: {breed}." if breed else "Wake County Animal Center lost/found record.",
            location_text=location,
            image_url=image_url,
            reported_at=reported_at,
            raw={
                "breed": breed,
                "geocode_context": "Wake County, North Carolina, USA",
                "source_posted_at": source_posted_at.isoformat() if source_posted_at else None,
            },
        )
