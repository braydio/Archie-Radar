# NEXT SLICE TASK PACKET — MIN TOKEN

## Archie Radar v1 · Slice 8B
### Surveyor Environmental Hardening + Field-Map Correctness

**Base reviewed:** `main@be94085b90a75a8962500016c17515efa6408ae7`
**Target:** latest `main`
**Intent:** correct concrete Slice 8 defects, finish missing Surveyor zone semantics, and clean two adjacent candidate-map provenance regressions. Do not redesign Surveyor.

---

# 0. TOKEN RULES

Read only:
1. `AGENTS.md`
2. this file
3. exact files in §1

No repo-wide rediscovery unless an anchor is missing.
No new dependencies.
No DB migration.
No `npm install`.
No live provider calls in tests.
Do not rebuild cameras, outings, journal, media, access, candidate identity, or search-session systems.

Implement in the order in §15. Run focused checks once near the end.

---

# 1. EXACT FILE SET

## Modify

```text
backend/app/surveyor/environment.py                 164 lines
backend/tests/test_surveyor_environment.py          107 lines
frontend/src/surveyor/environmentLayers.js          102 lines
frontend/src/surveyor/catMapStyle.js                 84 lines
frontend/src/views/SurveyorView.vue                1504 lines
frontend/src/components/surveyor/LayerDrawer.vue     32 lines
frontend/src/components/surveyor/DraftObjectSheet.vue 47 lines
frontend/src/surveyor/objectTypes.js                 29 lines
frontend/src/components/surveyor/EnvironmentalInspector.vue 29 lines
frontend/src/style.css                              1065 lines
frontend/src/components/SearchMap.vue               695 lines
frontend/src/views/CandidateCaseView.vue            223 lines
frontend/src/views/CandidatesView.vue                review-page orientation
frontend/src/components/surveyor/SearchSessionBar.vue duplicate overlay control
frontend/src/components/surveyor/MarkerTypePicker.vue NEW · marker-first placement
```

Do not touch other files unless a named anchor no longer exists.

---

# 1A. P0 — SURVEYOR MUST OPEN AT HOME + NEARBY FIELD CONTEXT

Current:
`frontend/src/views/SurveyorView.vue:1250-1258`

The map starts from a hardcoded center/zoom and does not fit itself to actual home + nearby Surveyor objects.

Do not add another backend endpoint.

Use existing:
```text
GET /api/search-config
home_latitude
home_longitude
```

Add:
```js
const searchConfig = ref(null)
let initialViewportApplied = false
```

Load `/api/search-config` before/while initializing Surveyor.

Replace the hardcoded startup coordinates with `searchConfig.home_longitude/home_latitude` when available.

After `loadObjects()` has populated local Surveyor objects, run exactly once:

```js
fitInitialHomeContext()
```

Behavior:
1. home is the required anchor;
2. collect valid point coordinates or object centroids;
3. calculate distance from home;
4. keep the nearest **up to 8 objects within 3 miles**;
5. fit bounds to home + those objects;
6. padding ~64 desktop / ~42 mobile;
7. `maxZoom: 13.5`;
8. if no nearby objects, center home at ~13.2.

Do not include distant candidates in initial fit. A far report must not zoom the field map out to county scale.

Explicit navigation intent overrides the home fit:
- `?object=`;
- active location focus;
- photo GPS focus;
- a deliberate session/map focus.

Add a subtle permanent HOME point using a dedicated `survey-home` GeoJSON source/layer. Do not overload temporary `location-focus`.

The user can pan/zoom normally after initial fit. Do not continuously snap back home.

---

# 1B. P0 — "LAYERS" → ONE SINGLE "OVERLAYS" CONTROL

Current duplication is real:

```text
frontend/src/components/surveyor/SearchSessionBar.vue
  emits/shows a Layers button

frontend/src/views/SurveyorView.vue:1477
  also renders a floating Layers button
```

Keep only the floating map control.

Remove `layers` emit/button from `SearchSessionBar.vue`.

Rename user-facing map control:
```text
Layers → Overlays
```

Keep internal names such as `layerSettings` / `LayerDrawer.vue`; do not waste tokens renaming architecture.

In `LayerDrawer.vue` user-facing copy becomes:

```text
eyebrow: OVERLAYS
heading: Map context
aria-label: Map overlays
```

