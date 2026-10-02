# NEXT SLICE TASK PACKET

## Archie Radar v1 · Slice 8
### Surveyor Geographic Context + Environmental Intelligence
### MINIMUM-TOKEN IMPLEMENTATION PACKET

**Code anchors verified against:** `main@bf04e47af90d6411009316b1ad290d070f0982dc`
**Target branch:** `main`
**Goal:** make Surveyor show useful cat-search geography immediately, then add bounded environmental/wildlife overlays without disturbing the existing field-journal systems.

---

# 0. TOKEN-BURN RULES — FOLLOW THESE FIRST

Do **not** rediscover the repository.

Read only:

1. `AGENTS.md`
2. this file
3. the exact files in §2

Do not run repo-wide architecture searches unless a named anchor below is missing.

Do not re-research provider APIs. Exact provider endpoints/parameters are supplied in §6.

Do not add dependencies. Existing stack already has:
- backend: `httpx`, FastAPI, Shapely, pyproj
- frontend: MapLibre GL + TerraDraw

Do not change these unless a real blocker is proven:
- `backend/app/models.py`
- `backend/app/db.py`
- `backend/app/settings.py`
- `backend/pyproject.toml`
- `frontend/package.json`
- `frontend/src/surveyor/objectTypes.js`
- `frontend/src/components/surveyor/SurveyTimeline.vue`

No database migration is required for this slice.

Do not run `npm install`.
Do not run the full backend suite repeatedly.
Implement once, run the focused checks in §12 once near the end, fix only failures caused by this slice.

If an upstream provider is temporarily unavailable, implement the specified degraded state and continue. Do not spend tokens diagnosing the provider beyond one bounded request.

---

# 1. CURRENT STATE — PRESERVE IT

Surveyor already has:
- full-page MapLibre map;
- TerraDraw lines/polygons/select;
- road/trail/water/object snapping;
- trail cameras + cones + placement history;
- zones;
- object/corkboard links;
- search sessions;
- evidence/media;
- property/access records;
- timeline;
- journal;
- outing/preflight;
- candidate layer;
- undo/redo;
- mobile field controls.

Do **not** rebuild those systems.

P0 defect: the live Surveyor page currently does not show enough useful geographic detail. Fix that first.

---

# 2. EXACT FILE SCOPE

## Modify only these existing files

| File | Current anchor / lines | Required work |
|---|---:|---|
| `frontend/src/views/SurveyorView.vue` | imports 1–38; defaults 42–46; visibility 136+; map init 1244–1278; map shell 1450–1451 | wire environment controller, health, inspector, legend, defaults |
| `frontend/src/surveyor/catMapStyle.js` | **entire file 1–37** | replace with hardened cat-view style + base-style audit |
| `frontend/src/surveyor/snapEngine.js` | 45–53 | recognize/prefer authoritative hydrography |
| `frontend/src/components/surveyor/LayerDrawer.vue` | **entire file 1–14** | replace placeholder landscape/wildlife controls |
| `frontend/src/style.css` | Surveyor map 516–537; timeline 602+; append new selectors near Surveyor block | geography health, legend, environmental inspector, mobile |
| `backend/app/main.py` | router imports/includes 348–357 | two-line environment-router registration |

## Add these files

```text
backend/app/surveyor/environment.py
frontend/src/surveyor/environmentLayers.js
frontend/src/components/surveyor/EnvironmentalInspector.vue
frontend/src/components/surveyor/MapLegend.vue
backend/tests/test_surveyor_environment.py
```

That is the complete expected file set.

If implementation requires touching anything else, stop first and verify it is truly necessary.

---

# 3. P0 BASE-MAP FIX

## 3.1 Replace `catMapStyle.js`

Current file: `frontend/src/surveyor/catMapStyle.js:1-37`.

Do not invent styling logic from scratch.

Reuse the better existing styling rules already present in:

`frontend/src/components/SearchMap.vue:188-252`

Copy/adapt those rules into `catMapStyle.js` so Surveyor gets:

- warm neutral background;
- water fills + water lines;
- woodland/forest/grass fills;
- developed/building context;
- motorway/trunk;
- primary;
- secondary;
- local/tertiary roads;
- place + road labels;
- hidden POI/shop/transit/address clutter.

Export exactly:

```js
export function applyCatMapStyle(map) { ... }
export function auditCatMapStyle(map) { ... }
export const CAT_MAP_PALETTE = ...
```

`auditCatMapStyle(map)` returns:

```js
{
  roads: boolean,
  water: boolean,
  labels: boolean,
  natural: boolean,
  status: 'ready' | 'degraded'
}
```

Detection is by layer id + `source-layer`, same classification strategy already used in SearchMap.

Do not require every category for `ready`; required minimum is:
- roads;
- water;
- labels.

If one is absent: `degraded`.

## 3.2 Surveyor map health

In `SurveyorView.vue` near refs after current line 48, add:

```js
const mapHealth = ref({ status: 'loading', roads: false, water: false, labels: false, natural: false })
const environmentStatus = ref({})
const selectedEnvironment = ref(null)
let environmentController = null
```

At current `map.on('load')` around line 1255:

```js
applyCatMapStyle(map)
mapHealth.value = auditCatMapStyle(map)
```

Also:

```js
map.on('error', () => {
  if (!map?.isStyleLoaded()) mapHealth.value = { ...mapHealth.value, status: 'failed' }
})
```

Render one compact badge inside `.surveyor-map-shell`:

- loading: `Loading geography…`
- degraded: `Base geography degraded · Retry`
- failed: `Base geography unavailable · Retry`

Retry may call `map.setStyle('https://tiles.openfreemap.org/styles/positron')`, then re-install custom/environment layers on `style.load`.

Never hide the user's local Surveyor objects because an external geography source failed.

---

# 4. DEFAULT LAYER SETTINGS

Current:

`frontend/src/views/SurveyorView.vue:45`

Replace:

```js
const defaultLayers = {
  objects: true,
  links: true,
  cameras: true,
  cameraHistory: false,
  candidates: true,
  landcover: true,
  hydrography: true,
  boundaries: true,
  wetlands: false,
  wildlife: false,
  wildlifeSpecies: {
    coyote: false,
    red_fox: false,
    gray_fox: false,
    bobcat: false,
    raccoon: false,
    deer: false
  }
}
```

Keep the current merge behavior at line 46 so old localStorage preferences survive while new keys receive defaults.

Do not make wetlands or wildlife default-on.

---

# 5. FRONTEND ENVIRONMENT CONTROLLER

Add:

`frontend/src/surveyor/environmentLayers.js`

This file owns external geography so `SurveyorView.vue` does not grow another 400 lines.

Export one factory:

```js
export function createEnvironmentLayers({
  map,
  api,
  getTimeline,
  onStatus,
  onSelect
}) {
  return {
    install,
    applyVisibility,
    refreshViewport,
    retry,
    destroy
  }
}
```

## Responsibilities

### install(settings)
1. install Annual NLCD raster;
2. install NWI raster;
3. install empty GeoJSON sources/layers for:
   - `survey-hydro-streams`
   - `survey-hydro-waterbodies`
   - `survey-wildlife`
4. install Census boundaries using the already-working SearchMap code (§7);
5. register map click handlers for environmental layers;
6. register debounced `moveend`;
7. call `applyVisibility(settings)`;
8. call `refreshViewport(settings)`.

### applyVisibility(settings)
Set MapLibre visibility for:
- annual landcover;
- hydrography;
- boundaries;
- wetlands;
- wildlife.

If wildlife is disabled, do not issue iNaturalist requests.

### refreshViewport(settings)
Debounce 350 ms.

Cancel stale fetches with one `AbortController`.

Only request:
- hydrography when `settings.hydrography`;
- wildlife when `settings.wildlife` and at least one species is selected.

Use current map bounds.

