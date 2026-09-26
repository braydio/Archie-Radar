from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_db():
        db = sessions()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    try:
        # Avoid the production lifespan hook: the override owns this isolated DB.
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


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
