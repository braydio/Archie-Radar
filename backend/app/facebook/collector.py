from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select

from ..db import SessionLocal
from ..models import FacebookGroupSubscription, FacebookGroupSyncReceipt, FacebookGroupSyncRun, utcnow
from ..settings import get_settings
from .schemas import BatchIn
from .session import session_status, storage_state_path, update_session_meta

logger = logging.getLogger("archie-radar.facebook")
settings = get_settings()


class FacebookLoginRequired(RuntimeError):
    pass


_EXTRACT_FEED = r"""
() => {
  const canonicalUrl = href => {
    try {
      const url = new URL(href, location.href);
      url.hash = '';
      // Keep story_fbid/id query parameters because they can be the only stable ID.
      for (const key of [...url.searchParams.keys()]) {
        if (!['story_fbid', 'id'].includes(key)) url.searchParams.delete(key);
      }
      return url.href.replace(/\/$/, '');
    } catch { return ''; }
  };

  const extractPost = article => {
    const text = (article.innerText || '').trim().slice(0, 30000);
    if (!text) return null;
    const permalink = article.querySelector(
      'a[href*="/posts/"], a[href*="/permalink/"], a[href*="story_fbid="], a[href*="/videos/"]'
    );
    const postUrl = canonicalUrl(permalink?.href || '');
    const idMatch = postUrl.match(/\/posts\/(\d+)|\/permalink\/(\d+)|[?&]story_fbid=(\d+)/);
    const times = [...article.querySelectorAll('time[datetime]')];
    const postedAt = times.map(time => time.getAttribute('datetime')).find(Boolean) || null;
    const images = [...article.querySelectorAll('img')]
      .filter(image => (image.naturalWidth || Number(image.getAttribute('width')) || 0) >= 120)
      .filter(image => (image.naturalHeight || Number(image.getAttribute('height')) || 0) >= 120)
      .filter(image => image.currentSrc || image.src)
      .slice(0, 8)
      .map(image => ({
        url: image.currentSrc || image.src,
        width: image.naturalWidth || Number(image.getAttribute('width')) || null,
        height: image.naturalHeight || Number(image.getAttribute('height')) || null
      }));

    return {
      facebook_post_id: idMatch?.[1] || idMatch?.[2] || idMatch?.[3] || null,
      canonical_url: postUrl || null,
      text,
      author_name: null,
      posted_at: postedAt,
      images,
      video_present: !!article.querySelector('video, a[href*="/videos/"]'),
      captured_at: new Date().toISOString()
    };
  };

  const articles = [...document.querySelectorAll('[role="article"], article')];
  const posts = [];
  const seen = new Set();
  for (const article of articles) {
    const post = extractPost(article);
    if (!post) continue;
    const key = post.facebook_post_id || post.canonical_url || post.text.slice(0, 160);
    if (seen.has(key)) continue;
    seen.add(key);
    posts.push(post);
  }
  const heading = document.querySelector('h1')?.innerText?.trim();
  return {
    posts,
    article_count: articles.length,
    group_name: heading || document.title || 'Facebook group'
  };
}
"""


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _run_due(db) -> bool:
    minutes = max(0, int(settings.facebook_sync_minutes))
    if not settings.facebook_server_collector_enabled or minutes <= 0 or not session_status()["ready"]:
        return False
    if db.scalar(select(FacebookGroupSyncRun.id).where(
        FacebookGroupSyncRun.status.in_(["queued", "syncing"])
    ).limit(1)) is not None:
        return False
    if db.scalar(select(FacebookGroupSubscription.id).where(
        FacebookGroupSubscription.enabled.is_(True)
    ).limit(1)) is None:
        return False
    latest = db.scalar(select(FacebookGroupSyncRun).where(
        FacebookGroupSyncRun.completed_at.is_not(None)
    ).order_by(FacebookGroupSyncRun.completed_at.desc()).limit(1))
    if latest is None:
        return True
    completed = _as_utc(latest.completed_at)
    return completed is None or utcnow() - completed >= timedelta(minutes=minutes)


def _queue_sync(db) -> FacebookGroupSyncRun | None:
    groups = list(db.scalars(select(FacebookGroupSubscription).where(
        FacebookGroupSubscription.enabled.is_(True)
    )))
    if not groups:
        return None
    run = FacebookGroupSyncRun(requested_group_count=len(groups), status="queued")
    db.add(run)
    db.flush()
    for group in groups:
        db.add(FacebookGroupSyncReceipt(
            sync_run_id=run.id,
            group_subscription_id=group.id,
            status="queued",
        ))
    db.commit()
    db.refresh(run)
    return run


