# Tasks: Dev B (Evgenii) — Δεδομένα & backend

Board for the Dev B track of [SPEC.md](SPEC.md). Workflow and rules: [`../../CLAUDE.md`](../../CLAUDE.md).
Base branch: `dev-b`. Every task: branch `agent/B<n>-<name>` in `.worktrees/B<n>`, merged into `dev-b` on Evgenii's
word. Code step on Claude (A-31): B1, B6, B8, B9 (`CLAUDE_STEPS=code agents/drive.sh B<n>`); the rest
fully in Antigravity. Cards get a full test list (like [TASKS_A.md](TASKS_A.md)) before they start.

Dev B owns (SPEC «Ιδιοκτησία αρχείων»): `web/js/api.js`, `web/mock/*`, `web/js/ui/{report,points,stoa,workstab}.js`,
the backend (`app/`, `tests/`, `scripts/`, `data/`). Existing routes don't change (SPEC rule); new ones are added.
The real routes vs the SPEC's short names: [SPEC.md, Παράρτημα](SPEC.md#παράρτημα-spec--υπάρχον-backend).

| Task | Phase | What | State |
|---|---|---|---|
| B0 Contracts + first mocks | 0 | Lock the SPEC contracts against the Παράρτημα; `web/mock/*` (env, access, works with 10–15 real works, transit, health, points, stoa) realistic enough for the demo; offline boundary + main roads for A1 | **merged** into `dev-b` |
| B1 `api.js` | 1 | Only door to the backend; live → `localStorage` cache → `mock/`; `source: live\|cache\|mock`; maps the real routes to SPEC shapes; offline report queue sent on `online` | **merged** into `dev-b` |
| B2 Works adapters | 2 | Διαύγεια + ΚΗΜΔΗΣ, join on ΑΔΑ/ΑΔΑΜ, curated geocoding; `/api/map/works` with every SPEC field | **merged** into `dev-b` |
| B3 `/api/map/transit` | 2 | ΟΑΣΑ telematics (buses), GTFS/OSM metro + suburban lines and stations | **merged** into `dev-b` |
| B4 On-duty pharmacies/hospitals | 2 | `/api/map/health` (A-33) | **merged** into `dev-b` |
| B5 Env grid | 2 | Open-Meteo forecast + air-quality on a grid over the Δήμος, `temp_c`, `aqi`, `pm25` per point | **merged** into `dev-b` |
| B6 Report flow «+» | 2 | `ui/report.js`; `/api/map/reports` with `category`, `work_id`, optional photo; plate blur; public location rounded ~10 m; points per SPEC rules | **merged** into `dev-b` |
| B7 Points pill + panel | 2 | `ui/points.js`, pulse + «+N»; SPEC rewards; `/points/redeem` (Nice) | **merged** into `dev-b` |
| B8 Stoa citations + flyTo | 2 | `/api/map/stoa_ask` with `citations[{label, lon, lat, kind}]`; `ui/stoa.js` | **merged** into `dev-b` |
| B9 Route cost per profile | 2 | wheelchair / stroller / cool from the same layers the map shows; `reasons[{text, layer, feature_id}]` | **merged** into `dev-b` |
| B10 Works tab (F8) | 3 | `ui/workstab.js`, crowdsourced progress | **merged** into `dev-b` |
| B11 Phase 4 integration & end-to-end demo rehearsal | 4 | Combine `dev-a` + `dev-b`, end-to-end tests of the 3-min demo script (`bootstrap`, `api.js`, all 4 Dev B HUD widgets + `bus` events, offline degradation) | **merged** into `dev-b` |
| B12 Cross-module backend wiring (`works_map` + `routing_map` + `map_reports`) | 4 | `works_map._open_reports` and `routing_map._open_reports` include `map_reports`; `route_cost.in_progress` supports B2 evidence-wrapped dates via `works_src.status_of` | **merged** into `dev-b` |
| B13 Service guide from the sandbox registry | 5 | `GET /api/map/services?category=` → the official municipal service for a report category (documents, cost, online link); `api.js serviceFor()` + `web/mock/services.json` | **merged** into `dev-b` |
| B14 Official POI layer | 5 | `GET /api/map/pois` → sandbox POIs as GeoJSON with `official: true`; `api.js pois()` + `web/mock/pois.geojson` | **merged** into `dev-b` (fix round: finite bbox, ≤ 5 categories) |
| B15 «Διορθώθηκαν κοντά σου» | 5 | `GET /api/map/resolved` → resolved sandbox requests as GeoJSON, hours to resolve, no personal fields; `api.js resolved()` | **merged** into `dev-b` (fix round: bad coords skipped, no negative hours, `source`, A-39) |
| B16 Backend backlog fixes | 6 | Athens-day points cap, reports outside the Δήμος → 422, routing `blocked`, duplicate reports not double-counted | **merged** into `dev-b` |
| B17 Frontend backlog fixes + service after report | 6 | `report.js` shows the official service (B13) after submit; Athens dates in points; mock filters in `api.js` | **merged** into `dev-b` (fix: http(s)-only service links) |

### B0: Contracts + first mocks (phase 0)
SPEC «Backend contracts», «Εξωτερικές πηγές» (Fallback column), «Offline fallback», «Demo script». Every file in
`web/mock/` has **exactly the SPEC response shape** of its endpoint, so `api.js` (B1) can return it as is, and is
realistic enough that the demo runs on it with the Wi-Fi off. Dev A builds against these files from now on.
**Files:** `web/mock/{env.json, access.geojson, works.geojson, transit.geojson, health.geojson, reports.geojson,
points.json, stoa.json, base.geojson, README.md}`, `scripts/build_mocks.py` (one-off builder; may read `data/` and download once
from OSM/Overpass or Διαύγεια, never at test time), `THIRD_PARTY.md` (data sources), `tests/test_B0_mocks.py`.
- Every file carries top-level `snapshot` (date) and `note` (where the data comes from, what is real, what is
  invented). GeoJSON is a `FeatureCollection` in WGS84 inside the Δήμος Αθηναίων bbox (lon 23.68–23.80,
  lat 37.95–38.03).
- `env.json`: GeoJSON points on a grid over the Δήμος (≥ 20), `temp_c`, `aqi`, `pm25`, `updated_at`; a visibly
  hotter/worse zone so the Δροσερότερη route has something to avoid.
- `access.geojson`: real OSM features (`kerb=lowered`, `wheelchair=*`, `ramp=yes`, `tactile_paving=yes`) around
  Σύνταγμα–Μοναστηράκι–Πλάκα; property `kind` ∈ {kerb_lowered, wheelchair, ramp, tactile_paving} plus the OSM id.
- `works.geojson`: 10–15 works, LineStrings on real streets, every contract field (`id, title, status, contractor,
  amount_contract_eur, amount_paid_eur, ada, adam, start_date, end_date, guarantee_end, reports_count`), `status` ∈
  {planned, in_progress, completed}. A work is real only if its ΑΔΑ was found on diavgeia.gov.gr (`source_url` set);
  otherwise `ada` starts with `SEED-` and `seed: true`. **Never** a made-up ΑΔΑ that looks real. At least one
  `in_progress` work lies on the Σύνταγμα → Μοναστηράκι walk (demo step 4).
- `transit.geojson`: `{lines, stations, buses}` (three FeatureCollections). Metro M1/M2/M3 + Προαστιακός lines
  in the centre with official colours (`color`, comment with source), stations with `name`, `lines[]`, `elevator`
  (bool or null if unknown), including Σύνταγμα and Μοναστηράκι; a few buses with `line`, `bearing`.
- `health.geojson`: points with `kind` ∈ {φαρμακείο, νοσοκομείο}, `name`, `address`, `phone`, `hours`,
  `specialties[]`, `on_duty` (bool); real hospitals of central Athens; pharmacies' on-duty flags marked invented in
  `note`. At least one on-duty pharmacy within 500 m of Σύνταγμα (demo step 5).
- `reports.geojson`: points with `category` (συμφόρηση / συμβάν / εμπόδιο / ζημιά / πρόοδος έργου), `created_at`,
  `confirmations`; coordinates rounded to 4 decimals (~10 m, SPEC «Privacy»); no ids of people, no photos.
- `points.json`: `{balance, district:{name, progress_pct, goal}, history:[{ts, delta, reason}], rewards:[{id, title,
  cost}]}`, deltas from SPEC «Κανόνες πόντων»; no `user_id`.
- `stoa.json`: `[{question, answer_md, citations:[{label, lon, lat, kind}]}]`, including the demo question «Ποιο
  φαρμακείο εφημερεύει κοντά μου;»; every citation `label` appears in `answer_md`.
- `base.geojson`: Δήμος boundary polygon (from the CKAN districts in `data/ckan/`) + a handful of main roads as
  LineStrings, for A1's offline style.

