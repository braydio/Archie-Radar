# NEXT SLICE TASK PACKET — MIN TOKEN

## Slice 8 · Surveyor Geographic Context
**Target:** latest `main`  
**Anchors verified:** `main@c2333b9f48f4735a0ea69e2ed90e3973b55aa5dd`  
**P0:** Surveyor must show useful geography on first load. Then add bounded hydro/wetland/wildlife overlays.

## 0. TOKEN RULES
Read only `AGENTS.md`, this file, and files listed below. No repo-wide rediscovery unless an anchor is missing.
Do not research providers; exact URLs are below.
Do not add dependencies, DB tables, migrations, generic provider frameworks, or new settings.
Do not run `npm install`. Run focused tests once near the end.
Do not rebuild cameras/zones/links/search sessions/journal/access/outing systems; they already exist.
If an upstream provider fails, show degraded/unavailable state and continue.

## 1. EXACT FILE SET

### Modify
| file | current anchor |
|---|---|
| `frontend/src/views/SurveyorView.vue` | imports 1–38; defaults 42–46; visibility 136+; map init/load 1244–1278; map shell 1450–1451 |
| `frontend/src/surveyor/catMapStyle.js` | replace whole file, lines 1–37 |
| `frontend/src/surveyor/snapEngine.js` | lines 45–53 |
| `frontend/src/components/surveyor/LayerDrawer.vue` | replace whole file, lines 1–14 |
| `frontend/src/style.css` | Surveyor block begins ~516; map shell ~533 |
| `backend/app/main.py` | router block 348–357 |

### Add
```text
backend/app/surveyor/environment.py
backend/tests/test_surveyor_environment.py
frontend/src/surveyor/environmentLayers.js
frontend/src/components/surveyor/EnvironmentalInspector.vue
frontend/src/components/surveyor/MapLegend.vue
```

### Do not touch unless blocked
```text
backend/app/models.py
backend/app/db.py
backend/app/settings.py
backend/pyproject.toml
frontend/package.json
frontend/src/surveyor/objectTypes.js
frontend/src/components/surveyor/SurveyTimeline.vue
```

## 2. BASE MAP: FIX FIRST

### `frontend/src/surveyor/catMapStyle.js`
Reuse/adapt the better existing style logic from:
```text
frontend/src/components/SearchMap.vue:188-252
```
Do not invent another styling system.

Required result:
- quiet warm background;
- forest/woodland + grass visible;
- developed/building context visible but subdued;
- water fill/lines strong enough to read;
- motorway/trunk > primary > secondary > local road hierarchy;
- place/road/water labels readable;
- hide shops/restaurants/transit/POI/address-number clutter.

Export:
```js
export function applyCatMapStyle(map) {}
export function auditCatMapStyle(map) {}
export const CAT_MAP_PALETTE = {}
```

`auditCatMapStyle(map)`:
```js
{ roads, water, labels, natural, status: 'ready'|'degraded' }
```
Required for ready: roads + water + labels.

### `SurveyorView.vue`
After refs around line 48:
```js
const mapHealth = ref({ status:'loading', roads:false, water:false, labels:false, natural:false })
const environmentStatus = ref({})
const selectedEnvironment = ref(null)
let environmentController = null
```

Change import:
```js
import { applyCatMapStyle, auditCatMapStyle } from '../surveyor/catMapStyle.js'
import { createEnvironmentLayers } from '../surveyor/environmentLayers.js'
import EnvironmentalInspector from '../components/surveyor/EnvironmentalInspector.vue'
import MapLegend from '../components/surveyor/MapLegend.vue'
```

At current `map.on('load')` ~1255:
```js
applyCatMapStyle(map)
mapHealth.value = auditCatMapStyle(map)
```
Add compact map badge:
- loading: `Loading geography…`
- degraded: `Base geography degraded · Retry`
- failed: `Base geography unavailable · Retry`

Never hide local Surveyor objects because base/external geography fails.

## 3. DEFAULT LAYERS

Replace `SurveyorView.vue:45` with:
```js
const defaultLayers = {
  objects:true, links:true, cameras:true, cameraHistory:false, candidates:true,
  landcover:true, hydrography:true, boundaries:true, wetlands:false, wildlife:false,
  wildlifeSpecies:{ coyote:false, red_fox:false, gray_fox:false, bobcat:false, raccoon:false, deer:false }
}
```
Keep current `{ ...defaultLayers, ...saved }` merge.

At end of current `applyLayerVisibility()` ~136:
```js
environmentController?.applyVisibility(settings)
```

## 4. ONE FRONTEND ENVIRONMENT CONTROLLER

