from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import SurveyorOutingPlan
from app.surveyor.outings import normalize_legacy_ready_statuses


def create_plan(client: TestClient) -> dict:
    response = client.post("/api/surveyor/outings", json={
        "title": "Creek check", "objective": "Check cameras and search the creek edge.", "method": "walking",
    })
    assert response.status_code == 201, response.text
    return response.json()


def add_item(client: TestClient, plan_id: int, section: str, title: str, **extra) -> dict:
    response = client.post(f"/api/surveyor/outings/{plan_id}/items", json={
        "section": section, "title": title, **extra,
    })
    assert response.status_code == 201, response.text
    return response.json()


def test_outing_preflight_dependencies_and_autosaved_readiness(client: TestClient) -> None:
    plan = create_plan(client)
    prep_plan = add_item(client, plan["id"], "prep", "Charge camera battery")
    prep = next(item for item in prep_plan["items"] if item["title"] == "Charge camera battery")
    game_plan = add_item(client, plan["id"], "gameplan", "Move creek camera",
        note="Aim toward the crossing.", depends_on_prep_ids=[prep["id"]])
    game = next(item for item in game_plan["items"] if item["title"] == "Move creek camera")
    assert game["depends_on_prep_ids"] == [prep["id"]]
    assert game_plan["readiness"]["setup_blockers"] == 1
    assert game_plan["readiness"]["ready"] is False

    completed = client.patch(f"/api/surveyor/outings/items/{prep['id']}", json={"status": "completed"})
    assert completed.status_code == 200, completed.text
    current = client.get("/api/surveyor/outings/current").json()
    assert current["readiness"]["ready"] is True
    assert current["items"][1]["depends_on_prep_ids"] == [prep["id"]]


def test_outing_rejects_cross_plan_or_non_prep_dependency(client: TestClient) -> None:
    one, two = create_plan(client), create_plan(client)
    prep_plan = add_item(client, one["id"], "prep", "Charge batteries")
    prep = next(item for item in prep_plan["items"] if item["section"] == "prep")
    response = client.post(f"/api/surveyor/outings/{two['id']}/items", json={
        "section": "packing", "title": "Camera kit", "depends_on_prep_ids": [prep["id"]],
    })
    assert response.status_code == 422

    packing_plan = add_item(client, one["id"], "packing", "Camera kit")
    packing = next(item for item in packing_plan["items"] if item["section"] == "packing")
    response = client.put(f"/api/surveyor/outings/items/{packing['id']}/dependencies", json={
        "prep_item_ids": [packing["id"]],
    })
    assert response.status_code == 422


def test_reuse_last_outing_copies_structure_and_resets_item_state(client: TestClient) -> None:
    plan = create_plan(client)
    prep_plan = add_item(client, plan["id"], "prep", "Charge batteries")
    prep = next(item for item in prep_plan["items"] if item["section"] == "prep")
    game_plan = add_item(client, plan["id"], "gameplan", "Check camera", depends_on_prep_ids=[prep["id"]])
    game = next(item for item in game_plan["items"] if item["section"] == "gameplan")
    client.patch(f"/api/surveyor/outings/items/{prep['id']}", json={"status": "completed"})
    client.patch(f"/api/surveyor/outings/items/{game['id']}", json={"status": "completed"})
    started = client.post(f"/api/surveyor/outings/{plan['id']}/start", json={"method": "walking"})
    assert started.status_code == 201, started.text
    client.patch(f"/api/surveyor/sessions/{started.json()['session']['id']}", json={"result_summary": "Ended"})

    response = client.post("/api/surveyor/outings/reuse-last")
    assert response.status_code == 201, response.text
    copied = response.json()
    copied_items = {item["title"]: item for item in copied["items"]}
    assert copied["id"] != plan["id"]
    assert copied["status"] == "draft"
    assert copied_items["Charge batteries"]["status"] == "pending"
    assert copied_items["Check camera"]["status"] == "pending"
    assert copied_items["Check camera"]["depends_on_prep_ids"] == [copied_items["Charge batteries"]["id"]]


