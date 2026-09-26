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
from .base import Connector, extract_source_posted_at


class Pet911Connector(Connector):
    source_name = "pet911"

    def __init__(self, places: list[str]):
        self.places = places

    async def fetch(self) -> list[PetPostIn]:
        headers = {"User-Agent": "ArchieRadar/0.7 (+lost-pet-reunion-project)"}
        posts: list[PetPostIn] = []
        async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=25) as client:
            for place in self.places:
                url = f"https://pet911.org/{place}/found"
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
        records: list[PetPostIn] = []

        # Prefer card-like anchors when available. Pet911 links individual notices from
        # the listing; walking parent containers keeps title/location/date together.
        candidates = []
        for anchor in soup.find_all("a", href=True):
            label = anchor.get_text(" ", strip=True)
            href = urljoin(source_url, anchor["href"])
            if not re.search(r"\bfound\b", label, re.I) and "/found" not in href.lower():
                continue
            node = anchor
            for _ in range(5):
                node = getattr(node, "parent", None)
                if node is None:
                    break
                chunk = node.get_text("\n", strip=True)
                if len(chunk) >= 40 and re.search(r"\bFound\b", chunk, re.I):
                    candidates.append((href, node, chunk))
                    break

        # Fallback for server-rendered pages where notice links are not easy to identify.
        if not candidates:
            text = soup.get_text("\n", strip=True)
            chunks = re.split(r"(?=\nFound\n)", "\n" + text)
            for chunk in chunks:
                if len(chunk) > 40 and re.search(r"\bcat\b", chunk, re.I):
                    candidates.append((source_url, None, chunk))

        seen: set[str] = set()
        for href, node, chunk in candidates:
            if not re.search(r"\bcat\b", chunk, re.I):
                continue
            lines = [x.strip() for x in chunk.splitlines() if x.strip()]
            title = next((x for x in lines if re.search(r"\bcat\b", x, re.I) and len(x) > 8), "Found cat")
            date_text = next((x for x in reversed(lines) if re.search(r"\b\d{1,2}[./-]\d{1,2}[./-]\d{4}\b", x)), "")
            reported_at = None
            if date_text:
                try:
                    reported_at = dtparser.parse(date_text, dayfirst=True).replace(tzinfo=timezone.utc)
                except Exception:
                    pass
            # Location usually appears as a street/address line directly below title.
            location = ""
            for line in lines:
                if line == title or line.lower() in {"found", "back", "back to list"}:
                    continue
                if re.search(r"\b(?:road|rd|street|st|drive|dr|lane|ln|court|ct|avenue|ave|place|pl|highway|hwy|chapel hill|durham|raleigh|carrboro|pittsboro)\b", line, re.I):
                    location = line
                    break
            description = next((x for x in lines if x not in {title, location, date_text, "Found"} and len(x) >= 20), "")

            source_posted_at = extract_source_posted_at(str(node), BeautifulSoup(str(node), "html.parser")) if node is not None else None
            image_url = None
            if node is not None:
                img = node.find("img")
                if img:
                    src = img.get("src") or img.get("data-src") or img.get("data-lazy-src")
                    if src:
                        image_url = urljoin(source_url, src)
            source_id = hashlib.sha1(f"{href}|{title}|{location}|{date_text}".encode()).hexdigest()[:16]
            if source_id in seen:
                continue
            seen.add(source_id)
            sex = "male" if re.search(r"\bmale\b", chunk, re.I) else "female" if re.search(r"\bfemale\b", chunk, re.I) else "unknown"
            records.append(PetPostIn(
                source="pet911",
                source_id=source_id,
                source_url=href,
                status="found",
                species="cat",
                sex=sex,
                description=description[:1000],
                location_text=location,
                image_url=image_url,
                reported_at=reported_at,
                raw={
                    "listing_url": source_url,
                    "listing_text": chunk[:2500],
                    "geocode_context": "Triangle, North Carolina, USA",
                    "source_posted_at": source_posted_at.isoformat() if source_posted_at else None,
                },
            ))
        return records