| Test | Given | Expected |
|---|---|---|
| `test_all_mock_files_exist_and_parse` | `web/mock/` | the 9 files exist and parse as JSON |
| `test_every_mock_has_snapshot_and_note` | each file (top level; for `stoa.json` a wrapper object is not allowed, so it lives in `web/mock/README.md`) | `snapshot` is an ISO date, `note` non-empty |
| `test_geojson_is_wgs84_in_athens` | every Feature in every GeoJSON file (incl. `transit` sub-collections) | all coordinates inside lon 23.68–23.80, lat 37.95–38.03 |
| `test_env_points_have_contract_fields` | `env.json` | ≥ 20 Points, each with numeric `temp_c`, `aqi`, `pm25` and ISO `updated_at` |
| `test_env_has_hot_zone` | `env.json` | max `temp_c` − min `temp_c` ≥ 2 |
| `test_access_kinds_present` | `access.geojson` | each of the 4 kinds appears at least once; every feature has an OSM id |
| `test_works_count_and_fields` | `works.geojson` | 10–15 features, all 12 contract fields present, `status` in the allowed set |
| `test_works_money_and_dates_consistent` | each work | `amount_paid_eur` ≤ `amount_contract_eur` when both known; `guarantee_end` ≥ `end_date` when both known |
| `test_works_ada_real_or_seed` | each work | either `source_url` starts with `https://diavgeia.gov.gr/` or (`ada` starts with `SEED-` and `seed` is true) |
| `test_works_on_demo_route` | Σύνταγμα [23.7348, 37.9755] → Μοναστηράκι [23.7257, 37.9761] | ≥ 1 `in_progress` LineString within 150 m of that segment |
| `test_transit_has_three_collections` | `transit.geojson` | keys `lines`, `stations`, `buses`, each a FeatureCollection, each non-empty |
| `test_transit_lines_have_colours` | metro/suburban lines | every line has `name` and a `#rrggbb` `color` |
| `test_transit_demo_stations` | stations | Σύνταγμα and Μοναστηράκι present; `elevator` is bool or null |
| `test_health_fields_and_kinds` | `health.geojson` | both kinds present; `name, address, phone, hours, specialties, on_duty` on every feature |
| `test_health_on_duty_near_syntagma` | pharmacies with `on_duty` true | ≥ 1 within 500 m of Σύνταγμα |
| `test_reports_rounded_and_anonymous` | `reports.geojson` | coordinates have ≤ 4 decimals; no property named like `user`, `token`, `email`, `photo` |
| `test_points_contract_and_sum` | `points.json` | contract keys; `0 ≤ progress_pct ≤ 100`; `balance` = sum of `history[].delta`; no `user_id` |
| `test_stoa_citations_in_answer` | `stoa.json` | every citation `label` occurs in its `answer_md`; every citation has numeric `lon`, `lat` |
| `test_stoa_pharmacy_demo_question` | the «Ποιο φαρμακείο εφημερεύει κοντά μου;» entry | its first citation is within 20 m of an on-duty pharmacy in `health.geojson` |
| `test_base_has_boundary_and_roads` | `base.geojson` | ≥ 1 (Multi)Polygon and ≥ 3 LineStrings |

### Common to B2–B5 (adapters)
- Each new endpoint is a module `app/routers/<name>.py` (A-32) under the prefix **`/api/map/`** (A-33) and returns
  the SPEC «Backend contracts» shape exactly, plus a top-level `source` (`live` | `cache` | `snapshot`) and
  `updated_at`. Existing routes don't change.
- The external call lives in its own adapter `app/<name>_src.py`: one function per upstream call, `httpx` with a
  10 s timeout, in-memory TTL cache, and the last good answer written to `data/<name>/last.json`. Upstream down →
  serve `last.json` with `source: "snapshot"`; nothing at all → an empty FeatureCollection with
  `source: "unavailable"`, HTTP 200, never a guess. `api.js` (B1) then falls back to `web/mock/`.
- The URLs in SPEC «Εξωτερικές πηγές» were written without an online check. The **implementer verifies them online
  first** and records in the code report what each returned; real responses are saved as test fixtures in
  `tests/fixtures/B<n>/`. Tests are fully offline: they patch the adapter's HTTP function to return the fixtures.
- Config (URLs, TTLs, line lists) goes in `app/config.py` inside a `# --- B<n> ---` block, from env vars with
  defaults. Data sources and licences go in `THIRD_PARTY.md`.

### B2: Works from Διαύγεια + ΚΗΜΔΗΣ (phase 2)
SPEC F4, «Εξωτερικές πηγές» Έργα, contract `GET /works`.
**Files:** `app/works_src.py`, `app/routers/works_map.py`, `scripts/fetch_works.py`, `data/stoa/works.json`
(output), `app/config.py` (B2 block), `THIRD_PARTY.md`, `tests/fixtures/B2/*`, `tests/test_B2_works.py`.
- `fetch_works.py` (run by hand, online): Διαύγεια OpenData search for Δήμος Αθηναίων decisions about public works
  (αναθέσεις, πληρωμές), ΚΗΜΔΗΣ OpenData for the matching contracts (ανάδοχος, ποσά, ΑΔΑΜ), join on ΑΔΑ/ΑΔΑΜ,
  street geocoded from the decision text by a curated street → LineString table (Nominatim only as a hint, by
  hand). Output in the `data/works_seed.json` schema (every field `{value, label: CITED|UNKNOWN, source:{ada}}`)
  to `data/stoa/works.json`, which `works.py` already prefers. 10–15 works in the centre.
- `GET /api/map/works?bbox=&status=` → SPEC fields from `works.all_cards()`; `status` derived from dates
  (`planned` before start, `in_progress`, `completed` after end); `guarantee_end` from `works.clock()`;
  `reports_count` = open reports within 30 m of the line. Unknown fields are `null`, never 0.

| Test | Given | Expected |
|---|---|---|
| `test_map_works_contract_fields` | SEED dataset | FeatureCollection; every feature has the 12 SPEC fields |
| `test_map_works_bbox_filter` | bbox around one work only | exactly that work |
| `test_map_works_status_filter` | `status=in_progress` | only in-progress works |
| `test_status_from_dates` | `STOA_TODAY` before start / between / after end | planned / in_progress / completed |
| `test_unknown_amount_is_null` | a work whose `amount_paid_eur` is UNKNOWN | `amount_paid_eur` is `null` |
| `test_reports_count_near_line` | 2 open reports within 30 m of a work, 1 at 100 m | `reports_count` 2 |
| `test_diavgeia_parser_fixture` | saved Διαύγεια search response | parsed decisions with ΑΔΑ, subject, date, amount |
| `test_khmdhs_join_on_ada` | saved ΚΗΜΔΗΣ fixture + Διαύγεια fixture | contractor and contract amount joined to the right ΑΔΑ |
| `test_existing_works_routes_unchanged` | `/api/works/geojson`, `/api/works/radar` | same keys as before B2 |

### B3: `/api/map/transit` — metro, suburban, OASA buses (phase 2)
SPEC F2 Τηλεματική + Μετρό/Προαστιακός, contract `GET /transit`.
**Files:** `app/transit_src.py`, `app/routers/transit.py`, `scripts/fetch_transit.py`, `data/transit/static.json`
(output), `app/config.py` (B3 block), `THIRD_PARTY.md`, `tests/fixtures/B3/*`, `tests/test_B3_transit.py`.
- Static lines + stations: OASA/STASY GTFS if reachable, else OSM `route=subway|train|light_rail` via Overpass;
  built once by `fetch_transit.py` into `data/transit/static.json`. Lines carry `name`, `ref`, official `color`
  (source in a comment); stations `name`, `lines[]`, `elevator` (OSM `elevator`/`wheelchair`, else `null`).
- Buses: OASA telematics (`getBusLocation` per route code, `getStopArrivals` for waits) for the route codes in
  `config.TRANSIT_ROUTES` that cross the bbox; cached 20 s (SPEC polling); `line`, `route_code`, `bearing`,
  `updated_at` per bus.

| Test | Given | Expected |
|---|---|---|
| `test_transit_contract` | static file + bus fixture | `{lines, stations, buses}` each a FeatureCollection, plus `source` |
| `test_transit_bbox_filters_stations_and_buses` | bbox around Σύνταγμα | Σύνταγμα in, Πειραιάς out; buses outside bbox dropped |
| `test_line_colours_hex` | static lines | every line has a `#rrggbb` `color` |
| `test_bus_location_parser_fixture` | saved `getBusLocation` response | buses with lon/lat floats, line, bearing |
| `test_bus_cache_20s` | two calls 5 s apart, patched clock | upstream called once |
| `test_oasa_down_serves_snapshot` | upstream raises | last good buses, `source: "snapshot"` |
| `test_nothing_available_empty_200` | upstream raises, no snapshot | 200, empty `buses`, `source: "unavailable"` |

