# NEXT SLICE IMPLEMENTATION

## Archie Radar v1 · Slice 7 of 9
### Correctness Rollup + External Environmental Intelligence

**Reviewed baseline:** `main` at `e224bce96275bc4fc555584d2becc149fe071a88`

This file is the active implementation brief for the next repository-changing run.

The repository already contains the major CandidateCase, Case Workspace, Media Vault, Surveyor field-operations, candidate performance, and server-side selected-group Facebook collector work. Do not rebuild those systems from scratch.

The next slice has two jobs:

1. close the correctness and UX defects still present in latest `main`;
2. implement the first real external environmental/context layer stack for Surveyor.

Do not implement Radar/LLM functionality in this slice.

---

# 0. CURRENT-MAIN REVIEW

The following are already present and should be preserved:

- CandidateCase and stable external identifiers;
- coherent case projection helpers;
- case workspace route;
- review history / case notes / merge-split support;
- lean `/api/candidate-cases/map`;
- candidate request cancellation/version guard;
- incremental case reconciliation after ingestion;
- Surveyor field objects, cameras, links, access, evidence, tasks, search sessions, coverage, undo, media;
- Media Vault / batch export / local media handling;
- server-side Facebook selected-group collector with Playwright session state;
- root `AGENTS.md` deployment instructions.

The following defects are still visible in latest `main` and MUST be rolled into this slice before declaring it complete:

1. `CandidatesView.clientPrioritize()` still sorts trait boost ahead of match score and can materially distort smart review order.
2. `CandidatesView.locateCandidate()` still uses top-level `post.latitude/post.longitude`, hardcodes precision to `address`, and can disagree with `current_location`.
3. Candidate cards still expose source-record provenance in the collapsed view and still label any `source_url` as `Original`.
4. 24PetConnect parsing still falls back to the saved `/ViewAnimals/<request-id>` URL when no animal-specific detail link is found.
5. The saved 24PetConnect search page's `Your request is currently Inactive` state must not be treated as the state of every animal in the results.
6. The Surveyor `Layers` button is still hidden by mobile CSS because it lives inside `.surveyor-actions`.
7. Surveyor still requests Annual NLCD directly from the browser against the MRLC WMS.
8. Wildlife / hydrography / wetlands external providers are not implemented yet.
9. The MapLibre console warning `Expected value to be of type number, but found null instead` still needs a defensive source/style cleanup.
10. `backend/app/main.py` is already very large. New external-provider code must not be added there beyond router registration.

---

# 1. PHASE A · REVIEW QUEUE CORRECTNESS

## A1. Smart ordering

The backend `sort=smart` order is the authoritative base order.

The backend match score already incorporates normal Archie traits, recency, distance, and photo signals. Do not apply the same default traits again as a dominant client-side sort.

Change `clientPrioritize(list, filters)` as follows:

- if sort is not `smart`, return server order;
- if trait mode is not `prioritize`, return server order;
- if the applied trait selections equal the Archie default trait set, return server order unchanged;
- if the user has intentionally changed prioritization traits, custom trait boost may only act as a tie-breaker inside a narrow match-score band.

Recommended comparator for custom prioritization:

1. score band descending: `Math.floor(match_score / 10)`;
2. usable real source image before no-image when otherwise similar;
3. custom trait boost descending;
4. raw `match_score` descending;
5. meaningful event time descending.

A 68/100 candidate must never fall below a 31/100 candidate merely because the 31 matches one more selected client trait.

Displayed queue rank must always be derived from the final visible order.

## A2. Pure sorts

Keep these semantics exact:

- Strongest match signals: `match_score DESC`, then meaningful event time;
- Newest: meaningful event time DESC;
- Closest: `current_location.distance_from_home_miles ASC`;
- Smart: server order plus only the narrow custom-priority tie-breaking described above.

## A3. Card hierarchy

Collapsed cards should emphasize operational information in this order:

1. holding entity / custody context;
2. Animal ID or other useful external identity;
3. small provider/source context;
4. found/sighted/posted time;
5. current location and distance/bearing from home;
6. strongest trait chips;
7. match-signal score;
8. review actions;
9. Open case / More details.

