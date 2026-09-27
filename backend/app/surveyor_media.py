from __future__ import annotations

import asyncio
import json
import mimetypes
import re
import shutil
import subprocess
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException, UploadFile
from PIL import Image, ImageOps
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.staticfiles import StaticFiles

CHUNK_SIZE = 1024 * 1024
ALLOWED_TYPES = {
    "image/jpeg": "image", "image/png": "image", "image/webp": "image", "image/gif": "image",
    "image/heic": "image", "image/heif": "image",
    "video/mp4": "video", "video/webm": "video", "video/quicktime": "video", "video/3gpp": "video",
    "audio/mpeg": "audio", "audio/mp3": "audio", "audio/wav": "audio", "audio/x-wav": "audio",
    "audio/webm": "audio", "audio/ogg": "audio", "audio/mp4": "audio", "audio/m4a": "audio",
    "application/pdf": "document", "text/plain": "document",
}


def safe_original_name(filename: str | None) -> str:
    name = (filename or "field-media").replace("\\", "/").split("/")[-1].strip()
    name = re.sub(r"[^A-Za-z0-9._ -]+", "_", name)
    name = re.sub(r"\s+", "_", name).strip("._-")
    return (name[:180] or "field-media")


def classify_media(mime_type: str | None, filename: str | None = None) -> tuple[str, str]:
    value = (mime_type or "application/octet-stream").split(";", 1)[0].strip().lower()
    kind = ALLOWED_TYPES.get(value)
    if not kind:
        guessed, _ = mimetypes.guess_type(filename or "")
        if guessed:
            value = guessed
            kind = ALLOWED_TYPES.get(value)
    return (kind, value) if kind else ("", value)


def contained_path(media_dir: Path, storage_path: str) -> Path:
    root = media_dir.resolve()
    path = (root / storage_path).resolve()
    if path != root and root not in path.parents:
        raise HTTPException(status_code=400, detail="Attachment path is outside the media directory")
    return path


class PublicMediaFiles(StaticFiles):
    """Serve existing public/candidate assets without exposing Surveyor originals."""
    async def get_response(self, path: str, scope):
        if Path(path).parts[:1] == ("surveyor",):
            raise StarletteHTTPException(status_code=404)
        return await super().get_response(path, scope)


def delete_attachment_files(row, media_dir: Path) -> None:
    paths = []
    if row.storage_path:
        paths.append(row.storage_path)
    for relative in (attachment_metadata(row).get("derivatives") or {}).values():
        paths.append((Path("surveyor") / relative).as_posix())
    resolved_paths = [contained_path(media_dir, relative) for relative in paths]
    for path in resolved_paths:
        if path.is_file():
            path.unlink()