### B4: `/api/map/health` — on-duty pharmacies and hospitals (phase 2)
SPEC F2 Εφημερεύοντα, contract `GET /health` (served as `/api/map/health`, A-33; `/api/health` stays the server
status). **Files:** `app/onduty_src.py`, `app/routers/onduty.py`, `data/onduty/hospitals.json` (curated: real
central-Athens hospitals, address, phone, coordinates, source per row), `app/config.py` (B4 block),
`THIRD_PARTY.md`, `tests/fixtures/B4/*`, `tests/test_B4_onduty.py`.
- Pharmacies: the Φαρμακευτικός Σύλλογος Αττικής on-duty list for `date` (scraper, once a day, cached to
  `data/onduty/pharmacies-<date>.json`), addresses geocoded once and cached. Hospitals: the curated file + the
  Υπουργείο Υγείας daily εφημερίες announcement → `on_duty` and `specialties` per hospital.
- A source that can't be fetched or parsed gives `on_duty: null` (unknown) for its rows, never a guess; the
  response says which source failed.

| Test | Given | Expected |
|---|---|---|
| `test_onduty_contract` | fixtures | GeoJSON points with `kind, name, address, phone, hours, specialties, on_duty` |
| `test_api_health_unchanged` | `GET /api/health` | still the server-status object (`ok`, `mock`, …) |
| `test_pharmacy_parser_fixture` | saved on-duty page | pharmacies with name, address, hours |
| `test_hospital_announcement_parser_fixture` | saved announcement | the right hospitals `on_duty` true with specialties |
| `test_geocode_cached` | same address twice | geocoder called once |
| `test_source_down_on_duty_null` | pharmacy source raises | pharmacies (from last cache) with `on_duty: null`, failed source named |
| `test_date_param` | `?date=2026-11-22` | the adapter asked for that date |

### B5: `/api/map/env` — temperature / AQI grid (phase 2)
SPEC F2 Θερμοκρασία/AQI, «Εξωτερικές πηγές», contract `GET /env`.
**Files:** `app/envgrid_src.py`, `app/routers/envgrid.py`, `app/config.py` (B5 block), `THIRD_PARTY.md`,
`tests/fixtures/B5/*`, `tests/test_B5_envgrid.py`.
- A fixed grid over the Δήμος (step `config.ENV_GRID_M`, default 600 m), one Open-Meteo forecast call and one
  air-quality call for all grid points (multi-coordinate request), cached 15 min. Per point `temp_c`, `aqi`
  (European AQI), `pm25`, `updated_at`. Where a City CKAN station (`ckan.nearest_air`) is within 300 m, its values
  win and the point says `station`.
- `?bbox=minLon,minLat,maxLon,maxLat` keeps only points inside.

| Test | Given | Expected |
|---|---|---|
| `test_env_contract` | fixtures | GeoJSON points with `temp_c, aqi, pm25, updated_at`, plus `source` |
| `test_grid_covers_dimos` | default config | ≥ 20 points, all inside the Δήμος bbox |
| `test_bbox_param_spec_format` | `bbox=23.72,37.97,23.74,37.98` | only points inside |
| `test_single_upstream_call_per_kind` | full grid | one forecast call, one air-quality call |
| `test_cache_15min` | two calls 10 min apart | upstream called once per kind |
| `test_station_overrides_model` | CKAN station 100 m from a grid point | that point uses the station's values, `station` set |
| `test_open_meteo_down_snapshot` | upstream raises after one good call | last good grid, `source: "snapshot"` |

### Common to B6–B9
- New routes under `/api/map/` in `app/routers/<name>.py` (A-32, A-33), SPEC shapes exactly. Existing routes and
  their tests don't change. Logic in its own `app/<name>.py`; small hooks into shared files only where the card says,
  inside a `# --- B<n>: … ---` block.
- UI modules follow A-35 (`export function mount(ctx)`), never call `fetch` (only `ctx.api`), touch no `document` or
  `maplibregl` at import time, and keep their pure parts (labels, formatting, link building, queues) as exported
  functions tested with `node --test` in `web/tests/B<n>_*.test.js`. Greek UI strings, WCAG AA (labels, keyboard,
  `aria-live` for messages).
- The code step of B6, B8, B9 runs on Claude (A-31).

### B6: Report flow «+» (phase 2)
SPEC F3, HUD «Κάτω αριστερά», «Privacy», «Κανόνες πόντων», contracts `POST /reports`, `GET /reports`.
**Files:** `app/map_reports.py`, `app/routers/map_reports.py`, `app/privacy.py` (B6 block: plates),
`app/points.py` (B6 block: A-36 actions and caps), `app/main.py` (B6 block inside approve: `city_confirmed` for map
reports only), `web/js/ui/report.js`, `THIRD_PARTY.md`, `tests/test_B6_reports.py`, `web/tests/B6_report.test.js`.
- `POST /api/map/reports` (multipart `category, lon, lat, note, work_id?, photo?`) → `{id, photo_url_blurred,
  points_awarded, blur:{faces, plates}}`. Categories: `congestion` συμφόρηση, `incident` συμβάν, `obstacle` εμπόδιο,
  `damage` ζημιά, `work_progress` πρόοδος έργου. Photo optional; when present it goes through
  `privacy.process_photo()` (faces + plates blurred, EXIF stripped, original never on disk). Plates: OpenCV's bundled
  plate cascade (BSD, ships with `opencv`), best effort; count reported as `blur.plates`.
- Stored in our DB (table `map_reports`, own module); public coordinates rounded to 4 decimals (~10 m). `obstacle`
  and `damage` are also created as City requests in the sandbox (as `/api/report` does), without the token.
- `GET /api/map/reports?bbox=&since=` → GeoJSON points `category, created_at, confirmations` (+ `id`); `POST
  /api/map/reports/{id}/confirm` → `confirmations + 1`, +2 to the confirmer (not to the author, once per account).
- Points per A-36 via `points.grant`; daily cap 10; duplicate (same category, ≤ 50 m, ≤ 30 min) → `points_awarded 0`.
- `ui/report.js`: «+» button → radial menu of the 5 categories → draggable pin at the map centre → optional photo →
  send; «Θολώνουμε πρόσωπα και πινακίδες…» while uploading; shows the blurred photo from `photo_url_blurred`;
  emits `points:earned`. Listens to `report:open` (from the works popup, with `work_id`). Offline: queued in
  `localStorage`, sent on `online`.

| Test | Given | Expected |
|---|---|---|
| `test_map_report_contract` | POST with photo | `id, photo_url_blurred, points_awarded, blur.faces, blur.plates` |
| `test_map_report_without_photo` | POST, no photo | 200, `photo_url_blurred` null |
| `test_map_report_bad_category_422` | category `foo` | 422 |
| `test_photo_exif_stripped_original_not_on_disk` | JPEG with EXIF GPS | stored file has no EXIF; no other new file in `data/photos/` |
| `test_plate_blur_counted` | fixture image with a plate | `blur.plates ≥ 1` |
| `test_public_coords_rounded` | lon/lat with 7 decimals | `GET /api/map/reports` shows ≤ 4 decimals |
| `test_points_map_report_5` | first `incident` today | `points_awarded` 5 |
| `test_points_work_progress_photo_15` | `work_progress` with photo and `work_id` | 15 |
| `test_duplicate_no_points` | same category 20 m away, 10 min later | `points_awarded` 0 |
| `test_daily_cap_10` | 11 reports, one account, spread apart | 11th gets 0 |
| `test_confirm_other_plus_2_once` | account B confirms A's report twice | one +2 for B, `confirmations` 1; A confirming own report gets 0 |
| `test_obstacle_creates_city_request_without_token` | `obstacle` report with a cookie token | sandbox mock got a request; token not in anything it received |
| `test_city_confirmed_bonus_20` | operator approves the city request of a map report | +20 to the reporter |
| `test_get_reports_bbox_since` | reports in/out of bbox and before/after `since` | only the matching ones |
| `test_existing_report_route_unchanged` | `POST /api/report` as in `test_smoke.py` | same response keys |
| `test_js_categories_in_spec_order` (node) | `CATEGORIES` | 5 ids and Greek labels |
| `test_js_build_form` (node) | category, lngLat, note, no photo, `work_id` | FormData fields `category, lon, lat, note, work_id`, no `photo` |
| `test_js_offline_queue_flush` (node) | fake api throws, then works; fake `localStorage` | report queued, then sent once on flush, queue empty |

#### B6 fix round (Evgenii, after review)
- **Privacy (sandbox coordinates):** `_city_request` in `app/routers/map_reports.py` receives `saved["lon"], saved["lat"]` (rounded to 4 decimals, ~10 m) instead of the raw 7-decimal coordinates, and `address` is formatted to 4 decimals.
- **No duplicate City requests:** `map_reports.create()` returns `"duplicate": bool`; when `saved["duplicate"]` is true, no duplicate City request is sent to the sandbox.
- Tests in `tests/test_B6_reports_fix.py`; existing B6 tests stay unchanged.

| Test | Given | Expected |
|---|---|---|
| `test_city_request_receives_rounded_coords` | `obstacle` report at `lon=23.7275123, lat=37.9838123` | `sb.create_request` receives `lng=23.7275, lat=37.9838` and 4-decimal `address` |
| `test_duplicate_obstacle_no_second_city_request` | two `obstacle` reports 20 m apart within 10 min | `sb.create_request` called once |

