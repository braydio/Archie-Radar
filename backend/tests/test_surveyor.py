import pytest
import asyncio
from fastapi.testclient import TestClient
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile
from PIL import Image
from fastapi import HTTPException

from app import main
from app.surveyor_media import PublicMediaFiles, contained_path, delete_attachment_files


def create_pin(client: TestClient, coordinates: list[float], name: str = "Field marker") -> dict:
    response = client.post("/api/surveyor/objects", json={
        "object_type": "pin", "subtype": "sighting", "name": name,
        "geometry": {"type": "Point", "coordinates": coordinates},
    })
    assert response.status_code == 201, response.text
    return response.json()


def test_point_object_has_centroid_and_bbox(client: TestClient) -> None:
    result = create_pin(client, [-79.1, 35.8])
    assert result["centroid_lon"] == pytest.approx(-79.1)
    assert result["centroid_lat"] == pytest.approx(35.8)
    assert result["bbox"] == pytest.approx([-79.1, 35.8, -79.1, 35.8])


def test_malformed_geojson_is_rejected(client: TestClient) -> None:
    response = client.post("/api/surveyor/objects", json={
        "object_type": "zone", "geometry": {"type": "Polygon", "coordinates": []},
    })
    assert response.status_code == 422


def create_camera(client: TestClient) -> dict:
    response = client.post("/api/surveyor/cameras", json={
        "name": "CAM 2", "latitude": 35.8, "longitude": -79.1,
        "heading_degrees": 60, "fov_degrees": 62, "range_meters": 45,
    })
    assert response.status_code == 201, response.text
    return response.json()


def test_camera_aim_updates_active_placement_in_place(client: TestClient) -> None:
    camera = create_camera(client)
    response = client.patch(f"/api/surveyor/cameras/{camera['id']}", json={"heading_degrees": 75, "fov_degrees": 70, "range_meters": 55})
    assert response.status_code == 200, response.text
    result = response.json()
    assert len(result["history"]) == 1
    assert result["placement"]["heading_degrees"] == 75
    assert result["placement"]["fov_degrees"] == 70
    assert result["placement"]["range_meters"] == 55
    saved = client.patch(f"/api/surveyor/cameras/{camera['id']}", json={"save_as_new_placement": True})
    assert saved.status_code == 200, saved.text
    assert len(saved.json()["history"]) == 2


def test_camera_move_creates_history(client: TestClient) -> None:
    camera = create_camera(client)
    response = client.patch(f"/api/surveyor/cameras/{camera['id']}", json={"latitude": 35.81, "longitude": -79.09})
    assert response.status_code == 200, response.text
    history = response.json()["history"]
    assert len(history) == 2
    assert sum(placement["removed_at"] is None for placement in history) == 1
    assert sum(placement["removed_at"] is not None for placement in history) == 1


def test_link_endpoint_follows_moved_source_object(client: TestClient) -> None:
    source = create_pin(client, [-79.1, 35.8], "Source")
    target = create_pin(client, [-79.08, 35.82], "Target")
    linked = client.post("/api/surveyor/links", json={
        "source_object_id": source["id"], "target_object_id": target["id"], "link_type": "association",
    })
    assert linked.status_code == 201, linked.text
    original = linked.json()["geometry"]["coordinates"][0]
    moved = client.patch(f"/api/surveyor/objects/{source['id']}", json={
        "geometry": {"type": "Point", "coordinates": [-79.11, 35.8]},
    })
    assert moved.status_code == 200, moved.text
    refreshed = client.get("/api/surveyor/links").json()[0]
    assert refreshed["geometry"]["coordinates"][0] != original
    assert refreshed["geometry"]["coordinates"][0] == pytest.approx([-79.11, 35.8])


def test_archived_object_is_omitted_from_normal_list(client: TestClient) -> None:
    obj = create_pin(client, [-79.1, 35.8])
    response = client.delete(f"/api/surveyor/objects/{obj['id']}")
    assert response.status_code == 204
    objects = client.get("/api/surveyor/objects").json()
    assert all(item["id"] != obj["id"] for item in objects)


def test_researched_zone_refresh_records_zone_researched_event(client: TestClient) -> None:
    response = client.post("/api/surveyor/objects", json={
        "object_type": "zone", "subtype": "searched", "status": "searched", "name": "Creek edge",
        "geometry": {"type": "Polygon", "coordinates": [[[-79.1, 35.8], [-79.09, 35.8], [-79.09, 35.81], [-79.1, 35.8]]]},
        "properties": {"searched_at": "2026-09-20T12:00:00+00:00"},
    })
    assert response.status_code == 201, response.text
    obj = response.json()
    updated = client.patch(f"/api/surveyor/objects/{obj['id']}", json={
        "properties": {"searched_at": "2026-09-26T12:00:00+00:00", "search_method": "walking"},
    })
    assert updated.status_code == 200, updated.text
    events = client.get("/api/surveyor/events", params={"limit": 20}).json()
    assert any(event["event_type"] == "zone_researched" and event["entity_id"] == str(obj["id"]) for event in events)


