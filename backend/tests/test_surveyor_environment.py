import asyncio
import httpx

from app.surveyor import environment


BOUNDS = {"west": -79.3, "south": 35.7, "east": -79.0, "north": 36.0}


def test_rejects_invalid_bbox(client):
    response = client.get("/api/surveyor/environment/hydrography", params={**BOUNDS, "west": 181})
    assert response.status_code == 400


def test_rejects_bbox_over_two_degrees(client):
    response = client.get("/api/surveyor/environment/hydrography", params={**BOUNDS, "east": -76.9})
    assert response.status_code == 400


def test_hydrography_normalizes_provider_features(monkeypatch, client):
    async def fake_get_json(url, params):
        assert params["where"] == "1=1"
        layer = int(url.rsplit('/', 2)[-2])
        assert params["outFields"] == ("STREAM_NAM,WATERBODY" if layer == 2 else "STREAM_NAM")
        return {"features": [{"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[-79, 35], [-79.1, 35.1]]}, "properties": {"STREAM_NAM": "Morgan Creek", "OTHER": 1}}]}

    monkeypatch.setattr(environment, "_get_json", fake_get_json)
    environment._cache.clear()
    response = client.get("/api/surveyor/environment/hydrography", params=BOUNDS)
    assert response.status_code == 200
    result = response.json()
    assert result["provider"] == "NC OneMap"
    assert result["streams"]["features"][0]["properties"] == {"provider": "NC OneMap", "feature_type": "stream", "name": "Morgan Creek"}
    assert result["waterbodies"]["features"][0]["properties"]["feature_type"] == "waterbody"


def test_hydrography_cache_hit(monkeypatch, client):
    calls = []

    async def fake_get_json(_url, _params):
        calls.append(1)
        return {"features": []}

    monkeypatch.setattr(environment, "_get_json", fake_get_json)
    environment._cache.clear()
    client.get("/api/surveyor/environment/hydrography", params=BOUNDS)
    client.get("/api/surveyor/environment/hydrography", params=BOUNDS)
    assert len(calls) == 2


def test_wildlife_keeps_observed_and_added_dates(monkeypatch, client):
    async def fake_get_json(_url, _params):
        return {"results": [{"id": 17, "location": "35.8,-79.1", "geoprivacy": "open", "time_observed_at": "2026-09-18T18:22:00Z", "observed_on": "2026-09-18", "created_at": "2026-09-20T12:00:00Z", "quality_grade": "research", "positional_accuracy": 25, "taxon": {"preferred_common_name": "Coyote"}}]}

    monkeypatch.setattr(environment, "_get_json", fake_get_json)
    environment._cache.clear()
    response = client.get("/api/surveyor/environment/wildlife", params={**BOUNDS, "from_date": "2026-09-01", "to_date": "2026-09-30", "species": "coyote"})
    props = response.json()["features"][0]["properties"]
    assert props["observed_at"] == "2026-09-18T18:22:00Z"
    assert props["added_at"].startswith("2026-09-20")
    assert props["species_key"] == "coyote"


def test_wildlife_preserves_obscured_geoprivacy(monkeypatch, client):
    async def fake_get_json(_url, _params):
        return {"results": [{"id": 18, "location": "35.8,-79.1", "geoprivacy": "obscured", "taxon": {}}]}

    monkeypatch.setattr(environment, "_get_json", fake_get_json)
    environment._cache.clear()
    response = client.get("/api/surveyor/environment/wildlife", params={**BOUNDS, "from_date": "2026-09-01", "to_date": "2026-09-30", "species": "coyote"})
    feature = response.json()["features"][0]
    assert feature["properties"]["geoprivacy"] == "obscured"
    assert feature["geometry"]["coordinates"] == [-79.1, 35.8]


def test_wildlife_cache_key_includes_species_and_dates(monkeypatch, client):
    calls = []

    async def fake_get_json(_url, params):
        calls.append((params["taxon_name"], params["d1"], params["d2"]))
        return {"results": []}

    monkeypatch.setattr(environment, "_get_json", fake_get_json)
    environment._cache.clear()
    base = {**BOUNDS, "from_date": "2026-09-01", "to_date": "2026-09-30"}
    client.get("/api/surveyor/environment/wildlife", params={**base, "species": "coyote"})
    client.get("/api/surveyor/environment/wildlife", params={**base, "species": "coyote"})
    client.get("/api/surveyor/environment/wildlife", params={**base, "species": "red_fox"})
    client.get("/api/surveyor/environment/wildlife", params={**base, "to_date": "2026-09-29", "species": "coyote"})
    assert len(calls) == 3


def test_provider_timeout_returns_bounded_502(monkeypatch, client):
    calls = []

    class FailingClient:
        def __init__(self, **_kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *_args): return False
        async def get(self, *_args, **_kwargs):
            calls.append(1)
            raise httpx.ReadTimeout("provider timed out")

    monkeypatch.setattr(environment.httpx, "AsyncClient", FailingClient)
    environment._cache.clear()
    response = client.get("/api/surveyor/environment/hydrography", params=BOUNDS)
    assert response.status_code == 502
    assert len(calls) == 4


def test_expanded_bucket_covers_nearby_viewports(monkeypatch, client):
    seen = []
    async def fake_get_json(_url, params):
        seen.append(tuple(map(float, params["geometry"].split(","))))
        return {"features": []}
    monkeypatch.setattr(environment, "_get_json", fake_get_json)
    environment._cache.clear()
    first = {"west": -79.311, "south": 35.711, "east": -79.101, "north": 35.911}
    second = {"west": -79.312, "south": 35.712, "east": -79.102, "north": 35.912}
    client.get("/api/surveyor/environment/hydrography", params=first)
    client.get("/api/surveyor/environment/hydrography", params=second)
    assert len(seen) == 2
    west, south, east, north = seen[0]
    assert west <= first["west"] and west <= second["west"]
    assert south <= first["south"] and south <= second["south"]
    assert east >= first["east"] and east >= second["east"]
    assert north >= first["north"] and north >= second["north"]


def test_hydrography_prefers_waterbody_name(monkeypatch):
    calls = []
    async def fake_get_json(_url, params):
        calls.append(params["resultOffset"])
        return {"features": [{"type": "Feature", "geometry": {"type": "Polygon", "coordinates": []}, "properties": {"STREAM_NAM": "Creek", "WATERBODY": "Lake Name"}}]}
    monkeypatch.setattr(environment, "_get_json", fake_get_json)
    collection, truncated = asyncio.run(environment._hydro_layer(2, (-80, 35, -79, 36), "waterbody"))
    assert collection["features"][0]["properties"]["name"] == "Lake Name"
    assert calls == [0] and not truncated


def test_hydrography_paginates_and_marks_cap(monkeypatch):
    async def paged(_url, params):
        if params["resultOffset"] == 0:
            return {"features": [{"properties": {}}] * 2000, "exceededTransferLimit": True}
        return {"features": [{"properties": {}}]}
    monkeypatch.setattr(environment, "_get_json", paged)
    collection, truncated = asyncio.run(environment._hydro_layer(1, (-80, 35, -79, 36), "stream"))
    assert len(collection["features"]) == 2001 and not truncated

    async def capped(_url, _params): return {"features": [{"properties": {}}] * 2000, "exceededTransferLimit": True}
    monkeypatch.setattr(environment, "_get_json", capped)
    collection, truncated = asyncio.run(environment._hydro_layer(1, (-80, 35, -79, 36), "stream"))
    assert len(collection["features"]) == 6000 and truncated


def test_hydrography_partial_and_total_failure(monkeypatch, client):
    async def partial(layer, _bounds, kind):
        if layer == 1: raise RuntimeError("streams down")
        return ({"type": "FeatureCollection", "features": [{"properties": {"feature_type": kind}}]}, False)
    monkeypatch.setattr(environment, "_hydro_layer", partial)
    environment._cache.clear()
    response = client.get("/api/surveyor/environment/hydrography", params=BOUNDS)
    assert response.status_code == 200
    assert response.json()["degraded_layers"] == ["streams"]
    assert response.json()["waterbodies"]["features"]

    async def failed(*_args): raise RuntimeError("provider down")
    monkeypatch.setattr(environment, "_hydro_layer", failed)
    environment._cache.clear()
    assert client.get("/api/surveyor/environment/hydrography", params=BOUNDS).status_code == 502


def test_wildlife_paginates_and_marks_truncation(monkeypatch, client):
    calls = []
    async def fake_get_json(_url, params):
        calls.append(params["page"])
        if params["page"] == 1:
            return {"total_results": 401, "results": [{"id": i, "location": "35.8,-79.1", "geoprivacy": "open", "observed_on": "2026-09-18", "taxon": {}} for i in range(200)]}
        return {"total_results": 401, "results": [{"id": 500, "location": "35.8,-79.1", "geoprivacy": "open", "observed_on": "2026-09-18", "taxon": {}} for _ in range(200)]}
    monkeypatch.setattr(environment, "_get_json", fake_get_json)
    environment._cache.clear()
    response = client.get("/api/surveyor/environment/wildlife", params={**BOUNDS, "from_date": "2026-09-01", "to_date": "2026-09-30", "species": "coyote"})
    assert calls == [1, 2]
    assert response.json()["truncated"] is True
    assert len(response.json()["features"]) == 400
