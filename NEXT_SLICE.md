# NEXT SLICE TASK PACKET

## Archie Radar v1 · Slice 8
### Surveyor Geographic Context + Environmental Intelligence

**Base:** `main` at `edc09f868e80dee0ee8599781653702e43c17875`

This is the next Surveyor feature slice after the Slice 7B hardening work already landed on `main`.

The Surveyor architecture is already substantially aligned with the product direction: full-page map, TerraDraw geometry, object types, search sessions, trail cameras with placement history, sight cones, snap support, corkboard-style links, access records, evidence/media, timeline, journal, outing planning, and candidate integration are present. Preserve those systems.

The primary current failure is that the **Surveyor page does not present useful geographic context**. The map may render as an empty/featureless canvas even though the user needs to read woodland, developed areas, roads, waterways, county/state context, and environmental/wildlife observations before adding any custom search objects.

Do not rebuild Surveyor. Make the existing Surveyor map a dependable field GIS with a cat-oriented visual hierarchy.

---

# 0. REPOSITORY / BRANCH PRECHECK

Repository instructions in `AGENTS.md` are authoritative:

- work from latest `main`;
- commit and push every completed repository change to `main`;
- deploy to DietPi only when the current environment genuinely has SSH/Tailscale access;
- do not destroy persistent volumes or secrets.

Important repository state observed when this packet was written:

- GitHub repository default branch is currently `feature/surveyor-v1`;
- that branch is an ancestor of `main`, with no commits ahead and roughly 49 commits behind;
- `AGENTS.md` correctly states that production work/deployment uses `main`.

**Do not implement this packet on `feature/surveyor-v1`.**

If the execution environment has permission to change repository settings, set the GitHub default branch to `main`. If not, report that as a repository-admin follow-up, not an implementation blocker.

---

# 1. PRODUCT LOCK

Surveyor is the field-work surface.

Navigation remains:

```text
Candidates | Surveyor | Journal
```

Responsibilities:

- **Candidates**: Could this report be Archie?
- **Surveyor**: What does this landscape look like, what do we know about it, and where should we search next?
- **Journal**: What did we actually do and observe?

The default Surveyor map should answer a missing-cat field question before the user creates any custom object.

It should read more like:

```text
woodland edge
creek / drainage
residential pocket
major road barrier
wetland / low ground
search coverage
camera coverage
wildlife observations
```

and less like a generic consumer street map.

Do not add restaurant/shop/POI clutter.

---

# 2. CURRENT IMPLEMENTATION TO PRESERVE

Review current code before editing.

Core files already in place:

```text
frontend/src/views/SurveyorView.vue
frontend/src/surveyor/catMapStyle.js
frontend/src/surveyor/snapEngine.js
frontend/src/surveyor/objectTypes.js
frontend/src/components/surveyor/LayerDrawer.vue
frontend/src/components/surveyor/SurveyTimeline.vue
frontend/src/components/surveyor/SurveyorToolbar.vue
frontend/src/components/surveyor/DraftObjectSheet.vue
frontend/src/components/surveyor/ObjectInspector.vue
frontend/src/components/surveyor/SearchSessionBar.vue
frontend/src/views/JournalView.vue
backend/app/models.py
backend/app/main.py
backend/app/surveyor/*
```

Already implemented and **not to be rebuilt**:

- MapLibre Surveyor map;
- TerraDraw select/polygon/line modes;
- optional snapping to roads, trails, waterways, pins, zone boundaries, cameras;
- trail-camera current placements;
- camera heading / FOV / range;
- camera cones;
- camera placement history;
- object links / corkboard connections;
- searched / needs-search / wildlife / access-style custom objects;
- search sessions;
- evidence/media capture;
- property/access records;
- timeline;
- Surveyor events/journal;
- undo/redo;
- candidate report layer;
- field toolbar;
- mobile field controls;
- outing/preflight system.

This slice should close the environmental/geographic gap and integrate it with these existing tools.

---

# 3. P0: THE MAP MUST SHOW GEOGRAPHY ON FIRST LOAD

Current Surveyor initialization uses OpenFreeMap Positron and calls `applyCatMapStyle(map)`, but the live Surveyor is currently being observed as having little or no useful geographic detail.

Fix that first.

## Required default visible geography

Without opening Layers, the map must show:

- roads with a clear road-class hierarchy;
- place / road labels at sensible zooms;
- streams and rivers;
- ponds / lakes;
- woodland / forest context;
- developed / residential context;
- county boundaries, subtle;
- state boundary, slightly stronger;
- home/reference context when applicable.

The user must not need to enable Annual NLCD just to see usable geography.

## Base-style health

Do not silently show an empty canvas when the base style or tile source fails.

Add a lightweight Surveyor map-health state:

```text
loading
ready
degraded
failed
```

At minimum detect:

- MapLibre style loaded;
- expected road layer family exists;
- expected water layer family exists;
- expected place/label family exists.

If the OpenFreeMap style loads but expected semantic layers cannot be found, show:

`Base geography degraded · Retry`

If the style request fails, show:

`Base geography unavailable · Retry`

The user-created Surveyor objects must remain usable even if an external environmental layer fails.

Do not block the whole Surveyor workspace waiting for county/wetland/wildlife providers.

---

# 4. REPLACE REGEX-ONLY BASEMAP STYLING WITH A HARDENED CAT-VIEW STYLE PASS

Current `catMapStyle.js` is a useful first pass but relies heavily on regular expressions over whatever layers happen to exist in the third-party style.

Keep compatibility with OpenFreeMap, but harden the contract.

Prefer:

```text
frontend/src/surveyor/catMapStyle.js
frontend/src/surveyor/environmentLayers.js
frontend/src/surveyor/mapHealth.js
```

or an equivalent small separation.

## Visual hierarchy

### Woodland / forest
- strongest non-user land context;
- muted natural green;
- enough contrast to identify connected cover and edges;
- do not make forest so opaque that user zones disappear.

### Developed / residential
- warm neutral;
- visually distinct from forest/open land;
- buildings may appear only at close zoom.

### Open grass / field
- subdued warm-green/straw tone.

### Water
- visually stronger than the generic basemap;
- distinguish line water from polygon water where possible;
- streams/creeks must remain readable beneath custom objects.

### Roads
Use distinct line weights/tones for:
- motorway / highway;
- primary;
- secondary;
- local/residential;
- path/trail where base source exposes it.

Large roads should read as possible barriers.
Residential roads should be quieter.

### Labels
Keep:
- places;
- road names;
- water names;
- county labels at appropriate zoom.

Suppress:
- shops;
- restaurants;
- transit stops;
- POIs;
- address numbers;
- commercial labels that do not assist field search.

---

# 5. DEFAULT NATURAL CONTEXT

Current `defaultLayers` has `landcover: false`.

Change the default experience so a first-time Surveyor user gets environmental context automatically.

Recommended default:

```js
{
  objects: true,
  links: true,
  cameras: true,
  cameraHistory: false,
  candidates: true,
  landcover: true,
  hydrography: true,
  wetlands: false,
  boundaries: true,
  wildlife: false
}
```

Existing users with saved layer preferences should retain explicit choices where possible.

Do not let a legacy localStorage object permanently omit newly introduced defaults. Merge stored values onto defaults.

---

# 6. ANNUAL NLCD LAND COVER

The current Surveyor already contains a raster Annual NLCD WMS source.

Harden it rather than replacing it blindly.

Authoritative source:
- USGS / MRLC Annual NLCD;
- MRLC publishes OGC WMS map services.

Requirements:

- do not hardcode a year without a graceful fallback;
- prefer a configurable/default documented year;
- if the configured year fails, degrade without hiding the base geography;
- expose source/year in the Layer drawer;
- opacity approximately 0.18–0.32, tuned so roads/water and Surveyor geometry remain legible;
- keep land-cover provenance visible;
- do not call NLCD a real-time habitat observation.

If practical, add a compact legend mapping the displayed broad classes to:

```text
woodland
open/grass
developed
wetland
water
```

Do not reproduce the full NLCD legend unless the user opens environmental details.

---

# 7. NC HYDROGRAPHY

Add a first-class hydrography provider.

Preferred source for North Carolina:
**NC OneMap Major Hydrography**.

At minimum use:
- streams/rivers;
- waterbodies.

Do not fetch statewide GeoJSON into the browser.

Implement bbox-scoped requests using the current map bounds through a backend provider/proxy.

Suggested backend surface:

```text
GET /api/surveyor/environment/hydrography
  ?west=
  &south=
  &east=
  &north=
```

