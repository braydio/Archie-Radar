from __future__ import annotations

import asyncio
import hashlib
import re
from datetime import timezone
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from dateutil import parser as dtparser

from ..schemas import PetPostIn
from .base import Connector, extract_source_posted_at


class APSDurhamFoundPetsConnector(Connector):
    """Community found-pet reports hosted by APS of Durham.

    APS explicitly distinguishes these reports from animals currently at the shelter,
    so this source complements the 24PetConnect shelter feed.
    """

    source_name = "aps_durham_found"
    archive_url = "https://www.apsofdurham.org/found-pets/"

    def __init__(self, max_details: int = 30):
        self.max_details = max_details

    async def fetch(self) -> list[PetPostIn]:
        headers = {"User-Agent": "ArchieRadar/0.7 (+lost-pet-reunion-project)"}
        async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=25) as client:
            response = await client.get(self.archive_url)
            response.raise_for_status()
            links = self.parse_archive_links(response.text, str(response.url))[: self.max_details]
            records: list[PetPostIn] = []
            for url in links:
                try:
                    detail = await client.get(url)
                    detail.raise_for_status()
                    row = self.parse_detail(detail.text, str(detail.url))
                    if row and row.species == "cat":
                        records.append(row)
                except httpx.HTTPError:
                    continue
                await asyncio.sleep(0.2)
            return records

    @staticmethod
    def parse_archive_links(html: str, base_url: str) -> list[str]:
        soup = BeautifulSoup(html, "html.parser")
        seen: set[str] = set()
        links: list[str] = []
        for anchor in soup.find_all("a", href=True):
            href = urljoin(base_url, anchor["href"])
            path = urlparse(href).path.rstrip("/")
            if not path.startswith("/found-pets/") or path == "/found-pets":
                continue
            if href not in seen:
                seen.add(href)
                links.append(href)
        return links

    @staticmethod
    def parse_detail(html: str, source_url: str) -> PetPostIn | None:
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text("\n", strip=True)
        if "Found Near" not in text or "Found On Date" not in text:
            return None

        heading = soup.find(["h1", "h2", "h3"])
        title = heading.get_text(" ", strip=True) if heading else "Found pet"
        lowered = text.lower()
        species = "cat" if re.search(r"\b(cat|kitten|domestic shorthair|domestic longhair|tabby|siamese)\b", lowered) else "dog" if re.search(r"\b(dog|puppy)\b", lowered) else "unknown"

        # The archive commonly lists age/sex as bullet items near the title.
        if re.search(r"\bmale\b", text, re.I):
            sex = "male"
        elif re.search(r"\bfemale\b", text, re.I):
            sex = "female"
        else:
            sex = "unknown"

        def field(label: str) -> str:
            m = re.search(rf"{re.escape(label)}\s*\n\s*([^\n]+)", text, re.I)
            return m.group(1).strip() if m else ""

        fur_type = field("Fur Type")
        color = field("Fur Color")
        marks = field("Identifying Marks")
        location = field("Found Near")
        date_text = field("Found On Date")
        reported_at = None
        if date_text:
            try:
                reported_at = dtparser.parse(date_text).replace(tzinfo=timezone.utc)
            except Exception:
                pass

        image_url = None
        for img in soup.find_all("img"):
            src = img.get("src") or img.get("data-src") or img.get("data-lazy-src")
            if src and not any(token in src.lower() for token in ("logo", "icon", "avatar")):
                image_url = urljoin(source_url, src)
                break

        source_posted_at = extract_source_posted_at(html, soup)
        slug = urlparse(source_url).path.rstrip("/").split("/")[-1]
        source_id = slug or hashlib.sha1(source_url.encode()).hexdigest()[:12]
        description = ". ".join(part for part in [f"Fur: {fur_type}" if fur_type else "", f"Color: {color}" if color else "", f"Marks: {marks}" if marks else ""] if part)
        return PetPostIn(
            source="aps_durham_found",
            source_id=source_id,
            source_url=source_url,
            status="found_with_finder",
            species=species,
            name=None if title.lower().startswith("found ") else title[:120],
            sex=sex,
            description=description,
            location_text=location,
            image_url=image_url,
            reported_at=reported_at,
            raw={
                "geocode_context": "Durham County, North Carolina, USA",
                "title": title,
                "source_posted_at": source_posted_at.isoformat() if source_posted_at else None,
            },
        )
