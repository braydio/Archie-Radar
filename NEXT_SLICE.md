# NEXT SLICE TASK PACKET

## Archie Radar v1 · Slice 7B
### Preflight Hardening + Candidate/Map Correctness

**Base:** `main` at `98a23466ef0b949034d64e43bbce1aca61b79b36`

This packet is corrective and incremental. Do not rebuild the outing/preflight system. Review the current implementation first, then harden what landed in `98a23466` and finish the correctness items that still remain from the prior packets.

The goal is to make the newly landed Prep / Packing / Gameplan flow dependable enough for real field use, while closing the candidate-order, location, 24PetConnect, Surveyor Layers, and MapLibre issues that are still present in current `main`.

Do **not** begin External Environmental Intelligence in this packet. That remains the next numbered feature slice after this hardening pass.

---

# 1. CURRENT STATE VERIFIED IN MAIN

The following has landed and should be preserved:

- additive outing tables:
  - `SurveyorOutingPlan`
  - `SurveyorOutingItem`
  - `SurveyorOutingDependency`
- `backend/app/surveyor/outings.py`
- one-screen Prep / Packing / Gameplan UI in `OutingPreflight.vue`
- inline Prep dependencies
- Add & link setup item
- Reuse last outing
- Add to outing from Surveyor objects/tasks/candidate map inspector
- mission strip during active search
- optional time hints
- All / Remaining mode
- responsive styling
- initial outing tests

The implementation is a good first pass, but current `main` still contains correctness gaps and several behaviors from the prior packet were not implemented.

---

# 2. P0 OUTING MODEL CORRECTIONS

## 2.1 Readiness must be derived, never stored

Current code still uses:

```python
PlanStatus = Literal["draft", "ready", "active", "completed", "abandoned"]
```

and `_refresh_readiness_status()` writes `ready` into `SurveyorOutingPlan.status`.

Remove persisted `ready` semantics.

Allowed plan lifecycle states:

```text
draft
active
completed
abandoned
```

Readiness is always computed from items/dependencies.

Existing databases may already contain `status = "ready"` from `98a23466`. Normalize those legacy rows safely to `draft` without rebuilding or deleting the database.

Do not add a schema migration framework solely for this. A small idempotent normalization during application startup or outing initialization is sufficient.

## 2.2 Correct readiness semantics

Current `_readiness()` effectively treats every required item not completed as blocking and does not expose dependency-specific state.

Return at least:

```json
{
  "ready_to_leave": false,
  "prep_remaining": 1,
  "packing_remaining": 1,
  "dependency_blockers": 1,
  "skipped_required": 0,
  "waived_dependency_count": 0,
  "gameplan_total": 4,
  "gameplan_remaining": 4,
  "packed_items": 2,
  "blocking_prep_item_ids": [12]
}
```

Rules:

- required Prep with `status == pending` blocks departure;
- required Packing with `status == pending` blocks departure;
- pending Gameplan items do **not** block departure;
- optional items never block departure;
- a skipped item is an explicit user waiver and does not remain a hard blocker;
- if a required Prep item is skipped, expose it in `skipped_required`;
- if a dependent Packing/Gameplan item relies on a skipped Prep item, expose that in `waived_dependency_count`;
- do not call the plan unconditionally "fully prepared" when setup was explicitly skipped. UI may say:
  - `Ready to go · 1 setup item skipped`
  instead of silently hiding the waiver;
- count a shared unfinished Prep dependency once, not once per dependent item.

Keep backward-compatible aliases only if needed temporarily by the frontend, but migrate UI to the explicit field names above.

## 2.3 Do not conflate "skipped" with "completed"

A skipped item must stay visibly skipped.

Do not render it with the same green/checkmark semantics as completed.

Recommended display:

- completed: checkmark;
- skipped: muted `Skipped` state;
- pending: normal unchecked state.

For Prep dependency display:

- completed dependency: `Setup ready`;
- pending dependency: `Needs setup`;
- skipped dependency: `Setup skipped`.

---

# 3. P0 TRANSACTIONAL START FLOW

Current frontend starts a `SurveyorSearchSession` first, then PATCHes the outing plan to active.

That can create an orphan active session if the second request fails.

Move linked start behavior to the backend.

Add:

```text
POST /api/surveyor/outings/{plan_id}/start
```

Payload:

```json
{
  "method": "walking",
  "start_with_blockers": false
}
```

In one database transaction:

1. load plan;
2. reject abandoned/completed/active plan;
3. compute readiness;
4. if pending blockers exist and `start_with_blockers == false`, return 409 with readiness details;
5. create `SurveyorSearchSession`;
6. set plan `status = active`;
7. set `search_session_id`;
8. record SurveyorEvent;
9. commit once;
10. return:
   - updated plan;
   - created session.

If blockers were explicitly overridden, record a distinct `outing_started_with_blockers` event.

`Start without plan` may continue to use the existing direct session endpoint.

Frontend must use the outing start endpoint whenever a plan exists.

---

# 4. P0 OUTING COMPLETION / HISTORY

Current `finishSearch()` changes a linked outing back to `draft` or `ready` when Gameplan work remains.

That is incorrect historical behavior.

An outing describes what was planned for one actual field outing. When its linked search session ends:

- the outing becomes `completed`;
- its completed/skipped/pending item state remains exactly as it was;
- unfinished Gameplan items remain visible as unfinished historical work;
- `completed_at` is set;
- it must no longer be returned as the current draft outing.

Add a backend operation such as:

```text
POST /api/surveyor/outings/{plan_id}/complete
```

or make the existing session-finish path complete the linked outing transactionally.

Prefer backend ownership of lifecycle changes over frontend PATCH choreography.

Do not mutate unfinished items merely because the outing ended.

---

# 5. CONTINUE UNFINISHED

The prior packet required this and it did not land.

Add:

```text
POST /api/surveyor/outings/{plan_id}/continue-unfinished
```

Create a fresh `draft` plan containing:

- only unfinished Gameplan items from the completed outing;
- required Prep items that those copied Gameplan items depend on;
- dependencies remapped to the new item IDs;
- preserved map/task/candidate references when still valid;
- pending state for all copied items.

Do not copy completed Packing rows by default.

If unfinished work has no Prep dependency, do not drag unrelated Prep items into the new outing.

Frontend entry:

```text
2 unfinished from last outing · Continue
```

One tap creates/opens the new draft.

---

# 6. REUSE LAST OUTING CORRECTIONS

Current `reuse-last` searches the newest non-abandoned plan, which can accidentally clone the current draft/active outing.

Change "last outing" semantics to the most recent **completed** outing.

If no completed outing exists, return a clear 404/empty state.

Reuse copies:

- title/objective;
- method;
- all item structure;
- order;
- dependencies;
- source references;
- required/optional flags;
- time hints.

Reset:

- plan status to draft;
- search session link;
- item statuses to pending;
- completed timestamps.

If an old source reference no longer exists, keep the copied text and omit/clear only the broken reference. Do not fail the whole reuse operation.

---

# 7. CURRENT OUTING SELECTION

Current lookup should be deterministic.

Priority:

1. active plan linked to an unfinished active SearchSession;
2. newest draft plan;
3. none.

Do not let a newer draft hide an actually active outing.

There should be no persisted `ready` state after normalization.

When the frontend has an active session, the mission strip must use the outing linked to **that session**, not simply whichever plan happened to be returned by `/current`.

If useful, add:

```text
GET /api/surveyor/outings/by-session/{session_id}
```

or make `/current` active-session aware.

---

# 8. TASK-LINKED GAMEPLAN COMPLETION

Current outing items can store `surveyor_task_id`, but completing the Gameplan item does not complete the linked task.

Implement this in the backend transaction for item completion.

When:

- item.section == `gameplan`;
- item has `surveyor_task_id`;
- item changes from pending/skipped -> completed;

then:

- mark the linked open task completed;
- set task `completed_at`;
- record the normal task completion event;
- record outing item completion.

Do not auto-complete linked tasks from Prep or Packing items.

If the Gameplan item is later changed back to pending, do **not** silently reopen the historical task. Reopening a task remains an explicit task action.

Frontend label when linked:

`Done · completes follow-up`

Do not expose `follow-up #123` as the primary human label.

---

# 9. ATOMIC ADD-AND-LINK PREP

Current `Add & link` performs:

1. create Prep item;
2. second request to set dependency.

If request 2 fails, the user gets an orphan Prep row that was not linked.

Add one atomic backend operation, for example:

```text
POST /api/surveyor/outings/items/{dependent_item_id}/create-prep-dependency
```

Payload:

```json
{
  "title": "Charge camera batteries"
}
```

Transaction:

1. validate dependent item belongs to Packing/Gameplan;
2. create Prep row in same plan;
3. create dependency;
4. commit once;
5. return updated plan.