### B7: Points pill + panel, redeem (phase 2)
SPEC F7, HUD «Πάνω δεξιά», contracts `GET /points`, `POST /points/redeem`.
**Files:** `app/rewards.py`, `app/routers/points_map.py`, `data/rewards.json`, `web/js/ui/points.js`,
`tests/test_B7_points.py`, `web/tests/B7_points.test.js`.
- `GET /api/map/points` (cookie, A-34) → `{balance, district:{name, progress_pct, goal}, history:[{ts, delta,
  reason}], rewards:[{id, title, cost}]}`. `balance` = ledger sum (`points.wallet`) − redeemed. `district` = the
  account's latest report district from `points.districts()`.
- `data/rewards.json`: a few example rewards (δημοτικές εκδηλώσεις, στάθμευση, τοπικά καταστήματα), labelled in the
  file and on screen as «πρόταση, ανοιχτό ερώτημα προς τον Δήμο».
- `POST /api/map/points/redeem` `{reward_id}` → `{ok, balance, voucher_code}`; table `redemptions` in its own
  module; not enough points → `ok: false`, nothing written; `voucher_code` random, not derived from the token.
- `ui/points.js`: pill with balance + district bar; on `points:earned` a 600 ms pulse and a rising «+N»; click opens
  a panel with history and rewards.

| Test | Given | Expected |
|---|---|---|
| `test_points_contract` | an account with grants | all SPEC keys; `rewards` from `data/rewards.json` |
| `test_balance_minus_redeemed` | 50 earned, redeem a 30 reward | `balance` 20 in both responses |
| `test_redeem_not_enough` | 10 points, reward 30 | `ok: false`, balance unchanged, no row |
| `test_redeem_unknown_reward_404` | `reward_id` missing | 404 |
| `test_voucher_not_token` | redeem | `voucher_code` ≠ token and contains no part of it |
| `test_no_cookie_new_account_zero` | no cookie | balance 0, cookie set |
| `test_district_progress_pct_bounds` | district total above goal | `progress_pct` 100 |
| `test_existing_points_routes_unchanged` | `/api/points/me`, `/api/points/districts` | same keys as before |
| `test_js_format_delta` (node) | 5, −30 | «+5», «−30» |
| `test_js_pulse_on_event` (node) | fake bus emits `points:earned` `{delta: 5}`, fake pill | pill gets the pulse class and «+5», balance +5 |

#### B7 fix round (Evgenii, after review)
- **Reset clears redemptions:** `app/rewards.py` adds `clear()` (`DELETE FROM redemptions`), and `app/store.py` `clear()` deletes from `redemptions` if the table exists (inside a `# --- B7 ---` block), so `/api/admin/reset` never leaves a negative balance.
- **UI error handling:** `redeem()` in `web/js/ui/points.js` wraps `await api.redeem(reward.id)` in `try / catch` so a thrown error sets `status.textContent` instead of an unhandled rejection.
- Tests in `tests/test_B7_points_fix.py` and `web/tests/B7_points_fix.test.js`; existing B7 tests stay unchanged.

| Test | Given | Expected |
|---|---|---|
| `test_reset_clears_redemptions` | earn 50, redeem 30, then `POST /api/admin/reset` | `GET /api/map/points` with the same cookie has `balance == 0` |
| `test_js_redeem_throw_handled` (node) | `api.redeem` rejects with an Error, user clicks redeem button | no unhandled rejection; `.points-status` shows an error message |

### B8: Stoa AI with citations + flyTo (phase 2)
SPEC F6, HUD «Κάτω δεξιά», contract `POST /stoa_ask`.
**Files:** `app/stoa_map.py`, `app/routers/stoa_map.py`, `web/js/ui/stoa.js`, `tests/test_B8_stoa.py`,
`web/tests/B8_stoa.test.js`.
- `POST /api/map/stoa_ask` `{question, center:[lon,lat], history:[...]}` → `{answer_md, citations:[{label, lon, lat,
  kind}]}`. General purpose, by a plain router (rules, not AI): works questions → `stoa_ask.ask()` (keeps its `[ΑΔΑ …]`
  citations), with a citation per matched work at its line's midpoint, `kind: "work"`; on-duty pharmacy/hospital
  questions → the on-duty provider (`app.onduty_src` when B4 is merged; until then the provider returns nothing and
  the answer is the refusal), nearest to `center`, `kind: "pharmacy" | "hospital"`; anything else → the City
  answer of `/api/ask` (sandbox sources as Markdown links), `citations` only for results with coordinates.
- No source → «Δεν βρήκα τεκμηριωμένα στοιχεία…»; never an invented place. Every citation `label` occurs in
  `answer_md`.
- `ui/stoa.js`: bubble → panel 380×520 (transform + opacity, 250 ms); Markdown rendered safely (escaped, links
  only); each citation label becomes a link that emits `map:flyto`.

| Test | Given | Expected |
|---|---|---|
| `test_stoa_map_contract` | works question about «Δείγμα Οδός Α» | `answer_md` with `[ΑΔΑ …]`, a `work` citation with numeric lon/lat |
| `test_citation_labels_in_answer` | any answered question | every `label` occurs in `answer_md` |
| `test_pharmacy_question_uses_provider` | patched provider with 2 on-duty pharmacies, `center` near one | that one first, `kind: "pharmacy"` |
| `test_pharmacy_no_provider_refuses` | provider returns nothing | refusal text, `citations` empty |
| `test_city_question_has_source_links` | patched `/api/ask` answer with sources | `answer_md` contains the source URLs |
| `test_unknown_refuses_no_invented_place` | question nothing matches | refusal, no citations |
| `test_existing_stoa_route_unchanged` | `POST /api/stoa/ask` | same response keys |
| `test_js_link_citations` (node) | `answer_md` + 2 citations | HTML with 2 links carrying `data-lon`/`data-lat`, text otherwise escaped |
| `test_js_markdown_escapes_html` (node) | `answer_md` with `<script>` | no element created, shown as text |
| `test_js_click_emits_flyto` (node) | fake bus, click handler on a citation link | `map:flyto` with that lon/lat/label |

#### B8 fix round (Evgenii, after review)
- **Sandbox outage degrades to refusal:** `city_ask` / `answer_city` in `app/stoa_map.py` catches `SandboxError` (and any upstream error) and returns `_refusal()` (HTTP 200 with `REFUSAL_MD` and `citations: []`) instead of HTTP 502.
- Tests in `tests/test_B8_stoa_fix.py`; existing B8 tests stay unchanged.

| Test | Given | Expected |
|---|---|---|
| `test_sandbox_error_returns_refusal_200` | `city_ask` / `sb.search` raises `SandboxError` | HTTP 200, refusal text in `answer_md`, `citations: []` |

### B9: Route cost per profile (phase 2)
SPEC F5, «Routing», contract `POST /routing`.
**Files:** `app/route_cost.py`, `app/routers/routing_map.py`, `tests/test_B9_routing.py`.
- `POST /api/map/routing` `{from:[lon,lat], to:[lon,lat], profile:"wheelchair"|"stroller"|"cool"}` →
  `{geometry: LineString, distance_m, duration_s, legs:[{mode, line?}], reasons:[{text, layer, feature_id}]}`.
- Builds on `routing.candidates()` and `env.score_line()` (as `/api/navigate` does), with the layers the map shows:
  **wheelchair** excludes open obstacle reports and in-progress works (avoid polygons around the work lines), Valhalla
  wheelchair costing, prefers lowered kerbs/ramps; **stroller** avoids works and congestion reports (soft), prefers
  good AQI; **cool** weights shade and penalises hot/high-PM2.5 grid cells (`app.envgrid_src` when B5 is merged,
  else the existing station/forecast heat logic).
- `reasons` name what changed the route versus the plain shortest: each avoided work (`layer: "works"`,
  `feature_id` = work id), report (`reports`, report id), heat/air (`env`), with Greek `text` («αποφεύγει 2 έργα»,
  «−2°C σκιά»). Transit legs: `legs` is `[{mode: "walk"}]` for now (metro/bus legs are a later card).

| Test | Given | Expected |
|---|---|---|
| `test_routing_contract` | Σύνταγμα → Μοναστηράκι, fallback router (no Valhalla) | all SPEC keys; geometry LineString; `legs` `[{mode:"walk"}]` |
| `test_wheelchair_avoids_in_progress_work` | a SEED in-progress work on the direct path | candidate passing it not chosen; a `works` reason with that work id |
| `test_wheelchair_avoids_obstacle_report` | open obstacle report on the direct path | avoided; a `reports` reason with its id |
| `test_stroller_avoids_congestion_soft` | congestion report on the direct path, only alternative 3× longer | direct path kept (soft), no reason claimed |
| `test_cool_prefers_shade` | two candidates, one shadier | the shadier chosen; an `env` reason |
| `test_profiles_differ` | same from/to with a work on the direct path | wheelchair and cool return different geometries |
| `test_bad_profile_422` | profile `car` | 422 |
| `test_reasons_point_at_real_features` | any reasons | every `feature_id` exists in its layer's data |
| `test_existing_navigate_unchanged` | `/api/navigate` as in existing tests | same keys |