Sections:
- YOUR SEARCH
- LAND + WATER
- WILDLIFE OBSERVATIONS

The purpose is: **what extra context should be drawn over the field map?**

Do not show "Layers" anywhere else on Surveyor.

---

# 1C. P0 — SURFACE THE EXISTING NIGHTLY READINESS SYSTEM

The system already exists. Do not rebuild it.

Existing implementation:

```text
frontend/src/components/surveyor/OutingPreflight.vue
backend/app/surveyor/outings.py
```

It already supports:
- Prep / Setup;
- Packing List;
- Gameplan;
- editable titles/details;
- required vs optional;
- skip/restore;
- reordering;
- dependencies;
- "Used by N items";
- "Needs setup";
- shared blockers;
- readiness counts;
- reuse last outing;
- continue unfinished;
- linked candidate/map/task context.

Current UX defect:
it is mostly discoverable only by pressing **Start search**.

## Add a persistent Tonight readiness bar

In `SurveyorView.vue`, directly below the top bar and before the map workspace, render a compact clickable `night-readiness-bar`.

When no draft/current plan:
```text
TONIGHT
Build tonight's checklist
Prep · pack · gameplan
[Plan tonight]
```

When plan exists and not ready:
```text
TONIGHT · 3 things left
2 setup · 1 unpacked · 4 stops
[Open plan]
```

When ready:
```text
TONIGHT · READY
6 packed · 4 stops
[Review plan]
```

Click opens the existing `OutingPreflight` by setting `preflightOpen=true`.

Use `outingPlan.readiness`; do not duplicate readiness calculations client-side beyond formatting.

During an active search, the existing OutingPreflight mission strip remains the primary "NEXT" surface. Avoid showing two competing readiness bars.

## Dependency visibility

The full plan must continue to visibly show:
- each gameplan/packing item's dependency summary;
- pending dependency warning;
- shared prep item "Used by N items";
- add/link setup dependency UI.

Do not hide these under another advanced menu.

## Mental-load principle

The normal nightly flow should now read:

```text
TONIGHT → finish setup/packing → review gameplan → START SEARCH → NEXT stop
```

The user should not need to remember where the readiness checklist lives.

---

# 1D. P1 — MAKE EACH PAGE SAY WHAT JOB IT DOES

The app currently has features but weak "what should I do now?" hierarchy.

## Candidates page

Current:
`frontend/src/views/CandidatesView.vue:523-532`

Keep it compact, but change the lede to an action sequence:

```text
Review #1 first → classify it → open anything promising → add field follow-up to Tonight.
```

Add a tiny `review-flow-strip` under the header:

```text
1 Review new reports   2 Mark Possible / Hold / Not Archie   3 Send field work to Tonight
```

This is instructional UI, not a modal/tutorial.

Do not add another dashboard card.

## Surveyor page

Current header:
`SurveyorView.vue:1468+`

Keep the Surveyor name but add one compact field-flow line:

```text
Plan tonight → map what matters → start search → log what you find
```

The readiness bar immediately below it provides the actual next action.

No onboarding carousel.
No forced walkthrough.
No repeated explanatory paragraphs.

---

# 1E. P0 — MARKER/PIN FLOW MUST BE TYPE-FIRST

Current behavior:
- user clicks Pin;
- user taps map;
- draft opens;
- type selection happens too late.

There is also a correctness risk:
`SurveyorView.vue:705-707` currently uses the shared editing ref `subtype.value` for new pins, so a previously selected object's subtype can leak into a new marker draft.

## Rename user-facing "Pin" to "Marker"

Keep stored object type `pin`. Only UI wording changes.

`SurveyorToolbar.vue`:
```text
Pin → Marker
```

Mobile:
```text
Pin → Marker
```

## Add
`frontend/src/components/surveyor/MarkerTypePicker.vue`

Use existing:
```js
PIN_GROUPS
OBJECT_TYPES
```

Do not create another marker taxonomy.

Picker requirements:
- opens immediately when user taps/clicks Marker;
- grouped Search / Environment / Wildlife / Evidence;
- large touch targets;
- common label + icon/color indicator;
- close/cancel;
- mobile = bottom sheet;
- desktop = compact popover/panel.

Suggested top/common choices may be shown first:
- Sighting
- Possible sighting
- Outdoor cat
- Coyote
- Fox
- Dog lives here
- Food station
- Scent item