Do not render a generic title such as `Shelter intake cat`, `Found cat`, `Unknown`, or `Cat` as a large heading when the holding/custody context is more useful.

Do not display `Current location · source record #...` in the collapsed card. Put that in expanded provenance/details.

Review actions MUST remain above `More details`.

---

# 2. PHASE B · LOCATION / MAP CONSISTENCY

## B1. One canonical case location

All candidate-level map and relationship-to-home actions must use `post.current_location`.

Use:

- `current_location.map_latitude`;
- `current_location.map_longitude`;
- `current_location.precision`;
- `current_location.distance_from_home_miles`;
- `current_location.distance_is_approximate`;
- `current_location.location_text`.

Do not use top-level `post.latitude/post.longitude` when a case-level current location bundle exists.

## B2. Fix `locateCandidate()`

Update `CandidatesView.locateCandidate()` so the coordinates, bearing, precision, displayed place name, and distance all come from the same current-location record.

Never hardcode precision to `address`.

If `current_location` has text but no usable coordinates, fall back to the existing deterministic `/api/places/resolve` flow.

## B3. Candidate map is the primary quick map

The candidate card's primary `Map` action should focus the existing Candidates map, not immediately launch an external map.

Implement a focused-case state such as `focusedCaseId` and a SearchMap prop/event that:

1. expands the Candidates map when needed;
2. flies to the current case location;
3. highlights/opens the candidate marker.

Keep an external OpenStreetMap action in expanded details as a secondary link.

The Case Workspace may continue to provide `Open in Surveyor`.

## B4. Human-readable location formatting

Display-only formatting may turn `Fairfax St And Waterford St` into `Fairfax St & Waterford St`.

Do not mutate source text in persistence.

Approximate/city/street precision must remain visible where relevant.

---

# 3. PHASE C · 24PETCONNECT LINK AND STATUS CORRECTNESS

## C1. Separate link types

Introduce normalized source-link semantics for 24PetConnect:

- `exact_detail`;
- `search_results`;
- `provider_home`;
- `unavailable`.

Persist this in raw metadata so existing schema can remain additive:

- `source_link_kind`;
- `listing_url`;
- `detail_url`.

Existing `PetPost.source_url` may remain the best exact link for compatibility, but list/case output must classify it.

## C2. Discover actual animal detail links

For each animal card/result, inspect only the DOM container belonging to that Animal ID.

Accept a detail link only when:

- host is `24petconnect.com`;
- path is a recognized animal detail path such as `/DetailsMain/<provider-code>/<animal-id>` or another observed official animal-detail form;
- the final Animal ID matches the current record.

Check likely link attributes:

- `href`;
- `data-href`;
- `data-url`;
- `onclick`.

Do not search the full document in a way that can pair Animal A with Animal B's detail link.

Do not guess shelter/provider codes.

## C3. Search result fallback

If no exact animal-specific detail URL is discoverable:

- retain the saved `ViewAnimals` URL as a search/fallback URL;
- mark `source_link_kind = search_results`;
- do not label that URL `Original`.

Candidate UI:

When exact detail exists:
- `View on 24PetConnect ↗`.

When only search/provider fallback exists:
- `Open 24PetConnect ↗`;
- `Copy Animal ID`.

Never show a saved search page under a button labeled `Original`.

## C4. Search-request inactive is not animal inactive

The text `Your request is currently Inactive` on a saved `ViewAnimals` page describes the saved search request.

It does NOT prove that each displayed animal is inactive.

Do not set animal lifecycle state based solely on this request-level text.

An animal may be marked inactive/terminal only when an animal-specific detail response or other source-supported record explicitly indicates the animal/listing state.

## C5. Detail validation

If an exact detail URL is discovered, validation may check:

- HTTP success;
- final page still corresponds to the matching Animal ID.

A broken detail link should downgrade `source_link_kind` to `unavailable` or fallback behavior. It must not by itself mark the animal inactive.

## C6. Legacy rows

Do not require a destructive reingest.

At output time, classify existing `source_url` values whose path contains `/ViewAnimals/` as `search_results`.

On later source refresh, replace with a verified exact detail link when one is actually found.

## C7. Holder/custody fallback

Centralize 24Pet display-context normalization and use it:

- during connector ingestion;
- during case output/backfill fallback for legacy rows.

Known source-specific holder fallbacks may be used only for their matching source namespaces:

- `chatham_24petconnect` → `Chatham County · Animal Resources Center`;
- `durham_24petconnect` → `Animal Protection Society of Durham`;
- `wake_24petconnect` → `Wake County Animal Center`;
- `orange_county_24petconnect` → `Orange County Animal Services`.

Do not infer a holder for generic `regional_24petconnect`.

---

# 4. PHASE D · SURVEYOR LAYER CONTROL HOTFIX

## D1. Persistent map-level control

Do not depend on `SearchSessionBar` for map-layer access.

Add `frontend/src/components/surveyor/SurveyorMapControls.vue` or an equivalent small component inside `.surveyor-map-shell`.

Provide an always-visible 44x44+ `Layers` control:

- desktop: top-right of map, below/clear of native MapLibre controls;
- mobile portrait: top-right of map, always visible;
- phone landscape: top-right of map pane.

It opens/closes `layerDrawerOpen`.

The existing header Layers button may remain as a desktop duplicate, but it must not be the only entry point.

## D2. Drawer backdrop

When LayerDrawer is open:

- mobile: use a subtle map backdrop / click-catcher;
- desktop: allow click-away close without blocking drawer scroll.

## D3. Capability-driven drawer

Extend `LayerDrawer.vue` to receive capabilities and layer status.

Example:

```js
{
  landcover: true,
  hydrography: true,
  wetlands: true,
  wildlife: true
}
```

Do not render dead toggles for unavailable capabilities.

Remove the placeholder sentence saying providers will appear later once the real providers land.

## D4. Apply visibility explicitly

Create a single `applyLayerVisibility()` function.

Call it:

- after all custom MapLibre sources/layers are created;
- whenever layer settings change.

Do not rely on reactive timing tricks to make the initial state apply.

## D5. Overlay status chips

When a non-base contextual overlay is enabled, show compact chips over the map:

- `LAND COVER · 2025 ×`;
- `STREAMS ×`;
- `WETLANDS ×`;
- `COYOTE · 90D ×`.

Clicking × disables that layer.

---

# 5. PHASE E · MAPLIBRE NUMERIC SANITIZATION

Resolve the console warning:

`Expected value to be of type number, but found null instead.`

Before each `setData()` / initial GeoJSON handoff, sanitize:

- coordinates must be finite;
- style numeric properties read by MapLibre expressions must be finite.

Examples:

- camera opacity;
- positional accuracy;
- task counts;
- urgency counts;
- overdue counts;
- heading/FOV/range when style expressions consume them.

For optional numeric data, omit the property when unknown or use a null-safe style expression:

```js
["coalesce", ["get", "property"], DEFAULT]
```

Do not map an unknown value to zero when zero has a real semantic meaning.

A small development-only feature validator is acceptable. Do not spam production logs.

---

# 6. PHASE F · EXTERNAL PROVIDER BACKEND ARCHITECTURE

Do not add this implementation to `main.py`.

Create:

```text
backend/app/external/
    __init__.py
    router.py
    service.py
    schemas.py
    models.py
    cache.py
    geometry.py
    rate_limit.py

    providers/
        __init__.py
        base.py
        inaturalist.py
        nc_onemap.py
        nwi.py
        mrlc.py
```

Use existing dependencies where possible:

- `httpx`;
- `shapely`;
- `pyproj`;
- SQLAlchemy.

Do not add a new dependency unless it clearly removes substantial complexity.

Register only the external router in `main.py`.

All new DB structures must be additive. Existing startup uses `Base.metadata.create_all()`, so new tables are appropriate. Do not require destructive alteration of existing tables.

---

# 7. PHASE G · EXTERNAL CACHE / HEALTH / RATE LIMITING

## G1. External fetch receipts/cache

Add an additive cache/receipt model, either as `ExternalFetchReceipt` plus payload storage or an equivalent clean design.

Required semantics:

- provider;
- request kind;
- stable query hash;
- normalized parameters JSON;
- bbox JSON when relevant;
- fetched/started/completed timestamps;
- status;
- result count;
- error summary;
- expires_at;
- cached payload or linkage to normalized observations.