### B1: `api.js` — the only door to the backend (phase 1)
SPEC «Αρχιτεκτονική» (`api.js`), «Offline fallback» 3–4, «Backend contracts»; A-33, A-34, A-37.
**Files:** `web/js/api.js`, `web/package.json` (exactly `{"type": "module", "private": true}` + newline, same as A0,
so the two tracks add an identical file), `web/tests/B1_api.test.js`.
- One exported async function per contract, each resolving to the SPEC shape **plus** a top-level `source`
  (`live` | `cache` | `mock`): `env(bbox)`, `works({bbox, status})`, `transit(bbox)`, `health(date)`,
  `reports({bbox, since})`, `sendReport(fields)`, `points()`, `redeem(rewardId)`, `stoaAsk(question, center,
  history)`, `routing(from, to, profile)`, plus `access()` and `base()` (mock files only, always `source: "mock"`).
- Order (SPEC): live `/api/map/…` (A-33; `fetch` with a 5 s timeout, `credentials: "same-origin"`, never a
  `user_id` in the URL, A-34) → the last good live answer for the same key in `localStorage` (`cache`) → the file in
  `mock/` (`mock`). An HTTP error, a timeout or a 404 (endpoint not merged yet) counts as a failure.
- Mock fallbacks without a 1:1 file: `stoaAsk` answers from `mock/stoa.json` by accent- and case-insensitive match
  on `question`, else the refusal «Δεν βρήκα τεκμηριωμένα στοιχεία για αυτό.» with no citations; `routing` returns a
  straight line from → to with `legs [{mode: "walk"}]` and the reason «Χωρίς σύνδεση: ευθεία γραμμή, χωρίς
  υπολογισμό εμποδίων»; `redeem` and `sendReport` don't fall back: offline → `{ok: false, error: "offline"}` /
  a thrown `OfflineError` (the report queue lives in `ui/report.js`, B6).
- `export const status` is an `EventTarget`: every call dispatches `source` `{key, source}`; `isOffline()` is true
  while the latest answer of any key isn't `live` (drives the «Offline λειτουργία» badge, Dev A).
- `configure({fetch, storage, base, mockBase, timeoutMs})` for tests and for `main.js`; defaults are the browser's.
- No DOM, no `maplibregl`, no other module imports it except through `ctx.api` (A-35).

| Test | Given | Expected |
|---|---|---|
| `test_live_answer_has_source_live` | fake fetch returns a works FeatureCollection | same object + `source: "live"`; URL `/api/map/works` |
| `test_live_answer_cached` | one live call, then fetch fails | second call returns the first answer with `source: "cache"` |
| `test_no_cache_falls_back_to_mock` | fetch fails, empty storage | answer from `mock/works.geojson`, `source: "mock"` |
| `test_404_counts_as_failure` | fetch returns 404 | `cache` or `mock`, never the 404 body |
| `test_timeout_5s` | fetch never resolves, mocked timers +5 s | falls back, no hang |
| `test_query_params_spec_format` | `env([23.72,37.97,23.74,37.98])`, `works({status:"in_progress"})` | `bbox=23.72,37.97,23.74,37.98`, `status=in_progress` |
| `test_no_user_id_in_urls` | every function called | no URL contains `user_id` or the cookie value; `credentials: "same-origin"` |
| `test_stoa_mock_match_accent_insensitive` | fetch fails, question «ποιο φαρμακειο εφημερευει κοντα μου» | the stoa.json pharmacy answer with its citations |
| `test_stoa_mock_no_match_refuses` | fetch fails, unknown question | refusal text, `citations: []` |
| `test_routing_offline_straight_line` | fetch fails | LineString from → to, `legs [{mode:"walk"}]`, the offline reason, `source: "mock"` |
| `test_redeem_offline_not_faked` | fetch fails | `{ok: false, error: "offline"}`, no voucher |
| `test_send_report_offline_throws` | fetch fails | rejects with `OfflineError` |
| `test_status_events_and_is_offline` | one live call, one mock call | two `source` events; `isOffline()` true, then false after a live call for that key |
| `test_import_has_no_dom` | import in Node | no error, no global touched |

#### B1 fix round (Evgenii, after review)
- **Privacy:** `stoaAsk` and `routing` are never cached (no `localStorage` write; offline → straight to `mock`). No
  storage key or value may hold the user's question, `center`, `from` or `to`.
- **Rejected ≠ offline (A-38):** for `sendReport` and `redeem`, only a network error, a timeout, a 404 or a 5xx count
  as offline. Any other 4xx → `sendReport` rejects with `RejectedError` carrying `status` and the server's `detail`;
  `redeem` resolves `{ok: false, error: "rejected", status, detail}`. B6 shows the reason instead of queueing.
- Tests in a new file `web/tests/B1_api_fix.test.js`; the existing B1 tests stay as they are.

| Test | Given | Expected |
|---|---|---|
| `test_stoa_not_cached` | one live `stoaAsk`, then fetch fails | second answer `source: "mock"`, not `cache` |
| `test_routing_not_cached` | one live `routing`, then fetch fails | second answer `source: "mock"` (straight line) |
| `test_no_user_location_or_question_in_storage` | every function called once live with distinctive coordinates and question text | no storage key or value contains those coordinates or the question |
| `test_send_report_429_rejected` | fetch returns 429 `{detail: "όριο αναφορών"}` | rejects with `RejectedError`, `status` 429, `detail` set; not `OfflineError` |
| `test_send_report_500_offline` | fetch returns 500 | rejects with `OfflineError` |
| `test_send_report_404_offline` | fetch returns 404 | rejects with `OfflineError` (endpoint not merged yet) |
| `test_redeem_400_rejected` | fetch returns 400 `{detail: "…"}` | `{ok: false, error: "rejected", status: 400, detail}` |

### B10: Works tab (F8) — list, filters, crowdsourced progress (phase 3)
SPEC F8, HUD «Πάνω αριστερά», «Demo script» step 6; A-35.
**Files:** `web/js/ui/workstab.js`, `web/tests/B10_workstab.test.js`.
- Top-left HUD pill bar (`mount({map, api, root, bus})`, A-35): tabs «Χάρτης» / «Έργα» (`role="tab"`, `aria-selected`).
  Clicking «Έργα» opens a `.glass` panel listing the works from `api.works()`; clicking «Χάρτης» (or pressing `Escape`)
  closes the panel.
- Status filter chips (`all` Όλα, `in_progress` Σε εξέλιξη, `planned` Προγραμματισμένα, `completed` Ολοκληρωμένα) and a
  text query box (accent- and case-insensitive match on `title`, `contractor`, `ada`).
- Each work card shows `title`, Greek status label (`Προγραμματισμένο` / `Σε εξέλιξη` / `Ολοκληρωμένο` / `άγνωστο`),
  `contractor` (or `«άγνωστο»`), formatted `amount_paid_eur` / `amount_contract_eur` (`«άγνωστο»` when `null`, never 0),
  ΑΔΑ link (`https://diavgeia.gov.gr/decision/view/<ada>` only for real ΑΔΑ where `!seed` and `!ada.startsWith("SEED-")`,
  otherwise a `SEED` / `δοκιμαστικό` badge), `reports_count`, a button to focus on the map (`bus` event `map:flyto`
  `{lon, lat, label}` at the work LineString's midpoint), and a button «Ανέφερε πρόοδο» (`bus` event `report:open`
  `{work_id, lngLat}` so `ui/report.js` opens pre-filled for that work).
- Pure exported helpers for Node tests: `STATUS_FILTERS`, `filterWorks(features, {status, query})`, `workMidpoint(geometry)`,
  `diavgeiaLink(props)`, `formatWorkCard(feature)`. No `fetch`, no DOM or `maplibregl` touched at import time.

| Test | Given | Expected |
|---|---|---|
| `test_js_status_filters_in_order` (node) | `STATUS_FILTERS` | 4 filters (`all`, `in_progress`, `planned`, `completed`) with Greek labels |
| `test_js_filter_works_by_status_and_query` (node) | works features; filter `status: "in_progress"` and accent-insensitive query `"ερμου"` | only matching in-progress works on Ερμού returned |
| `test_js_unknown_values_never_zero` (node) | a work with `contractor: null`, `amount_contract_eur: null`, `amount_paid_eur: null` | formatted card shows `«άγνωστο»` for missing fields, never `0` |
| `test_js_seed_ada_not_linked_to_diavgeia` (node) | one real work (`ada: "Ψ0ΣΝΩ6Μ-5ΙΖ"`, `seed: false`) and one SEED work (`ada: "SEED-ΑΔΑ-001"`, `seed: true`) | real work gets `https://diavgeia.gov.gr/decision/view/Ψ0ΣΝΩ6Μ-5ΙΖ`; SEED work gets `null` URL and is labelled SEED |
| `test_js_work_midpoint` (node) | LineString `[[23.72, 37.97], [23.74, 37.99]]` | `[23.73, 37.98]` |
| `test_js_mount_emits_report_open_and_flyto` (node) | fake DOM/bus/api, open «Έργα» tab, click «Ανέφερε πρόοδο» and map-focus button on a work | `report:open` emitted with `{work_id, lngLat}` and `map:flyto` emitted with `{lon, lat, label}` |
| `test_js_import_has_no_dom` (node) | import `ui/workstab.js` in Node | no error, no globals touched |