Use this from `Add & link`.

---

# 10. ATOMIC REORDER

Current reorder swaps positions through two independent PATCH calls.

That can leave duplicate/partial positions if one request succeeds and the second fails.

Add a backend reorder endpoint:

```text
POST /api/surveyor/outings/{plan_id}/reorder
```

Payload may be:

```json
{
  "section": "gameplan",
  "ordered_item_ids": [21, 18, 24]
}
```

Validate:

- all IDs belong to this plan;
- all IDs belong to the supplied section;
- no duplicates;
- list contains exactly the items being reordered.

Set contiguous positions `0..n-1` in one transaction.

Frontend move-up/move-down should call this endpoint once.

---

# 11. CONSISTENT MUTATION RESPONSES

Current outing mutations return inconsistent shapes:

- create item returns full plan;
- dependency update returns full plan;
- patch item returns one item and then the frontend refetches `/current`.

Standardize outing mutations to return the updated full plan.

At minimum:

- create item;
- patch item;
- set dependencies;
- atomic add/link;
- reorder;
- complete/skip item.

This allows the frontend to update readiness and dependency state from one response without a second `GET /current`.

Remove the current "PATCH item then fetch /current" pattern.

Benefits:

- fewer requests;
- no race against a different current plan;
- simpler optimistic rollback;
- correct readiness immediately.

---

# 12. OUTING EVENT HISTORY

Current outing implementation does not record the event history specified previously.

Use existing `SurveyorEvent`.

Record meaningful state changes:

- `outing_created`;
- `outing_item_added`;
- `outing_item_completed`;
- `outing_item_skipped`;
- `outing_dependency_added`;
- `outing_started`;
- `outing_started_with_blockers`;
- `outing_completed`;
- `outing_abandoned`;
- `outing_reused`;
- `outing_continued`.

Do not create an event for each character while editing title/notes.

---

# 13. HUMAN SOURCE LABELS

Current preflight shows technical text such as:

`Linked field item · object #42`

or:

`follow-up #17`.

Replace these with useful human context.

Outing item output should include a small resolved source object, for example:

```json
{
  "linked_context": {
    "kind": "trail_camera",
    "label": "Raccoon Creek camera",
    "focusable": true
  }
}
```

Examples:

- `Trail camera · Raccoon Creek`;
- `Needs-search zone · Abandoned-house edge`;
- `Follow-up · Check creek camera`;
- `Candidate · Animal ID A016828`.

Do not expose internal IDs unless in advanced/debug details.

---

# 14. MISSION STRIP FOCUS CORRECTIONS

Current mission strip always renders `Map` for a pending Gameplan item.

Only render Map when there is a usable focus target.

Focusable:

- linked map object with valid geometry/centroid;
- linked CandidateCase with usable current map location.

Not focusable:

- task with no spatial reference;
- plain text item.

If source reference exists but cannot currently be resolved, show a small `Location unavailable` note in the full plan, not a dead Map button.

Candidate focus must use the case's coherent current location fields.

Validate coordinates with `Number.isFinite` before `flyTo`.

---

# 15. ADD TO OUTING FROM CANDIDATE CASE WORKSPACE

The candidate map inspector has Add to outing, but `CandidateCaseView.vue` still lacks it.

Add a clear action near:

`Open location in Surveyor`

such as:

`＋ Add to outing`

Behavior:

- use current draft outing if present;
- otherwise create a draft;
- create a Gameplan item;
- link `candidate_case_id`;
- default title should prefer useful external identity:
  - `Check candidate A016828`
  - fallback `Check candidate case`;
- note/location context may be included, but do not duplicate large source descriptions.

This action should not require navigating to Surveyor first.

---

# 16. PREFLIGHT UI HARDENING

Keep the current single-screen structure.

Do not redesign into separate pages.

Required refinements:

## 16.1 Summary

Use derived fields.

Examples:

`2 setup blockers · 1 item not packed`

`Ready to go`

`Ready to go · 1 setup item skipped`

Do not display a percentage.

## 16.2 Dependencies

For each dependent item distinguish:

- `Needs setup: Charge battery`;
- `Setup ready`;
- `Setup skipped: Charge battery`.

## 16.3 Completed section collapsing

Current behavior is acceptable. Preserve it.

## 16.4 Remaining mode

Preserve All / Remaining.

Skipped items should remain visible in Remaining unless the user explicitly wants "pending only", because skipped items are useful context.