Add `frontend/src/surveyor/environmentLayers.js`.

Export only:
```js
export function createEnvironmentLayers({ map, api, getTimeline, onStatus, onSelect }) {
  return { install, applyVisibility, refreshViewport, retry, destroy }
}
```

### install(settings)
- add Annual NLCD raster;
- add NWI raster;
- add empty GeoJSON sources/layers for NC hydro + wildlife;
- add Census boundary layers by reusing SearchMap code below;
- register click handlers;
- register debounced `moveend`;
- apply visibility;
- refresh viewport.

### refreshViewport(settings)
- debounce 350 ms;
- one AbortController, abort stale request;
- hydro only if enabled and zoom >= 8;
- wildlife only if enabled, >=1 species checked, zoom >= 9;
- use current map bounds;
- no JS request for wetlands (raster);
- provider status via `onStatus`.

### destroy()
Abort requests and remove listeners.

## 5. REUSE CENSUS CODE, DO NOT REWRITE IT

Copy/adapt:
```text
frontend/src/components/SearchMap.vue:8-10       Census URLs/cache age
frontend/src/components/SearchMap.vue:157-173   cached fetch + 3.5s abort
frontend/src/components/SearchMap.vue:261-312   county/state layers
```

Surveyor ids:
```text
survey-county-lines
survey-county-labels
survey-state-lines
```

Failure must settle to `unavailable`, never infinite `loading`.

## 6. EXISTING NLCD: MOVE, DON'T REDESIGN

Current source:
```text
frontend/src/views/SurveyorView.vue:1275-1278
```
Move it to `environmentLayers.js`; delete inline copy from SurveyorView.

Keep current 2025 WMS URL.
Use opacity ~0.22.
Default visible.
Label: `Annual NLCD · 2025 · USGS/MRLC`.

## 7. NWI WETLANDS: RASTER ONLY

No backend endpoint.

MapServer export:
```text
https://fwspublicservices.wim.usgs.gov/wetlandsmapservice/rest/services/Wetlands/MapServer/export
```

MapLibre tile:
```text
https://fwspublicservices.wim.usgs.gov/wetlandsmapservice/rest/services/Wetlands/MapServer/export?bbox={bbox-epsg-3857}&bboxSR=3857&imageSR=3857&size=256,256&format=png32&transparent=true&layers=show:0&f=image
```

Source: raster, tileSize 256.  
Layer id: `survey-wetlands`.  
Opacity ~0.26, minzoom 10, default hidden.  
Attribution: `USFWS National Wetlands Inventory`.

No wetland identify popup required this slice.

## 8. BACKEND: ONE NEW ROUTER FILE

Add `backend/app/surveyor/environment.py`.
Use existing `httpx`. No new models/settings/deps.

```python
router = APIRouter(prefix="/api/surveyor/environment", tags=["surveyor-environment"])
```

Endpoints:
```text
GET /status
GET /hydrography?west=&south=&east=&north=
GET /wildlife?west=&south=&east=&north=&from_date=&to_date=&species=coyote&species=red_fox
```

Validation:
- legal lat/lon;
- west < east, south < north;
- reject bbox width or height > 2° with 400.

Cache: in-memory dict, no DB.
Key uses bbox rounded to 0.02° + provider filters.
TTL hydro 24h, wildlife 15m.
Max ~128 entries, evict oldest.
Upstream timeout 4s, max one retry.

### /status
No upstream calls:
```json
{"hydrography":{"provider":"NC OneMap","available":true},"wetlands":{"provider":"USFWS NWI","available":true},"boundaries":{"provider":"US Census TIGERweb","available":true},"wildlife":{"provider":"iNaturalist","available":true}}
```

## 9. NC ONEMAP HYDROGRAPHY

Streams:
```text
https://services.nconemap.gov/secure/rest/services/NC1Map_Hydrography/FeatureServer/1/query
```
Waterbodies:
```text
https://services.nconemap.gov/secure/rest/services/NC1Map_Hydrography/FeatureServer/2/query
```

Params:
```text
where=1=1
geometry=<west>,<south>,<east>,<north>
geometryType=esriGeometryEnvelope
inSR=4326
outSR=4326
spatialRel=esriSpatialRelIntersects
outFields=STREAM_NAM
returnGeometry=true
resultRecordCount=2000
f=geojson
```

Return:
```json
{"provider":"NC OneMap","streams":<FeatureCollection>,"waterbodies":<FeatureCollection>}
```
Normalize each feature properties:
```json
{"provider":"NC OneMap","feature_type":"stream|waterbody","name":"<STREAM_NAM or empty>"}
```