Cache zero-result queries too.

Suggested TTLs:

- wildlife query results: 6 hours;
- hydrography: 7 days;
- wetlands: 7 days;
- land-cover raster tiles: 30 days.

If refresh fails and a previously successful cached result exists, return stale data with:

- `cached: true`;
- `stale: true`;
- last successful fetch time.

Do not make a working layer disappear because its provider is temporarily unavailable.

## G2. Provider health

Add:

`GET /api/external/providers`

Return provider status:

- `ready`;
- `degraded`;
- `unavailable`;
- `disabled`.

Include last success/error timestamps, not private stack traces.

## G3. In-flight coalescing

Identical requests already in progress should share/coalesce work instead of generating duplicate upstream requests.

## G4. HTTP behavior

Use one reusable async HTTP client or clearly bounded clients with:

- identifying User-Agent;
- sensible connect/read timeouts;
- bounded retry only for transient failures;
- no infinite retries.

---

# 8. PHASE H · ANNUAL NLCD 2025

This should be the first external provider implemented because latest main already has a working direct WMS layer.

## H1. Replace browser-direct WMS

Current `SurveyorView.vue` directly requests MRLC WMS tiles.

Remove direct browser dependency.

Add backend:

`GET /api/external/landcover/{z}/{x}/{y}.png`

Server behavior:

1. validate z/x/y;
2. calculate XYZ tile bounds in EPSG:3857;
3. build the configured Annual NLCD 2025 WMS GetMap request;
4. request a 256x256 PNG;
5. cache the tile;
6. return PNG with appropriate content type/cache headers.

Do not implement an arbitrary WMS proxy.

Provider host/layer/product/year are server-controlled constants/settings.

## H2. Product semantics

UI:

- `Annual NLCD land cover · 2025`;
- attribution `USGS / MRLC`.

Never call it `current land cover`.

## H3. Frontend source

MapLibre raster source tiles must point only to Archie Radar:

`/api/external/landcover/{z}/{x}/{y}.png`

No direct MRLC request should appear in the browser network log after this slice.

Default OFF.

Opacity target: roughly 0.28–0.35, with optional 15–60% slider if straightforward.

---

# 9. PHASE I · NC ONEMAP HYDROGRAPHY

Use official NC OneMap Major Hydrography as authoritative contextual geography.

Implement:

`GET /api/external/hydrography`

Parameters:

- west;
- south;
- east;
- north;
- include = streams,waterbodies.

Query only the current viewport plus a modest 10–15% buffer.

Request/normalize WGS84 GeoJSON.

Support both:

- streams/rivers;
- waterbodies.

Retain only useful normalized attributes in the browser payload:

- feature/provider ID;
- name;
- basin/subbasin when available;
- source-supported classification.

If the upstream service indicates a transfer/record limit, subdivide the bbox with a strict recursion cap and deduplicate provider feature IDs.

Do not silently truncate.

Suggested frontend minimum zoom: about 11.

Style:

- streams: subtle contextual line;
- waterbodies: muted low-saturation fill/outline;
- below user search geometry and annotations.

Default ON is acceptable for streams/waterbodies if performance is good because this is core field context.

---

# 10. PHASE J · USFWS NWI WETLANDS

Implement:

`GET /api/external/wetlands`

Query only local viewport context.

Normalize to GeoJSON where practical.

Expose source classification/code and provider provenance.

UI label:

`Mapped wetlands`

Never imply:

- standing water now;
- flooded now;
- live hydrology.

Suggested minimum zoom: about 12.

Default OFF.

Use a restrained translucent fill/pattern so user-created searched/needs-search zones remain visually dominant.

---

# 11. PHASE K · INATURALIST PUBLIC WILDLIFE

## K1. Scope

Read-only public observations only.

Do not authenticate to access private coordinates.

Do not request or store private/trusted-project coordinates.

Implement default species:

- Coyote: `Canis latrans`;
- Red fox: `Vulpes vulpes`;
- Gray fox: `Urocyon cinereoargenteus`;
- Bobcat: `Lynx rufus`;
- Raccoon: `Procyon lotor`;
- White-tailed deer: `Odocoileus virginianus`;
- Virginia opossum: `Didelphis virginiana`.

