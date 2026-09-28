# Archie Radar v0.9

Archie Radar consolidates local lost/found cat reports into one review queue and map centered on the Archie search.

## v0.9 review-flow update

- Queue priority is ordinal: **#1 is highest priority and appears first**. Match-signal scores are separate and are not identity probabilities.
- Default Archie selections: orange, striped/tabby, short hair, male, neutered, white chest, no collar, not microchipped. White belly is **not** a default and no longer changes the backend match score.
- Default review distance is **25 miles**.
- Default date cutoff remains June 1, 2026, shown only in the filter date field (`On or after:`), not as its own dashboard button.
- Filter edits are staged. Use **Apply Selections**, **Clear Selections**, or **Apply Defaults**. Clicking outside or Collapse closes the panel without applying staged edits.
- Non-default applied filters appear as a compact strip on the main page.
- Body-part filters now include white chest, belly, paws/feet, and face/muzzle.
- Source cards start collapsed and active automated sources can be refreshed individually.
- Candidate cards emphasize time since found/sighted before the calendar date and avoid midnight-heavy timestamps in the main panel. Full timestamps and parsed traits live in **Full parsed details**.
- Source posting date remains distinct from the date Archie Radar first saw the listing.
- Map starts collapsed. Candidate pins use queue rank (`#1`, `#2`, …). Clicking a cluster opens a list of the reports represented by that cluster.
- Map probe is now linked with an orange line, endpoint halo, label, and matching HUD indicator.
- Census boundary loading no longer blocks the map and times out quickly when unavailable.
- 24PetConnect detail pages are checked for inactive/closed/reunited/adopted records when a detail URL is available.

## Upgrade from v0.8

Back up your current directory, then extract the upgrade package over it:

```bash
cd /path/to/archie-radar
cp -a . ../archie-radar-v0.8-backup-$(date +%Y%m%d-%H%M)
unzip -o /path/to/archie-radar-v0.9-upgrade.zip -d .
docker compose build --no-cache
docker compose up -d
```

Do **not** run `docker compose down -v`; that would remove the persistent data volume.

If your existing `.env` explicitly contains the old radius, change it to:

```bash
ARCHIE_SEARCH_RADIUS_MILES=25
```

Then reload the web UI at `http://<server-ip>:5173`.

## Services

- Vue / Vite frontend: port 5173
- FastAPI backend: port 8000
- SQLite + persistent media in the Docker data volume

## Current source layer

PawBoost, Orange County, regional 24PetConnect, APS Durham community reports, Wake County, Pet911, Petkey, plus selected Facebook groups. Petco Love remains setup-dependent on approved API access.

## Facebook selected-group collector

Facebook aggregation no longer depends on leaving your everyday browser open. Archie Radar runs a headless Chromium collector on the backend and only visits groups you explicitly enable.

One-time setup:

1. Rebuild/restart the backend so Playwright Chromium is installed.
2. In **Sources → Facebook**, choose **Connect Facebook once** to mint a short-lived helper pairing token.
3. Load the `browser-extension` folder as an unpacked Chromium extension while signed into Facebook.
4. In the helper popup, enter the Archie Radar API URL and the token, then choose **Connect & hand off session**.
5. Once Sources shows **Server session ready**, the ordinary browser can be closed. Manual and scheduled selected-group scans run on the Archie Radar server.

The helper never sends a Facebook password. The explicit handoff copies the current Facebook session cookies to the local Archie Radar server, where they are written to the configured storage-state file with restricted permissions. The collector does not browse arbitrary groups, profiles, member lists, or comments.

Docker defaults to an hourly selected-group sync. Configure with:

```bash
ARCHIE_FACEBOOK_SERVER_COLLECTOR_ENABLED=true
ARCHIE_FACEBOOK_SYNC_MINUTES=60
ARCHIE_FACEBOOK_SESSION_STATE_PATH=/data/facebook/storage-state.json
```

For a non-Docker backend install, run `python -m playwright install chromium` once after installing the package.

## Notes

The map uses MapLibre/OpenFreeMap for base geography and Census TIGERweb for county/state context. City-level approximate report coordinates remain visibly approximate; Archie Radar does not invent exact sighting locations.
