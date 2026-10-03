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
frontend/src/components/FacebookGroupsPanel.vue        Facebook sync observability
backend/app/connectors/regional_24petconnect.py       inactive-link correctness
backend/tests/test_regional_24petconnect.py            focused 24Pet regression
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

# 1I. P0 — CLOSE-RANGE FIELD DETAIL FOR THE 1–2 MILE WORK AREA

Surveyor is primarily a neighborhood field map, not a county overview.

The normal icon/camera workload is expected to live within roughly **1–2 miles of home**. At that scale the user must be able to place a camera relative to the correct house, driveway, path, tree-line edge, fence/barrier, creek crossing, and neighboring structure.

Current problems:

```text
frontend/src/views/SurveyorView.vue:1255-1258
  hardcoded zoom 12

existing home-fit instruction in §1A
  maxZoom 13.5 / fallback ~13.2 is still too regional

frontend/src/surveyor/catMapStyle.js:18-20
  hides address / housenumber symbols

catMapStyle.js
  building footprints are faint and have no deliberate close-range outline

environment rasters
  remain visually strong when close structural detail matters more
```

Do not add a separate "detail overlay" the user must remember to turn on.
Make close-range detail emerge automatically with zoom.

## A. Initial home/work-area zoom

Update §1A implementation values:

Home + nearby objects:
- use nearest up to 8 local Surveyor objects within **2 miles**, not 3;
- fit bounds with `maxZoom: 15.5`;
- if resulting bounds are tiny, do not zoom beyond 15.5 on initial page load;
- if no nearby objects, home fallback zoom **14.8**;
- explicit object/location focus may zoom closer.

Goal:
first page load should normally show a useful neighborhood/walkable work area, not half the county.

Add compact map actions:

```text
Home
1 mi
2 mi
```

Place next to the single Overlays control, not in another toolbar.

Behavior:
- Home → center home at zoom ~16;
- 1 mi → fit a 1-mile radius around home;
- 2 mi → fit a 2-mile radius around home.

Use the loaded `searchConfig.home_latitude/home_longitude`.
Do not add backend calls.

These are deliberate user actions; unlike initial-fit logic, they may reset the viewport.

## B. Zoom ceiling / navigation

Map initialization in `SurveyorView.vue`:

```js
new maplibregl.Map({
  ...
  maxZoom: 20,
  renderWorldCopies: false
})
```

Do not cap normal manual zoom at 15.x. Camera placement needs zoom 17–20.

Keep north-up behavior simple:
- `dragRotate: false`;
- `pitchWithRotate: false`;
- `map.touchZoomRotate.disableRotation()`.

Do not add 3D/pitch in this slice.

## C. Scale bar

At `SurveyorView.vue:1272` beside current NavigationControl add:

```js
map.addControl(new maplibregl.ScaleControl({
  maxWidth: 120,
  unit: 'imperial'
}), 'bottom-left')
```

The scale bar must remain readable on mobile and must not sit under the mobile field bar/timeline.

Use CSS positioning only if necessary.

## D. BUILDINGS / HOMES / ADDRESSES ARE CORE GEOGRAPHY

Current `catMapStyle.js` hides:
```js
/poi|shop|restaurant|transit|station|address|housenumber|amenity|building/
```

Change symbol handling.

Still hide:
```text
poi
shop
restaurant
transit
station
amenity
```

Do **not** hide:
```text
address
housenumber
```

Building-name symbols may remain hidden unless they carry actual address/house-number information.

### House numbers / addresses

For symbol layers matching:
```text
housenumber|house_number|address
```

- set visible;
- `map.setLayerZoomRange(layer.id, 16, 24)` when supported;
- text size ~10–11;
- text color #6b6256;
- halo #faf7ef, width ~1.3;
- opacity ~0.82;
- allow normal collision detection; do not force every house number to overlap.

If the underlying OpenFreeMap/OSM data does not contain a house number, do not invent one.

### Building footprints

For fill layers matching `building|structure`:

```js
fill-color: '#d8d0c1'
fill-opacity: ['interpolate',['linear'],['zoom'],14,0.30,16,0.58,18,0.72]
fill-outline-color: '#a99f90'
```