But all existing `PIN_GROUPS` types remain available.

## New state

In `SurveyorView.vue` add:

```js
const markerPickerOpen = ref(false)
const pendingMarkerType = ref(null)
```

Do **not** reuse the object editor's `subtype` ref.

## Activation flow

```text
tap Marker
→ marker picker opens
→ choose "Outdoor cat"
→ active tool becomes marker placement
→ map shows "OUTDOOR CAT · Tap map to place"
→ cursor/placement visual indicates placement mode
→ tap map
→ draft opens already typed Outdoor cat
```

`activateTool('pin')` should open the picker instead of immediately entering placement mode.

After a marker type is chosen:
- set `pendingMarkerType`;
- set `activeTool='pin'`;
- close picker;
- clear competing selected inspectors.

## Placement cue

While `activeTool === 'pin'` and `pendingMarkerType`:
- cursor = crosshair on desktop;
- show small colored placement badge using the type color/icon;
- text: `<TYPE> · Tap map to place`;
- include a small `Change` action that reopens MarkerTypePicker.

No heavy ghost rendering is required.

Optional tiny tap feedback:
show a brief marker pulse at the clicked coordinate before the draft sheet appears if trivial.

## Map click

Change:
```js
createPin(coordinates)
```

to:
```js
createPin(coordinates, pendingMarkerType.value)
```

and:

```js
function createPin(coordinates, markerType) {
  if (!markerType) return
  draftObject.value = {
    kind: 'pin',
    geometry: { type:'Point', coordinates },
    subtype: markerType
  }
}
```

The DraftObjectSheet may still allow changing the type before save, but it should open on the already chosen type.

After save:
- clear `pendingMarkerType`;
- return to Select.

After cancel:
- return to Select and clear pending type.

Long-press/right-click QuickAdd remains available as the location-first shortcut. That is a separate expert shortcut and does not define the normal Marker workflow.

---

# 1F. P0 — WILDLIFE/WETLANDS "UNAVAILABLE" IS A UI STATE BUG

Current defaults:
`SurveyorView.vue:48`
```text
wetlands:false
wildlife:false
all wildlifeSpecies:false
```

Current controller initializes/uses `unavailable` for these normal inactive states.

So today's UI does **not** establish that USFWS or iNaturalist are actually down.

Apply §4 status semantics strictly:

Wetlands default-off:
```text
Wetlands                     Off
```

Wildlife default-off:
```text
Wildlife observations        Off
```

Wildlife enabled but no taxa:
```text
Wildlife observations        Choose species
```

Wildlife enabled below zoom 9:
```text
Wildlife observations        Zoom in
```

Only real request/config failure may say:
```text
Unavailable
```

Do not turn wetlands or wildlife on by default merely to avoid the word unavailable.

---

# 2. P0 — ENVIRONMENT LAYER USES STALE SETTINGS AFTER PAN

Current bug:

`frontend/src/surveyor/environmentLayers.js:61`

```js
const onMove = () => refreshViewport(settings)
```

This closes over the settings passed to `install()`. After layer/species toggles, a later pan can restore old behavior and fetch layers the user disabled or omit layers the user enabled.

Fix:

- declare `let currentSettings = {}` near other controller state, before `install`;
- at start of `install(settings)`: `currentSettings = settings`;
- `onMove = () => refreshViewport(currentSettings)`;
- every public `applyVisibility(settings)` / `refreshViewport(settings)` wrapper updates `currentSettings`.

Add a pure/helper test if practical; otherwise cover via focused frontend syntax/manual acceptance.

---

# 3. P0 — STOP UNNECESSARY PROVIDER REFRESHES

Current:

`environmentLayers.js:71-75`

`applyVisibility()` always calls `refreshViewport(settings)`.

Because `SurveyorView.vue:161-163` deep-watches all layer settings, toggling:
- candidate reports;
- links;
- camera history;
- local objects;

can re-run hydro/wildlife network fetches.

Change controller behavior:

```js
applyVisibility(nextSettings) {
  const previous = currentSettings
  currentSettings = nextSettings
  // set layout visibility
  if (environmentQueryChanged(previous, nextSettings)) refreshViewport(nextSettings)
}
```

`environmentQueryChanged` compares only:
- `hydrography`;
- `wildlife`;
- `wildlifeSpecies`.