Frontend ids:
```text
survey-hydro-streams
survey-hydro-waterbodies
survey-hydro-streams-line
survey-hydro-waterbodies-fill
survey-hydro-waterbodies-outline
survey-hydro-stream-labels
```

Style:
- stream line #6f9ca6, 1.2→2.8px by zoom;
- water fill #bfd6dc ~0.55;
- outline #789fa7;
- labels minzoom 11.

Put below Surveyor objects/cameras and above landcover.

## 10. INATURALIST WILDLIFE

Endpoint:
```text
https://api.inaturalist.org/v1/observations
```

Species:
```python
WILDLIFE_TAXA = {
 "coyote":"Canis latrans",
 "red_fox":"Vulpes vulpes",
 "gray_fox":"Urocyon cinereoargenteus",
 "bobcat":"Lynx rufus",
 "raccoon":"Procyon lotor",
 "deer":"Odocoileus virginianus",
}
```

One concurrent request per enabled species, max 6.

Params:
```text
taxon_name=<scientific>
swlat=<south>
swlng=<west>
nelat=<north>
nelng=<east>
d1=<timeline YYYY-MM-DD>
d2=<timeline YYYY-MM-DD>
quality_grade=research
per_page=200
order_by=observed_on
order=desc
```

Normalize:
```json
{
 "provider":"iNaturalist",
 "provider_record_id":123,
 "species_key":"coyote",
 "scientific_name":"Canis latrans",
 "common_name":"Coyote",
 "observed_at":"...",
 "added_at":"...",
 "quality_grade":"research",
 "geoprivacy":"open|obscured|private|null",
 "coordinate_accuracy_m":25,
 "latitude":35.0,
 "longitude":-79.0,
 "url":"https://www.inaturalist.org/observations/123"
}
```

Only use coordinates returned publicly. Never de-obscure/infer coordinates.
External observations are not persisted to Journal automatically.

Frontend source: `survey-wildlife`.
Small species-colored circles/icons.
Opacity open ~0.82; obscured ~0.55.
Clearly visually distinct from user-created wildlife markers.
No heatmap this slice.

## 11. REGISTER ROUTER

`backend/app/main.py:348-357`

Add:
```python
from .surveyor.environment import router as surveyor_environment_router
app.include_router(surveyor_environment_router)
```
No other environment code in `main.py`.

## 12. LAYER DRAWER: REPLACE WHOLE FILE

`frontend/src/components/surveyor/LayerDrawer.vue:1-14`.

Keep current MY SEARCH controls.

Add ENVIRONMENT:
- Annual NLCD · 2025
- Streams / waterbodies · NC OneMap
- Wetlands · USFWS NWI
- County / state boundaries · Census

Add WILDLIFE DATA:
- master Public wildlife observations · iNaturalist
- Coyote / Red fox / Gray fox / Bobcat / Raccoon / Deer

Props:
```js
modelValue
counts
providerStatus
```

Show provider status: `ready|loading|degraded|unavailable`.
No dead controls.

## 13. ENVIRONMENTAL INSPECTOR

Add `frontend/src/components/surveyor/EnvironmentalInspector.vue`.

Props: `feature`. Emits: `close`, `add-note`, `add-marker`.

Hydro:
- feature name;
- Stream/river or Waterbody;
- `NC OneMap hydrography`.

Wildlife:
- common + scientific name;
- `Observed <date>`;
- `Added <date>` when available/different;
- quality grade;
- accuracy if available;
- obscured warning;
- provider link.

Buttons:
- Add note here
- Drop field marker here

Use existing Surveyor draft/object flows. Do not add a parallel persistence path.

## 14. MAP LEGEND

Add `frontend/src/components/surveyor/MapLegend.vue`.

Small/collapsible. Mobile collapsed by default.
Only visible semantics:
- woodland;
- developed;
- water;
- wetland if enabled;
- county line if enabled;
- external wildlife if enabled;
- current/historical camera;
- searched / needs search.

## 15. SURVEYORVIEW WIRING

At map load ~1255, make callback async and:
```js
applyCatMapStyle(map)
mapHealth.value = auditCatMapStyle(map)
environmentController = createEnvironmentLayers({
  map,
  api: API,
  getTimeline: () => timelineWindow.value,
  onStatus: v => environmentStatus.value = v,
  onSelect: v => selectedEnvironment.value = v
})
await environmentController.install(layerSettings.value)
```

Delete current NLCD lines 1275–1278.

Watch `timelineWindow`: if wildlife enabled call `refreshViewport`.

