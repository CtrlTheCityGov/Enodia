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
| B1 `api.js` | 1 | Only door to the backend; live → `localStorage` cache → `mock/`; `source: live\|cache\|mock`; maps the real routes to SPEC shapes; offline report queue sent on `online` | **running** |
| B2 Works adapters | 2 | Διαύγεια + ΚΗΜΔΗΣ, join on ΑΔΑ/ΑΔΑΜ, curated geocoding; `/api/map/works` with every SPEC field | **running** |
| B3 `/api/map/transit` | 2 | ΟΑΣΑ telematics (buses), GTFS/OSM metro + suburban lines and stations | **running** |
| B4 On-duty pharmacies/hospitals | 2 | `/api/map/health` (A-33) | **running** |
| B5 Env grid | 2 | Open-Meteo forecast + air-quality on a grid over the Δήμος, `temp_c`, `aqi`, `pm25` per point | **merged** into `dev-b` |
| B6 Report flow «+» | 2 | `ui/report.js`; `/api/map/reports` with `category`, `work_id`, optional photo; plate blur; public location rounded ~10 m; points per SPEC rules | **running** |
| B7 Points pill + panel | 2 | `ui/points.js`, pulse + «+N»; SPEC rewards; `/points/redeem` (Nice) | **running** |
| B8 Stoa citations + flyTo | 2 | `/api/map/stoa_ask` with `citations[{label, lon, lat, kind}]`; `ui/stoa.js` | **running** |
| B9 Route cost per profile | 2 | wheelchair / stroller / cool from the same layers the map shows; `reasons[{text, layer, feature_id}]` | **running** |
| B10 Works tab (F8) | 3 | `ui/workstab.js`, crowdsourced progress | later |

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
