# NEXT SLICE IMPLEMENTATION

## Archie Radar v1 · Slice 7 of 9
### Field Readiness + Review/Map Correctness

**Reviewed application baseline:** `main` at `0c91cea316e6a14d59c1bea8bb335b2a000f6095`  
**Instruction baseline:** `main` at `797ee832138fa898ace63e1bbdada459c1ed6530`

This packet supersedes the previous Slice 7 brief.

The previous packet bundled too much work into one slice: queue correctness, 24PetConnect correctness, Surveyor layer-control defects, and a full external environmental provider stack. That was technically coherent but operationally too broad.

The current user-facing friction is more immediate:

- before leaving, it is hard to answer **"is everything prepped?"**
- it is hard to answer **"do I have everything?"**
- it is hard to answer **"what specifically am I doing?"**
- once outside, it should be obvious **what is next** without reopening or mentally reconciling several systems.

Therefore the roadmap is intentionally re-sequenced:

- **Slice 7:** Field Readiness + Review/Map Correctness
- **Slice 8:** External Environmental Intelligence
- **Slice 9:** Final hardening / release polish

Progress remains **6/9 slices complete (67%)** before this slice.

The already-landed server-side Facebook selected-group collector remains in place. Do not redesign it in this slice unless an actual regression is discovered.

---

# 1. CURRENT-MAIN REVIEW

Latest application code already includes:

- CandidateCase and stable case/source-record separation;
- Case Workspace;
- case notes, merges/splits, projection provenance, evidence export;
- lean candidate map endpoint and batched candidate reads;
- candidate request cancellation/version guard;
- Surveyor map objects, links, trail cameras, access records, evidence, tasks, search sessions and route coverage;
- Media Vault and local media handling;
- server-side selected-group Facebook collection;
- Docker deployment workflow instructions in `AGENTS.md`.

The following issues are still present and are mandatory corrections in this slice:

1. `CandidatesView.clientPrioritize()` still lets client trait boost outrank meaningful score differences.
2. `CandidatesView.locateCandidate()` still uses top-level `post.latitude/post.longitude` rather than the coherent `current_location` projection and hardcodes location precision to `address`.
3. Candidate cards still expose internal source-record provenance in the collapsed card.
4. Candidate cards still label every `source_url` as `Original`.
5. The 24PetConnect connector still falls back to a saved `/ViewAnimals/<request-id>` URL when no animal detail URL is found.
6. Request-level `Your request is currently Inactive` text from 24PetConnect must not be interpreted as every animal being inactive.
7. Surveyor's only direct `Layers` button still lives inside `.surveyor-actions`, where mobile CSS hides it.
8. Surveyor still has the MapLibre numeric-null warning risk.
9. There is no outing-level Prep / Packing / Gameplan model.
10. `Start search` currently jumps directly into a search session with no preflight.

The full external environmental provider stack from the prior packet is deferred to Slice 8. Do not implement iNaturalist, NWI, NC OneMap hydrography, or the MRLC backend proxy in this slice.

---

# 2. PRODUCT RULE FOR THIS SLICE

The field-readiness system should obey one rule:

> **Before leaving, show what is unresolved. Once outside, show what is next.**

Do not turn this into generic project management software.

No Gantt charts.
No dependency graph editor.
No mandatory scheduling.
No route optimizer.
No AI-generated outing plan.
No forced completion gate before leaving.

---

# 3. PHASE A · FIX REVIEW QUEUE ORDERING

## A1. Backend smart order remains authoritative

For `sort=smart`, the backend result order is the authoritative base order.

The backend match score already incorporates normal Archie traits, recency, distance and photo signals.

Do not apply the default Archie trait set again as a dominant client-side sort.

## A2. Default priorities must not double-count

Change `frontend/src/views/CandidatesView.vue::clientPrioritize()`.

If:

- sort != `smart`, return server order;
- traitMode != `prioritize`, return server order;
- selected prioritization traits equal the normal Archie default selections, return server order unchanged.

## A3. Custom prioritization is a tie-breaker only

If the user deliberately changes prioritization traits, custom trait boost may reorder only within a narrow score neighborhood.

Recommended comparator:

1. `Math.floor(match_score / 10)` descending;
2. usable source photo before no-photo when otherwise similar;
3. custom trait boost descending;
4. exact `match_score` descending;
5. meaningful event time descending.