## 16.5 Start choices

When pending blockers exist:

- `Review blockers`;
- `Start search anyway`.

When no pending blockers:

- `Start search`.

If setup has been skipped but no pending blockers remain:

- allow normal Start search;
- keep the skipped-warning visible.

`Start without plan` stays available only in the no-plan state.

---

# 17. SEARCH SESSION END UX

After saving the search:

- linked outing becomes completed;
- mission strip disappears because session is no longer active;
- unfinished count is preserved.

Next time Preflight opens with no draft:

show, when applicable:

`2 unfinished from last outing · Continue`

Then:

- `Continue unfinished`;
- `Reuse last outing`;
- `Build plan`;
- `Start without plan`.

Do not automatically create a new draft without user action.

---

# 18. P0 CANDIDATE REVIEW ORDER STILL UNFIXED

Current `CandidatesView.clientPrioritize()` still sorts by client trait boost before match score.

Fix now.

Rules:

- backend `sort=smart` is authoritative;
- if applied prioritization traits equal Archie defaults, do not client-resort;
- custom prioritization only tie-breaks inside a narrow score band.

Recommended order for custom prioritize:

1. `Math.floor(match_score / 10)` descending;
2. usable real photo before no-photo;
3. custom trait boost descending;
4. exact match score descending;
5. meaningful event time descending.

A 68 score must not fall below a 31 because of client boost.

Pure sort modes remain pure.

Add focused unit/helper coverage if practical. If frontend has no unit harness, extract comparator into a small pure module and test via a minimal JS check or cover backend ordering separately plus manual acceptance.

---

# 19. P0 CURRENT LOCATION STILL UNFIXED

Current `locateCandidate()` still uses:

- `post.latitude`;
- `post.longitude`;
- hardcoded `precision: "address"`.

Fix it.

All candidate location actions use `post.current_location`:

- map_latitude;
- map_longitude;
- location_text;
- precision;
- distance_from_home_miles;
- distance_is_approximate.

Bearing must be computed from those same coordinates.

If there is useful current-location text but no coordinates, use existing place-resolution behavior.

Do not mix one record's coordinates with another record's text.

---

# 20. CANDIDATE CARD CLEANUP STILL UNFIXED

Current collapsed card still shows:

`Current location · source record #...`

Move that to expanded details.

Current card still renders any source URL as:

`Original ↗`

This must be replaced by source-link-aware labels described in Section 21.

The large generic title should be suppressed/de-emphasized when it is only:

- Found cat;
- Shelter intake cat;
- Cat;
- Unknown.

Keep review actions before More details.

---

# 21. 24PETCONNECT LINK CORRECTNESS STILL UNFIXED

Current connector still:

- initializes `detail_url = source_url`;
- searches globally for links containing the Animal ID;
- uses the saved ViewAnimals URL when no exact detail URL exists;
- UI calls that URL Original.

Implement the previously specified link semantics:

```text
exact_detail
search_results
provider_home
unavailable
```

Persist/add raw metadata:

- `source_link_kind`;
- `listing_url`;
- `detail_url`.

Animal detail extraction:

- find the DOM region/card belonging to the current Animal ID;
- inspect only that region;
- accept official 24PetConnect detail URLs whose Animal ID matches;
- support actual observed detail patterns such as `/DetailsMain/<provider>/<animal-id>`;
- do not guess provider codes;
- do not pair one animal with another animal's link.

Legacy `/ViewAnimals/` rows classify as `search_results` at output time without requiring destructive reingest.

UI:

Exact:
`View on 24PetConnect ↗`

Fallback:
`Open 24PetConnect ↗`
plus
`Copy Animal ID`

Never label a saved search `Original`.

---

# 22. 24PET REQUEST-LEVEL INACTIVE IS NOT ANIMAL INACTIVE

The saved search page may say:

`Your request is currently Inactive`.

That is the state of the saved search request.

Do not use it as lifecycle evidence for every listed animal.

Only set an animal inactive when an animal-specific record/detail supports:

- reunited;
- adopted;
- listing closed;
- no longer active/available;
- equivalent animal-specific state.

A broken detail URL alone is not proof of inactivity.

A valid result row whose detail check fails should remain unknown/active-as-seen according to source-row semantics, not be removed solely because detail validation failed.

Add fixtures/tests for this exact distinction.

---

# 23. SURVEYOR LAYERS CONTROL STILL UNFIXED

`SearchSessionBar.vue` still has a plain Layers button inside `.surveyor-actions`.