Return normalized GeoJSON.

Server responsibilities:

- query only current/padded viewport;
- request output coordinates in WGS84 / EPSG:4326 when supported;
- cache by rounded bbox + provider;
- short timeout;
- bounded result count;
- return source/provenance metadata;
- never block Surveyor startup on provider failure.

Frontend:

- line layer for streams/rivers;
- fill layer for waterbodies;
- labels when names are available and zoom is appropriate;
- minimum zoom/line simplification as needed for performance.

The snap engine must treat this hydrography layer as `waterway` so line/polygon drawing can snap to it.

---

# 8. WETLANDS

Add an optional wetlands environmental layer.

Preferred authoritative source:
**U.S. Fish & Wildlife Service National Wetlands Inventory (NWI)**.

NWI exposes REST and WMS services and is updated independently of Archie Radar.

For Slice 8, use either:

1. a low-opacity WMS raster layer for broad field context, or
2. bbox-scoped normalized GeoJSON if the chosen REST layer is performant enough locally.

Default: **off**.

Reasons:
- valuable in field analysis;
- can become visually noisy;
- not required to render core geography.

Layer label:

`Wetlands · USFWS NWI`

Never label NWI as current water depth or guaranteed passability.

---

# 9. COUNTY + STATE CONTEXT

Add non-blocking boundaries directly to Surveyor.

Use current U.S. Census TIGERweb state/county services.

Visual treatment:

- county line: thin, low-opacity, dashed;
- state line: slightly stronger;
- county labels: subtle and zoom-gated;
- no full political-map styling.

Boundaries load asynchronously.

Timeout/failure must result in a quiet disabled/degraded indicator, not an endless `Loading boundaries…` state.

Cache returned GeoJSON.

Only fetch the region needed around the current search area, not the whole country.

---

# 10. WILDLIFE OBSERVATIONS

Add the first real external wildlife provider.

Preferred provider:
**iNaturalist public observations API**.

This is an observation layer, not an inferred predator-risk engine.

Initial species set:

```text
coyote
red fox
gray fox
bobcat
raccoon
white-tailed deer
```

Store species configuration separately from rendering.

Recommended file:

`backend/app/surveyor/environment.py`

or:

`backend/app/surveyor/environment/providers/inaturalist.py`

Do not put a large new provider implementation back into `main.py`.

## Query behavior

Use viewport/bbox plus the Surveyor timeline.

Default wildlife observation mode:
- mappable public observations;
- research-grade where practical;
- observed date, not API ingestion date, drives the map timeline;
- bounded result count and pagination;
- cache results by bbox/species/time window;
- do not make one iNaturalist request per point or pan event.

Debounce viewport requests.

## Geoprivacy

Respect iNaturalist geoprivacy exactly.

- open observations may use exposed coordinates;
- obscured observations remain obscured;
- private coordinates are never reconstructed or inferred;
- never imply an obscured observation is exact.

## Provenance

Every external observation must carry:

```text
provider
provider_record_id
taxon/common name
observed_at
date_added when available
quality grade
coordinate accuracy when available
geoprivacy
provider URL
```

Inspector copy should distinguish:

`Observed Sep 18 · added Sep 20`

rather than collapsing both timestamps.

---

# 11. WILDLIFE MAP PRESENTATION

External wildlife observations must look different from user-created wildlife evidence.

User object:
`Coyote sighting · firsthand`

External observation:
`iNaturalist · Coyote observation`

Do not merge them into the same marker type.

Default wildlife layer is off.

When enabled:

- use small species-colored dots/icons;
- age can fade marker opacity;
- tapping opens environmental inspector;
- provenance link is visible;
- accuracy/geoprivacy is visible.

Optional density mode:

`Observation concentration`

may render a heat/density surface only when enough observations exist.

Label it explicitly as:

`Public observation concentration`

Never call a computed heat surface:
- predator territory;
- risk zone;
- known coyote route;
- wildlife hotspot.

`Wildlife hotspot` remains a user-authored Surveyor zone type.

---

# 12. ENVIRONMENTAL INSPECTOR

Add one compact inspector for external geography/environment features.

Examples:

### Stream
```text
Morgan Creek
NC OneMap hydrography
Stream / river
```

### Wetland
```text
Freshwater forested/shrub wetland
USFWS NWI
Mapped habitat feature
```