A 68/100 case must not fall below a 31/100 case merely because the 31 has a larger client trait boost.

## A4. Pure sorts

Keep these exact:

- Strongest match signals: `match_score DESC`, then meaningful event time;
- Newest: meaningful event time DESC;
- Closest: `current_location.distance_from_home_miles ASC`;
- Smart: backend order plus the limited custom-priority tie-breaking above.

Displayed rank must match final visible order.

---

# 4. PHASE B · FIX CANDIDATE CARD HIERARCHY

Collapsed candidate cards should emphasize:

1. holder / custody context;
2. external Animal ID or useful identity;
3. small provider context;
4. found/sighted/posted time;
5. current location + distance/bearing;
6. strongest trait chips;
7. match-signal score;
8. review actions;
9. Open case / More details.

Do not render generic titles such as:

- `Shelter intake cat`;
- `Found cat`;
- `Unknown`;
- `Cat`;

as a visually dominant H2 when holder/custody context is more useful.

Move technical provenance such as:

`Current location · source record #180`

into expanded details.

Keep review actions above `More details`.

---

# 5. PHASE C · FIX CURRENT LOCATION / MAP ACTIONS

## C1. One canonical case location

Candidate-level location actions must use `post.current_location`.

Use:

- `current_location.map_latitude`;
- `current_location.map_longitude`;
- `current_location.location_text`;
- `current_location.precision`;
- `current_location.distance_from_home_miles`;
- `current_location.distance_is_approximate`.

Do not combine top-level coordinates from one source record with current-location text from another.

## C2. Fix `locateCandidate()`

Update `CandidatesView.locateCandidate()` so:

- map coordinates;
- bearing;
- distance;
- precision;
- display name

all come from the same `current_location` bundle.

Never hardcode precision to `address`.

If current location has useful text but no coordinates, use the existing `/api/places/resolve` path.

## C3. Primary Map action stays in Archie Radar

The candidate card's primary `Map` action should:

1. expand the Candidates map if collapsed;
2. focus/fly to the case's current location;
3. highlight/open the candidate marker.

Use a small state such as `focusedCaseId` and a prop/event to `SearchMap`.

Keep external OSM navigation under expanded details as a secondary action.

## C4. Human-readable location formatting

Display formatting may convert:

`Fairfax St And Waterford St`

to:

`Fairfax St & Waterford St`.

Do not mutate persisted source text.

---

# 6. PHASE D · FIX 24PETCONNECT LINKS AND STATUS

## D1. Link kinds

Normalize 24Pet link semantics:

- `exact_detail`;
- `search_results`;
- `provider_home`;
- `unavailable`.

Use additive raw metadata:

- `source_link_kind`;
- `listing_url`;
- `detail_url`.

Existing `PetPost.source_url` may remain for compatibility, but output/UI must classify it.

## D2. Extract actual animal-specific detail links

In `backend/app/connectors/regional_24petconnect.py`, find the DOM container for each specific Animal ID and inspect only that container for likely detail navigation:

- `href`;
- `data-href`;
- `data-url`;
- `onclick`.

Accept an exact detail URL only when:

- host is `24petconnect.com`;
- path is a recognized animal-detail path;
- the Animal ID in the target matches the current record.

Do not guess provider/shelter codes.

Do not search the whole page in a way that can associate Animal A with Animal B's link.

## D3. Saved search URL is not Original

If only `/ViewAnimals/<request-id>` is known:

- classify it as `search_results`;
- do not label it `Original`.

UI behavior:

Exact detail:
- `View on 24PetConnect ↗`.

Search/provider fallback:
- `Open 24PetConnect ↗`;
- `Copy Animal ID`.

## D4. Request inactive != animal inactive

The text:

`Your request is currently Inactive`

describes the saved search request.

It does not establish that each displayed animal is inactive.

Do not use request-level inactive state as animal lifecycle evidence.

Only mark the animal/listing inactive when an animal-specific source record or detail response supports it.

## D5. Broken exact link

If a previously discovered animal-specific detail link fails:

- downgrade link availability;
- keep the source record;
- do not infer that the animal itself is inactive merely because the URL broke.

## D6. Legacy rows