def _claim_next_run(db) -> tuple[FacebookGroupSyncRun, list[FacebookGroupSubscription]] | None:
    run = db.scalar(select(FacebookGroupSyncRun).where(
        FacebookGroupSyncRun.status == "queued"
    ).order_by(FacebookGroupSyncRun.started_at, FacebookGroupSyncRun.id).limit(1))
    if run is None:
        return None
    run.status = "syncing"
    receipts = list(db.scalars(select(FacebookGroupSyncReceipt).where(
        FacebookGroupSyncReceipt.sync_run_id == run.id
    )))
    group_ids = [item.group_subscription_id for item in receipts]
    groups_by_id = {row.id: row for row in db.scalars(select(FacebookGroupSubscription).where(
        FacebookGroupSubscription.id.in_(group_ids or [-1])
    ))}
    now = utcnow()
    groups: list[FacebookGroupSubscription] = []
    for receipt in receipts:
        group = groups_by_id.get(receipt.group_subscription_id)
        if group is None or not group.enabled:
            receipt.status = "disabled"
            receipt.completed_at = now
            continue
        group.last_sync_started_at = now
        receipt.status = "syncing"
        groups.append(group)
    db.commit()
    return run, groups


def _fail_group(db, run_id: int, group_id: int, error: str, parser_warning: str = "") -> None:
    receipt = db.scalar(select(FacebookGroupSyncReceipt).where(
        FacebookGroupSyncReceipt.sync_run_id == run_id,
        FacebookGroupSyncReceipt.group_subscription_id == group_id,
    ))
    group = db.get(FacebookGroupSubscription, group_id)
    if receipt is None or group is None:
        return
    now = utcnow()
    receipt.scanned = 0
    receipt.parser_warning = parser_warning[:1000]
    receipt.error = error[:2000]
    receipt.status = "parser_warning" if parser_warning and not error else "failed"
    receipt.completed_at = now
    group.last_sync_completed_at = now
    group.last_error = receipt.error or receipt.parser_warning
    group.parser_warning = receipt.parser_warning
    db.commit()


def _finish_run(db, run_id: int, errors: list[str]) -> None:
    run = db.get(FacebookGroupSyncRun, run_id)
    if run is None:
        return
    receipts = list(db.scalars(select(FacebookGroupSyncReceipt).where(
        FacebookGroupSyncReceipt.sync_run_id == run_id
    )))
    now = utcnow()
    for receipt in receipts:
        if receipt.status in {"queued", "syncing"}:
            receipt.status = "failed"
            receipt.error = "Server collector ended before this group completed"
            receipt.completed_at = now
    problems = [item for item in receipts if item.status in {"failed", "parser_warning"}]
    summaries = [value for value in errors if value]
    summaries.extend(item.error or item.parser_warning for item in problems if item.error or item.parser_warning)
    run.error_summary = "\n".join(dict.fromkeys(value for value in summaries if value))
    run.completed_at = now
    if problems and run.successful_group_count:
        run.status = "partial"
    elif problems or not run.successful_group_count:
        run.status = "failed"
    else:
        run.status = "complete"
    db.commit()


async def _hash_images(context, post: dict[str, Any]) -> dict[str, Any]:
    images = []
    for image in (post.get("images") or [])[:3]:
        url = str(image.get("url") or "")
        enriched = dict(image)
        if not url.startswith(("https://", "http://")):
            continue
        try:
            response = await context.request.get(url, timeout=8000)
            if response.ok:
                raw_size = response.headers.get("content-length")
                if raw_size is None or int(raw_size) <= 5_000_000:
                    body = await response.body()
                    if len(body) <= 5_000_000:
                        enriched["sha256"] = hashlib.sha256(body).hexdigest()
        except Exception:
            pass
        images.append(enriched)
        await asyncio.sleep(0.12)
    return {**post, "images": images}


