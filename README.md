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

PawBoost, Orange County, regional 24PetConnect, APS Durham community reports, Wake County, Pet911, Petkey, plus the Facebook manual/capture bridge. Petco Love remains setup-dependent on approved API access.

## Notes

The map uses MapLibre/OpenFreeMap for base geography and Census TIGERweb for county/state context. City-level approximate report coordinates remain visibly approximate; Archie Radar does not invent exact sighting locations.