Existing DB rows with `/ViewAnimals/` URLs must be classified at read/output time as `search_results`.

No destructive reingest required.

## D7. Centralize holder/custody fallback

Reuse one 24Pet context normalizer for ingestion and legacy output fallback.

Known namespace-specific defaults may be used:

- `chatham_24petconnect` → `Chatham County · Animal Resources Center`;
- `durham_24petconnect` → `Animal Protection Society of Durham`;
- `wake_24petconnect` → `Wake County Animal Center`;
- `orange_county_24petconnect` → `Orange County Animal Services`.

Do not invent a holder for generic `regional_24petconnect`.

---

# 7. PHASE E · SURVEYOR LAYER CONTROL HOTFIX

This slice does not add new environmental providers, but it must make the existing layer system discoverable and deterministic.

## E1. Persistent map-level Layers control

Add a persistent Layers button inside `.surveyor-map-shell`.

Suggested component:

`frontend/src/components/surveyor/SurveyorMapControls.vue`

Requirements:

- desktop: top-right of map, clear of native MapLibre controls;
- mobile portrait: always visible;
- phone landscape: visible in the map pane;
- tap target at least 44x44;
- opens/closes `layerDrawerOpen`.

The existing header Layers button may remain on desktop.

Do not rely on `SearchSessionBar` as the only access point.

## E2. Backdrop / click-away

When LayerDrawer is open:

- mobile: use a subtle backdrop and bottom-sheet behavior;
- desktop: allow click-away close without preventing drawer scrolling.

## E3. Apply layer visibility explicitly

Create one `applyLayerVisibility()` function.

Call it:

- after custom sources/layers are created;
- whenever layer settings change.

Do not rely on assigning a shallow-copied settings object to trigger timing side-effects.

## E4. Overlay chips

Show compact chips for enabled contextual overlays, e.g.:

- `LAND COVER · 2025 ×`;
- future Slice 8 layers can reuse this control.

Click × disables the layer.

## E5. Keep future capabilities extensible

LayerDrawer should be ready to receive provider capabilities in Slice 8, but do not add dead toggles for providers that do not exist yet.

---

# 8. PHASE F · MAPLIBRE NUMERIC SANITIZATION

Resolve the warning class:

`Expected value to be of type number, but found null instead.`

Before handing GeoJSON to style expressions, ensure:

- coordinates are finite;
- numeric style properties consumed by MapLibre are finite.

Audit especially:

- task_count;
- urgent_count;
- overdue_count;
- camera heading/FOV/range;
- opacity-like properties;
- any numeric property read by `get` in a numeric expression.

For truly optional numeric values:

- omit property when unknown; or
- use a null-safe MapLibre expression such as `coalesce`.

Do not map semantic unknown to zero when zero has a real meaning.

Development-only feature validation is acceptable. Do not spam production logs.

---

# 9. PHASE G · OUTING / PREFLIGHT DATA MODEL

Do not overload `SurveyorTask` or per-object checklist properties.

Create a first-class outing model using additive tables only.

Do not add a new required column to the existing `surveyor_search_sessions` table because `Base.metadata.create_all()` does not migrate existing SQLite columns.

Create in `backend/app/models.py`:

## G1. `SurveyorOutingPlan`

Recommended fields:

```text
id
title
objective
status
method
search_session_id nullable
notes
created_at
updated_at
completed_at nullable
```

Status values:

- `draft`;
- `active`;
- `completed`;
- `abandoned`.

**Correction from the earlier design:** do NOT persist a `ready` status. Readiness is derived from item/dependency state and would become stale if items change.

`search_session_id` may be a nullable FK because the outing table is new.

Method values should align with existing Surveyor search-session methods.

## G2. `SurveyorOutingItem`

Recommended fields:

```text
id
plan_id
section
title
note
position
required
status
time_hint nullable

map_object_id nullable
task_id nullable
candidate_case_id nullable

created_at
updated_at
completed_at nullable
```

Sections:

- `prep`;
- `packing`;
- `gameplan`.

Statuses:

- `pending`;
- `completed`;
- `skipped`.

UI vocabulary:

- Prep completed → `Ready`;
- Packing completed → `Packed`;
- Gameplan completed → `Done`.

`required` defaults true.

Do not add Low/Normal/High/Urgent priority to outing items.