Mobile CSS hides it.

Add a persistent map-level control inside `.surveyor-map-shell`.

Requirements:

- desktop visible;
- portrait visible;
- phone landscape visible;
- 44x44 minimum tap area;
- opens/closes LayerDrawer;
- does not require an active session;
- does not live under More.

Existing desktop header Layers button can remain.

Add click-away/backdrop behavior for LayerDrawer.

Do not add new external providers in this packet.

---

# 24. EXPLICIT LAYER VISIBILITY APPLICATION

Replace the current reactive timing trick with:

```js
function applyLayerVisibility() {
  ...
}
```

Call:

- after custom layers are created;
- when layer settings change.

This packet should leave the LayerDrawer ready for Slice 8 external-provider capability flags, but do not add dead controls now.

---

# 25. MAPLIBRE NULL-NUMBER WARNING

Audit all Surveyor GeoJSON passed to MapLibre.

Sanitize numeric style inputs, especially:

- task_count;
- urgent_count;
- overdue_count;
- camera heading/FOV/range;
- coordinates and centroids.

Use finite numbers or null-safe expressions such as `coalesce`.

Do not turn semantically unknown values into zero unless zero is a valid intended fallback for that property.

No production log spam.

Acceptance: no `Expected value to be of type number, but found null instead` warning during normal Surveyor load/use.

---

# 26. BACKEND TESTS

Expand `backend/tests/test_surveyor_outings.py`.

Add at least:

1. legacy `ready` status normalizes to draft.
2. readiness is not persisted as lifecycle status.
3. required pending Prep blocks.
4. required pending Packing blocks.
5. pending Gameplan does not block departure.
6. optional pending item does not block.
7. skipped required item is reported but does not remain a hard pending blocker.
8. skipped Prep dependency is reported as waived dependency.
9. shared Prep dependency counted once.
10. atomic start creates exactly one session and links plan.
11. start with blockers returns 409 without creating a session.
12. explicit blocker override starts and records state.
13. completing a linked outing marks it completed even with unfinished Gameplan.
14. completed outing no longer appears as current.
15. continue-unfinished copies only pending Gameplan + required Prep dependencies.
16. reuse-last selects completed outing, not current draft/active.
17. Gameplan completion completes linked open SurveyorTask.
18. Packing completion does not complete task.
19. atomic add-and-link leaves no orphan Prep item on validation failure.
20. reorder produces contiguous unique positions.
21. mutation responses return updated readiness/full plan.
22. candidate reference may be absent after reuse without failing entire clone.

Also add/extend 24Pet tests:

23. ViewAnimals classified search_results.
24. exact detail target must match Animal ID.
25. request-level inactive text does not mark animal inactive.
26. broken detail URL does not alone mark animal inactive.
27. known Chatham source context resolves correctly for legacy output.

Keep tests focused. Do not run the entire suite repeatedly during implementation.

---

# 27. FRONTEND MANUAL ACCEPTANCE

## Preflight

Create:

Prep:
- Charge camera batteries
- Clear SD card

Packing:
- Camera bag
- Flashlight

Gameplan:
- Raccoon Creek camera
- Blue Lagoon camera
- Dusk pass

Dependencies:

- Camera bag -> Charge batteries
- Raccoon Creek -> Charge batteries
- Blue Lagoon -> Clear SD card

Verify:

- shared Charge batteries blocker counted once;
- dependency labels update immediately;
- Add & link is atomic;
- reorder cannot produce duplicate order;
- skipped setup remains visible as skipped/waived;
- no general Save button;
- no technical object/task IDs dominate UI.

## Start

With blockers:
- normal Start does not accidentally create an orphan session;
- Start search anyway works with explicit override.

Without blockers:
- one Start action creates linked outing+session.

Start without plan still works.

## Active field mode

- mission strip belongs to the outing linked to current active session;
- Map only appears for focusable items;
- Done advances;
- linked task completes when corresponding Gameplan item completes;
- Skip advances and remains visibly skipped in plan.

## Finish

End search with 2 unfinished Gameplan items.

Verify:

- old outing status is completed;
- old plan remains historical;
- no old "ready" outing hijacks current preflight;
- next preflight offers Continue unfinished;
- Continue creates a fresh draft with only those stops + needed Prep dependencies.

## Candidate queue

Verify:

- a 68-signal candidate does not fall below a 31-signal candidate due to default client trait boost;
- location text/map/distance/bearing agree;
- collapsed card does not show internal source-record ID;
- saved 24Pet search links are not called Original.