Timeline changes already explicitly call `refreshViewport` from `SurveyorView.vue:332`.

Do not refetch external data for landcover/wetland/boundary/local-layer visibility changes.

---

# 4. P0 — PROVIDER STATUS MUST NOT CALL "OFF" UNAVAILABLE

Current statuses:
`environmentLayers.js:8, 71-96`

Disabled layers and zoom-gated layers are reported as `unavailable`, which falsely implies provider failure.

Supported status values:

```text
off
loading
ready
degraded
zoom_in
select_species
unavailable
```

Rules:

- disabled => `off`;
- hydro enabled, zoom < 8 => `zoom_in`;
- wildlife enabled, no species => `select_species`;
- wildlife enabled, zoom < 9 => `zoom_in`;
- request in flight => `loading`;
- success => `ready`;
- request/source error => `degraded`;
- provider cannot be configured/used => `unavailable`.

Update `LayerDrawer.vue:7,20-29` to render friendly labels:
- off → `off`
- zoom_in → `zoom in`
- select_species → `choose species`.

Restore the object count regression:
`Markers, notes, zones, and lines <b>{{ counts.objects || 0 }}</b>`.

---

# 5. P0 — LAYER ORDER: ENVIRONMENT MUST NOT COVER ROAD/PLACE LABELS

Current `environmentLayers.js:31-58` appends NLCD and NWI raster layers above the entire OpenFreeMap base style, including labels.

Add:

```js
function firstBaseLabelLayer() {
  return map.getStyle()?.layers?.find(layer => layer.type === 'symbol')?.id
}
```

Insert these **before** first base symbol layer:
- `annual-landcover`
- `survey-wetlands`
- hydro waterbody fill/outline
- hydro stream line

Hydro stream labels may remain above base labels but below Surveyor user layers.

Surveyor objects/cameras/links created later must remain above all environment layers.

Manual acceptance:
road/place labels remain crisp with NLCD + wetlands enabled.

---

# 6. P0 — HYDROGRAPHY CACHE BOUNDS CAN OMIT VIEWPORT EDGES

Current:
`backend/app/surveyor/environment.py:32-33`

The cache key rounds bounds, but the upstream request uses the first request's exact bounds. A slightly larger later viewport can hit the same rounded key and receive geometry that does not cover its edge.

Replace key-only rounding with an **expanded bucket bbox**:

```python
step = 0.02
west  = floor(west / step) * step
south = floor(south / step) * step
east  = ceil(east / step) * step
north = ceil(north / step) * step
```

Use that same expanded bbox for:
- cache key;
- NC OneMap request;
- iNaturalist request.

Keep the user's original bbox validation before expansion.

Test two nearby viewports in one bucket and assert returned/query bbox covers both.

---

# 7. P0 — HYDROGRAPHY NAME + PAGINATION + PARTIAL FAILURE

Current:
`backend/app/surveyor/environment.py:72-106`

## 7.1 Waterbody name

Official NC OneMap waterbody layer exposes both `STREAM_NAM` and `WATERBODY`.

For layer 1:
```text
outFields=STREAM_NAM
name = STREAM_NAM
```

For layer 2:
```text
outFields=STREAM_NAM,WATERBODY
name = WATERBODY || STREAM_NAM
```

Do not leave named lakes/ponds blank merely because `STREAM_NAM` is empty.

## 7.2 Pagination

Current request caps at 2000 and silently ignores provider truncation.

Implement bounded ArcGIS pagination:
- `resultRecordCount=2000`;
- `resultOffset=0,2000,4000`;
- max 3 pages / 6000 features per layer;
- stop when returned feature count < 2000 or provider indicates no more;
- response includes `truncated: true` if cap reached with another page likely.

Return:
```json
{
  "provider":"NC OneMap",
  "streams": {...},
  "waterbodies": {...},
  "truncated": false,
  "degraded_layers": []
}
```

## 7.3 Partial failure

Do not fail all hydrography because one of streams/waterbodies fails.

Use `asyncio.gather(..., return_exceptions=True)`.

If one succeeds:
- HTTP 200;
- successful FeatureCollection;
- failed collection empty;
- add layer name to `degraded_layers`.

Only return 502 when both fail.

Frontend:
- render successful layer;
- provider status `degraded` when `degraded_layers.length`;
- `ready` otherwise.

---