## K2. Taxon resolution

Add an additive `ExternalTaxon` model or equivalent.

Resolve configured scientific names against iNaturalist and require:

- returned scientific name matches;
- rank is species.

Do not trust the first fuzzy common-name match.

Cache the resulting taxon IDs.

## K3. Observation model

Add normalized `ExternalObservation` persistence/cache with at least:

- provider;
- provider observation ID;
- taxon key / provider taxon ID;
- scientific/common name;
- observed_at;
- provider created/updated timestamps;
- public latitude/longitude;
- positional accuracy;
- geoprivacy / taxon geoprivacy;
- normalized location precision;
- quality grade;
- source URL;
- raw JSON;
- fetched_at.

Unique on provider + provider observation ID.

## K4. Geoprivacy

Normalize public-location semantics to:

- `public`;
- `approximate`;
- `obscured`;
- `unknown`.

Obscured iNaturalist coordinates are not exact.

UI for obscured points:

- `Approximate public location`;
- `Exact location intentionally obscured by source`.

Do not:

- snap camera/search geometry to an obscured point;
- draw a fake meter-accuracy circle around an obscured public coordinate;
- treat the displayed point as exact evidence.

Observations with no public coordinate are not mapped.

## K5. API

Add:

`GET /api/external/wildlife`

Parameters:

- west/south/east/north;
- from/to;
- taxa[];
- quality;
- refresh=false.

Validate supported taxa and bbox/date bounds.

Default period: 90 days.

Presets in UI:

- 7 days;
- 30 days;
- 90 days;
- Since Archie disappeared;
- 1 year;
- Custom.

Use `observed_at` as the map/filter time, not upload date.

## K6. Rate limits

Use a conservative one-upstream-request-per-second limiter for iNaturalist.

On provider 429:

- back off;
- serve stale cache if available.

Do not continuously retry.

## K7. Result limits

Bound viewport results.

If provider returns more than the supported limit, return `truncated: true` and tell the UI.

Do not silently imply exhaustiveness.

Suggested individual-observation minimum map zoom: 11.

---

# 12. PHASE L · FRONTEND EXTERNAL LAYER MODULE

Create:

```text
frontend/src/external/
    api.js
    store.js
    layers.js
    time.js
    legend.js

frontend/src/components/external/
    ExternalLayerGroup.vue
    WildlifeLayerControls.vue
    ExternalObservationPopup.vue
    EnvironmentInspector.vue
    EnvironmentLegend.vue
    ProviderStatus.vue
```

Do not let `SurveyorView.vue` absorb another large block of provider-specific logic.

## L1. Layer defaults

Extend Surveyor layer settings approximately:

```js
external: {
  hydrography: true,
  wetlands: false,
  landcover: false,
  wildlife: false,
  wildlifeTaxa: {
    coyote: false,
    red_fox: false,
    gray_fox: false,
    bobcat: false,
    raccoon: false,
    white_tailed_deer: false,
    virginia_opossum: false
  }
}
```

Migrate existing localStorage settings defensively.

## L2. Strict lazy fetch

If a layer is OFF:

- no upstream request;
- no Archie external endpoint request except optional provider-health/capability lookup.

Wildlife with no taxon selected: no request.

Below minimum zoom: no request.

Fetch on `moveend` only, debounced roughly 300 ms.

Use AbortController to cancel stale browser requests.

Use a 10–15% viewport buffer so tiny pans do not immediately refetch.

## L3. Source organization

Use one MapLibre source per external family, not one per feature:

- `external-wildlife`;
- `external-streams`;
- `external-waterbodies`;
- `external-wetlands`;
- raster `external-landcover`.

Local/user-created objects must win hit priority over external layers.

---

# 13. PHASE M · VISUAL LANGUAGE

Maintain the epistemic hierarchy.

## User observations

Existing first-hand Surveyor objects:

- crisp;
- strong;
- filled.

## External public wildlife

- hollow/smaller marker;
- muted external-data accent;
- visually distinct from user wildlife observations.

## Obscured public wildlife

- hollow marker;
- larger soft/dotted uncertainty halo;
- no implication that halo center is the true location.

## Environmental layers