def test_skipped_required_setup_is_a_visible_waiver_not_a_pending_blocker(client: TestClient) -> None:
    plan = create_plan(client)
    item_plan = add_item(client, plan["id"], "prep", "Format spare SD card")
    item = next(row for row in item_plan["items"] if row["section"] == "prep")

    response = client.patch(f"/api/surveyor/outings/items/{item['id']}", json={"status": "skipped"})
    assert response.status_code == 200, response.text
    current = client.get("/api/surveyor/outings/current").json()
    assert current["readiness"]["prep_remaining"] == 0
    assert current["readiness"]["skipped_required"] == 1
    assert current["readiness"]["ready_to_leave"] is True
    assert current["items"][0]["status"] == "skipped"

    restored = client.patch(f"/api/surveyor/outings/items/{item['id']}", json={"status": "pending"})
    assert restored.status_code == 200
    assert client.get("/api/surveyor/outings/current").json()["items"][0]["status"] == "pending"


def test_outing_can_link_to_search_session(client: TestClient) -> None:
    plan = create_plan(client)
    linked = client.post(f"/api/surveyor/outings/{plan['id']}/start", json={"method": "walking"})
    assert linked.status_code == 201, linked.text
    assert linked.json()["plan"]["status"] == "active"
    assert linked.json()["plan"]["search_session_id"] == linked.json()["session"]["id"]


def test_start_rejects_blockers_without_creating_session_and_override_is_atomic(client: TestClient) -> None:
    plan = create_plan(client)
    add_item(client, plan["id"], "prep", "Charge batteries")
    rejected = client.post(f"/api/surveyor/outings/{plan['id']}/start", json={"method": "walking"})
    assert rejected.status_code == 409
    assert len(client.get("/api/surveyor/sessions").json()) == 0

    started = client.post(f"/api/surveyor/outings/{plan['id']}/start", json={"method": "walking", "start_with_blockers": True})
    assert started.status_code == 201, started.text
    body = started.json()
    assert body["plan"]["status"] == "active"
    assert body["plan"]["search_session_id"] == body["session"]["id"]
    assert len(client.get("/api/surveyor/sessions").json()) == 1
    assert any(event["event_type"] == "outing_started_with_blockers" for event in client.get("/api/surveyor/events").json())


def test_pending_gameplan_and_optional_pending_items_do_not_block(client: TestClient) -> None:
    plan = create_plan(client)
    add_item(client, plan["id"], "gameplan", "Check creek crossing")
    add_item(client, plan["id"], "packing", "Optional camera", required=False)
    started = client.post(f"/api/surveyor/outings/{plan['id']}/start", json={"method": "walking"})
    assert started.status_code == 201, started.text
    assert started.json()["plan"]["readiness"]["ready_to_leave"] is True


def test_required_packing_and_shared_setup_waivers_are_counted_correctly(client: TestClient) -> None:
    plan = create_plan(client)
    setup = add_item(client, plan["id"], "prep", "Charge battery")
    prep = next(item for item in setup["items"] if item["section"] == "prep")
    first = add_item(client, plan["id"], "packing", "Camera bag", depends_on_prep_ids=[prep["id"]])
    second = add_item(client, plan["id"], "gameplan", "Creek camera", depends_on_prep_ids=[prep["id"]])
    packing = next(item for item in first["items"] if item["section"] == "packing")
    readiness = second["readiness"]
    assert readiness["prep_remaining"] == 1
    assert readiness["packing_remaining"] == 1
    assert readiness["dependency_blockers"] == 1
    client.patch(f"/api/surveyor/outings/items/{packing['id']}", json={"status": "completed"})
    waived = client.patch(f"/api/surveyor/outings/items/{prep['id']}", json={"status": "skipped"}).json()
    assert waived["readiness"]["ready_to_leave"] is True
    assert waived["readiness"]["skipped_required"] == 1
    assert waived["readiness"]["waived_dependency_count"] == 2