If `fill-outline-color` is unsupported on a layer, skip just that property.

For building line/outline layers:
- line color #a99f90;
- line width 0.6 at z15 → 1.2 at z19;
- opacity 0.75.

Buildings should be clearly visible at z15+ without visually overpowering Surveyor markers.

## E. DRIVEWAYS / SERVICE ROADS / WALKABLE PATHS

In `catMapStyle.js`, add high-zoom transport classes before the generic road branch.

### Service / driveway
Match:
```text
service|driveway|parking_aisle|parking-aisle
```

Style:
- color #c7bca9;
- line width z14 0.7 → z18 2.2;
- opacity 0.82;
- if semantic layer separation exists, minzoom ~14.

### Footpath / trail
Match:
```text
footway|path|trail|track|pedestrian|steps
```

Style:
- color #8d826d;
- width z14 0.7 → z18 1.8;
- opacity 0.8;
- dashed when the source/style permits.

Do not classify a motorway/primary/secondary as trail because a layer id also contains generic `transport`.

Order matching from most specific to most general.

## F. FENCES / WALLS / BARRIERS / HEDGES

Where OpenFreeMap exposes semantic line layers matching:
```text
fence|wall|barrier|hedge
```

Show them only at close zoom:
- zoom range ~16+;
- color #7f8278;
- width 0.6 → 1.1;
- opacity ~0.7;
- hedge may use muted green #78896f.

These are useful cat/field boundaries.

Do not add a new external fence provider.

## G. SMALL WATER + DRAINAGE DETAIL

Current water styling is acceptable regionally but close-range needs small channels.

At z15+ retain:
- stream;
- ditch;
- drain;
- canal;
- intermittent water lines if present in source.

Line width:
- z14 ~1.2;
- z17 ~2.2;
- z19 ~3.

NC OneMap hydrography remains authoritative when available and already participates in snapping.

Do not hide generic base water when NC OneMap is unavailable.

## H. ENVIRONMENT OVERLAYS MUST FADE AT FIELD ZOOM

In `frontend/src/surveyor/environmentLayers.js`:

Annual NLCD opacity should be zoom-dependent:

```js
'raster-opacity': [
  'interpolate', ['linear'], ['zoom'],
  9, 0.22,
  13, 0.20,
  15, 0.12,
  17, 0.04,
  18, 0.0
]
```

NWI wetlands:

```js
'raster-opacity': [
  'interpolate', ['linear'], ['zoom'],
  10, 0.26,
  14, 0.20,
  16, 0.10,
  18, 0.04
]
```

County labels/lines:
- fade strongly after z13;
- hide by z15 if easiest with `maxzoom`.

State lines:
- hide by z13.

At field zoom, the map priority is:
```text
buildings + house numbers + driveways + paths + water
→ Surveyor objects/cameras
→ environmental texture
→ administrative geography
```

## I. FIELD-DETAIL ZOOM STATE

Add one compact computed/readout, not another settings panel:

```text
Neighborhood
Field detail
Close detail
```

Suggested:
- <14 = Neighborhood
- 14–16 = Field detail
- >16 = Close detail

It may live adjacent to the scale bar or Home/1mi/2mi controls.

Do not expose raw `Zoom 17.34` as the main label.

## J. CAMERA PLACEMENT / EDITING SHOULD ENTER PRECISION SCALE

When placing a **new** camera:
- after map tap, open camera draft as now;
- keep map at current location;
- if zoom <17, ease to ~17 around the clicked location before/while draft opens.

When selecting/editing an existing current trail camera:
- if user chooses Move/Edit placement and zoom <17, ease to at least 17;
- camera center/heading/range handles remain visible.

When a camera is selected at z17+:
- center handle remains ~14 px touch target;
- heading/range handles minimum ~12 px;
- cone outline increases from current 1.5 px to ~2 px for current placement;
- current camera point gets a stronger contrasting halo/stroke;
- historical placement remains faded/dashed and must not visually compete.

Do not enlarge stored camera range or geometry. This is display/edit ergonomics only.

## K. PRECISE OBJECT PLACEMENT FEEDBACK