- visually quiet;
- below search objects, cameras, evidence, planning zones and interaction handles.

## Hypotheses/planning

Keep existing dashed/dotted planning semantics.

A saved third-party wildlife observation must remain visibly third-party after saving.

---

# 14. PHASE N · EXTERNAL OBSERVATION POPUP / SAVE AS CONTEXT

Wildlife popup should show:

- common/scientific species;
- `Public observation`;
- observed date;
- quality grade;
- public location precision;
- positional accuracy when meaningful;
- provider;
- source link.

Buttons:

- `Open source`;
- `Save as context`.

`Save as context` explicitly creates a SurveyorMapObject:

- object_type = `context`;
- subtype = `external_wildlife_observation`;
- epistemic_state = `observed`;
- confidence = `context`.

Properties must preserve:

- provider;
- provider observation ID;
- taxon;
- observed_at;
- source URL;
- location precision;
- positional accuracy;
- geoprivacy;
- `third_party = true`.

Do not call saved public observations `evidence of Archie`.

Do not automatically persist every external feature.

---

# 15. PHASE O · PUBLIC OBSERVATION CONCENTRATION

Optional but included in Slice 7 if core providers are stable.

Add:

`Public observation concentration`

Only enable when at least 5 observations are available.

Use deterministic grid/bin counts, not opaque KDE.

Suggested base cell size: about 500 m, adjusted modestly by zoom if needed.

Correct labels:

- `Public coyote observation concentration`;
- `12 public observations · Jul 1–Sep 27`.

Never label:

- predator hotspot;
- coyote density;
- population estimate.

Display:

`Public-report concentration does not estimate animal population.`

No absence inference. A lack of public observations does not mean the animal is absent.

---

# 16. PHASE P · ENVIRONMENT INSPECTOR

Add a Surveyor tool/action:

`Inspect area`

Endpoint:

`GET /api/external/context?lat=...&lon=...&radius_m=500`

Return when available:

- Annual NLCD class/year at point;
- nearest stream and metric distance;
- nearest waterbody and metric distance;
- mapped-wetland intersection/context;
- public wildlife observation counts in selected/default recent window;
- provider/cached/stale status.

Use a local metric CRS through pyproj for nearest-distance calculations. Do not calculate meter distances directly on raw lat/lon geometry.

If a provider is unavailable, return that section as unavailable rather than inventing data.

## P1. Camera context

Trail-camera inspector gets:

`Environmental context`

Use the active camera placement coordinate.

Display context only. Do not automatically recommend moving the camera.

## P2. Candidate context

Candidate Case Workspace gets:

`Environmental context`

Use `current_location`.

If the candidate location is approximate/city-level, say:

`Context is based on an approximate candidate location.`

Do not imply precision beyond the source.

---

# 17. PHASE Q · PROVIDER PRIVACY BOUNDARY

External provider requests may contain only geographic/provider query information:

- bbox;
- coordinates needed for the query;
- taxa;
- dates;
- product/layer parameters.

Never send:

- textual home address;
- Archie profile/name;
- CandidateCase IDs;
- Animal IDs;
- private access notes;
- contact information;
- user notes.

A bbox may naturally encompass home, but providers are never told that a coordinate is the user's home or the missing-cat origin.

---

# 18. PHASE R · FAILURE / OFFLINE BEHAVIOR

Each provider owns its own error state.

If iNaturalist fails, Surveyor, hydrography, wetlands and land cover must still work.

If internet is unavailable and cached data exists:

- show cached data;
- expose last refresh time;
- mark stale when appropriate.

Manual `Refresh layer` may retry.

No rapid automatic retry loops.

---

# 19. TEST PLAN

Automated provider tests must mock upstream HTTP. Do not call live public APIs from pytest.

Add focused tests covering at least:

## Review/location/24Pet

1. 68 match score remains above 31 despite client trait boost.
2. default Archie selections do not double-resort smart order.
3. current-location text/distance/bearing/map all use the same record.
4. location precision is not hardcoded to address.
5. `/ViewAnimals/` is classified as search-results, not exact original.
6. exact animal detail link must match Animal ID.
7. request-level `Inactive` does not mark displayed animals inactive.
8. legacy Chatham record can derive the correct holding entity.

