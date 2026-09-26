from fastapi.testclient import TestClient


def create_report(client: TestClient, source_id: str, name: str = "Found cat") -> dict:
    response = client.post("/api/bridge/facebook", json={
        "source_id": source_id,
        "source_url": f"https://example.test/{source_id}",
        "status": "found",
        "species": "cat",
        "name": name,
        "description": "Orange tabby cat",
        "location_text": "Chapel Hill",
        "latitude": 35.9,
        "longitude": -79.0,
    })
    assert response.status_code in (200, 201), response.text
    return response.json()


def test_candidate_case_list_returns_identity_group_and_review_is_authoritative(client: TestClient):
    post = create_report(client, "case-review-1", "Milo")
    cases = client.get("/api/candidate-cases").json()
    assert len(cases) == 1
    case_id = cases[0]["case_id"]
    assert cases[0]["record_count"] == 1
    post_id = post["post_ids"][0]
    assert cases[0]["primary_post_id"] == post_id

    reviewed = client.patch(f"/api/candidate-cases/{case_id}/review", json={"review_state": "possible"})
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["review_state"] == "possible"
    assert client.get("/api/posts", params={"review_state": "possible"}).json()[0]["id"] == post_id


def test_case_review_legacy_post_route_updates_case(client: TestClient):
    post = create_report(client, "case-review-legacy")
    case_id = client.get("/api/candidate-cases").json()[0]["case_id"]
    reviewed = client.post(f"/api/posts/{post['post_ids'][0]}/review", json={"review_state": "needs_review"})
    assert reviewed.status_code == 200
    cases = client.get("/api/candidate-cases", params={"review_state": "needs_review"}).json()
    assert [item["case_id"] for item in cases] == [case_id]