### Wildlife observation
```text
Coyote
Observed Sep 18, 2026
iNaturalist
Research grade
Location accuracy: 24 m
```

Actions:

- Add note here;
- Drop field marker here;
- create user wildlife observation from current location only when explicitly chosen;
- copy/open provider source where available.

Do not silently convert external data into user evidence.

---

# 13. LAYER DRAWER REBUILD

Current `LayerDrawer.vue` has a placeholder Wildlife section.

Replace it with real capability-driven sections.

Recommended structure:

```text
MY SEARCH
✓ Markers / notes / zones / lines
✓ Object connections
✓ Trail cameras + cones
  Previous camera placements
✓ Candidate reports

ENVIRONMENT
✓ Cat-view base geography
✓ Annual NLCD land cover
✓ Streams / waterbodies
  Wetlands
✓ County / state boundaries

WILDLIFE DATA
  Coyotes
  Red fox
  Gray fox
  Bobcats
  Raccoons
  Deer
  [time window follows Surveyor timeline]
```

Show provider health:

```text
NC OneMap        ready
NWI              off
iNaturalist      ready
Census           degraded
```

Do not create dead toggles for providers that have no backend implementation.

---

# 14. MAP LEGEND

Add a compact legend that can collapse.

It should explain only currently visible map semantics.

Examples:

- woodland;
- developed;
- water;
- wetland;
- county boundary;
- current camera;
- historical camera;
- searched;
- needs search;
- cat corridor;
- external wildlife observation.

Do not make the legend a permanent giant panel.

---

# 15. CAT-VIEWED SEARCH ZONES

Preserve current user zone support and ensure the following are selectable/styled:

## Search coverage
- searched;
- needs search;
- needs re-check;
- low priority.

## Search interpretation
- known cat highway;
- probable animal corridor;
- wildlife hotspot;
- likely shelter zone;
- dog territory;
- high human activity;
- private / no access;
- permission obtained;
- avoid disturbing.

Where current values exist under slightly different names, migrate/alias rather than destroying existing objects.

Use patterned/hatch/outline treatments. Avoid opaque blocks.

Suggested semantics:

```text
searched            quiet diagonal hatch
needs search        amber dotted hatch
needs re-check      stronger dotted outline
cat highway         narrow directional corridor
wildlife hotspot    stipple
dog territory       red-orange boundary
private/no access   neutral crosshatch
```

---

# 16. SEARCH COVERAGE FRESHNESS

The repository already tracks Surveyor object dates/search sessions.

Make searched coverage age visually.

Suggested states:

```text
fresh      <= 3 days
recent     <= 14 days
stale      <= 45 days
old        > 45 days
```

Do not erase old searched zones.

Fade/hatch them progressively.

Inspector should expose:

`Last searched 18 days ago · now stale`

If exact search-session linkage exists, show it.

---

# 17. TRAIL CAMERA EXPERIENCE

Preserve current camera models / placements / cones.

Close any remaining usability gaps.

A current camera must expose:

```text
name
heading
field of view
useful range
installed_at
model
power
notes
```

On-map interaction:

- move current camera;
- rotate heading;
- change FOV;
- change range;
- inspector shows current placement metadata.

Historical placement behavior:

- moving/deactivating a camera never destroys placement history;
- old camera point/cone becomes faded;
- history toggle reveals previous placements;
- older placements fade more than newer historical placements;
- selecting a historical placement shows date range;
- historical placement cannot silently mutate current placement.

---

# 18. CORKBOARD LINKS

Preserve existing Surveyor object links and make line semantics visually obvious.

Styles:

```text
observed movement       solid arrow
hypothesized movement   dashed arrow
association             dotted line
possible corridor       double/directional dashed
evidence for            solid thin
evidence against        crossed/contrasting relation
```

Endpoints must stay attached to linked objects after object movement.

Support snapping endpoints to:
- pins;
- cameras;
- zones;
- other eligible field objects.

Connections remain Surveyor-authored interpretation, never external-provider truth.

---

# 19. SNAPPING

Current `snapEngine.js` already supports roads/trails/waterways/user objects.

Harden it for the new environment layers.

Snap menu:

```text
Roads
Trails
Waterways
Zone boundaries
Pins
Trail cameras
```

Rules:

- snap to the visible geometry from either base vector style or normalized hydrography;
- prefer explicit NC hydrography over generic base water when both are within threshold;
- show a visible snap target + type;
- preserve user's drawn geometry as Archie Radar data;
- store optional metadata describing which provider/feature was snapped to;
- never edit authoritative provider geometry.

---

# 20. SEARCH SESSION / SURVEYOR JOURNAL

These systems already exist. Do not rebuild them.

Ensure environmental context can enrich them.

Search-session summary should be able to expose:

- start/end;
- duration;
- method;
- distance;
- linked notes/evidence;
- areas searched;
- cameras serviced;
- unresolved field tasks.

Journal entry types continue to include:

- search sessions;
- sightings/evidence;
- camera changes;
- object links;
- access changes;
- candidate actions;
- wildlife observations created by the user;
- attachments.

External iNaturalist observations do **not** become permanent Journal entries merely because they were displayed.

Only a user action such as `Add note here` or `Create field marker` creates persistent local history.

---

# 21. EVIDENCE LEDGER

The current attachments/events/object system already provides the foundation.

Ensure any evidence object can link:

- image;
- audio;
- video;
- notes;
- candidate case/post;
- camera;
- zone;
- another evidence object.

Inspector should expose unresolved/linked relationships without turning the map into a graph browser.

A user must be able to answer:

`Show everything related to this location/object.`

Use current object link/event models where possible.

---

# 22. PROPERTY / ACCESS LEDGER

Preserve and improve existing access records.

Supported field state should include:

```text
unknown
no answer
permission granted
partial permission
permission denied
do not contact
```

Additional context:

- dog count;
- outdoor cat count;
- camera permission;
- last contact date;
- notes.

Map badges remain subtle.

`Dog lives here` remains a useful independent environment marker even when no structured access record exists.

---

# 23. THREE-PART SURVEYOR FIELD WORKFLOW

The intended field workflow is:

## A. Search Sessions
Record what was physically searched and when.

## B. Evidence Ledger
Record what was observed/captured/reported and how it relates to other evidence.

## C. Property / Access Ledger
Record where the searcher can/cannot go and recurring contextual hazards such as dogs/outdoor cats.

These are already represented in current main. This packet should integrate them with the improved geography rather than inventing parallel systems.

---

# 24. TIME AS A FIRST-CLASS FILTER

Preserve `SurveyTimeline.vue`.

The timeline must affect:

- user observations;
- evidence;
- camera placements;
- search sessions;
- searched zones where date semantics apply;
- external wildlife observations.

Presets remain:

```text
Now
Tonight
7 days
30 days
Since Archie disappeared
Custom
All dates
```

For external iNaturalist data, use the observation date as the primary temporal field.

---

# 25. MAP OBJECT UNCERTAINTY

Preserve the epistemic distinction.

User-authored objects/zones should support:

```text
observed
inferred
hypothesis
planning
```

Recommended styling:

```text
observed     solid
inferred     lightly dashed
hypothesis   dotted
planning     hatch
```

Do not collapse confidence and epistemic state into one field.

---

# 26. MOBILE FIELD UX

Surveyor must remain field-usable on a phone.

Acceptance widths:

- 320 px portrait;
- typical Android portrait;
- phone landscape;
- desktop.

Mobile behavior:

- map remains primary surface;
- tool bar remains reachable with one hand;
- Layers is always reachable;
- selected object/external feature opens bottom-sheet style inspector;
- no permanent desktop sidebars consuming half the map;
- touch targets >= 44 px;
- drawing/snapping controls do not overlap the mobile bottom bar;
- environmental legend collapses;
- timeline remains usable.

Do not optimize only for desktop GIS interaction.

---

# 27. PERFORMANCE / REQUEST DISCIPLINE

External provider data must not turn pan/zoom into a request storm.

Requirements:

- debounce viewport loads;
- cancel stale requests;
- bbox rounding for cache keys;
- server cache / SQLite cache where appropriate;
- provider timeouts;
- bounded result counts;
- only load detailed layers at useful zooms;
- do not request wildlife observations while wildlife layer is disabled;
- do not load wetlands while disabled;
- landcover raster should not trigger JS-side feature parsing.

Environmental provider failure must not break:
- trail cameras;
- drawing;
- local objects;
- journal;
- candidate layer.

---