### B11: Phase 4 integration & end-to-end demo rehearsal (phase 4)
SPEC «Φάσεις» 4, «Κριτήρια αποδοχής», «Demo script (3 λεπτά)»; A-35, A-38.
**Files:** `web/js/api.js`, `web/js/ui/{points,report,stoa,workstab}.js`, `tests/test_B11_e2e_demo.py`,
`web/tests/B11_e2e_demo.test.js`.
- Verify and harden the end-to-end 3-minute demo flow across the backend (`/api/map/*`) and the frontend ES modules
  (`api.js`, `ui/points.js`, `ui/report.js`, `ui/stoa.js`, `ui/workstab.js`) when mounted into a DOM with the HUD slots
  of `web/citizen.html` (`#hud-tabs`, `#hud-points`, `#hud-report`, `#hud-stoa`) and a shared `EventTarget` `bus`.
- Ensure that:
  1. `ui/workstab.js` listens to `tab:change` `{tab: "works"|"map"}` on `bus` (dispatched by Dev A's `main.js` when
     `#tab-works` / `#tab-map` is clicked) in addition to direct clicks on the tab buttons, and refreshes the works list
     when opened via `tab:change`.
  2. When a report is submitted via `ui/report.js` (`submitReport` or form submit), it emits `points:earned` on `bus`
     so `ui/points.js` pulses and increments its displayed balance, and also emits `report:created` `{id, category,
     lon, lat}` on `bus` so the map reports layer can refresh.
  3. On backend `/api/map/*`: all 6 demo steps (env grid, transit, works + work progress report with photo blur & +15
     points, wheelchair vs cool routing avoiding in-progress work, Stoa pharmacy question near Syntagma with citation
     coordinates, points & voucher redemption) succeed end-to-end in sequence on a single `TestClient` session.

| Test | Given | Expected |
|---|---|---|
| `test_e2e_demo_backend_6_steps` | single `TestClient` running SPEC Demo script steps 2–6 against `/api/map/*` | env grid ≥ 20 pts; transit 3 collections; work progress photo report awards 15 pts & strips EXIF; wheelchair & cool routes return LineStrings; Stoa pharmacy query returns citation; points balance 15 & redeem works after earning 30 |
| `test_js_workstab_opens_on_bus_tab_change` (node) | `workstab.mount({map, api, root, container, bus})`, dispatch `tab:change` `{tab: "works"}` then `{tab: "map"}` on `bus` | panel opens and loads works from `api.works()` on `"works"`, hides on `"map"` |
| `test_js_report_to_points_pulse_via_bus` (node) | `points.mount` and `report.mount` sharing `bus`, submit a report awarding 15 points | `points` pill balance increases by 15 and gets `.pulse` class + `+15` float |
| `test_js_workstab_report_open_prefills_report_panel` (node) | `workstab.mount` and `report.mount` sharing `bus`, click «Ανέφερε πρόοδο» on work `W-SEED-001` | `report` panel opens with `work_progress` category and title containing `W-SEED-001` |
| `test_js_stoa_citation_emits_flyto_on_shared_bus` (node) | `stoa.mount` with `api.stoaAsk` returning a pharmacy citation, submit question and click citation link | `map:flyto` dispatched on `bus` with numeric `lon`, `lat`, and pharmacy `label` |

### B12: Cross-module backend wiring (`works_map` + `routing_map` + `map_reports`) (phase 4)
SPEC F3, F4, F5, «Demo script» steps 3–4.
**Files:** `app/map_reports.py`, `app/routers/works_map.py`, `app/routers/routing_map.py`, `app/route_cost.py`,
`tests/test_B12_cross_wiring.py`.
- `app/map_reports.py`: add `all_reports() -> list[dict]` returning stored rows (`id, category, lon, lat, work_id,
  city_request_id, created_at`).
- `app/routers/works_map.py`: `_open_reports()` includes SQLite `map_reports` rows that have no `city_request_id`
  (such as `work_progress`, `incident`, `congestion`) alongside the open sandbox requests (so `obstacle`/`damage`
  reports forwarded to the sandbox are not double-counted). Submitting a `work_progress` report within 30 m of a work
  via `POST /api/map/reports` increments that work's `reports_count` in `GET /api/map/works`.
- `app/routers/routing_map.py`: `_open_reports()` includes `map_reports.all_reports()` (where `category == "obstacle"`
  has `blocker: True`, `category == "congestion"` has `blocker: False` and is in `SOFT_REPORT_CATEGORIES`, and any row
  linked to `city_request_id` checks that its sandbox status is still in `main.OPEN`), so `POST /api/map/routing`
  avoids `obstacle` and `congestion` reports created through `POST /api/map/reports` and returns their `MR-...` id in
  `reasons[].feature_id`.
- `app/route_cost.py`: `in_progress(work, today)` accepts both B2 evidence-wrapped works records (`start_date` /
  `end_date` as `{"value": "YYYY-MM-DD", ...}` via `works_src.status_of(work, today.isoformat()) == "in_progress"`) and
  top-level `status == "in_progress"` records.

| Test | Given | Expected |
|---|---|---|
| `test_work_progress_map_report_increments_works_reports_count` | `POST /api/map/reports` with `category="work_progress"` on `W-SEED-001` (`lon=23.7420, lat=37.9660`) | `GET /api/map/works` shows `reports_count == 1` for `W-SEED-001` |
| `test_obstacle_map_report_not_double_counted_on_work` | `POST /api/map/reports` with `category="obstacle"` on `W-SEED-001` (`lon=23.7420, lat=37.9660`) | `GET /api/map/works` shows `reports_count == 1` (not 2) for `W-SEED-001` |
| `test_wheelchair_routing_avoids_map_report_obstacle` | `POST /api/map/reports` with `category="obstacle"` at Syntagma→Monastiraki midpoint (`lon=23.73025, lat=37.9758`) | `POST /api/map/routing` (`profile="wheelchair"`) avoids the midpoint (> 20 m) and includes a `reports` reason with that `MR-...` id |
| `test_wheelchair_routing_avoids_b2_evidence_wrapped_in_progress_work` | B2-schema work with evidence-wrapped `start_date: {"value": "2026-10-01", "label": "CITED"}` and `end_date: {"value": "2026-12-31", "label": "CITED"}` (no top-level `status` key) on Syntagma→Monastiraki | `POST /api/map/routing` (`profile="wheelchair"`) avoids the work and includes a `works` reason with its id |

## Phase 5: more from the AthensGov Sandbox

B13–B15 use sandbox endpoints we already call (`app/sandbox.py`) but only thinly. They run in parallel: each one
has its own router, module, test file and mock file. Shared files: `app/sandbox.py` (B13 touches only
`_MockData.services/service`) and `web/js/api.js` (each task adds one exported function at the end of the reads
section; nothing else in the file changes). No existing route changes (SPEC rule). The real sandbox response
fields beyond the ones in `app/sandbox.py`'s mock are **not verified** (we have no OpenAPI copy yet): read every
optional field with `.get()`, never crash on a missing one, and say in the report which fields you assumed.

### B13: Service guide from the sandbox registry (phase 5)
SPEC F5 (report flow) and the Stoa idea of «what do I do now». The 570-service registry is used today only by
`POST /api/ask` (top hit). Here a report category gets its official service.
**Files:** `app/service_guide.py` (new), `app/routers/service_guide.py` (new), `app/sandbox.py` (only
`_MockData.services` and `_MockData.service`), `web/js/api.js` (new `serviceFor`), `web/mock/services.json` (new),
`web/mock/README.md` (one row), `tests/test_B13_service_guide.py`, `web/tests/B13_service_guide.test.js`.
- `app/service_guide.py`: `QUERIES: dict[str, str | None]`, one curated Greek registry query per sandbox category
  (`categories.SANDBOX`): `pothole` «λακκούβα οδόστρωμα», `streetlight` «βλάβη ηλεκτροφωτισμού», `garbage`
  «αποκομιδή απορριμμάτων», `bulky_waste` «αποκομιδή ογκωδών αντικειμένων», `graffiti` «καθαρισμός γκράφιτι»,
  `tree` «κλάδεμα δέντρων», `sidewalk` «επισκευή πεζοδρομίου», `abandoned_vehicle` «εγκαταλελειμμένα οχήματα»,
  `noise` «ηχορύπανση», `stray_animals` «αδέσποτα ζώα», `water_leak` «διαρροή νερού», `other` `None`.
  `guide(sb, category) -> dict`: `sb.services(query, size=3)`, first item with `score > 0`, then
  `sb.service(id)`. Returns `{category, label_el (categories.LABEL_EL), query, service, source}` where `service` is
  `{id, title, documents: [], cost_eur, online_url, where, when, faq: []}` (missing fields → `None` / `[]`) or
  `None` when there is no match or the category is `other`; `source` is `"mock"` when `sb.mock` else `"sandbox"`.