## Surveyor layers

Verify Layers control on:

- desktop;
- portrait phone;
- phone landscape.

Verify no MapLibre null-number warning.

---

# 28. FILE BOUNDARIES

Prefer keeping outing-specific backend logic in:

`backend/app/surveyor/outings.py`

Do not move it back into the already-large `main.py`.

Frontend:

- keep `OutingPreflight.vue`;
- small helpers/components may be split if the file becomes harder to maintain;
- keep `SurveyorView.vue` orchestration thin.

If needed, add:

```text
frontend/src/surveyor/outings.js
frontend/src/components/surveyor/OutingMissionStrip.vue
frontend/src/components/surveyor/OutingItemRow.vue
```

Do not refactor merely for aesthetics if the current component remains clear.

---

# 29. IMPLEMENTATION ORDER

1. remove persisted ready status + legacy normalization;
2. fix readiness/skipped/dependency semantics;
3. transactional outing start;
4. correct outing completion lifecycle;
5. continue-unfinished;
6. reuse-last selection correction;
7. task-linked Gameplan completion;
8. atomic add-and-link Prep;
9. atomic reorder;
10. consistent mutation responses;
11. event history;
12. human linked-context labels;
13. mission-strip focus rules;
14. CandidateCase Workspace Add to outing;
15. preflight UI semantics;
16. candidate smart-order fix;
17. current-location fix;
18. candidate card cleanup;
19. 24Pet link/lifecycle fixes;
20. persistent Surveyor Layers control;
21. explicit layer visibility application;
22. MapLibre numeric sanitization;
23. focused backend tests;
24. frontend build;
25. manual acceptance;
26. push all changes to `main`;
27. deploy to DietPi only if the execution environment actually has device access, per `AGENTS.md`.

---

# 30. DO NOT IMPLEMENT YET

Defer until the next feature slice:

- iNaturalist;
- NC OneMap hydrography;
- NWI wetlands;
- MRLC backend tile proxy;
- environmental context inspector;
- wildlife concentration overlays;
- route optimization;
- automatic camera placement;
- AI-generated outing plans;
- packing inventory / consumable tracking;
- generic dependency graphs.

---

# 31. DEFINITION OF DONE

This packet is done when:

- no persisted ready lifecycle state remains;
- existing ready rows normalize safely;
- readiness correctly distinguishes pending, completed, skipped and dependency waivers;
- linked outing start is transactional;
- ending the search always completes the historical outing;
- unfinished work can be continued into a fresh draft;
- reuse-last cannot clone the current draft/active outing by mistake;
- Gameplan completion resolves linked SurveyorTask;
- Add & link and reorder are atomic;
- outing mutations return consistent fresh plan/readiness state;
- mission strip is tied to the active session's outing;
- dead Map actions are hidden;
- CandidateCase Workspace supports Add to outing;
- candidate smart ordering is corrected;
- candidate location actions use current_location coherently;
- collapsed card provenance is cleaned up;
- 24Pet exact/search links are truthful;
- saved-search inactive state is not treated as animal inactivity;
- Layers is always discoverable on Surveyor;
- MapLibre numeric-null warning is gone;
- focused tests pass;
- frontend build passes;
- manual acceptance passes;
- changes are pushed to `main`.

---

# 32. END-OF-RUN REPORT

Return:

```text
SLICE 7B STATUS

Base SHA:
Final SHA:

OUTING CORRECTIONS
Derived readiness:
Legacy ready normalization:
Skipped/waived semantics:
Transactional start:
Completion lifecycle:
Continue unfinished:
Reuse last:
Task linkage:
Atomic add/link:
Atomic reorder:
Mutation response consistency:
Event history:
Human linked labels:
Mission strip:

CANDIDATE CORRECTIONS
Smart review order:
Current-location consistency:
Collapsed card cleanup:

24PETCONNECT
Exact detail links:
Search fallback labels:
Request-level inactive handling:
Legacy rows:

SURVEYOR
Persistent Layers control:
Layer visibility application:
MapLibre null warning:

TESTS:
FRONTEND BUILD:
MANUAL ACCEPTANCE:

DEPLOYMENT
main SHA:
DietPi deployment:

KNOWN LIMITATIONS:
```

If this environment cannot reach DietPi:

`DietPi deployment: not attempted from this environment`

Do not treat lack of device access as implementation failure.