Do not request hydrography below zoom 8.
Do not request wildlife below zoom 9.
Do not request wetlands data in JS; it is a raster layer.

### retry()
Retry environment requests without recreating the whole Vue view.

### destroy()
Abort active requests and remove registered map event handlers.

---

# 6. PROVIDERS — EXACT URLS / REQUEST SHAPES

No provider research is required.

## 6.1 NC OneMap hydrography

Streams:
```text
https://services.nconemap.gov/secure/rest/services/NC1Map_Hydrography/FeatureServer/1/query
```

Waterbodies:
```text
https://services.nconemap.gov/secure/rest/services/NC1Map_Hydrography/FeatureServer/2/query
```

Both support GeoJSON.

Backend query parameters:

```text
where=1=1
geometry=<west>,<south>,<east>,<north>
geometryType=esriGeometryEnvelope
inSR=4326
outSR=4326
spatialRel=esriSpatialRelIntersects
outFields=STREAM_NAM
returnGeometry=true
f=geojson
resultRecordCount=2000
```

Normalize properties to:

```json
{
  "provider": "NC OneMap",
  "feature_type": "stream" | "waterbody",
  "name": "Morgan Creek"
}
```

## 6.2 iNaturalist

Endpoint:

```text
https://api.inaturalist.org/v1/observations
```

Use one request per **enabled species**, concurrently, maximum 6.

Scientific-name config:

```python
WILDLIFE_TAXA = {
    "coyote": "Canis latrans",
    "red_fox": "Vulpes vulpes",
    "gray_fox": "Urocyon cinereoargenteus",
    "bobcat": "Lynx rufus",
    "raccoon": "Procyon lotor",
    "deer": "Odocoileus virginianus",
}
```

Params:

```text
taxon_name=<scientific name>
swlat=<south>
swlng=<west>
nelat=<north>
nelng=<east>
d1=<YYYY-MM-DD from Surveyor timeline>
d2=<YYYY-MM-DD to Surveyor timeline>
quality_grade=research
per_page=200
order_by=observed_on
order=desc
```

Use the public read endpoint only. No auth.

Normalize each result:

```json
{
  "provider": "iNaturalist",
  "provider_record_id": 123,
  "species_key": "coyote",
  "scientific_name": "Canis latrans",
  "common_name": "Coyote",
  "observed_at": "...",
  "added_at": "...",
  "quality_grade": "research",
  "geoprivacy": "open|obscured|private|null",
  "coordinate_accuracy_m": 25,
  "latitude": 35.0,
  "longitude": -79.0,
  "url": "https://www.inaturalist.org/observations/123"
}
```

Coordinates:
- use only coordinates present in the public API response;
- never derive unobscured coordinates;
- pass through `geoprivacy`;
- obscured coordinates remain approximate.

## 6.3 Census boundaries

Do **not** build new Census backend code.

Reuse the already-working code from:

- URLs: `frontend/src/components/SearchMap.vue:8-10`
- cached fetch helper: `SearchMap.vue:157-173`
- boundary layers: `SearchMap.vue:261-312`

Move/adapt that logic into `environmentLayers.js`.

Keep the 3.5 second timeout and 7-day localStorage cache.

## 6.4 NWI wetlands

Use a MapLibre raster source directly; no backend code.

Service:

```text
https://fwspublicservices.wim.usgs.gov/wetlandsmapservice/rest/services/Wetlands/MapServer/export
```

Tile URL:

```text
https://fwspublicservices.wim.usgs.gov/wetlandsmapservice/rest/services/Wetlands/MapServer/export?bbox={bbox-epsg-3857}&bboxSR=3857&imageSR=3857&size=256,256&format=png32&transparent=true&layers=show:0&f=image
```

MapLibre source:
- type `raster`
- tileSize `256`
- attribution `USFWS National Wetlands Inventory`

Layer:
- id `survey-wetlands`
- opacity ~0.26
- default hidden
- minzoom 10

## 6.5 Annual NLCD

Do not replace the current service.

Current source exists at:

`frontend/src/views/SurveyorView.vue:1275-1278`

Move this source/layer creation into `environmentLayers.js`.

Keep the same URL initially.
Set opacity to ~0.22.
Default visible.

Do not spend this slice dynamically discovering the newest NLCD year. Keep current 2025 service value and expose `Annual NLCD · 2025` in Layers.

---

# 7. CENSUS CODE REUSE — NO DUPLICATE INVENTION

The existing candidate map already solved boundaries.

Do not research or redesign it.

Copy/adapt:

```text
frontend/src/components/SearchMap.vue:8-10
frontend/src/components/SearchMap.vue:157-173
frontend/src/components/SearchMap.vue:261-312
```

into `environmentLayers.js`.

Surveyor styling:
- county: thin dashed, opacity ~0.22;
- county label minzoom ~8.6;
- state: solid, opacity ~0.45;
- boundary load failure => status `unavailable`, never infinite loading.

---

# 8. BACKEND — ONE NEW ROUTER FILE ONLY

Add:

`backend/app/surveyor/environment.py`

Do not add models/tables/settings/dependencies.

Use existing `httpx`.

Router:

```python
router = APIRouter(prefix="/api/surveyor/environment", tags=["surveyor-environment"])
```

Endpoints:

```text
GET /status
GET /hydrography?west=&south=&east=&north=
GET /wildlife?west=&south=&east=&north=&from_date=&to_date=&species=coyote&species=red_fox
```

## /status

Static capability response:

```json
{
  "hydrography": {"provider":"NC OneMap","available":true},
  "wetlands": {"provider":"USFWS NWI","available":true},
  "boundaries": {"provider":"US Census TIGERweb","available":true},
  "wildlife": {"provider":"iNaturalist","available":true}
}
```

Do not make upstream calls from `/status`.

## Shared validation

Reject invalid bbox:
- west/east outside -180..180;
- south/north outside -90..90;
- west >= east;
- south >= north.

Reject excessively large bbox:
- width > 2 degrees or height > 2 degrees => HTTP 400.

This protects provider calls.

## Cache

Implement a tiny process-local TTL dictionary in `environment.py`.

No DB table.

Key:
```python
(provider, round(west, 2), round(south, 2), round(east, 2), round(north, 2), extra_filters)
```

TTL:
- hydro: 24 hours;
- wildlife: 15 minutes.

Cap dictionary at ~128 entries; evict oldest entry when full.

## HTTP behavior

Use one shared `httpx.AsyncClient(timeout=4.0)` pattern or scoped clients.

On upstream timeout/error, return HTTP 502 with short provider-specific detail.

Do not retry more than once.

---

# 9. REGISTER THE ROUTER

Current router block:

`backend/app/main.py:348-357`

Add:

```python
from .surveyor.environment import router as surveyor_environment_router
```

and:

```python
app.include_router(surveyor_environment_router)
```

No other `main.py` environmental code.

---

# 10. SURVEYORVIEW SURGICAL CHANGES

## Imports

Current imports: `SurveyorView.vue:1-38`.

Add:

```js
import { applyCatMapStyle, auditCatMapStyle } from '../surveyor/catMapStyle.js'
import { createEnvironmentLayers } from '../surveyor/environmentLayers.js'
import EnvironmentalInspector from '../components/surveyor/EnvironmentalInspector.vue'
import MapLegend from '../components/surveyor/MapLegend.vue'
```

Replace the existing one-symbol `applyCatMapStyle` import rather than duplicating it.

## Visibility hook

Current function begins:

`SurveyorView.vue:136`

At the end of `applyLayerVisibility(settings)` add:

```js
environmentController?.applyVisibility(settings)
```

Do not hand-code every environmental layer in this function.

## Map load

Current block begins:

`SurveyorView.vue:1255`

Immediately after base styling and before local field layers finish installing:

```js
mapHealth.value = auditCatMapStyle(map)
environmentController = createEnvironmentLayers({
  map,
  api: API,
  getTimeline: () => timelineWindow.value,
  onStatus: status => { environmentStatus.value = status },
  onSelect: feature => { selectedEnvironment.value = feature }
})
await environmentController.install(layerSettings.value)
```

Make the `load` callback async.

Delete current inline NLCD creation:

`SurveyorView.vue:1275-1278`

because `environmentLayers.js` owns it.

After all custom layers exist, keep calling current `applyLayerVisibility()`.

## Timeline

Watch `timelineWindow`.

If wildlife is enabled:

```js
environmentController?.refreshViewport(layerSettings.value)
```

Debouncing happens inside controller.

## Unmount

Call:

```js
environmentController?.destroy()
```

before `map.remove()`.

## Map shell

Current map shell is one very long line:

`SurveyorView.vue:1450`

Do not rewrite unrelated controls.

Add inside the shell:
- map-health badge;
- `<MapLegend ... />`.

Add after the shell / alongside existing inspectors:
- `<EnvironmentalInspector v-if="selectedEnvironment" ... />`.

---

# 11. LAYER DRAWER — REPLACE THE 14-LINE FILE

Replace:

`frontend/src/components/surveyor/LayerDrawer.vue:1-14`

Props:

```js
defineProps({
  modelValue: { type: Object, required: true },
  counts: { type: Object, default: () => ({}) },
  providerStatus: { type: Object, default: () => ({}) }
})
```

Sections:

## MY SEARCH
Keep current five controls unchanged.

## ENVIRONMENT
- Annual NLCD · 2025
- Streams / waterbodies · NC OneMap
- Wetlands · USFWS NWI
- County / state boundaries · Census

## WILDLIFE DATA
Master:
- Public wildlife observations · iNaturalist

Species toggles:
- Coyote
- Red fox
- Gray fox
- Bobcat
- Raccoon
- Deer

Only show species toggles when wildlife master is enabled.

Show compact provider status text:
- ready
- loading
- degraded
- unavailable

Do not add a second modal/settings flow.

---

# 12. SNAPPING — TWO-LINE CHANGE

Current:

`frontend/src/surveyor/snapEngine.js:45-53`

Change water recognition from:

```js
/water|stream|river|canal|drain/
```

to:

```js
/water|stream|river|canal|drain|hydro/
```

Add authoritative preference:

When two candidates are within threshold and one comes from source/layer containing:
`survey-hydro`

prefer that hydro candidate over a generic base-map water candidate unless the generic candidate is >4 screen pixels closer.

Do not otherwise rewrite snapping.

---

# 13. ENVIRONMENTAL INSPECTOR

Add:

`frontend/src/components/surveyor/EnvironmentalInspector.vue`

Props:
```js
feature
```

Emits:
```text
close
add-note
add-marker
```

Render by `feature.kind`.

## hydrography
Show:
- name;
- Stream/river or Waterbody;
- `NC OneMap hydrography`.

## boundary
Show:
- county/state name;
- `U.S. Census TIGERweb`.

## wetland
If only raster identify is unavailable, do **not** fake an inspector.
No wetland click handling is required in this slice.

## wildlife
Show:
- common/scientific name;
- `Observed <date>`;
- `Added <date>` when different/available;
- quality grade;
- coordinate accuracy if supplied;
- `Approximate / obscured location` when geoprivacy is obscured;
- provider link.

Buttons:
- Add note here
- Drop field marker here

Those actions create normal existing Surveyor drafts/objects. Do not persist external observations automatically.

---

# 14. MAP LEGEND

Add:

`frontend/src/components/surveyor/MapLegend.vue`

Keep it tiny.

Props:
```js
layers
```

Collapsed by default on mobile.

Only list visible semantics:
- woodland;
- developed;
- water;
- wetland when enabled;
- county line when enabled;
- external wildlife when enabled;
- current/historical camera when relevant;
- searched / needs-search if objects are enabled.

No full provider documentation in the legend.

---

# 15. WILDLIFE MAP LAYER

In `environmentLayers.js`:

Source:
```text
survey-wildlife
```

Use one GeoJSON source.

Feature properties:
```text
kind=wildlife
species_key
common_name
scientific_name
observed_at
added_at
provider
provider_record_id
quality_grade
geoprivacy
accuracy_m
url
```

Layer:
- small circle/icon;
- color by species;
- opacity 0.82 open location;
- opacity 0.55 obscured;
- no heatmap in this slice unless trivial after point layer is complete.

External wildlife markers must look different from user-created wildlife evidence.

Do not call them hotspots, territories, risk, or routes.

---

# 16. HYDROGRAPHY MAP LAYERS

In `environmentLayers.js`:

Sources:
```text
survey-hydro-streams
survey-hydro-waterbodies
```

Layers:
```text
survey-hydro-waterbodies-fill
survey-hydro-waterbodies-outline
survey-hydro-streams-line
survey-hydro-stream-labels
```

Suggested styling:
- streams: #6f9ca6, 1.2–2.8 px by zoom;
- waterbody fill: #bfd6dc, opacity ~0.55;
- outline: #789fa7;
- labels minzoom 11.

Put hydrography **below Surveyor user objects/cameras**, above land-cover raster.

---

# 17. BOUNDARIES

Reuse SearchMap code only.

Do not create a backend endpoint.

Layer ids:
```text
survey-county-lines
survey-county-labels
survey-state-lines
```

Avoid ids used by candidate SearchMap to prevent conceptual confusion.

Timeout 3.5s.
Cache 7d.
Failure status must settle to `unavailable`, never `loading` forever.

---

# 18. CSS — EDIT ONLY SURVEYOR BLOCK + APPEND

Current Surveyor block begins around:

`frontend/src/style.css:516`

Existing map shell around:
`533-537`.

Add styles for:
- `.map-health-badge`
- `.map-health-badge.degraded`
- `.map-health-badge.failed`
- `.surveyor-map-legend`
- `.environment-inspector`
- `.provider-status`
- wildlife species grid
- environment layer labels.

Mobile:
- inspector becomes bottom sheet;
- legend collapses;
- Layers remains >=44x44;
- no horizontal overflow at 320 px;
- do not cover `.mobile-field-bar`.

Do not restyle the whole application.

---

# 19. SEARCH COVERAGE FRESHNESS

Existing helper already exists:

`frontend/src/surveyor/zoneState.js`

and current Surveyor already computes:
`searchFreshness(object)`

Do not invent a second freshness system.

Only adjust map paint expressions for searched zones to make current freshness visible:

```text
fresh   <=3d      normal
recent  <=14d     ~0.78 opacity
stale   <=45d     ~0.52 opacity
old     >45d      ~0.32 opacity
```

If existing `searchFreshness` returns different named buckets, use those existing names rather than changing the helper unless necessary.

Inspector wording:
`Last searched 18 days ago · stale`

This is optional P1 after geography/wildlife are working.

---

# 20. TRAIL CAMERAS / LINKS — AUDIT, DO NOT REBUILD

No new camera model.

Acceptance only:
- current cones remain visible above environment layers;
- historical placement remains faded;
- environmental layers do not swallow click targets;
- moving camera still preserves history;
- object links remain attached and visible;
- corkboard line patterns remain readable against NLCD/water.

Do not rewrite camera geometry or link persistence in Slice 8.

---

# 21. BACKEND TEST FILE

Add:

`backend/tests/test_surveyor_environment.py`

Only focused tests:

1. invalid bbox rejected;
2. bbox >2° rejected;
3. NC OneMap response normalizes stream/waterbody FeatureCollections;
4. hydro cache reuses identical rounded bbox;
5. iNaturalist normalization keeps `observed_at` distinct from `added_at`;
6. obscured geoprivacy survives normalization;
7. wildlife cache key includes species + date range;
8. upstream timeout returns bounded 502/degraded response.

Mock `httpx`; never call live providers during tests.

---