- `app/routers/service_guide.py`: `GET /api/map/services?category=` (A-32 discovery). Unknown category → 422.
  `SandboxError` → 503 (so `api.js` falls back to the mock).
- `_MockData.services(q)`: a small fictional catalogue, every title ending in «(mock)», with entries for at least
  `bulky_waste`, `streetlight`, `sidewalk`, `pothole`, `tree`, matched by a keyword of the query. A query that
  matches nothing returns the existing `svc-mock-1` item (so `POST /api/ask` keeps working); a query from
  `service_guide.QUERIES` that has no mock entry returns `items: []`. `_MockData.service(id)` returns the matching
  entry, `svc-mock-1` otherwise. Existing tests keep passing.
- `web/js/api.js`: `serviceFor(category)` → `read("service:"+category, "/api/map/services?category=…", …,
  mock: the entry for that category in web/mock/services.json, or {category, service: null})`. Cached like other
  reads (registry data is stable, not Stoa).
- `web/mock/services.json`: `{ "<category>": {category, label_el, query, service, source: "mock"} }` for all 12
  categories, same shape as the route.

| Test | Given | Expected |
|---|---|---|
| `test_services_bulky_waste_returns_official_service` | mock sandbox, `GET /api/map/services?category=bulky_waste` | 200; `service.title` contains «ογκωδ» (case-insensitive); `documents` is a list; `source == "mock"`; `label_el == "Ογκώδη"` |
| `test_services_every_category_has_query_except_other` | `service_guide.QUERIES` | keys == set(`categories.SANDBOX`); every value a non-empty str except `other` → `None` |
| `test_services_other_returns_null_service` | `GET …?category=other` | 200, `service is None`, `sb.services` not called (monkeypatched spy) |
| `test_services_unknown_category_422` | `GET …?category=spaceship` | 422 |
| `test_services_no_match_returns_null` | monkeypatch `sb.services` → `{"items": []}` | 200, `service is None` |
| `test_services_zero_score_ignored` | monkeypatch `sb.services` → one item with `score: 0` | `service is None`, `sb.service` not called |
| `test_services_missing_fields_default` | monkeypatch `sb.service` → `{"id": "x", "title": "T"}` | `service == {id:"x", title:"T", documents:[], cost_eur:None, online_url:None, where:None, when:None, faq:[]}` |
| `test_services_sandbox_error_503` | monkeypatch `sb.services` raising `SandboxError` | 503 |
| `test_ask_still_returns_mock_service` | `POST /api/ask {"text": "βεβαίωση μόνιμης κατοικίας"}` | `service.id == "svc-mock-1"` (unchanged behaviour) |
| `serviceFor: live answer marked live` (JS) | fake fetch → 200 JSON for `bulky_waste` | `source == "live"`, URL path `/api/map/services?category=bulky_waste` |
| `serviceFor: offline falls back to mock file entry` (JS) | fetch rejects, fake mock loader returns services.json | `source == "mock"`, `category == "pothole"` |
| `services.json has all 12 categories` (JS) | read `web/mock/services.json` | keys == the 12 sandbox categories; each `source == "mock"`; `other.service === null` |

### B14: Official POI layer (phase 5)
SPEC F2 layers. `/v1/pois` is used today only for Friendship Clubs and libraries (cool places, envgrid). This
exposes the sandbox POIs as a map layer marked as the City's own data.
**Files:** `app/routers/pois_map.py` (new), `web/js/api.js` (new `pois`), `web/mock/pois.geojson` (new),
`web/mock/README.md` (one row), `tests/test_B14_pois.py`, `web/tests/B14_pois.test.js`.
- `GET /api/map/pois?categories=friendship_club,library&bbox=minLon,minLat,maxLon,maxLat`. `categories` is
  comma-separated, default `friendship_club,library` (the two verified categories; any other string is passed
  through to the sandbox). `bbox` optional: centre = bbox centre, radius = half the bbox diagonal (haversine km),
  capped at 5 km; no bbox → Σύνταγμα `[23.7348, 37.9755]`, 3 km. Bad bbox (not 4 floats, min > max) → 422.
- One `sb.pois(category=c, lat, lng, radius_km, size=50)` call per category. A `SandboxError` on one category
  skips it and lists it in top-level `errors: [category]`; all categories failing → 503.
- Response: GeoJSON `FeatureCollection`; each Feature `id` = POI id, Point `[lng, lat]`, properties `{id, name,
  category, address, open_now, distance_km, source: "sandbox"|"mock", official: true}`; duplicates (same id) once;
  sorted by `distance_km`. POIs with no lat/lng are dropped.
- `web/js/api.js`: `pois({ bbox, categories } = {})` → `read("pois", …, mock web/mock/pois.geojson)`.
- `web/mock/pois.geojson`: the 3 fictional POIs of `_MockData` (names end in «(mock)»), same shape, `source: "mock"`.

| Test | Given | Expected |
|---|---|---|
| `test_pois_default_returns_feature_collection` | mock sandbox, `GET /api/map/pois` | 200, `type == "FeatureCollection"`, 3 features, every `properties.official is True`, `source == "mock"` |
| `test_pois_feature_coordinates_are_lng_lat` | same | feature `poi-mock-1` geometry `[23.7476, 37.9689]` |
| `test_pois_single_category_filter` | `?categories=library` | only `library` features |
| `test_pois_bbox_radius_excludes_far` | bbox of ~200 m around Σύνταγμα | 0 features (mock POIs are in Παγκράτι, > 1 km away) |
| `test_pois_bbox_radius_capped_5km` | monkeypatched `sb.pois` spy, bbox spanning the whole Δήμος and more | spy saw `radius_km <= 5` |
| `test_pois_bad_bbox_422` | `?bbox=1,2,3` and `?bbox=23.8,37.9,23.7,38.0` | 422 both |
| `test_pois_one_category_error_listed` | `sb.pois` raises `SandboxError` for `library` only | 200, `errors == ["library"]`, friendship_club features present |
| `test_pois_all_categories_error_503` | `sb.pois` always raises | 503 |
| `test_pois_drops_missing_coordinates_and_duplicates` | `sb.pois` returns the same id twice + one item without lat | one feature |
| `pois: live answer marked live` (JS) | fake fetch → 200 FeatureCollection | `source == "live"`, path starts `/api/map/pois` |
| `pois: offline falls back to pois.geojson` (JS) | fetch rejects | `source == "mock"`, 3 features, all `official === true` |

### B15: «Διορθώθηκαν κοντά σου» — resolved requests layer (phase 5)
SPEC F5 (closing the loop) and the pitch: the City does fix things. Requests the sandbox marks `resolved` become a
layer, with how long each took. `/api/equity` (per-district stats) already exists and is not touched.
**Files:** `app/routers/resolved_map.py` (new), `web/js/api.js` (new `resolved`), `tests/test_B15_resolved.py`,
`web/tests/B15_resolved.test.js`.
- `GET /api/map/resolved?bbox=&days=30`. `sb.list_requests(status="resolved", lat, lng, radius_km, size=100)`
  with the same bbox → centre/radius rule as B14 (no bbox: Σύνταγμα, 3 km; cap 5 km; bad bbox 422). `days` 1–365
  (else 422). Today = `works.today()` (honours `STOA_TODAY`).
- `resolved_at` = the `at` of the first `history` entry with status `resolved`, else `updated_at`. Requests with
  `resolved_at` older than `days` before today are dropped. `hours_to_resolve` = hours from `created_at` to
  `resolved_at`, 1 decimal, `None` if a timestamp is missing or unparsable.
- Response: `FeatureCollection` + top-level `summary: {count, median_hours_to_resolve}` (median of non-null
  values, `None` when none). Feature properties **only** `{id, category, label_el, resolved_at,
  hours_to_resolve, district_name}`; coordinates rounded to 4 decimals (~10 m, SPEC privacy). Never `title`,
  `description`, `address`, `note`, `history`, photos, persona or `created_by_you`. Requests without lat/lng are
  dropped. `SandboxError` → 503.
- `web/js/api.js`: `resolved({ bbox, days } = {})` → `read("resolved", …, mock: empty FeatureCollection with
  summary {count: 0, median_hours_to_resolve: null})` (no mock file: we have no real resolved data to show).