For active Marker / Camera / Note / Access placement:
- desktop cursor = crosshair;
- retain the type-first marker badge from §1E;
- after click, show a brief ~350 ms pulse/ring at exact selected coordinate before opening the sheet if straightforward;
- never move the selected coordinate to a nearby label/address automatically.

For drawing/snap:
- current snap indicator remains;
- at zoom >=16, reduce snap threshold from 12 px to ~9 px for more precise choice among close roads/objects;
- cameras/objects still use touch-friendly hit targets separately from snap threshold.

Implement threshold as:
```js
const threshold = map.getZoom() >= 16 ? 9 : 12
```
inside `createMapFeatureSnapper`, rather than adding a user setting.

## L. STRUCTURE DETAIL HEALTH

Extend `auditCatMapStyle(map)` with optional signals:

```js
buildings: boolean
addresses: boolean
paths: boolean
```

These do **not** determine overall `ready` status because source coverage varies.

At zoom >=16, if no building semantic layer exists, do not display a scary map failure.
Optional dev/diagnostic text in Overlays may say:
```text
Structure detail: limited by map data
```

Do not blame the user or imply the provider failed.

## M. DO NOT ADD THIS SLICE

Do not add:
- parcel/property boundary provider;
- satellite imagery provider;
- 3D buildings;
- LiDAR;
- automatic tree detection;
- new geocoding provider.

Those may be useful later, but building/address/service-road detail from the existing vector source should be fixed first.

## N. MANUAL ACCEPTANCE FOR FIELD DETAIL

At home area:

1. 2-mile view:
   - home + nearby Surveyor objects visible;
   - roads/woodland/water readable.

2. zoom 15–16:
   - individual building footprints visible;
   - local/service roads distinguishable;
   - paths/trails visible where source data exists.

3. zoom 17–19:
   - house numbers visible where source data contains them;
   - buildings have clear outlines;
   - driveways/paths usable as placement references;
   - NLCD no longer smears over structures;
   - county/state boundaries no longer distract.

4. Camera:
   - select a camera;
   - edit/move enters useful close scale;
   - cone + handles easy to see;
   - scale bar makes tens/hundreds of feet obvious.

5. Mobile:
   - pinch to z18+;
   - place camera/marker relative to a building;
   - scale bar and controls do not overlap bottom field controls.

---

# 1G. P0 — FACEBOOK SYNC MUST EXPLAIN WHAT HAPPENED

Current:
```text
frontend/src/components/FacebookGroupsPanel.vue:1-174
frontend/src/views/CandidatesView.vue:635
frontend/src/style.css:96-122
```

The backend already exposes enough telemetry. Do not add DB fields or migrations.

Available run fields:
```text
status
requested_group_count
successful_group_count
posts_seen
posts_new
posts_updated
posts_filtered
exact_duplicates
crossposts_combined
started_at
completed_at
error_summary
groups[]
```

Available group receipt fields:
```text
status
scanned
cat_related
posts_new
already_known
crossposts_combined
parser_warning
error
group.last_success_at
```

The UI currently surfaces only:
`scanned · new · cross-posts`

That makes "1 new" impossible to interpret.

## FacebookGroupsPanel.vue

Add computed totals from `latestRun.groups`:
```js
catRelated = sum(receipt.cat_related)
alreadyKnown = sum(receipt.already_known)
failedGroups = count(status === 'failed')
warningGroups = count(status === 'parser_warning')
finishedGroups = count(status in ['success','failed','parser_warning','disabled'])
```

Do not add backend aggregation for values already present in group receipts.

### Prominent run state

Replace the plain:
`Last sync · complete`

with a visually distinct state banner:

```text
✓ Facebook sync complete
4 / 4 groups completed
```

Statuses:
- queued → neutral/blue `Queued`
- syncing → active/blue `Syncing · 2/4 groups finished`
- complete → green `Sync complete`
- partial → amber `Partial sync`
- failed → red `Sync failed`

Use text + icon/symbol + color. Never color alone.

### Main receipt metrics

Always show a compact responsive metric row for a completed/partial/failed run:

```text
86 scanned
13 cat-related
1 new
12 already in Radar
73 filtered
2 cross-posts merged
```