def test_access_record_creates_geographic_object_and_can_mark_do_not_contact(client: TestClient) -> None:
    created = client.post("/api/surveyor/access", json={
        "longitude": -79.1, "latitude": 35.8, "name": "Creekside",
        "access_status": "permission_granted", "dog_count": 2,
        "camera_permission": "yes", "contact_notes": "Use the rear gate.",
    })
    assert created.status_code == 201, created.text
    row = created.json()
    assert row["dog_count"] == 2
    assert row["longitude"] == pytest.approx(-79.1)
    updated = client.patch(f"/api/surveyor/access/{row['id']}", json={"access_status": "do_not_contact"})
    assert updated.status_code == 200, updated.text
    assert updated.json()["access_status"] == "do_not_contact"
    assert client.get("/api/surveyor/events?event_type=access_updated").json()


def test_task_completion_records_event_and_timestamp(client: TestClient) -> None:
    obj = create_pin(client, [-79.1, 35.8])
    created = client.post("/api/surveyor/tasks", json={
        "title": "Check the creek crossing", "task_type": "recheck",
        "map_object_id": obj["id"], "priority": "high",
    })
    assert created.status_code == 201, created.text
    task = created.json()
    assert task["map_object_id"] == obj["id"]
    completed = client.patch(f"/api/surveyor/tasks/{task['id']}", json={"status": "completed"})
    assert completed.status_code == 200, completed.text
    assert completed.json()["completed_at"] is not None
    assert client.get("/api/surveyor/events?event_type=task_completed").json()


def test_browser_audio_mime_is_accepted_and_attachment_can_be_deleted(client: TestClient) -> None:
    obj = create_pin(client, [-79.1, 35.8])
    uploaded = client.post(f"/api/surveyor/objects/{obj['id']}/attachments", files={
        "file": ("recording.webm", b"field audio bytes", "audio/webm;codecs=opus"),
    })
    assert uploaded.status_code == 201, uploaded.text
    attachment = uploaded.json()
    assert attachment["attachment_type"] == "audio"
    deleted = client.delete(f"/api/surveyor/attachments/{attachment['id']}")
    assert deleted.status_code == 204