def _format_for_mime(mime_type: str) -> str:
    return {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP", "image/gif": "GIF"}.get(mime_type, "JPEG")


def _make_image_derivatives(original: Path, derived: Path, stem: str, mime_type: str) -> dict[str, Any]:
    try:
        with Image.open(original) as opened:
            gps = {}
            try:
                gps_ifd = opened.getexif().get_ifd(34853)
                def degrees(parts):
                    values = [float(value) for value in parts]
                    return values[0] + values[1] / 60 + values[2] / 3600
                if gps_ifd and gps_ifd.get(2) and gps_ifd.get(4):
                    latitude = degrees(gps_ifd[2]) * (-1 if str(gps_ifd.get(1, "N")) == "S" else 1)
                    longitude = degrees(gps_ifd[4]) * (-1 if str(gps_ifd.get(3, "E")) == "W" else 1)
                    if -90 <= latitude <= 90 and -180 <= longitude <= 180:
                        gps = {"latitude": latitude, "longitude": longitude}
            except Exception:
                gps = {}
            image = ImageOps.exif_transpose(opened)
            width, height = image.size
            image.load()
            image = image.convert("RGB")
        paths = {}
        for label, maximum in (("thumbnail", 360), ("preview", 1600)):
            display = image.copy()
            display.thumbnail((maximum, maximum), Image.Resampling.LANCZOS)
            destination = derived / f"{stem}_{label}.jpg"
            destination.parent.mkdir(parents=True, exist_ok=True)
            display.save(destination, "JPEG", quality=86, optimize=True)
            paths[label] = str(destination.relative_to(original.parents[1]))
        result = {"width": width, "height": height, "aspect_ratio": round(width / height, 6) if height else None, "derivatives": paths}
        if gps:
            result["exif_gps"] = gps
        return result
    except Exception:
        # A valid upload must remain stored even if derivative generation fails.
        return {"derivatives_error": "Image preview generation failed"}


def _video_details(original: Path, derived: Path, stem: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    probe = shutil.which("ffprobe")
    if probe:
        try:
            completed = subprocess.run(
                [probe, "-v", "error", "-show_entries", "format=duration:stream=width,height", "-of", "json", str(original)],
                capture_output=True, text=True, timeout=15, check=True,
            )
            info = json.loads(completed.stdout)
            duration = (info.get("format") or {}).get("duration")
            if duration is not None:
                result["duration_seconds"] = round(float(duration), 2)
            dimensions = next((item for item in info.get("streams", []) if item.get("width") and item.get("height")), None)
            if dimensions:
                result.update(width=int(dimensions["width"]), height=int(dimensions["height"]))
        except Exception:
            pass
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        poster = derived / f"{stem}_poster.jpg"
        try:
            poster.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run([ffmpeg, "-y", "-ss", "1", "-i", str(original), "-frames:v", "1", "-vf", "scale='min(640,iw)':-2", str(poster)],
                           capture_output=True, timeout=25, check=True)
            result.setdefault("derivatives", {})["poster"] = str(poster.relative_to(original.parents[1]))
        except Exception:
            poster.unlink(missing_ok=True)
    return result


async def store_upload(
    upload: UploadFile,
    media_dir: Path,
    *,
    caption: str = "",
    notes: str = "",
    observed_at: datetime | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    duration_seconds: float | None = None,
    width: int | None = None,
    height: int | None = None,
    max_bytes: int,
) -> tuple[str, dict[str, Any]]:
    media_type, mime_type = classify_media(upload.content_type, upload.filename)
    if not media_type:
        raise HTTPException(status_code=415, detail="Supported media: common photos, MP4/WebM video, MP3/WAV/OGG/M4A audio, PDF, and plain text")

    original_filename = safe_original_name(upload.filename)
    suffix = Path(original_filename).suffix.lower()
    if not re.fullmatch(r"\.[a-z0-9]{1,10}", suffix):
        suffix = mimetypes.guess_extension(mime_type) or ".bin"
    suffix = ".jpg" if mime_type == "image/jpeg" else suffix
    stem = uuid.uuid4().hex
    relative = Path("surveyor") / "original" / f"{stem}_{Path(original_filename).stem[:100]}{suffix}"
    destination = media_dir / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    size = 0
    try:
        with destination.open("wb") as output:
            while chunk := await upload.read(CHUNK_SIZE):
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(status_code=413, detail="Media exceeds the upload size limit")
                output.write(chunk)
        if size == 0:
            raise HTTPException(status_code=422, detail="Selected media file is empty")
        details: dict[str, Any] = {}
        derived_dir = media_dir / "surveyor" / "derived"
        if media_type == "image":
            details = await asyncio.to_thread(_make_image_derivatives, destination, derived_dir, stem, mime_type)
        elif media_type == "video":
            details = await asyncio.to_thread(_video_details, destination, derived_dir, stem)
        if duration_seconds is not None and duration_seconds >= 0:
            details.setdefault("duration_seconds", round(duration_seconds, 2))
        if width and height:
            details.setdefault("width", width)
            details.setdefault("height", height)
        metadata: dict[str, Any] = {
            **details,
            "media_type": media_type,
            "mime_type": mime_type,
            "original_filename": original_filename,
            "file_size_bytes": size,
            "notes": notes,
        }
        if latitude is not None and longitude is not None and -90 <= latitude <= 90 and -180 <= longitude <= 180:
            metadata["latitude"] = latitude
            metadata["longitude"] = longitude
        if observed_at:
            metadata["observed_at"] = observed_at.isoformat()
        return relative.as_posix(), {"caption": caption, **metadata}
    except Exception:
        destination.unlink(missing_ok=True)
        raise


def attachment_metadata(row) -> dict[str, Any]:
    try:
        value = json.loads(row.metadata_json or "{}")
        return value if isinstance(value, dict) else {}
    except (TypeError, json.JSONDecodeError):
        return {}