## G3. `SurveyorOutingDependency`

Fields:

```text
id
prep_item_id
dependent_item_id
created_at
```

Unique pair constraint.

Validation:

- both items belong to the same plan;
- `prep_item.section == prep`;
- dependent item section is `packing` or `gameplan`;
- item cannot depend on itself.

Do not allow dependency chains between non-prep items.

This restriction intentionally prevents the system from becoming a generic dependency graph.

---

# 10. PHASE H · OUTING API

Create:

`backend/app/surveyor/outings.py`

Register its router in `main.py`.

Recommended endpoints:

```text
GET    /api/surveyor/outings
GET    /api/surveyor/outings/current
POST   /api/surveyor/outings
GET    /api/surveyor/outings/{plan_id}
PATCH  /api/surveyor/outings/{plan_id}

POST   /api/surveyor/outings/{plan_id}/items
PATCH  /api/surveyor/outings/items/{item_id}
DELETE /api/surveyor/outings/items/{item_id}

POST   /api/surveyor/outings/items/{item_id}/dependencies/{prep_item_id}
DELETE /api/surveyor/outings/items/{item_id}/dependencies/{prep_item_id}

POST   /api/surveyor/outings/{plan_id}/reorder
POST   /api/surveyor/outings/{plan_id}/reuse
POST   /api/surveyor/outings/{plan_id}/start
POST   /api/surveyor/outings/{plan_id}/abandon
```

Deletion of a whole plan is not needed for ordinary UX. Prefer abandon/archive semantics.

---

# 11. PHASE I · READINESS IS DERIVED

Every plan output should include computed readiness.

Example:

```json
{
  "readiness": {
    "ready_to_leave": false,
    "prep_remaining": 2,
    "packing_remaining": 1,
    "dependency_blockers": 2,
    "gameplan_total": 4,
    "gameplan_remaining": 4,
    "blocking_prep_item_ids": [12, 14]
  }
}
```

Departure blockers are:

- required Prep items still pending;
- required Packing items still pending;
- unique unfinished Prep dependencies required by required Packing/Gameplan items.

Do NOT treat an unfinished Gameplan item by itself as a departure blocker. Gameplan items are work intended to happen after leaving.

Optional items do not block departure.

Avoid double-counting the same unfinished Prep item when three Gameplan items depend on it.

Human-facing summary should say things like:

- `2 setup blockers · 1 item not packed`;
- `Ready to go`.

Do not show a readiness percentage.

---

# 12. PHASE J · PREFLIGHT UX

Create:

```text
frontend/src/components/surveyor/PreflightSheet.vue
frontend/src/components/surveyor/OutingSection.vue
frontend/src/components/surveyor/OutingItemRow.vue
frontend/src/components/surveyor/OutingDependencyPicker.vue
frontend/src/components/surveyor/ActiveMissionStrip.vue
frontend/src/surveyor/outings.js
```

One vertically scrolling sheet, in this order:

1. Prep / Setup
2. Packing List
3. Gameplan

Do not make these separate pages or tabs.

## J1. Header

Show:

- plan title;
- one-line objective;
- readiness summary.

Example:

`2 setup blockers · 1 item not packed`

or:

`Ready to go`.

Objective example:

`Check creek cameras, cover abandoned-house edge, dusk pass at Coyote Island.`

Objective is optional but strongly surfaced because it answers "what is tonight about?"

## J2. Prep / Setup

Simple rows:

`○ Charge camera batteries`

`✓ Clear SD cards`

No priority selectors.

## J3. Packing

Rows may display dependency state:

```text
○ Camera bag
  ⚠ Needs setup: Charge camera batteries
```

If several dependencies:

`⚠ 2 setup items unfinished`

## J4. Gameplan

Ordered items:

```text
1. Raccoon Creek camera
   Pull card + swap battery
   ✓ Setup ready

2. Blue Lagoon camera
   Re-aim toward creek crossing
   ⚠ Needs setup: Clear SD card
```

If linked to a map object/candidate/task, show a compact source/link label, not database IDs.

## J5. Dependencies

On Packing and Gameplan rows provide:

`+ Needs setup`

Picker shows existing Prep items first.

Also provide:

`+ Add new setup item`

Creating a new Prep item from this picker must both:

1. create the Prep item;
2. attach the dependency;