# 8. P1 — WILDLIFE PAGINATION + PRECISE OBSERVED TIME

Current:
`environment.py:110-163`

Current iNaturalist fetch is one page of 200/species and silently truncates.

Implement:
- max 2 pages/species;
- `per_page=200`;
- page 1 and page 2 only when needed;
- use `total_results` when provided;
- response `truncated: true` if more data exists beyond cap.

Prefer event time:
```python
observed_at = observation.get("time_observed_at") or observation.get("observed_on")
```

Keep `added_at = created_at`.

Do not broaden beyond research-grade in this slice.

Frontend should not render thousands of naked points:
- make `survey-wildlife` GeoJSON source clustered;
- `clusterRadius ~35`;
- `clusterMaxZoom ~13`;
- add wildlife cluster + cluster-count layers;
- cluster click zooms to expansion zoom;
- individual click still opens EnvironmentalInspector.

No density/risk inference.

---

# 9. P0 — RETRY + BASE MAP HEALTH ARE CURRENTLY MISLEADING

## 9.1 Base health

Current:
`SurveyorView.vue:1261-1265`

Base geography only degrades on map errors while `!map.isStyleLoaded()`. Tile/source failures after style load can leave a blank/degraded map while badge still says ready.

Change `auditCatMapStyle()` in:
`frontend/src/surveyor/catMapStyle.js:72+`

Return:
```js
{
  status,
  roads,
  water,
  labels,
  natural,
  baseSourceIds: [...]
}
```

`baseSourceIds` = unique source ids used by layers classified as road/water/label.

In map error handler:
- if `event.sourceId` is in `baseSourceIds`, set map health degraded regardless of `isStyleLoaded()`;
- also degrade when error URL clearly references OpenFreeMap.

## 9.2 Retry

Current:
`SurveyorView.vue:1438`
```js
window.location.reload()
```

Keep page reload as the safe base-style recovery for now, but:
- button text = `Reload map`, not generic Retry;
- if an active search exists, await/call current session checkpoint save before reload.

Environment provider retry is separate:
fix `environmentLayers.js:97` so `retry()` actually:
- retries boundaries;
- retries current hydro/wildlife settings;
- does not force coyote/wildlife on.

Factor boundary fetch into `loadBoundaries({ force })`.

---

# 10. P0 — ENVIRONMENT INSPECTOR SELECTION MUST BE EXCLUSIVE

Current:
`SurveyorView.vue:1277, 893-920`

Environmental click clears current object + candidate but not historical camera placement.
Historical camera selection clears object + candidate but not environmental selection.

Fix both directions.

Whenever selecting:
- environment feature → clear `selected`, `selectedCandidate`, `selectedHistoricalPlacement`, object stack;
- current object → clear environmental/historical/candidate as already mostly done;
- historical camera → clear environmental/current/candidate;
- candidate → clear environmental/current/historical.

Only one inspector context at a time.

---

# 11. P0 — "DROP FIELD MARKER" MUST NOT CREATE A CAT SIGHTING

Current:
`SurveyorView.vue:1439-1444`

`createFromEnvironmentalFeature('marker')` calls:
```js
chooseQuickAdd('other', coordinates)
```
and `chooseQuickAdd('other')` maps to subtype `sighting`.

That turns a creek/wildlife context click into a false cat sighting.

Correct behavior:

### Add field marker…
Open the existing QuickAdd menu at the environmental click coordinate.
Do not select a subtype automatically.

### Add note here
Create normal note draft, but prefill:
- name: e.g. `Note near Morgan Creek` / `Note near Coyote observation`;
- notes with compact provenance:
  - provider;
  - feature/species;
  - observation date when applicable;
  - provider URL when available;
  - `Reference context only; not local field evidence.`

If the user then chooses a QuickAdd marker, prefill the same provenance in that draft's notes but keep the user-selected subtype.

Do not add schema fields or persist raw external payloads.

Rename inspector button:
`Drop field marker here` → `Add field marker…`

---

# 12. P1 — BOUNDARY INSPECTION

Current environment click listeners omit county/state layers.

Make county/state lines/labels selectable.

On select normalize properties:
```js
{
  provider: 'U.S. Census TIGERweb',
  feature_type: 'county' | 'state',
  name: ...
}
```

EnvironmentalInspector should render:
- `Orange County` / `North Carolina`;
- type;
- source.

Do not allow external boundary click to imply field evidence.