# 22. MANUAL ACCEPTANCE — 10 MINUTES MAX

Do not turn manual acceptance into an exploratory QA project.

## First load
Open Surveyor.

Pass if:
- roads visible;
- road/place labels visible;
- water visible;
- woodland/developed distinction visible;
- map is not blank;
- local Surveyor objects remain visible.

## Layers
Toggle:
- NLCD;
- hydro;
- boundaries;
- wetlands.

Pass if each toggles without blanking the map.

## Wildlife
Enable Coyote.

Pass if:
- bounded iNaturalist request returns/render points when observations exist;
- click shows provenance;
- observed date is primary;
- external point looks different from local wildlife evidence.

## Snapping
Draw one line near an NC OneMap stream.

Pass if snap indicator says WATERWAY and snaps.

## Mobile
Check one portrait viewport.

Pass if:
- Layers reachable;
- map usable;
- environmental inspector readable;
- no horizontal overflow.

---

# 23. FOCUSED COMMANDS ONLY

Backend:

```bash
cd backend
python -m pytest tests/test_surveyor_environment.py -q
```

Frontend:
- do **not** run `npm install`;
- if `node_modules` already exists, run:

```bash
npm run build
```

Otherwise skip local frontend build and let Docker Compose build during deployment.

Optional syntax sanity only if useful:

```bash
node --check src/surveyor/environmentLayers.js
```

Do not run unrelated full suites unless one of these changes breaks shared code.

---

# 24. IMPLEMENTATION ORDER

Do exactly this order:

1. `catMapStyle.js` hardened style + audit.
2. Surveyor base map health badge.
3. `environmentLayers.js` with NLCD + Census reuse.
4. NC OneMap backend + frontend hydro layer.
5. LayerDrawer environment controls.
6. NWI raster.
7. iNaturalist backend + point layer.
8. EnvironmentalInspector.
9. MapLegend.
10. snapEngine hydro preference.
11. mobile CSS.
12. focused tests.
13. one manual acceptance pass.
14. commit/push `main`.
15. deploy per `AGENTS.md` only if actual DietPi SSH/Tailscale access exists.

Do not start P1 polish before P0 first-load geography works.

---

# 25. DEFINITION OF DONE

Done when:

- Surveyor is geographically useful before user objects exist;
- base map does not silently degrade to an empty canvas;
- roads, labels, water, woodland/developed context are visible;
- NLCD defaults on;
- NC OneMap streams/waterbodies work;
- Census county/state context works non-blockingly;
- NWI wetlands can be toggled on;
- iNaturalist wildlife can be toggled by species;
- iNaturalist provenance/geoprivacy/date semantics are correct;
- environment provider failure does not break local Surveyor tools;
- hydrography participates in snapping;
- camera cones/history/links remain usable;
- mobile map remains field-usable;
- focused test file passes;
- changes are on `main`.

---

# 26. DO NOT IMPLEMENT

Not in this slice:

- route optimization;
- predator-risk scoring;
- automatic cat-highway inference;
- AI search-zone generation;
- automatic camera placement;
- Movebank;
- real-time social sharing;
- DB persistence of external wildlife observations;
- generic plugin/provider framework;
- environment settings UI beyond LayerDrawer.

---

# 27. REPOSITORY NOTE

At packet-writing time GitHub still reports default branch:
`feature/surveyor-v1`

That branch is stale/behind `main`.

Per `AGENTS.md`, implementation and deployment use `main`.

If repo-admin permission is available, set GitHub default branch to `main`.
If not, report it and continue on `main`.

---

# 28. END REPORT

Return only:

```text
SLICE 8

Base SHA:
Final SHA:

Base geography: pass/fail
NLCD: pass/fail
NC OneMap hydro: pass/fail
Census boundaries: pass/fail
NWI wetlands: pass/fail
iNaturalist: pass/fail
Hydro snapping: pass/fail
Mobile: pass/fail
Focused tests:
Frontend build: pass/skipped

Default branch:
DietPi deployment:

Known limitations:
```