in one action.

Shared Prep should be reused rather than duplicated.

If multiple items depend on one Prep item, the Prep row may show:

`Used by 3 items`.

Do not build a node graph.

---

# 13. PHASE K · AUTO-SAVE

Preflight must not have a general `Save checklist` button.

Actions persist immediately:

- check/uncheck;
- add item;
- edit title/note;
- reorder;
- add/remove dependency;
- required/optional;
- skip;
- objective edit.

Use optimistic UI.

Text editing may debounce briefly, e.g. 300–500 ms.

If persistence fails:

- restore last confirmed value;
- show a compact actionable error;
- do not silently lose edits.

This system exists to reduce "did I remember to save the thing that helps me remember?" friction.

---

# 14. PHASE L · COMPLETED-NOISE REDUCTION

Completed Prep/Packing sections should collapse automatically when all required items are complete.

Example:

`✓ Prep / Setup · 5 ready`

Tap to reopen.

Provide one small view control:

- `All`;
- `Remaining`.

When departure blockers become small, defaulting the sheet view to Remaining is acceptable, but do not make completed items impossible to inspect.

No percent-complete dashboard.

---

# 15. PHASE M · START SEARCH INTEGRATION

Current `SearchSessionBar` calls `startSearch()` directly.

Change behavior:

`Start search` → opens Preflight.

If no draft/current outing exists:

```text
Tonight's plan

[ Build plan ]
[ Reuse last outing ]
[ Start without plan ]
```

If a draft exists, open it directly.

If ready:

`[ Start search ]`

If blockers remain:

```text
2 setup blockers
1 item not packed

[ Review blockers ]
[ Start anyway ]
```

Do not hard-disable departure.

## M1. Starting with a plan

`POST /api/surveyor/outings/{plan_id}/start` should transactionally:

1. validate plan is startable;
2. create a `SurveyorSearchSession`;
3. link its ID to the outing plan;
4. set outing status = `active`;
5. record Surveyor events;
6. return plan + session.

Allow an explicit `start_with_blockers=true` flag.

If starting with blockers, record an event such as:

`outing_started_with_blockers`.

## M2. Start without plan

Keep the existing direct session endpoint/path available.

The planning system is an aid, not a gate.

---

# 16. PHASE N · REUSE LAST OUTING

Implement one-tap:

`Reuse last outing`

Clone:

- title/objective as a starting point;
- item text/notes/order;
- dependencies;
- linked map-object/task/candidate references when still valid;
- required/optional flags;
- time hints.

Reset:

- all item statuses to pending;
- completed_at;
- session link;
- plan status to draft.

Never copy yesterday's `ready`, `packed` or `done` state into today.

If a linked source entity no longer exists, keep the text but mark the reference unavailable rather than failing the clone.

---

# 17. PHASE O · ADD TO OUTING FROM EXISTING WORK

Add a low-friction `Add to outing` action where Archie Radar already knows something may need field work.

Priority integrations:

1. Surveyor map object inspector;
2. open SurveyorTask/follow-up;
3. Candidate Case Workspace;
4. trail camera inspector/context.

Default target:

- current draft outing, if one exists;
- otherwise create a draft outing and add the item.

Examples:

Trail camera:
`Check Raccoon Creek camera`

Needs-search zone:
`Search abandoned-house edge`

Candidate:
`Check candidate location`

Follow-up task:
use task title.

Automatically preserve the source reference.

Do not force the user to retype a location or title that already exists.

---

# 18. PHASE P · TASK / OUTING SOURCE-OF-TRUTH RULE

Do not create two independent follow-up states for the same action.

If a Gameplan item was created from an open `SurveyorTask`:

- show `From follow-up`;
- completing the Gameplan item should complete the linked task in the same backend operation/transaction;
- UI should make this behavior visible, e.g. `Done · completes follow-up`.

Do not auto-complete tasks when a Prep or Packing item is completed.

If a task is later reopened, do not rewrite historical outing completion. The task may be added to a future outing again.

---

# 19. PHASE Q · ACTIVE FIELD MISSION STRIP

Once the session starts, Prep and Packing should recede.

Show a compact active mission strip over Surveyor:

```text
NEXT
2 / 5 · Check Raccoon Creek camera
Pull SD · swap battery

[ Map ]   [ Done ]   [ Skip ]   [ Plan ]
```