---

# 13. P0 — ZONE TYPE PICKER IS INCONSISTENT

Current mismatch:

- `SurveyorView.vue:1477` hardcodes several zone types before drawing.
- `DraftObjectSheet.vue:31` only adds `needs_search` as a true zone option; the rest of the select is populated with **pin types**.

A drawn `searched`, `known_cat_highway`, etc. zone can therefore open a draft selector that does not actually contain its selected subtype.

## Centralize zones

Modify:
`frontend/src/surveyor/objectTypes.js`

Add:
```js
export const ZONE_TYPES = {
  searched: { label:'Searched', color:'#667d69' },
  needs_search: { label:'Needs search', color:'#dfad58' },
  needs_recheck: { label:'Needs re-check', color:'#c99746' },
  low_priority: { label:'Low priority', color:'#909b8d' },
  known_cat_highway: { label:'Known cat highway', color:'#58836f' },
  probable_animal_corridor: { label:'Probable animal corridor', color:'#688c78' },
  wildlife_hotspot: { label:'Wildlife hotspot', color:'#9b7f61' },
  likely_shelter: { label:'Likely shelter zone', color:'#7e755c' },
  dog_territory: { label:'Dog territory', color:'#ad6652' },
  high_human_activity: { label:'High human activity', color:'#9a7a56' },
  private_no_access: { label:'Private / no access', color:'#777777' },
  permission_obtained: { label:'Permission obtained', color:'#4f8162' },
  avoid_disturbing: { label:'Avoid disturbing', color:'#8f6b74' }
}
```

Then:

### DraftObjectSheet
- `kind === 'pin'` → current PIN_GROUPS;
- `kind === 'zone'` → only ZONE_TYPES.

### SurveyorView
Replace hardcoded zone subtype options with `v-for` over ZONE_TYPES.

### Map style
Expand zone fill/outline color matches for all ZONE_TYPES.
Do not change stored subtype strings for existing objects.

---

# 14. P1 — ADJACENT CANDIDATE PROVENANCE CLEANUP

These were already conceptually fixed elsewhere but remain inconsistent on latest main.

## 14.1 SearchMap still says "Original"

Current:
`frontend/src/components/SearchMap.vue:128-150, 449-473`

Add to GeoJSON properties:
- `source_link_kind`;
- `listing_url`;
- `detail_url`;
- source platform if available.

Popup link semantics must match CandidateCard:

- 24Pet exact detail → `View on 24PetConnect ↗`;
- 24Pet search/listing fallback → `Open 24PetConnect ↗`;
- other source → `Open source ↗`.

Never label a 24Pet saved search `Original`.

## 14.2 Candidate case hero still exposes internal record id

Current:
`frontend/src/views/CandidateCaseView.vue:157-ish`

Remove:
```text
· source record #123
```
from the prominent current-location line.

The technical source history remains available in the case record/history UI; do not remove provenance data itself.

---

# 15. LAYER DRAWER + STATUS RETRY UX

Keep LayerDrawer compact.

Add one small `Retry` action only when provider state is:
- degraded;
- unavailable.

Emit:
`retry-provider`

SurveyorView calls:
`environmentController.retry(providerKey)`

Do not add settings pages.

Provider-specific retry behavior:
- boundaries → refetch Census;
- hydrography → current viewport;
- wildlife → current viewport/species/time;
- raster landcover/wetlands → no manual retry beyond base `Reload map`; display degraded state only.

---

# 16. FRONTEND LAYER INTERACTION POLISH

In `environmentLayers.js`:
- pointer cursor on hydro, wildlife, county/state selectable layers;
- restore cursor on leave;
- include listeners in destroy cleanup.

Do not let external layer click also trigger map QuickAdd/probe behavior if an environment feature was handled.

Use `event.originalEvent?.stopPropagation?.()` only if required; prefer existing layer click ordering and an explicit handled flag if MapLibre behavior needs it.

---

# 17. TESTS

Expand only:
`backend/tests/test_surveyor_environment.py`

Add/adjust:

1. expanded bbox bucket covers nearby requests;
2. waterbody name prefers WATERBODY;
3. hydro pagination fetches page 2;
4. hydro cap marks truncated;
5. one hydro layer failure still returns 200 degraded result;
6. both hydro layers failing returns 502;
7. wildlife uses `time_observed_at` before `observed_on`;
8. wildlife page 2 fetched when needed;
9. wildlife cap marks truncated;
10. existing geoprivacy/date/cache tests remain.