def test_image_upload_preserves_original_and_serves_separate_derivative(client: TestClient, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(main, "media_dir", tmp_path)
    obj = create_pin(client, [-79.1, 35.8])
    original = BytesIO()
    Image.new("RGB", (64, 48), (240, 120, 20)).save(original, format="PNG")
    original_bytes = original.getvalue()

    uploaded = client.post(f"/api/surveyor/objects/{obj['id']}/attachments", files={
        "file": ("../field photo.png", original_bytes, "image/png"),
    }, data={"caption": "Orange cat near creek"})
    assert uploaded.status_code == 201, uploaded.text
    attachment = uploaded.json()
    assert attachment["original_filename"] == "field_photo.png"
    assert attachment["mime_type"] == "image/png"
    assert attachment["width"] == 64
    assert attachment["height"] == 48
    assert attachment["aspect_ratio"] == pytest.approx(4 / 3, abs=1e-5)
    assert attachment["file_size_bytes"] == len(original_bytes)

    download = client.get(f"/api/surveyor/attachments/{attachment['id']}/download")
    preview = client.get(f"/api/surveyor/attachments/{attachment['id']}/preview")
    assert download.status_code == 200
    assert download.content == original_bytes
    assert preview.status_code == 200
    assert preview.headers["content-type"].startswith("image/jpeg")
    assert preview.content != original_bytes
    assert client.delete(f"/api/surveyor/attachments/{attachment['id']}").status_code == 204
    assert not list((tmp_path / "surveyor" / "original").glob("*"))
    assert not list((tmp_path / "surveyor" / "derived").glob("*"))


def test_media_export_contains_original_and_context_manifests(client: TestClient, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(main, "media_dir", tmp_path)
    obj = create_pin(client, [-79.1, 35.8], "East Creek")
    original = b"original audio bytes"
    uploaded = client.post(f"/api/surveyor/objects/{obj['id']}/attachments", files={
        "file": ("creek-call.webm", original, "audio/webm"),
    }, data={"caption": "Two calls at the creek"})
    assert uploaded.status_code == 201, uploaded.text
    attachment = uploaded.json()
    library = client.get("/api/surveyor/media?limit=20")
    assert library.status_code == 200
    assert library.json()[0]["map_object_name"] == "East Creek"
    assert client.get("/api/surveyor/media/config").json()["max_video_mb"] == main.settings.surveyor_max_video_mb

    exported = client.post("/api/surveyor/media/export", json={"attachment_ids": [attachment["id"]]})
    assert exported.status_code == 200, exported.text
    with ZipFile(BytesIO(exported.content)) as archive:
        names = archive.namelist()
        root = next(name.split("/", 1)[0] for name in names)
        assert f"{root}/README.txt" in names
        manifest = __import__("json").loads(archive.read(f"{root}/manifest.json"))
        item = manifest["items"][0]
        assert item["caption"] == "Two calls at the creek"
        assert item["map_object"]["name"] == "East Creek"
        media_name = f"{root}/media/{item['export_filename']}"
        assert archive.read(media_name) == original
        assert f"{root}/manifest.csv" in names
        assert f"{root}/context/map_objects.json" in names


def test_video_upload_keeps_supplied_media_metadata(client: TestClient, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(main, "media_dir", tmp_path)
    obj = create_pin(client, [-79.1, 35.8])
    uploaded = client.post(f"/api/surveyor/objects/{obj['id']}/attachments", files={
        "file": ("short-clip.mp4", b"small test video bytes", "video/mp4"),
    }, data={"duration_seconds": "12.5", "width": "1920", "height": "1080"})
    assert uploaded.status_code == 201, uploaded.text
    item = uploaded.json()
    assert item["attachment_type"] == "video"
    assert item["duration_seconds"] == pytest.approx(12.5)
    assert item["width"] == 1920
    assert item["height"] == 1080


def test_attachment_paths_cannot_escape_media_root(tmp_path: Path) -> None:
    with pytest.raises(HTTPException) as error:
        contained_path(tmp_path, "../outside.txt")
    assert error.value.status_code == 400


def test_public_media_mount_hides_surveyor_files(tmp_path: Path) -> None:
    from starlette.exceptions import HTTPException as StarletteHTTPException

    static = PublicMediaFiles(directory=str(tmp_path))
    with pytest.raises(StarletteHTTPException) as error:
        asyncio.run(static.get_response("surveyor/original/private.jpg", {"type": "http"}))
    assert error.value.status_code == 404


def test_delete_attachment_rejects_malicious_derivative_before_deleting_original(tmp_path: Path) -> None:
    from types import SimpleNamespace
    import json

    original = tmp_path / "surveyor" / "original" / "safe.jpg"
    original.parent.mkdir(parents=True)
    original.write_bytes(b"original")
    outside = tmp_path.parent / "outside.jpg"
    outside.write_bytes(b"outside")
    row = SimpleNamespace(storage_path="surveyor/original/safe.jpg",
        metadata_json=json.dumps({"derivatives": {"preview": "../../../../outside.jpg"}}))
    with pytest.raises(HTTPException):
        delete_attachment_files(row, tmp_path)
    assert original.read_bytes() == b"original"
    assert outside.read_bytes() == b"outside"


def test_session_route_coverage_buffers_in_meters(client: TestClient) -> None:
    started = client.post("/api/surveyor/sessions", json={"method": "walking"})
    assert started.status_code == 201, started.text
    session = started.json()
    ended = client.patch(f"/api/surveyor/sessions/{session['id']}", json={
        "track_geojson": {"type": "LineString", "coordinates": [[-79.1, 35.8], [-79.099, 35.8]]},
        "distance_meters": 90,
    })
    assert ended.status_code == 200, ended.text
    coverage = client.post(f"/api/surveyor/sessions/{session['id']}/coverage", json={"buffer_meters": 15})
    assert coverage.status_code == 201, coverage.text
    result = coverage.json()
    assert result["geometry"]["type"] == "Polygon"
    assert result["properties"]["search_session_id"] == session["id"]
    assert result["properties"]["buffer_meters"] == 15
    assert result["bbox"][2] - result["bbox"][0] < 0.01
    assert result["bbox"][3] - result["bbox"][1] < 0.01
    summary = client.get(f"/api/surveyor/sessions/{session['id']}/summary")
    assert summary.status_code == 200, summary.text
    assert summary.json()["objects_by_type"]["zone"] == 1
    assert summary.json()["coverage_objects"] == [result["id"]]


def test_evidence_resolution_is_durable_and_journaled(client: TestClient) -> None:
    created = client.post("/api/surveyor/objects", json={
        "object_type": "evidence", "subtype": "reported_observation", "name": "Possible sighting",
        "geometry": {"type": "Point", "coordinates": [-79.1, 35.8]},
        "properties": {"evidence_type": "visual_sighting", "resolution": "unresolved"},
    })
    assert created.status_code == 201, created.text
    object_id = created.json()["id"]
    updated = client.patch(f"/api/surveyor/objects/{object_id}", json={
        "properties": {"evidence_type": "visual_sighting", "resolution": "likely_not_archie"},
    })
    assert updated.status_code == 200, updated.text
    assert updated.json()["properties"]["resolution"] == "likely_not_archie"
    assert client.get("/api/surveyor/events?event_type=evidence_resolved").json()