def test_add_and_link_validation_failure_does_not_create_orphan_prep(client: TestClient) -> None:
    plan = create_plan(client)
    item_plan = add_item(client, plan["id"], "prep", "Existing prep")
    prep = item_plan["items"][0]
    before = len(item_plan["items"])
    rejected = client.post(f"/api/surveyor/outings/items/{prep['id']}/create-prep-dependency", json={"title": "Bad orphan"})
    assert rejected.status_code == 422
    assert len(client.get("/api/surveyor/outings/current").json()["items"]) == before


def test_current_prefers_active_session_plan_over_newer_draft(client: TestClient) -> None:
    active = create_plan(client)
    started = client.post(f"/api/surveyor/outings/{active['id']}/start", json={"method": "walking"})
    assert started.status_code == 201
    newer_draft = create_plan(client)
    current = client.get("/api/surveyor/outings/current").json()
    assert current["id"] == active["id"]
    assert current["id"] != newer_draft["id"]


def test_plan_lifecycle_cannot_be_changed_through_metadata_patch(client: TestClient) -> None:
    plan = create_plan(client)
    response = client.patch(f"/api/surveyor/outings/{plan['id']}", json={"status": "active", "search_session_id": 100})
    assert response.status_code == 422
    assert client.get("/api/surveyor/outings/current").json()["status"] == "draft"


def test_linked_session_completion_preserves_unfinished_gameplan_and_clears_current(client: TestClient) -> None:
    plan = create_plan(client)
    game = add_item(client, plan["id"], "gameplan", "Second stop")
    started = client.post(f"/api/surveyor/outings/{plan['id']}/start", json={"method": "walking"}).json()
    session_id = started["session"]["id"]
    finished = client.patch(f"/api/surveyor/sessions/{session_id}", json={"result_summary": "Stopped after first stop"})
    assert finished.status_code == 200, finished.text
    old = client.get(f"/api/surveyor/outings/by-session/{session_id}").json()
    assert old["status"] == "completed"
    assert next(item for item in old["items"] if item["id"] == game["items"][-1]["id"])["status"] == "pending"
    assert client.get("/api/surveyor/outings/current").json() is None


def test_continue_unfinished_copies_only_pending_stops_and_needed_prep(client: TestClient) -> None:
    plan = create_plan(client)
    prep_a = add_item(client, plan["id"], "prep", "Charge camera")
    prep_b = add_item(client, plan["id"], "prep", "Unrelated scent prep")
    prep_a_item = next(row for row in prep_a["items"] if row["section"] == "prep")
    prep_b_item = next(row for row in prep_b["items"] if row["title"] == "Unrelated scent prep")
    client.patch(f"/api/surveyor/outings/items/{prep_b_item['id']}", json={"required": False})
    first = add_item(client, plan["id"], "gameplan", "Creek camera", depends_on_prep_ids=[prep_a_item["id"]])
    first_item = next(row for row in first["items"] if row["section"] == "gameplan")
    second = add_item(client, plan["id"], "gameplan", "Road edge", depends_on_prep_ids=[prep_a_item["id"]])
    second_item = next(row for row in second["items"] if row["title"] == "Road edge")
    packing = add_item(client, plan["id"], "packing", "Flashlight")
    packing_item = next(row for row in packing["items"] if row["section"] == "packing")
    client.patch(f"/api/surveyor/outings/items/{first_item['id']}", json={"status": "completed"})
    client.patch(f"/api/surveyor/outings/items/{prep_a_item['id']}", json={"status": "completed"})
    client.patch(f"/api/surveyor/outings/items/{packing_item['id']}", json={"status": "completed"})
    started = client.post(f"/api/surveyor/outings/{plan['id']}/start", json={"method": "walking"})
    assert started.status_code == 201, started.text
    client.patch(f"/api/surveyor/sessions/{started.json()['session']['id']}", json={"result_summary": "Ended"})

    continued = client.post(f"/api/surveyor/outings/{plan['id']}/continue-unfinished")
    assert continued.status_code == 201, continued.text
    titles = {item["title"] for item in continued.json()["items"]}
    assert titles == {"Charge camera", "Road edge"}
    copied_game = next(item for item in continued.json()["items"] if item["title"] == "Road edge")
    copied_prep = next(item for item in continued.json()["items"] if item["title"] == "Charge camera")
    assert copied_game["depends_on_prep_ids"] == [copied_prep["id"]]
    assert all(item["status"] == "pending" for item in continued.json()["items"])