Mock all network.

No new frontend test framework.
If existing node modules exist, build once.

---

# 18. MANUAL ACCEPTANCE — SHORT

### Environment state
- toggle hydro off, pan: no hydro request/state says off;
- toggle hydro on, pan: hydro follows current setting;
- wildlife on/no species: says choose species, no request;
- zoom below wildlife threshold: says zoom in.

### Layer order
Enable NLCD + wetlands:
- road/place labels stay readable above raster.

### Hydro
- named waterbody shows its waterbody name;
- one mocked/forced layer failure still leaves other hydro type usable.

### Inspectors
- select environmental item then historical camera: only camera inspector remains;
- select camera then environmental item: only environment inspector remains.

### Marker correctness
Click stream → Add field marker… → QuickAdd appears.
It must **not** immediately create a Sighting.
Saved note/marker includes source context.

### Zones
Draw each zone category; draft dropdown retains selected category.

### Candidate provenance
24Pet map popup never says Original for saved search.
Candidate-case main location line has no internal source record number.

### Mobile
One portrait pass: Layers + environment inspector + QuickAdd usable without overlap.

---

# 19. IMPLEMENTATION ORDER

1. single Overlays control + truthful off/zoom/species statuses;
2. load search config + home/nearby initial viewport;
3. surface Tonight readiness bar using existing outing plan;
4. Marker type-first picker + placement cue + stale-subtype fix;
5. Candidates/Surveyor one-line workflow orientation;
6. stale-setting closure + network refresh discipline;
7. environment layer order;
8. bbox bucket correctness;
9. hydro naming/pagination/partial failure;
10. wildlife pagination/clustering;
11. base health + retry;
12. inspector exclusivity + safe environmental marker action;
13. boundary inspection;
14. centralized zone types + picker fix;
15. candidate provenance cleanup;
16. pointer/mobile polish;
17. focused backend tests;
18. one frontend build if dependencies already exist;
19. manual acceptance;
20. commit/push `main`;
21. deploy per `AGENTS.md` only if real DietPi access exists.

---

# 20. DEFER

Do not add:
- predator-risk scores;
- automatic Archie-route inference;
- wildlife heat/risk claims;
- Movebank;
- route optimization;
- automatic camera placement;
- DB persistence of iNaturalist observations;
- generic provider framework;
- new dependencies.

The disabled `Measure · coming soon` control is not part of 8B.

---

# 21. DONE WHEN

- Surveyor opens framed around home + nearby local field markers;
- HOME is visually identifiable without dominating the map;
- only one user-facing Overlays control exists;
- wetlands/wildlife show Off/Choose species/Zoom in instead of false Unavailable states;
- Tonight readiness is visible before starting a search and opens the existing editable Prep/Packing/Gameplan plan;
- dependency blockers remain visible and editable in the plan;
- Candidates and Surveyor expose a compact obvious workflow;
- Marker placement is type-first and never inherits a stale selected-object subtype;
- selected marker type is visibly indicated while choosing the map location;
- pan/zoom always respects current environment toggles;
- non-environment toggles do not refetch providers;
- off/zoom/select-species/degraded states are truthful;
- raster overlays do not obscure base labels;
- cache bbox cannot omit viewport edges;
- hydro names/pagination/partial failure are correct;
- wildlife no longer silently caps at 200 and is clustered;
- base tile errors can degrade health after style load;
- environment selection is mutually exclusive with other inspectors;
- environmental "Add marker" never fabricates a cat sighting;
- zone picker contains all zone types and keeps selection;
- 24Pet map links are truthful;
- candidate case location hides internal source-record id;
- focused tests pass;
- changes land on `main`.

---

# 22. END REPORT

```text
SLICE 8B
Base SHA:
Final SHA:

Environment settings/state: pass/fail
Layer order: pass/fail
Hydro cache/pagination/partial failure: pass/fail
Wildlife pagination/clustering: pass/fail
Map health/retry: pass/fail
Inspector/marker correctness: pass/fail
Zone types: pass/fail
Candidate provenance cleanup: pass/fail
Mobile: pass/fail

Focused tests:
Frontend build: pass/skipped
DietPi deployment:
Known limitations:
```