# 28. BACKEND API SHAPE

Prefer a dedicated router/module rather than adding another large block to `backend/app/main.py`.

Recommended:

```text
backend/app/surveyor/environment.py
backend/app/surveyor/providers/
  __init__.py
  nconemap.py
  inaturalist.py
  census.py
  wetlands.py
```

Suggested endpoints:

```text
GET /api/surveyor/environment/status

GET /api/surveyor/environment/hydrography
GET /api/surveyor/environment/boundaries
GET /api/surveyor/environment/wildlife
```

Optional:
- keep NLCD/NWI raster tiles client-side if CORS and reliability are acceptable;
- otherwise proxy only where necessary.

Every endpoint must return provider metadata and an explicit degraded/error state instead of malformed empty success.

---

# 29. FRONTEND FILE BOUNDARIES

Keep `SurveyorView.vue` from becoming an unmaintainable mega-component.

Prefer extracting provider/state concerns.

Suggested:

```text
frontend/src/surveyor/environmentLayers.js
frontend/src/surveyor/catMapStyle.js
frontend/src/surveyor/mapHealth.js
frontend/src/surveyor/environmentProviders.js

frontend/src/components/surveyor/EnvironmentalInspector.vue
frontend/src/components/surveyor/MapLegend.vue
frontend/src/components/surveyor/LayerDrawer.vue
```

Do not refactor unrelated current field workflow merely for aesthetics.

---

# 30. CURRENT BLANK / FEATURELESS MAP ACCEPTANCE

This is P0.

On a clean page load centered near the Archie search anchor, before enabling optional wildlife/wetland layers, the user must be able to visually identify:

- at least one named road when at neighborhood/town zoom;
- visible local road network;
- waterway/waterbody geometry where present;
- woodland/developed/open-land differentiation;
- current city/place labels;
- county line context at appropriate zoom;
- state boundary if viewport reaches it.

If those details cannot load, show a clear degraded/error indicator.

A featureless neutral canvas is a failure.

Do not mark this slice complete based only on user-created pins rendering.

---

# 31. EXTERNAL DATA SOURCES / PROVENANCE LOCK

Use trustworthy published services.

Approved starting sources for this slice:

## Base vectors
OpenFreeMap / OpenStreetMap-derived vector style already used by Surveyor.

## Land cover
USGS / MRLC Annual NLCD WMS.

## North Carolina streams/waterbodies
NC OneMap Major Hydrography feature services.

## Wetlands
USFWS National Wetlands Inventory REST/WMS services.

## County/state boundaries
U.S. Census TIGERweb state/county services.

## Wildlife observations
iNaturalist public observations API.

Do not add:
- anonymous scraped wildlife maps;
- random forum sightings;
- unsourced predator heat maps.

Every non-base provider must have visible provenance.

---

# 32. DO NOT OVER-INTERPRET ENVIRONMENTAL DATA

Hard rule.

External layers tell us things like:

`A public coyote observation was recorded here on this date.`

They do **not** automatically tell us:

`Coyotes control this territory.`

Likewise:

- NLCD forest != guaranteed cat shelter;
- wetland != impassable;
- public observations != population density;
- a cluster of iNaturalist points != a known wildlife hotspot;
- a stream line != guaranteed current water flow.

Keep source facts and Surveyor interpretation visually/semantically distinct.

---

# 33. DO NOT IMPLEMENT YET

Defer:

- automated predator-risk scoring;
- automatic Archie-route prediction;
- automatic cat-highway inference;
- AI-generated search zones;
- route optimization;
- automatic trail-camera placement;
- Movebank unless a clearly useful local public study is identified later;
- generic social/community accounts;
- real-time location sharing.

The field map should become dependable before analytical automation is layered on top.

---

# 34. FOCUSED TESTING

Follow `AGENTS.md`: focused checks, no expensive suite churn.

Backend tests:

- hydro provider bbox normalization;
- external provider timeout/degraded output;
- iNaturalist observed date mapping;
- iNaturalist geoprivacy handling;
- cache key correctness;
- no provider request when layer disabled where backend state applies.

Frontend/pure helper tests if harness exists:

- base style health classification;
- environment visibility state;
- external observation normalization;
- timeline-to-provider query conversion.

Manual map acceptance is more important than chasing broad unrelated test coverage.

