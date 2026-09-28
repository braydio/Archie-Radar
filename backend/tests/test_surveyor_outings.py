from fastapi.testclient import TestClient


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

    response = client.post("/api/surveyor/outings/reuse-last")
    assert response.status_code == 201, response.text
    copied = response.json()
    copied_items = {item["title"]: item for item in copied["items"]}
    assert copied["id"] != plan["id"]
    assert copied["status"] == "draft"
    assert copied_items["Charge batteries"]["status"] == "pending"
    assert copied_items["Check camera"]["status"] == "pending"
    assert copied_items["Check camera"]["depends_on_prep_ids"] == [copied_items["Charge batteries"]["id"]]


def test_skipped_required_setup_remains_visible_as_a_blocker(client: TestClient) -> None:
    plan = create_plan(client)
    item_plan = add_item(client, plan["id"], "prep", "Format spare SD card")
    item = next(row for row in item_plan["items"] if row["section"] == "prep")

    response = client.patch(f"/api/surveyor/outings/items/{item['id']}", json={"status": "skipped"})
    assert response.status_code == 200, response.text
    current = client.get("/api/surveyor/outings/current").json()
    assert current["readiness"]["setup_blockers"] == 1
    assert current["readiness"]["ready"] is False

    restored = client.patch(f"/api/surveyor/outings/items/{item['id']}", json={"status": "pending"})
    assert restored.status_code == 200
    assert client.get("/api/surveyor/outings/current").json()["items"][0]["status"] == "pending"


def test_outing_can_link_to_search_session(client: TestClient) -> None:
    plan = create_plan(client)
    session = client.post("/api/surveyor/sessions", json={"method": "walking"})
    assert session.status_code == 201, session.text
    linked = client.patch(f"/api/surveyor/outings/{plan['id']}", json={
        "status": "active", "search_session_id": session.json()["id"],
    })
    assert linked.status_code == 200, linked.text
    assert linked.json()["status"] == "active"
    assert linked.json()["search_session_id"] == session.json()["id"]