On unmount call `environmentController?.destroy()`.

Inside current map shell ~1450 add health badge + `MapLegend`.
Near existing inspectors add `EnvironmentalInspector`.
Pass `environmentStatus` to LayerDrawer.

Do not rewrite the existing one-line map tool markup beyond inserting these hooks.

## 16. SNAPPING: SURGICAL CHANGE ONLY

`frontend/src/surveyor/snapEngine.js:45-53`.

Change:
```js
/water|stream|river|canal|drain/
```
to:
```js
/water|stream|river|canal|drain|hydro/
```

If two snap candidates are close and one layer/source contains `survey-hydro`, prefer survey-hydro unless generic candidate is >4 screen px closer.

No other snap rewrite.

## 17. CSS

Edit only Surveyor styles ~516+ / append nearby.

Add:
```text
.map-health-badge
.map-health-badge.degraded
.map-health-badge.failed
.surveyor-map-legend
.environment-inspector
.provider-status
.wildlife-species-grid
```

Mobile:
- inspector bottom-sheet behavior;
- legend collapsed;
- Layers >=44px;
- no 320px horizontal overflow;
- do not cover mobile field bar.

No global restyle.

## 18. EXISTING FEATURES: ACCEPTANCE ONLY

Do not rebuild:
- trail-camera geometry/history;
- zones;
- corkboard links;
- search coverage;
- journal;
- access ledger.

Just verify new environment layers do not cover/break them.

P1 only if trivial: searched-zone freshness already uses `searchFreshness(object)`; fade stale/old searched zones using current property. Do not create a second freshness helper.

## 19. FOCUSED TEST

Add `backend/tests/test_surveyor_environment.py`.

Mock httpx; no live calls.

Test only:
1. invalid bbox;
2. bbox >2°;
3. hydro response normalization;
4. hydro cache hit;
5. wildlife observed vs added date;
6. obscured geoprivacy preserved;
7. wildlife cache key includes species/date;
8. upstream timeout => bounded 502.

Run once near end:
```bash
cd backend
python -m pytest tests/test_surveyor_environment.py -q
```

Frontend:
- never `npm install`;
- if `node_modules` exists: `npm run build`;
- otherwise let Docker build later.
Optional: `node --check src/surveyor/environmentLayers.js`.

## 20. 10-MIN MANUAL ACCEPTANCE

First load:
- roads, labels, water, woodland/developed context visible;
- not blank;
- Surveyor objects above geography.

Layers:
- NLCD/hydro/boundaries/wetlands toggle independently;
- provider failure does not blank map.

Wildlife:
- enable Coyote;
- point/provenance/date render;
- external marker differs from local wildlife marker.

Snap:
- line snaps to NC OneMap stream and indicator says WATERWAY.

Mobile:
- Layers reachable;
- inspector readable;
- no horizontal overflow.

## 21. IMPLEMENT ORDER
1. catMapStyle + health.
2. environmentLayers with NLCD + Census reuse.
3. backend hydro.
4. LayerDrawer.
5. NWI.
6. iNaturalist.
7. inspector + legend.
8. snap tweak.
9. mobile CSS.
10. focused test/manual acceptance.
11. commit + push `main`.
12. deploy only if real DietPi SSH/Tailscale access exists, per `AGENTS.md`.

## 22. DONE WHEN
- Surveyor geography useful on first load;
- blank map has degraded/failure UI;
- NLCD default-on;
- NC OneMap hydro works + snaps;
- Census boundaries non-blocking;
- NWI optional;
- iNaturalist optional by species with correct provenance/geoprivacy/dates;
- existing cameras/zones/links/journal still work;
- mobile works;
- focused tests pass;
- pushed to `main`.

## 23. DO NOT IMPLEMENT
Route optimization, predator-risk scoring, automatic cat-highway inference, AI search zones, automatic camera placement, Movebank, real-time sharing, DB persistence of external observations, generic provider framework.

## 24. REPO NOTE
GitHub currently reports default branch `feature/surveyor-v1`, which is stale/behind. `AGENTS.md` says work/deploy from `main`. If admin permission exists, change default branch to `main`; otherwise report only.

## 25. END REPORT
```text
SLICE 8
Base SHA:
Final SHA:
Base geography: pass/fail
NLCD: pass/fail
NC OneMap hydro: pass/fail
Census: pass/fail
NWI: pass/fail
iNaturalist: pass/fail
Hydro snapping: pass/fail
Mobile: pass/fail
Focused tests:
Frontend build: pass/skipped
Default branch:
DietPi deployment:
Known limitations:
```