Rules:

- next = first pending Gameplan item by position;
- Done completes it and advances;
- Skip marks it skipped and advances;
- Plan opens full outing;
- Map focuses the linked map object/candidate when a usable location exists;
- if no location exists, hide Map rather than disabling a mystery button.

When no pending Gameplan remains:

`Gameplan complete`

Do not auto-end the search session.

Do not auto-optimize/reorder the route.

---

# 20. PHASE R · OPTIONAL TIME HINTS

Gameplan items may have a lightweight optional `time_hint`.

Examples:

- `Dusk`;
- `10:30 PM`;
- `Late`;
- `Anytime`.

This is display context, not scheduling infrastructure.

Do not require exact times.

Do not create reminders/automations from these fields in this slice.

---

# 21. PHASE S · ENDING A SEARCH

Ending a search session must not erase unfinished Gameplan items.

When the linked session ends:

- outing status becomes `completed`;
- completed/skipped/pending item states remain historical facts;
- show how many Gameplan items remain unfinished.

Do not force another questionnaire solely to preserve them.

For the next outing, surface:

`2 unfinished from last outing · Continue`

One tap should create a new draft containing the unfinished Gameplan items and any Prep dependencies still relevant.

This is separate from `Reuse last outing`, which copies the whole structure.

Suggested endpoint:

`POST /api/surveyor/outings/{plan_id}/continue-unfinished`

The new outing resets copied item state to pending.

---

# 22. PHASE T · PACKING KITS ARE DEFERRED

Named kits such as:

- Camera kit;
- Night kit;

are a useful future chunking mechanism, but do not block this slice.

Do NOT build a full inventory subsystem now.

Record as a Slice 9 polish candidate if field use shows repeated packing-list duplication.

---

# 23. PHASE U · DRAFT / FAILURE BEHAVIOR

Outing plans are server-persisted drafts, so do not duplicate the full plan into the existing local Surveyor draft-recovery system.

Frontend should tolerate:

- refresh;
- navigating away and back;
- mobile browser suspension.

On load:

- fetch current draft outing;
- fetch active outing linked to active search session if one exists.

If backend is temporarily unavailable during a checkbox action:

- retain the user-visible attempted state only while retry/error handling is clear;
- do not falsely indicate persistence.

---

# 24. PHASE V · EVENT HISTORY

Record meaningful outing events in `SurveyorEvent`.

At minimum:

- outing_created;
- outing_item_added;
- outing_item_completed;
- outing_item_skipped;
- outing_dependency_added;
- outing_started;
- outing_started_with_blockers;
- outing_completed;
- outing_abandoned;
- outing_reused;
- outing_continued.

Do not create a noisy event for every character typed into a note/title.

---

# 25. PHASE W · RESPONSIVE UX

## Desktop

Preflight may be a centered field sheet or right-side panel, but all three sections remain on one scroll surface.

## Portrait mobile

This is the primary design target.

Requirements:

- full-width bottom sheet;
- sticky readiness header;
- 44px minimum row/action targets;
- completed sections collapse;
- dependency picker opens as a small nested sheet;
- no horizontal scroll;
- active mission strip remains compact above the footer controls.

## Phone landscape

Use a side sheet where practical so the map remains usable.

Do not let preflight obscure the entire map unless the user explicitly opens the full plan.

---

# 26. PHASE X · FILE ORGANIZATION

Backend:

```text
backend/app/surveyor/outings.py
backend/app/models.py
backend/app/schemas.py
backend/tests/test_surveyor_outings.py
```

Frontend:

```text
frontend/src/components/surveyor/PreflightSheet.vue
frontend/src/components/surveyor/OutingSection.vue
frontend/src/components/surveyor/OutingItemRow.vue
frontend/src/components/surveyor/OutingDependencyPicker.vue
frontend/src/components/surveyor/ActiveMissionStrip.vue
frontend/src/surveyor/outings.js
```

Keep outing-specific logic out of the already-large `SurveyorView.vue` as much as practical.

---

# 27. BACKEND TESTS

Add focused tests.

## Queue / 24Pet