Do not repeatedly reinstall npm or run unrelated full suites.

---

# 35. MANUAL ACCEPTANCE

## First load

Open Surveyor on a clean browser profile.

Verify:
- geographic context appears without opening Layers;
- roads/place labels/water are legible;
- woodland/developed context is visible;
- map does not sit on Loading boundaries forever;
- local objects render above geography.

## Layer drawer

Toggle:
- NLCD;
- hydrography;
- wetlands;
- boundaries;
- wildlife species.

Verify one failed provider does not blank the map.

## Wildlife

Enable coyotes + foxes.

Verify:
- observations have provider attribution;
- observation date is distinct from date-added when both exist;
- external marker is visibly different from user wildlife evidence;
- time slider filters observations;
- obscured/private semantics are respected.

## Snapping

Draw:
- corridor snapped to a road;
- line snapped to NC hydrography;
- line endpoint snapped to a trail camera;
- polygon snapped partly to a zone boundary.

Verify snap indicator identifies the target type.

## Camera

Move one trail camera.

Verify:
- new active placement;
- old faded historical placement;
- history remains selectable;
- connections remain attached.

## Journal

Start/end a short search session.
Create evidence and a note from an environmental feature.
Verify only explicitly created local records appear in Journal.

## Mobile

Repeat Layers, marker placement, camera selection, and environmental inspector on portrait and landscape phone widths.

---

# 36. DEFINITION OF DONE

Slice 8 is complete when:

- Surveyor no longer presents a featureless geographic canvas;
- base geography is useful on first load;
- cat-view map styling is hardened beyond best-effort regex coloring;
- Annual NLCD is useful/default environmental context with graceful failure;
- NC OneMap hydrography is integrated;
- NWI wetlands are available as an optional layer;
- Census county/state context is non-blocking;
- iNaturalist wildlife observations are available with provenance/geoprivacy/date correctness;
- LayerDrawer exposes real capability-driven environmental controls;
- environmental features have an inspector;
- environmental providers cannot break core Surveyor tools;
- snap engine can use authoritative hydrography;
- search-zone/camera/link/current Surveyor systems remain intact;
- mobile field use remains practical;
- focused tests/checks pass;
- changes are committed and pushed to `main`;
- DietPi deployment follows `AGENTS.md` only if the execution environment actually has device access.

---

# 37. IMPLEMENTATION ORDER

1. verify latest main and current live map failure;
2. add base-map health/degraded state;
3. harden cat-view base style so road/water/place geography is always visible;
4. default environmental layer settings + merge legacy saved settings;
5. harden Annual NLCD;
6. add dedicated Surveyor environment backend router;
7. NC OneMap hydrography;
8. Census county/state context;
9. NWI wetlands;
10. iNaturalist provider + caching/geoprivacy/time;
11. LayerDrawer capability/provider health;
12. EnvironmentalInspector;
13. MapLegend;
14. snap-engine integration with hydrography;
15. search coverage freshness styles;
16. camera/history/corkboard visual audit against environmental layers;
17. timeline integration;
18. mobile pass;
19. focused tests;
20. manual acceptance;
21. commit + push main;
22. deploy to DietPi only if device access is genuinely available.

---

# 38. END-OF-RUN REPORT

Return:

```text
SLICE 8 STATUS

Base SHA:
Final SHA:

BASE GEOGRAPHY
OpenFreeMap health:
Road hierarchy:
Water:
Woodland/developed context:
Labels:
Blank-map fallback:

ENVIRONMENT
Annual NLCD:
NC OneMap hydrography:
NWI wetlands:
Census boundaries:

WILDLIFE
iNaturalist:
Species enabled:
Geoprivacy:
Observed/date-added semantics:
Provider cache:

FIELD TOOLS
Zones:
Snapping:
Trail cameras:
Camera history:
Corkboard links:
Search coverage freshness:
Environmental inspector:
Legend:

MOBILE:
FOCUSED TESTS:
MANUAL ACCEPTANCE:

REPOSITORY
Default branch status:
main SHA:

DEPLOYMENT
DietPi deployment:

KNOWN LIMITATIONS:
```

If repository settings cannot be changed:

`Default branch status: feature/surveyor-v1 remains configured in GitHub; main is authoritative per AGENTS.md`

If this environment cannot reach DietPi:

`DietPi deployment: not attempted from this environment`
