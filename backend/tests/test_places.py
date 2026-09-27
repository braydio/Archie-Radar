from unittest.mock import AsyncMock

from app import places


def test_address_resolver_returns_distance_bearing_and_precision(client, monkeypatch):
    monkeypatch.setattr(places.geocoder, "lookup_many", AsyncMock(return_value=[
        {"latitude": 35.9, "longitude": -79.0, "display_name": "Chapel Hill address", "addresstype": "house"},
        {"latitude": 36.1, "longitude": -79.2, "display_name": "Durham", "addresstype": "city"},
    ]))
    response = client.post("/api/places/resolve", json={"query": "64 Dollar Road, Chapel Hill"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["matches"]) == 2
    assert body["matches"][0]["precision"] == "address"
    assert body["matches"][0]["distance_miles"] > 0
    assert body["matches"][0]["bearing_label"] in {"NE", "ENE"}
    places.geocoder.lookup_many.assert_awaited_once()


def test_address_resolver_returns_cached_place_without_provider_call(client, monkeypatch):
    monkeypatch.setattr(places.geocoder, "lookup_many", AsyncMock(return_value=[]))
    client.post("/api/places/resolve", json={"query": "not a real address, Chapel Hill, NC"})
    response = client.post("/api/places/resolve", json={"query": "not a real address, Chapel Hill, NC"})
    assert response.status_code == 200
    assert response.json()["matches"] == []
    places.geocoder.lookup_many.assert_awaited_once()


def test_cached_address_lookup_preserves_precision_and_ambiguous_choices(client, monkeypatch):
    results = [
        {"latitude": 35.9, "longitude": -79.0, "display_name": "Dollar Road, Chapel Hill", "addresstype": "road", "type": "residential"},
        {"latitude": 36.0, "longitude": -79.1, "display_name": "Dollar Road, Durham", "addresstype": "road", "type": "residential"},
    ]
    monkeypatch.setattr(places.geocoder, "lookup_many", AsyncMock(return_value=results))

    first = client.post("/api/places/resolve", json={"query": "Dollar Road, Chapel Hill"})
    second = client.post("/api/places/resolve", json={"query": "Dollar Road, Chapel Hill"})

    assert first.status_code == second.status_code == 200
    assert [item["precision"] for item in first.json()["matches"]] == ["street", "street"]
    assert second.json()["matches"] == first.json()["matches"]
    assert len(second.json()["matches"]) == 2
    places.geocoder.lookup_many.assert_awaited_once()