Only render metrics that are available/nonzero except:
- scanned;
- new;
- successful groups.

`already in Radar` = sum of group `already_known`.

Do not present these values as an arithmetic partition unless the backend guarantees that relationship. They are diagnostics.

### Interpret "only 1 new"

Add one concise human sentence based on run state:

Complete, all groups successful, low new count:
```text
Collector completed normally. 1 unique candidate was new; 12 cat-related reports were already in Radar.
```

Complete and no cat-related:
```text
Collector completed normally. It scanned 86 rendered posts but found no cat-related candidates.
```

Partial:
```text
Only 3 of 4 groups completed. Open group receipts to see which group needs attention.
```

Failed:
```text
The Facebook scan did not complete successfully. Open group receipts for the failure.
```

Do not guess why a post was filtered beyond the existing parser/error information.

### Group receipts

Keep receipts collapsible, but:
- default them open for `partial` or `failed`;
- each row gets visible ✓ / ! / × state;
- render:
  ```text
  Group name
  ✓ Success
  28 scanned · 7 cat-related · 1 new · 6 already known · 1 cross-post merged
  ```
- warning/error text remains directly below;
- while syncing, show each group's live `queued / syncing / success / failed` state.

### Sync timing

Show:
- completed relative time;
- duration when both timestamps exist.

Do not show raw seconds if duration > 90s; format compactly.

## Candidate feed must refresh automatically

Current panel polling learns when a sync completes, but `CandidatesView` does not automatically reload the candidate feed.

Add emit:
```text
sync-finished
```

In `FacebookGroupsPanel.vue`:
- establish the current run id/status as baseline on first refresh;
- emit only when a **newly observed run** reaches `complete|partial|failed`, or a run transitions from `queued|syncing` to terminal;
- do not emit for the historical last sync merely because the component mounted.

In `CandidatesView.vue`:
```vue
<FacebookGroupsPanel ... @sync-finished="handleFacebookSyncFinished" />
```

Handler:
```js
async function handleFacebookSyncFinished(run) {
  await Promise.all([load(), loadQueueStats(), loadFilterOptions()])
  facebookSyncNotice.value = run
}
```

Render a compact dismissible notice near the main review controls so completion remains visible even if Sources is collapsed:

Examples:
```text
✓ Facebook sync complete · 1 new · 4/4 groups
! Facebook sync partial · 1 new · 3/4 groups
× Facebook sync failed
```

Auto-dismiss after ~12 seconds or allow manual dismiss.
Do not use browser notifications.

### Important diagnostic outcome

After this change, seeing `1 new` must immediately answer:
- how many groups actually completed;
- how many posts were scanned;
- how many were cat-related;
- how many were already known;
- whether parser/auth/group errors occurred.

This is the primary acceptance criterion.

---

# 1H. P0 — 24PETCONNECT: KEEP THE PHOTO, NEVER LINK A DEAD LISTING

Current concrete issues:

```text
backend/app/connectors/regional_24petconnect.py
  active(row) detail check

frontend/src/components/CandidateCard.vue
  sourceLink falls back to listing_url even when source_link_kind === 'unavailable'

frontend/src/components/CandidateCard.vue
  source-history anchors render whenever record.source_url exists

frontend/src/components/SearchMap.vue
  source popup semantics are already in this packet; unavailable must also suppress links
```

The photo and source link are independent.

**A useful 24PetConnect image may remain displayed after the source listing becomes inactive.**
Do not remove the image merely because the listing link is dead.

## Connector: explicit inactive animal

In `Regional24PetConnectConnector.fetch() -> active(row)`:

Current flow parses:
```python
state, reason = self.parse_animal_lifecycle(text, row.source_id or "")
```

When `state == "inactive"`, return the row with:

```python
raw = {
    **row.raw,
    "listing_state": "inactive",
    "listing_state_reason": reason,
    "listing_state_checked_at": checked_at,
    "source_link_kind": "unavailable",
    "detail_url": None,
}
return row.model_copy(update={
    "source_url": row.raw.get("listing_url") or row.source_url,
    "raw": raw,
})
```