## External backend

9. taxon resolution accepts exact species and rejects wrong rank/name.
10. public iNaturalist observation normalizes correctly.
11. obscured observation remains obscured.
12. private/no-coordinate observation is not mapped.
13. observed_at remains distinct from provider-created timestamp.
14. positional accuracy is preserved.
15. rate limiter spaces iNaturalist requests.
16. fresh cache prevents duplicate upstream request.
17. stale successful cache is returned after provider failure.
18. NC OneMap stream/waterbody responses normalize to WGS84 GeoJSON.
19. transfer-limit subdivision deduplicates features.
20. NWI normalization preserves mapped-wetland semantics.
21. land-cover tile endpoint rejects invalid z/x/y.
22. arbitrary proxy URLs/layers cannot be supplied by clients.
23. land-cover tile cache works.
24. external context distance uses projected metric calculation.
25. Save as context preserves provenance and third-party status.
26. no provider request includes private Archie Radar context.

Do not add fragile wall-clock performance assertions to CI.

---

# 20. MANUAL ACCEPTANCE

## Queue / 24Pet

Use at least 10 24Pet cases.

Verify:

- review order is sane;
- review actions stay before details;
- holder/custody is the dominant heading;
- location map uses the exact current-location bundle;
- internal source-record number is details-only;
- exact detail links open the matching Animal ID;
- saved ViewAnimals links are never called `Original`;
- request-level inactive text does not erase current animal results.

## Surveyor control

Desktop, portrait mobile, and phone landscape:

- persistent Layers control is visible;
- LayerDrawer opens without entering More/search-session menus;
- enabled overlay chips appear;
- toggles reliably apply after initial map load;
- no MapLibre null-number warning remains.

## Land cover

Enable land cover.

Browser network log must hit only Archie Radar's tile endpoint, not MRLC directly.

## Hydrography / wetlands

Enable each.

Verify:

- visually subordinate styling;
- no network storm while panning;
- no statewide payloads;
- toggling OFF stops fetches.

## Wildlife

Enable Coyote + Fox, 90 days.

Verify:

- markers are visibly different from user observations;
- observed date, quality, provider, precision are visible;
- obscured public points are clearly approximate;
- Save as context preserves third-party styling.

## Environment inspector

Inspect:

- arbitrary map point;
- one active trail camera;
- one candidate current location.

Verify provider wording and location precision are honest.

---

# 21. PERFORMANCE / RUNTIME REPORT

After implementation, report real local/LAN timings from the deployed app for:

- `GET /api/candidate-cases`;
- `GET /api/candidate-cases/map`;
- `GET /api/queue-stats`;
- `GET /api/surveyor/objects`;
- representative hydrography request, cached and uncached;
- representative wildlife request, cached and uncached;
- representative land-cover tile, cached and uncached.

Do not optimize based only on assumptions.

Surveyor's base map and local field objects must become usable without waiting for external providers.

---

# 22. IMPLEMENTATION ORDER

Follow this order:

1. fix smart queue ordering;
2. fix current-location/map action;
3. fix 24Pet link semantics/detail extraction/inactive-request behavior;
4. add persistent Surveyor Layers control;
5. fix numeric-null MapLibre warning;
6. create external backend package/router/cache/health primitives;
7. implement MRLC backend tile proxy and replace direct browser WMS;
8. implement NC OneMap hydrography;
9. wire capability-driven LayerDrawer and lazy frontend external store;
10. implement NWI wetlands;
11. implement iNaturalist taxon resolver + observation provider;
12. add wildlife styling/popup/geoprivacy semantics;
13. add Save as context;
14. add Environment Inspector;
15. add camera/candidate environmental context;
16. add observation-concentration view;
17. responsive polish;
18. focused mocked tests;
19. manual acceptance;
20. push to `main`, deploy to `dietpi` per `AGENTS.md`, and record timings.

---

# 23. RECOMMENDED COMMIT SEQUENCE

Suggested focused commits:

1. `fix(candidates): stabilize review order location and 24pet links`
2. `fix(surveyor): expose persistent layer controls and sanitize map properties`
3. `feat(external): add provider cache health and service framework`
4. `feat(external): proxy and cache annual NLCD landcover`
5. `feat(external): add NC OneMap hydrography`
6. `feat(external): add NWI mapped wetlands`
7. `feat(external): add iNaturalist public wildlife observations`
8. `feat(surveyor): add external layers provenance and context inspection`
9. `test(external): cover caching privacy precision and provider failures`

All commits must end on `main` and be pushed/deployed as required by `AGENTS.md`.

---

# 24. DO NOT IMPLEMENT IN THIS SLICE

Explicitly defer:

- Radar Assistant / LLM;
- OpenAI chat;
- image/video AI;
- automated search recommendations;
- automated camera placement;
- predator-risk scoring;
- inferred cat-highway generation;
- Movebank;
- eBird;
- rare-species Natural Heritage occurrence points;
- USGS GAP modeled animal-habitat overlays;
- automatic headless crawling of external environmental providers on a cron;
- redesign of the already-landed Facebook selected-group collector unless a regression is discovered.

---

# 25. DEFINITION OF DONE

Slice 7 is complete only when all of the following are true:

## Candidate correctness

- smart order no longer allows small trait boosts to swamp match score;
- default Archie traits are not double-counted in client sorting;
- candidate location/distance/bearing/map use one coherent current-location record;
- review actions precede details;
- internal record IDs are details-only;
- 24Pet search URLs are no longer labeled Original;
- real animal-specific 24Pet links are extracted/validated when available;
- request-level `Inactive` is not mistaken for animal inactivity.

## Surveyor shell

- Layers control is permanently discoverable on desktop/portrait/landscape;
- initial layer visibility is deterministic;
- overlay status chips work;
- MapLibre numeric-null warning is gone;
- Surveyor local/core data renders independently of external providers.

## Environmental providers

- Annual NLCD 2025 goes through Archie Radar backend cache/proxy;
- no direct MRLC browser WMS request remains;
- NC OneMap streams and waterbodies work;
- NWI mapped wetlands work;
- iNaturalist selected wildlife taxa work;
- external requests are lazy, bounded, cached, cancellable and failure-isolated;
- iNaturalist public geoprivacy is respected;
- public wildlife observations are visually distinct from user observations;
- Save as context is explicit and preserves provenance;
- observation concentration is neutrally labeled and does not imply population density;
- Environment Inspector works for map points, cameras and candidate locations;
- private Archie Radar context is never sent to third-party providers.

## Quality

- focused mocked backend tests pass;
- frontend build succeeds;
- manual desktop + portrait + landscape pass succeeds;
- representative runtime timings are reported;
- changes are pushed to `main`;
- `dietpi` pulls the pushed SHA and Docker Compose is rebuilt/restarted;
- lightweight deployment verification succeeds.

---

# 26. END-OF-RUN REPORT FORMAT

Return exactly this information at the end of implementation:

```text
SLICE 7 STATUS

Base SHA:
Final SHA:

CORRECTIONS
Smart review order:
Current-location/map consistency:
24Pet detail/fallback links:
24Pet request-level inactive handling:
Persistent Surveyor Layers control:
MapLibre null warning:

EXTERNAL FRAMEWORK
Provider health:
Cache:
Rate limiting:
Failure/stale-cache behavior:

LAND COVER
Backend proxy:
Tile cache:
Direct browser WMS removed:

HYDROGRAPHY
Streams:
Waterbodies:

WETLANDS:

WILDLIFE
Taxon resolution:
Observations:
Geoprivacy:
Popup:
Save as context:
Concentration:

ENVIRONMENT INSPECTOR
Point:
Camera:
Candidate:

RESPONSIVE
Portrait:
Landscape:
Desktop:

PERFORMANCE
candidate list:
candidate map:
queue stats:
surveyor objects:
hydro uncached/cached:
wildlife uncached/cached:
landcover uncached/cached:

TESTS:
MANUAL ACCEPTANCE:

DEPLOYMENT
main commit:
dietpi pulled SHA:
docker compose restart:
health verification:

KNOWN LIMITATIONS:
```

---

## Project progress after this brief

Before implementation: **6/9 sequential slices complete (67%)**.

Current slice: **Slice 7/9 · Correctness Rollup + External Environmental Intelligence**.