| Test | Given | Expected |
|---|---|---|
| `test_resolved_lists_resolved_request` | mock sandbox: create a request at Σύνταγμα, PATCH it to `resolved` | `GET /api/map/resolved` has 1 feature with its id, `category`, `label_el`, `resolved_at` |
| `test_resolved_excludes_open_requests` | one `submitted`, one `resolved` | only the resolved one |
| `test_resolved_hours_to_resolve` | monkeypatched `list_requests`: `created_at` 2026-11-20T10:00Z, history resolved at 2026-11-21T16:30Z | `hours_to_resolve == 30.5`; `summary.median_hours_to_resolve == 30.5` |
| `test_resolved_falls_back_to_updated_at` | no `resolved` history entry, `updated_at` set | `resolved_at == updated_at` |
| `test_resolved_days_window` | `STOA_TODAY=2026-11-21`; one resolved 2026-11-19, one 2026-09-01; `days=30` | only the first |
| `test_resolved_days_out_of_range_422` | `days=0` and `days=400` | 422 both |
| `test_resolved_no_personal_fields` | request with title, description, address, note, history, `created_by_you` | feature properties keys == `{id, category, label_el, resolved_at, hours_to_resolve, district_name}` |
| `test_resolved_coordinates_rounded` | lat `37.975512`, lng `23.734871` | geometry `[23.7349, 37.9755]` |
| `test_resolved_bad_bbox_422` | `?bbox=a,b,c,d` | 422 |
| `test_resolved_sandbox_error_503` | `list_requests` raises `SandboxError` | 503 |
| `test_resolved_median_none_when_empty` | no resolved requests | `summary == {count: 0, median_hours_to_resolve: None}` |
| `resolved: live answer marked live` (JS) | fake fetch → 200 | `source == "live"`, path starts `/api/map/resolved` |
| `resolved: offline gives empty collection` (JS) | fetch rejects | `source == "mock"`, `features.length == 0`, `summary.count == 0` |

## Phase 6: backlog (after freeze, owner's request 22 Nov)

The backlog was written over two days and **some items are already fixed** on `main`. For every item below the test
writer first checks whether the bug still exists: write the listed test anyway; if it already passes before any code,
keep it as a regression test and say so in the report ("already fixed"); the implementer then leaves that item alone.
B16 and B17 run in parallel with A10 (no shared files except that A10 only *reads* `api.pois()`).

### B16: Backend backlog fixes (phase 6)
**Files:** `app/store.py`, `app/routers/map_reports.py`, `app/routers/routing_map.py`, `app/route_cost.py`,
`app/routers/works_map.py`, `app/config.py` (only if a new constant is needed), `tests/test_B16_backlog.py`.
- **T2 Athens day:** the points daily cap counts by the Europe/Athens calendar day, not SQLite UTC `date('now')`.
  Use `zoneinfo.ZoneInfo("Europe/Athens")` (stdlib): compute the UTC start/end of today's Athens day in Python and
  compare `created_at` against them. Stored timestamps stay UTC.
- **B6 Athens bounds:** `POST /api/map/reports` with a point outside `config.ENV_BBOX` (the Δήμος bbox,
  `23.68,37.95,23.80,38.03`) → 422 `«Η αναφορά είναι εκτός Δήμου Αθηναίων»`; nothing stored, no points.
  `GET /api/map/reports?bbox=nan,nan,nan,nan` (or `inf`) → 422.
- **B9 blocked flag:** `POST /api/map/routing` answer gains `blocked: bool` (additive, A-40): `true` when the
  wheelchair profile's chosen route still touches a hard blocker (in-progress work or obstacle report), else `false`
  (always `false` for stroller / cool). Use the same "touches" test `route_cost.choose` uses.
- **B12 duplicates:** an `obstacle`/`damage` map report that the duplicate check folds into an existing case must not
  add a second count to `works_map` `reports_count` for the same work.

| Test | Given | Expected |
|---|---|---|
| `test_daily_cap_uses_athens_day` | cap reached with entries at 2026-11-21T21:30Z (= 23:30 Athens, 21 Nov); now = 2026-11-21T22:30Z (= 00:30 Athens, 22 Nov) | a new award is allowed (new Athens day). Inject "now" via a monkeypatched helper, not the wall clock |
| `test_daily_cap_same_athens_day_still_blocks` | cap reached at 2026-11-21T08:00Z, now 2026-11-21T20:00Z | award refused |
| `test_report_outside_athens_422` | `POST /api/map/reports` at Πειραιάς `lon=23.6470, lat=37.9420` | 422 with the Greek message; `GET /api/map/reports` unchanged; points balance unchanged |
| `test_report_inside_athens_still_ok` | same POST at Σύνταγμα `23.7348, 37.9755` | 200/201 as before |
| `test_reports_bbox_non_finite_422` | `GET /api/map/reports?bbox=nan,nan,nan,nan` and `?bbox=-inf,0,inf,1` | 422 both |
| `test_routing_blocked_true_when_every_candidate_blocked` | monkeypatched `routing.candidates` → candidates that all pass through an obstacle report; `profile="wheelchair"` | 200, `blocked is True` |
| `test_routing_blocked_false_normally` | the existing Σύνταγμα→Μοναστηράκι wheelchair case with no blockers | `blocked is False` |
| `test_routing_blocked_false_for_stroller` | same blocked candidates, `profile="stroller"` | `blocked is False` |
| `test_duplicate_obstacle_not_double_counted_on_work` | two `obstacle` reports 10 m apart within 5 min on `W-SEED-001` (`23.7420, 37.9660`) | `GET /api/map/works` `reports_count` for `W-SEED-001` == 1 |

### B17: Frontend backlog fixes + official service after a report (phase 6)
**Files:** `web/js/ui/report.js`, `web/js/ui/points.js`, `web/js/api.js`, `web/css/` **no** (inline classes already
in `hud.css` only; if a new style is needed write it under "Questions"), `web/tests/B17_backlog.test.js`.
- **Service after submit (B13):** after `sendReport` succeeds (live or queued), `report.js` calls
  `api.serviceFor(sandboxCategory)` and shows a block «Τι μπορείτε να κάνετε ακόμα» with the service title, the
  documents list, cost («Δωρεάν» for 0, «άγνωστο» for null) and a link «Επίσημη σελίδα» (`online_url`, `rel="noopener"`,
  `target="_blank"`). Mapping: `damage`/`obstacle` + subtype via `{sidewalk: "sidewalk", ramp: "sidewalk",
  pothole: "pothole", streetlight: "streetlight", other: "other"}` (same as `app/categories.py`
  `SUBTYPE_TO_SANDBOX`); `congestion`, `incident`, `work_progress` → no call. `service: null` or a failed call →
  nothing shown (never an error to the user). A `source`/`upstream_source` of `mock` adds «δοκιμαστικό».
  Export the mapping as `sandboxCategoryFor(category, subtype)`.
- **B7 dates:** `ui/points.js` history dates show the Europe/Athens date (`Intl.DateTimeFormat("el-GR",
  {timeZone: "Europe/Athens"})`), not `ts.slice(0, 10)`.
- **B1 mock filters:** when `api.works({status})` falls back to the mock, features are filtered by `status`; when
  any GeoJSON read with a `bbox` falls back to the mock or cache, Point features outside the bbox are dropped
  (LineString: kept if any vertex is inside).
- **B11 offline flush:** `flushQueue` dispatches `report:created` for every report it sends (check first; it may
  already).

| Test | Given | Expected |
|---|---|---|
| `sandboxCategoryFor maps subtypes` | `("damage","ramp")`, `("obstacle","pothole")`, `("damage","other")`, `("congestion")`, `("work_progress")` | `"sidewalk"`, `"pothole"`, `"other"`, `null`, `null` |
| `report shows official service after submit` | fake api: `sendReport` ok, `serviceFor("sidewalk")` → service with title, 2 documents, `cost_eur: 0`, `online_url` | the form shows «Τι μπορείτε να κάνετε ακόμα», the title, both documents, «Δωρεάν», a link with `rel` containing `noopener` |
| `report shows unknown cost as άγνωστο` | same, `cost_eur: null` | «άγνωστο» |
| `report skips service for congestion` | category `congestion` | `serviceFor` not called |
| `report hides block when service null or call fails` | `serviceFor` → `{service: null}`; then rejects | no block, no error text, submit success still shown |
| `report labels mock service` | `serviceFor` → `upstream_source: "mock"` | «δοκιμαστικό» shown in the block |
| `points history shows Athens date` | history entry `ts: "2026-11-21T22:30:00Z"` | rendered date is 22/11/2026 (Athens), not 2026-11-21 |
| `works mock filtered by status` | fetch rejects; `api.works({status: "completed"})` with a mock containing planned + completed | only completed features, `source == "mock"` |
| `mock GeoJSON filtered by bbox` | fetch rejects; `api.reports({bbox: [23.72,37.97,23.73,37.98]})`, mock with one point inside and one outside | only the inside point |
| `flushQueue dispatches report:created` | queued report, fake bus, `sendReport` ok | one `report:created` event per sent report |