Keep:
- `image_url`;
- animal id;
- description/location/history.

Do not delete an inactive source record. Candidate case history and its useful image remain valuable.

If a detail link 404s/redirects/mismatches but the animal is still present on the saved result page:
- keep existing active-as-seen lifecycle behavior;
- mark `source_link_kind="unavailable"`;
- never advertise the broken exact URL.

## CandidateCard: unavailable means NO anchor

Change 24Pet sourceLink logic:

```js
if (post.source_link_kind === 'unavailable') return null
```

Then:
- no clickable source button when unavailable;
- show a small non-link status:
  - `24PetConnect listing inactive` when case/source lifecycle says inactive;
  - otherwise `24PetConnect link unavailable`;
- keep `Copy Animal ID`.

In source history:
- only render anchor when `record.source_link_kind !== 'unavailable'`;
- unavailable row instead renders:
  `Listing inactive` or `Link unavailable`;
- if that row supplies the displayed image, keep:
  `Current photo`.

This makes the state understandable:
```text
Current photo · Listing inactive
```
is valid.

## SearchMap

When `source_link_kind === 'unavailable'`:
- render no source anchor;
- show `24PetConnect listing inactive` / `link unavailable` text;
- Animal ID remains visible where available.

Never fall back to a saved ViewAnimals URL merely to keep a button on screen when the normalized source-link state is unavailable.

## Candidate source selection

Do not change `choose_primary_case_image()`: inactive records may still supply the best image.

Do not promote inactive records for:
- current custody;
- current location;
- current record.

Existing lifecycle selection already excludes inactive records from current location/custody/current-record preference. Preserve that behavior.

## Regression tests

Expand:
`backend/tests/test_regional_24petconnect.py`

Add:

1. explicit adopted/reunited/inactive detail:
   - row retained;
   - image retained;
   - `listing_state == inactive`;
   - `source_link_kind == unavailable`;
   - `detail_url is None`.

2. broken exact detail URL with current search-result row:
   - row retained;
   - image retained when listing supplied one;
   - source link unavailable.

No new schema/migration.

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

1. Facebook sync observability + automatic candidate-feed refresh;
2. 24Pet inactive/dead-link suppression while retaining photos;
3. single Overlays control + truthful off/zoom/species statuses;
4. load search config + home/nearby initial viewport;
5. close-range field detail: buildings/addresses/driveways/paths/scale/camera precision;
6. surface Tonight readiness bar using existing outing plan;
7. Marker type-first picker + placement cue + stale-subtype fix;
8. Candidates/Surveyor one-line workflow orientation;
9. stale-setting closure + network refresh discipline;
10. environment layer order;
11. bbox bucket correctness;
12. hydro naming/pagination/partial failure;
13. wildlife pagination/clustering;
14. base health + retry;
15. inspector exclusivity + safe environmental marker action;
16. boundary inspection;
17. centralized zone types + picker fix;
18. candidate provenance cleanup;
19. pointer/mobile polish;
20. focused backend tests;
21. one frontend build if dependencies already exist;
22. manual acceptance;
23. commit/push `main`;
24. deploy per `AGENTS.md` only if real DietPi access exists.

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

- Facebook sync clearly shows success/partial/failure, group completion, scanned/cat-related/new/already-known counts, and per-group receipts;
- candidate review feed automatically refreshes when a newly observed Facebook sync finishes;
- "1 new" is diagnostically understandable without inspecting logs;
- inactive/unavailable 24PetConnect records may retain photos but never render dead source links;
- 24Pet source history explicitly distinguishes "Current photo" from "Listing inactive/link unavailable";
- Surveyor opens framed around home + nearby local field markers;
- close-range zoom exposes building footprints, house numbers where mapped, service roads/driveways, paths/trails, barriers where mapped, and small waterways;
- normal manual zoom supports camera-scale editing to z20;
- imperial scale bar is visible and unobtrusive;
- Home / 1 mi / 2 mi map controls make the walkable search area easy to recover;
- NLCD/wetland/admin context fades out as exact structure detail becomes more important;
- camera move/edit enters a practical close zoom and current cone/handles are easy to manipulate;
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