async def _scan_group(context, group: dict[str, Any]) -> dict[str, Any]:
    page = await context.new_page()
    try:
        await page.goto(
            group["group_url"],
            wait_until="domcontentloaded",
            timeout=max(10, int(settings.facebook_page_timeout_seconds)) * 1000,
        )
        await page.wait_for_timeout(2200)

        lowered_url = page.url.lower()
        login_count = await page.locator('input[name="email"], input[name="pass"]').count()
        if "/login" in lowered_url or "/checkpoint" in lowered_url or login_count:
            raise FacebookLoginRequired("Facebook login required. Reconnect the server session once from the helper extension.")

        seen_ids = set(group.get("watermark_post_ids") or [])
        cutoff_value = group.get("first_sync_cutoff")
        cutoff = datetime.fromisoformat(cutoff_value.replace("Z", "+00:00")) if cutoff_value else None
        if cutoff is not None and cutoff.tzinfo is None:
            cutoff = cutoff.replace(tzinfo=timezone.utc)

        by_key: dict[str, dict[str, Any]] = {}
        seen_watermarks: set[str] = set()
        seen_old_posts: set[str] = set()
        repeated_watermark = 0
        older_than_cutoff = 0
        scanned_articles = 0

        for pass_index in range(max(1, min(int(settings.facebook_scan_max_passes), 20))):
            snapshot = await page.evaluate(_EXTRACT_FEED)
            scanned_articles = max(scanned_articles, int(snapshot.get("article_count") or 0))
            for post in snapshot.get("posts") or []:
                key = post.get("facebook_post_id") or post.get("canonical_url")
                if key:
                    by_key[key] = post
                post_id = post.get("facebook_post_id")
                if post_id and post_id in seen_ids and post_id not in seen_watermarks:
                    seen_watermarks.add(post_id)
                    repeated_watermark += 1
                if key and cutoff and post.get("posted_at") and key not in seen_old_posts:
                    try:
                        posted = datetime.fromisoformat(str(post["posted_at"]).replace("Z", "+00:00"))
                        if posted.tzinfo is None:
                            posted = posted.replace(tzinfo=timezone.utc)
                        if posted < cutoff:
                            seen_old_posts.add(key)
                            older_than_cutoff += 1
                    except ValueError:
                        pass

            if repeated_watermark >= 20 or older_than_cutoff >= 10:
                break
            before = await page.evaluate("document.scrollingElement?.scrollHeight || document.documentElement.scrollHeight")
            await page.evaluate("window.scrollTo(0, document.scrollingElement?.scrollHeight || document.documentElement.scrollHeight)")
            await page.wait_for_timeout(950 + (pass_index % 3) * 140)
            after = await page.evaluate("document.scrollingElement?.scrollHeight || document.documentElement.scrollHeight")
            if after == before and pass_index >= 2:
                break

        posts = []
        for post in list(by_key.values())[:500]:
            posts.append(await _hash_images(context, post))

        return {
            "group_name": snapshot.get("group_name") if 'snapshot' in locals() else group.get("group_name"),
            "scanned": scanned_articles,
            "posts": posts,
            "parser_warning": "" if scanned_articles else "No rendered feed articles detected; Facebook layout, login, or group permissions may have changed.",
        }
    finally:
        await page.close()


async def _process_run(run_id: int, groups: list[dict[str, Any]]) -> None:
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        update_session_meta("collector_unavailable", "Playwright is not installed")
        raise RuntimeError("Playwright is not installed in the Archie Radar backend") from exc

    path = storage_state_path()
    if path is None:
        update_session_meta("missing", "Facebook server session has not been handed off yet")
        raise FacebookLoginRequired("Facebook server session is not connected")

    errors: list[str] = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=True,
            args=["--disable-dev-shm-usage", "--no-default-browser-check"],
        )
        context = await browser.new_context(
            storage_state=str(path),
            viewport={"width": 1280, "height": 900},
            locale="en-US",
        )
        try:
            for group in groups:
                try:
                    result = await _scan_group(context, group)
                    payload = BatchIn(
                        sync_run_id=run_id,
                        group_subscription_id=group["id"],
                        scanned=result["scanned"],
                        parser_warning=result["parser_warning"],
                        posts=result["posts"],
                    )
                    # Reuse the existing normalized ingestion + cross-post dedupe path.
                    from .router import _upsert_facebook_batch
                    with SessionLocal() as db:
                        _upsert_facebook_batch(db, payload)
                except FacebookLoginRequired:
                    update_session_meta("login_required", "Facebook login expired or challenged")
                    raise
                except Exception as exc:
                    message = f"{group['group_name']}: {exc}"
                    errors.append(message)
                    logger.warning("Facebook group scan failed: %s", message)
                    with SessionLocal() as db:
                        _fail_group(db, run_id, group["id"], str(exc))
                await asyncio.sleep(1.2)

            await context.storage_state(path=str(path))
            try:
                path.chmod(0o600)
            except OSError:
                pass
            update_session_meta("ready", "")
        finally:
            await context.close()
            await browser.close()

    with SessionLocal() as db:
        _finish_run(db, run_id, errors)


async def process_next_server_sync() -> bool:
    with SessionLocal() as db:
        if _run_due(db):
            _queue_sync(db)
        claimed = _claim_next_run(db)
        if claimed is None:
            return False
        run, group_rows = claimed
        groups = []
        for group in group_rows:
            watermarks = json.loads(group.watermark_json or "[]")
            groups.append({
                "id": group.id,
                "group_url": group.group_url,
                "group_name": group.group_name,
                "watermark_post_ids": watermarks[-30:],
                "first_sync_cutoff": (
                    _as_utc(group.initial_sync_cutoff).isoformat()
                    if group.last_success_at is None and group.initial_sync_cutoff
                    else None
                ),
            })
        run_id = run.id

    try:
        await _process_run(run_id, groups)
    except FacebookLoginRequired as exc:
        with SessionLocal() as db:
            for group in groups:
                _fail_group(db, run_id, group["id"], str(exc))
            _finish_run(db, run_id, [str(exc)])
    except Exception as exc:
        logger.exception("Facebook server collector failed")
        update_session_meta("collector_error", str(exc))
        with SessionLocal() as db:
            _finish_run(db, run_id, [str(exc)])
    return True


async def facebook_collector_forever() -> None:
    """Run Facebook group aggregation without depending on a user's browser process."""
    await asyncio.sleep(8)
    while True:
        try:
            worked = await process_next_server_sync()
            await asyncio.sleep(2 if worked else 15)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Facebook collector loop failed")
            await asyncio.sleep(30)