def test_reuse_last_uses_completed_plan_and_missing_references_are_cleared(client: TestClient) -> None:
    completed = create_plan(client)
    old_item = add_item(client, completed["id"], "gameplan", "Visit creek")
    item = old_item["items"][0]
    started = client.post(f"/api/surveyor/outings/{completed['id']}/start", json={"method": "walking"}).json()
    client.patch(f"/api/surveyor/sessions/{started['session']['id']}", json={"result_summary": "Ended"})
    draft = create_plan(client)
    reused = client.post("/api/surveyor/outings/reuse-last")
    assert reused.status_code == 201
    assert reused.json()["title"] == completed["title"]
    assert reused.json()["id"] != draft["id"]


def test_task_completion_is_limited_to_completed_gameplan_item(client: TestClient) -> None:
    task_response = client.post("/api/surveyor/tasks", json={"title": "Check camera follow-up", "task_type": "camera"})
    assert task_response.status_code == 201, task_response.text
    task = task_response.json()
    plan = create_plan(client)
    packing = add_item(client, plan["id"], "packing", "Camera kit", surveyor_task_id=task["id"])
    packing_item = next(item for item in packing["items"] if item["section"] == "packing")
    client.patch(f"/api/surveyor/outings/items/{packing_item['id']}", json={"status": "completed"})
    assert client.get("/api/surveyor/tasks").json()[0]["status"] == "open"
    gameplan = add_item(client, plan["id"], "gameplan", "Check camera", surveyor_task_id=task["id"])
    game_item = next(item for item in gameplan["items"] if item["section"] == "gameplan")
    done = client.patch(f"/api/surveyor/outings/items/{game_item['id']}", json={"status": "completed"})
    assert done.status_code == 200
    assert client.get("/api/surveyor/tasks").json()[0]["status"] == "completed"


def test_add_and_link_and_reorder_return_full_plan(client: TestClient) -> None:
    plan = create_plan(client)
    item_plan = add_item(client, plan["id"], "gameplan", "Check crossing")
    item = item_plan["items"][0]
    linked = client.post(f"/api/surveyor/outings/items/{item['id']}/create-prep-dependency", json={"title": "Charge pack"})
    assert linked.status_code == 201
    assert linked.json()["readiness"]["prep_remaining"] == 1
    prep = next(row for row in linked.json()["items"] if row["section"] == "prep")
    assert next(row for row in linked.json()["items"] if row["section"] == "gameplan")["depends_on_prep_ids"] == [prep["id"]]
    reordered = client.post(f"/api/surveyor/outings/{plan['id']}/reorder", json={"section": "gameplan", "ordered_item_ids": [item["id"]]})
    assert reordered.status_code == 200 and "readiness" in reordered.json()


def test_legacy_ready_status_normalization_is_idempotent() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        row = SurveyorOutingPlan(title="Legacy", status="ready")
        db.add(row); db.commit()
        assert normalize_legacy_ready_statuses(db) == 1
        assert row.status == "draft"
        assert normalize_legacy_ready_statuses(db) == 0
    engine.dispose()
