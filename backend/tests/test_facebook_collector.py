from fastapi.testclient import TestClient


def subscribe(client: TestClient, name: str, slug: str) -> dict:
    response = client.post("/api/facebook/groups", json={
        "group_url": f"https://www.facebook.com/groups/{slug}", "group_name": name,
    })
    assert response.status_code == 201, response.text
    return response.json()


def test_facebook_group_validation_and_soft_disable(client: TestClient):
    bad = client.post("/api/facebook/groups", json={"group_url": "https://facebook.com/profile.php?id=5"})
    assert bad.status_code == 422
    group = subscribe(client, "Chatham Lost Pets", "chatham-lost-pets")
    removed = client.delete(f"/api/facebook/groups/{group['id']}")
    assert removed.status_code == 200
    assert client.get("/api/facebook/groups").json()[0]["enabled"] is False


def test_facebook_batch_filters_noise_and_combines_strong_crossposts(client: TestClient):
    group_a = subscribe(client, "Chatham Lost Pets", "chatham-lost-pets")
    group_b = subscribe(client, "Chapel Hill Lost Pets", "chapel-hill-lost-pets")
    pair = client.post("/api/facebook/pair").json()
    headers = {"X-Archie-Facebook-Token": pair["token"]}
    run = client.post("/api/facebook/sync")
    assert run.status_code == 200, run.text
    job = client.get("/api/facebook/sync/next", headers=headers).json()["job"]
    assert {group["id"] for group in job["groups"]} == {group_a["id"], group_b["id"]}

    sha = "a" * 64
    first = client.post("/api/facebook/ingest-batch", headers=headers, json={
        "sync_run_id": run.json()["id"], "group_subscription_id": group_a["id"], "scanned": 2,
        "posts": [
            {"facebook_post_id": "post-a", "canonical_url": "https://www.facebook.com/groups/chatham-lost-pets/posts/post-a",
             "text": "Found orange cat near the creek. Please message me with a photo.",
             "posted_at": "2026-09-27T12:00:00Z", "images": [{"url": "https://images.example/cat.jpg", "sha256": sha}]},
            {"facebook_post_id": "dog-post", "text": "Found a friendly dog near the park."},
        ]
    })
    assert first.status_code == 200, first.text
    assert first.json()["posts_new"] == 1
    assert first.json()["filtered"] == 1

    second = client.post("/api/facebook/ingest-batch", headers=headers, json={
        "sync_run_id": run.json()["id"], "group_subscription_id": group_b["id"], "scanned": 1,
        "posts": [{"facebook_post_id": "post-b", "canonical_url": "https://www.facebook.com/groups/chapel-hill-lost-pets/posts/post-b",
                   "text": "Posting here too! Found orange cat near the creek. Please message me with a photo.",
                   "posted_at": "2026-09-27T12:12:00Z", "images": [{"url": "https://images.example/cat-copy.jpg", "sha256": sha}]}],
    })
    assert second.status_code == 200, second.text
    assert second.json()["crossposts_combined"] == 1
    cases = client.get("/api/candidate-cases").json()
    assert len(cases) == 1
    assert cases[0]["record_count"] == 2
    assert {appearance["group_name"] for source in cases[0]["source_records"]
            for appearance in source["facebook_group_appearances"]} == {"Chatham Lost Pets", "Chapel Hill Lost Pets"}
    assert client.post(f"/api/facebook/sync/{run.json()['id']}/complete", headers=headers, json={}).status_code == 200


def test_facebook_bridge_endpoints_require_paired_token(client: TestClient):
    assert client.get("/api/facebook/sync/next").status_code == 401
    group = subscribe(client, "Triangle Lost Pets", "triangle-lost-pets")
    assert group["facebook_group_id"] is None
    pair = client.post("/api/facebook/pair").json()
    assert pair["token"]
    assert client.get("/api/facebook/bridge/status", headers={"X-Archie-Facebook-Token": pair["token"]}).json()["paired"]