1. 68 match score remains above 31 despite larger trait boost on 31.
2. default Archie selections do not double-resort smart order.
3. current-location text/distance/bearing/map use the same record.
4. location precision is not hardcoded.
5. `/ViewAnimals/` classifies as search_results.
6. exact 24Pet detail link must correspond to the same Animal ID.
7. request-level `Inactive` does not mark displayed animal inactive.
8. legacy Chatham source can derive Chatham holder context.

## Outings

9. create plan.
10. create Prep/Packing/Gameplan items.
11. reject dependency whose source is not Prep.
12. reject cross-plan dependency.
13. shared Prep blocker is counted once.
14. optional unfinished item does not block departure.
15. unfinished Gameplan itself does not block departure.
16. unfinished Prep dependency for a required Gameplan item blocks departure.
17. completing Prep clears the dependency blocker.
18. reuse clones structure but resets all state.
19. continue-unfinished copies only unfinished Gameplan work plus required dependency context.
20. starting outing creates and links a SearchSession.
21. start-with-blockers requires explicit override.
22. completing Gameplan item linked from SurveyorTask completes that task.
23. completing Packing item does not complete linked task.
24. abandoning an outing preserves history.
25. new tables are created additively without destructive schema reset.

Keep tests local and deterministic.

---

# 28. FRONTEND / MANUAL ACCEPTANCE

No new frontend test framework is required solely for this slice if the repo does not already use one.

Run the frontend build and do focused manual acceptance.

## Review queue

Verify:

- smart ranking no longer behaves strangely under defaults;
- candidate location display and Map action agree;
- internal source record ID is details-only;
- 24Pet fallback URL is not called Original.

## Preflight

Create:

```text
PREP
○ Charge camera batteries
○ Clear SD cards

PACKING
○ Camera bag
○ Flashlight

GAMEPLAN
1. Check Raccoon Creek camera
2. Check Blue Lagoon camera
3. Dusk pass
```

Link:

- Camera bag → Charge camera batteries;
- Raccoon Creek camera → Charge camera batteries;
- Blue Lagoon camera → Clear SD cards.

Expected:

- readiness shows unresolved blockers;
- dependencies are visible where they matter;
- shared Charge-camera-batteries Prep appears only once;
- checking Charge camera batteries updates all dependent rows immediately;
- Packing/Gameplan rows remain manually actionable even when dependency unfinished;
- no general Save button.

## Departure

With blockers:

- Start search shows blockers;
- Start anyway remains available.

With everything required ready:

- UI says `Ready to go`;
- Start search starts/links a session.

## Active field use

- mission strip shows first pending Gameplan item;
- Done advances;
- Skip advances;
- Map focuses linked object;
- Plan opens full outing;
- screen remains usable in portrait and landscape.

## Session end

End with two Gameplan items unfinished.

Expected:

- session can finish normally;
- plan preserves unfinished history;
- next planning entry offers `2 unfinished from last outing · Continue`;
- Continue creates a fresh draft rather than silently reusing old completion state.

---

# 29. PERFORMANCE / FRICTION TARGETS

This slice is more about cognitive latency than benchmark latency.

Targets:

- opening Preflight from Surveyor should feel immediate on LAN;
- checkbox completion should update optimistically with no full-page reload;
- adding a dependency should not require leaving the current item;
- Start Search should require at most one extra tap when already ready;
- if no plan is desired, Start without plan remains a direct escape hatch;
- active field mode exposes the next action without opening a full sheet.

Do not add a heavy client state-management dependency for this.

---

# 30. IMPLEMENTATION ORDER

Use this order:

1. fix smart queue ordering;
2. fix candidate current-location/map action;
3. fix 24Pet link classification/detail extraction/request-level inactive handling;
4. add persistent Surveyor Layers control;
5. fix MapLibre numeric-null warning;
6. add outing models/schemas/router;
7. implement readiness calculation;
8. implement outing CRUD + dependencies + reorder;
9. implement reuse / continue-unfinished;
10. implement PreflightSheet and three sections;
11. implement inline dependency picker;
12. replace direct Start Search flow with preflight entry;
13. implement transactional outing→SearchSession start;
14. add `Add to outing` from map object/task/candidate/camera;
15. implement task-completion linkage;
16. implement active mission strip;
17. session-end carry-forward UX;
18. responsive polish;
19. focused tests;
20. manual acceptance;
21. commit/push to `main`;
22. if and only if the execution environment has device access, deploy to `dietpi` per `AGENTS.md`; otherwise report deployment not attempted from that environment.

