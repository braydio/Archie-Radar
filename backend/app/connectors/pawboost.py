from __future__ import annotations

import asyncio
import re
from datetime import timezone
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from dateutil import parser as dtparser

from ..schemas import PetPostIn
from .base import Connector, extract_source_posted_at


class PawBoostConnector(Connector):
    source_name = "pawboost"

    def __init__(self, areas: list[str] | None = None, pages: int = 2, detail_limit: int = 24):
        self.areas = areas or ["chapel-hill-nc-27516"]
        self.pages = pages
        self.detail_limit = max(0, detail_limit)

    def _url(self, area: str, page: int) -> str:
        return f"https://www.pawboost.com/lost-found-pets/{area}/all-found-stray-cats/page-{page}"

    @staticmethod
    def _candidate_image(img, source_url: str) -> str | None:
        if img is None:
            return None
        src = img.get("src") or img.get("data-src") or img.get("data-lazy-src")
        if not src:
            return None
        absolute = urljoin(source_url, src)
        value = absolute.lower()
        alt = (img.get("alt") or "").lower()
        # PawBoost's actual pet photos are served from img-cdn.pawboost.com. Do not
        # accidentally ingest logos/hero art found higher in the listing card tree.
        host = urlparse(absolute).netloc.lower()
        if host == "img-cdn.pawboost.com" and not any(x in value for x in ("logo", "hero", "placeholder")):
            return absolute
        if "cat" in alt and not any(x in value for x in ("logo", "hero", "placeholder")):
            return absolute
        return None

    async def fetch_listings(self) -> list[PetPostIn]:
        posts: list[PetPostIn] = []
        headers = {"User-Agent": "ArchieRadar/0.7 (+lost-pet-reunion-project)"}
        async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=20) as client:
            for area in self.areas:
                for page in range(1, self.pages + 1):
                    try:
                        response = await client.get(self._url(area, page))
                        if response.status_code == 404:
                            continue
                        response.raise_for_status()
                        posts.extend(self.parse_listing(response.text, str(response.url)))
                    except httpx.HTTPError:
                        continue
                    await asyncio.sleep(0.35)
        return list({(p.source, p.source_id): p for p in posts}.values())

    async def enrich_posts(self, posts: list[PetPostIn], source_ids: set[str]) -> list[PetPostIn]:
        if not source_ids or not self.detail_limit:
            return posts
        candidates = [
            p for p in posts
            if p.source_id in source_ids and "/landing/pet/" in (p.source_url or "")
        ][: self.detail_limit]
        if not candidates:
            return posts

        headers = {"User-Agent": "ArchieRadar/0.7 (+lost-pet-reunion-project)"}
        semaphore = asyncio.Semaphore(3)
        async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=20) as client:
            async def enrich_one(post: PetPostIn) -> PetPostIn:
                async with semaphore:
                    try:
                        response = await client.get(post.source_url)
                        response.raise_for_status()
                        enriched = self.enrich_from_detail(post, response.text, str(response.url))
                        await asyncio.sleep(0.12)
                        return enriched
                    except httpx.HTTPError:
                        return post

            enriched_rows = await asyncio.gather(*(enrich_one(p) for p in candidates))
        replacements = {p.source_id: p for p in enriched_rows}
        return [replacements.get(p.source_id, p) for p in posts]

    async def fetch(self) -> list[PetPostIn]:
        # Standalone connector behavior: fetch listings and enrich a bounded batch.
        posts = await self.fetch_listings()
        ids = {p.source_id for p in posts if not p.image_url or not p.reported_at}
        return await self.enrich_posts(posts, ids)

    @staticmethod
    def parse_listing(html: str, source_url: str) -> list[PetPostIn]:
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text("\n", strip=True)

        matches = list(re.finditer(r"(?:FOUND|SIGHTING|SHELTER\s+INTAKE)\s+PawBoost ID:\s*(\d+)", text, re.I))
        records: list[PetPostIn] = []
        for i, m in enumerate(matches):
            start = max(0, text.rfind("Reported", 0, m.start()))
            end = matches[i + 1].start() if i + 1 < len(matches) else min(len(text), m.end() + 1600)
            chunk = text[start:end]
            source_id = m.group(1)

            status_match = re.search(r"\b(FOUND|SIGHTING|SHELTER\s+INTAKE)\b\s+PawBoost ID", chunk, re.I)
            status = status_match.group(1).lower().replace(" ", "_") if status_match else "found"

            sex_match = re.search(r"(?:Found Pet|Shelter Intake|\S+)\s+(Male|Female|Unknown)\s+Cat", chunk, re.I)
            sex = sex_match.group(1).lower() if sex_match else "unknown"

            location_match = re.search(r"([^\n]+,\s*NC\s+\d{5}(?:,\s*USA)?)", chunk, re.I)
            location = location_match.group(1).strip() if location_match else ""

            desc = ""
            after_id = chunk[m.end() - start :]
            lines = [line.strip() for line in after_id.splitlines() if line.strip()]
            stop_words = {"View On Facebook", "Share On", "View Pet", "Reported", "View all pets at this shelter"}
            for line in lines:
                if line in stop_words or line.startswith("View ") or line == "[Input]":
                    continue
                if location and line == location:
                    continue
                if len(line) > 12 and not line.isdigit():
                    desc = line[:1000]
                    break

            reported_at = None
            rep = re.search(r"Reported\s+([^\n]+)", chunk, re.I)
            if rep:
                phrase = rep.group(1).split(", updated")[0].strip()
                try:
                    if not re.search(r"\b(?:ago|mins?|hours?|days?|weeks?|months?|years?)\b", phrase, re.I):
                        reported_at = dtparser.parse(phrase).replace(tzinfo=timezone.utc)
                except Exception:
                    reported_at = None

            detail_url = source_url
            image_url = None
            id_node = soup.find(string=re.compile(rf"PawBoost ID:\s*{re.escape(source_id)}", re.I))
            node = id_node.parent if id_node else None
            for _ in range(9):
                if node is None:
                    break
                anchor = node.find("a", href=re.compile(r"/landing/pet/")) if hasattr(node, "find") else None
                image = node.find("img") if hasattr(node, "find") else None
                if anchor and anchor.get("href"):
                    detail_url = urljoin(source_url, anchor["href"])
                candidate = PawBoostConnector._candidate_image(image, source_url)
                if candidate:
                    image_url = candidate
                if detail_url != source_url and image_url:
                    break
                node = getattr(node, "parent", None)

            # Fallback: explicitly search detail links whose surrounding card contains
            # this PawBoost ID. This is sturdier than assuming a fixed ancestor depth.
            if detail_url == source_url:
                for anchor in soup.find_all("a", href=re.compile(r"/landing/pet/")):
                    card = anchor
                    for _ in range(7):
                        if card is None:
                            break
                        if source_id in card.get_text(" ", strip=True):
                            detail_url = urljoin(source_url, anchor.get("href"))
                            candidate = PawBoostConnector._candidate_image(card.find("img"), source_url)
                            if candidate:
                                image_url = candidate
                            break
                        card = getattr(card, "parent", None)
                    if detail_url != source_url:
                        break

            records.append(
                PetPostIn(
                    source="pawboost",
                    source_id=source_id,
                    source_url=detail_url,
                    status=status,
                    species="cat",
                    sex=sex,
                    description=desc,
                    location_text=location,
                    image_url=image_url,
                    reported_at=reported_at,
                    raw={"listing_url": source_url, "listing_text": chunk[:2000]},
                )
            )

        return records

    @staticmethod
    def enrich_from_detail(post: PetPostIn, html: str, detail_url: str) -> PetPostIn:
        """Fill image/date/finder details from a PawBoost landing page.

        PawBoost's listing page can omit images that are present on the detail page.
        The selector below intentionally matches the public featured-pet image class
        and then falls back to an image whose alt text describes a cat.
        """
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text("\n", strip=True)

        img = (
            soup.select_one("img.pet-details-featured-image")
            or soup.select_one("img.no-padding.pet-details-featured-image.width-full")
            or soup.find("img", alt=re.compile(r"(?:Found|Stray|Sighting).*Cat", re.I))
        )
        image_url = PawBoostConnector._candidate_image(img, detail_url)

        def value_after(label: str) -> str:
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            for i, line in enumerate(lines[:-1]):
                if line.lower() == label.lower():
                    return lines[i + 1]
            return ""

        detail_source_id = value_after("PawBoost ID")
        source_id = post.source_id
        status_text = value_after("Status")
        sex_text = value_after("Sex")
        location = value_after("Location Found") or post.location_text
        landmark = value_after("Nearest Landmark")
        description = value_after("Description") or post.description

        # "Message from Finder" can span a single rendered text line on current
        # PawBoost pages. Capture until the next known page section.
        finder_message = ""
        finder_node = soup.find(string=re.compile(r"^Message from Finder$", re.I))
        if finder_node:
            parent = finder_node.parent
            sibling = parent.find_next() if parent else None
            if sibling:
                candidate_text = sibling.get_text(" ", strip=True)
                if candidate_text and candidate_text.lower() != "message from finder":
                    finder_message = candidate_text[:1600]
        if not finder_message:
            match = re.search(r"Message from Finder\s*\n([^\n]+)", text, re.I)
            if match:
                finder_message = match.group(1).strip()[:1600]

        reported_at = post.reported_at
        date_text = value_after("Date Found") or value_after("Date Sighted")
        if date_text:
            try:
                reported_at = dtparser.parse(date_text).replace(tzinfo=timezone.utc)
            except Exception:
                pass

        source_posted_at = extract_source_posted_at(html, soup)

        raw = dict(post.raw or {})
        raw.update({
            "detail_page_enriched": True,
            "detail_source_id": detail_source_id or None,
            "detail_id_mismatch": bool(detail_source_id and detail_source_id != post.source_id),
            "image_confirmed_missing": image_url is None,
            "nearest_landmark": landmark,
            "finder_message": finder_message,
            "contact_available": bool(re.search(r"CONTACT FINDER", text, re.I)),
            "source_posted_at": source_posted_at.isoformat() if source_posted_at else raw.get("source_posted_at"),
            "posted_metadata_checked": True,
        })

        return post.model_copy(update={
            "source_id": source_id,
            "source_url": detail_url,
            "status": status_text.lower().replace(" ", "_") if status_text else post.status,
            "sex": sex_text.lower() if sex_text.lower() in {"male", "female", "unknown"} else post.sex,
            "description": description,
            "location_text": location,
            "image_url": image_url or post.image_url,
            "reported_at": reported_at,
            "raw": raw,
        })