---

# 31. RECOMMENDED COMMITS

Suggested sequence:

1. `fix(candidates): stabilize review order location and 24pet links`
2. `fix(surveyor): expose persistent layers control and sanitize map properties`
3. `feat(surveyor): add outing plan and readiness model`
4. `feat(surveyor): add prep packing and gameplan preflight`
5. `feat(surveyor): integrate outing plans with field sessions`
6. `feat(surveyor): add active mission strip and unfinished carry-forward`
7. `test(surveyor): cover outing readiness dependencies and session linkage`

Do not force a commit boundary if the implementation naturally combines two tiny adjacent changes.

---

# 32. EXPLICITLY DEFER TO SLICE 8

Do not implement in this slice:

- iNaturalist wildlife;
- NC OneMap hydrography;
- NWI wetlands;
- MRLC backend WMS/tile proxy;
- environmental context inspector;
- public-observation concentration;
- predator-risk scoring;
- automatic search-route planning;
- automatic camera-placement recommendations.

Slice 8 will consume the cleaned-up persistent Layers control added here.

---

# 33. EXPLICITLY DEFER TO SLICE 9 / LATER

Do not implement now:

- packing inventory database;
- named packing kits unless a very small implementation falls out naturally;
- consumable counts;
- automatic restock;
- AI-generated outing plans;
- Gantt/calendar planning;
- generic dependency graphs;
- route optimization;
- mandatory duration estimates;
- automation/reminder scheduling from `time_hint`.

---

# 34. DEFINITION OF DONE

Slice 7 is complete only when:

## Review correctness

- smart order cannot let small client trait boosts swamp large score differences;
- default Archie traits are not double-counted;
- candidate map/location/distance/bearing use one coherent current-location record;
- review actions remain above details;
- technical source record IDs are details-only;
- 24Pet saved searches are not labeled Original;
- exact animal links are used only when verified to match that animal;
- request-level inactive state is not mistaken for animal inactivity.

## Surveyor shell

- persistent Layers control is visible desktop / portrait / landscape;
- initial layer visibility is deterministic;
- MapLibre numeric-null warning is gone.

## Field readiness

- one outing plan contains Prep / Packing / Gameplan;
- Prep dependencies can be attached to Packing/Gameplan rows inline;
- shared Prep work is not duplicated;
- readiness shows unresolved work, not a percentage;
- readiness is derived, not stored as stale plan state;
- all routine edits auto-save;
- Start Search opens Preflight;
- Start without plan remains available;
- blockers warn but never hard-lock departure;
- Reuse last outing resets completion state;
- Add to outing works from existing field entities;
- active search exposes the next Gameplan item;
- Done/Skip advances the mission strip;
- task-linked Gameplan completion resolves the linked task;
- unfinished Gameplan survives session end and can be continued next time;
- portrait / landscape / desktop are usable.

## Quality

- focused backend tests pass;
- frontend build succeeds;
- manual acceptance passes;
- changes are pushed to `main`;
- deployment is attempted only from environments that actually have device access.

---

# 35. END-OF-RUN REPORT

Return:

```text
SLICE 7 STATUS

Base SHA:
Final SHA:

CORRECTIONS
Smart review order:
Current-location/map consistency:
24Pet exact/fallback links:
24Pet request-level inactive handling:
Persistent Layers control:
MapLibre numeric warning:

OUTING MODEL
Plan:
Items:
Dependencies:
Readiness:
Reuse:
Continue unfinished:

PREFLIGHT
Prep / Setup:
Packing:
Gameplan:
Dependency UX:
Auto-save:
Remaining mode:

SESSION INTEGRATION
Start flow:
Start anyway:
Start without plan:
SearchSession linkage:
Mission strip:
Map focus:
Task completion linkage:
Session end carry-forward:

RESPONSIVE
Portrait:
Landscape:
Desktop:

TESTS:
FRONTEND BUILD:
MANUAL ACCEPTANCE:

DEPLOYMENT
main commit:
DietPi deployment:
verification:

KNOWN LIMITATIONS:
```

If the execution environment does not have device access, use:

`DietPi deployment: not attempted from this environment`

Do not treat that as an implementation failure.
