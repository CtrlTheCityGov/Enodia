# Tasks: Dev B (Evgenii) — Δεδομένα & backend

Board for the Dev B track of [SPEC.md](SPEC.md). Workflow and rules: [`../../CLAUDE.md`](../../CLAUDE.md).
Base branch: `dev-b`. Every task: branch `agent/B<n>-<name>` in `.worktrees/B<n>`, merged into `dev-b` on Evgenii's
word. Cards get a full test list (like [TASKS_A.md](TASKS_A.md)) before they start.

Dev B owns (SPEC «Ιδιοκτησία αρχείων»): `web/js/api.js`, `web/mock/*`, `web/js/ui/{report,points,stoa,workstab}.js`,
the backend (`app/`, `tests/`, `scripts/`, `data/`). Existing routes don't change (SPEC rule); new ones are added.
The real routes vs the SPEC's short names: [SPEC.md, Παράρτημα](SPEC.md#παράρτημα-spec--υπάρχον-backend).

| Task | Phase | What | State |
|---|---|---|---|
| B0 Contracts + first mocks | 0 | Lock the SPEC contracts against the Παράρτημα; `web/mock/*` (env, access, works with 10–15 real works, transit, health, points, stoa) realistic enough for the demo; offline boundary + main roads for A1 | **running** (approved by Evgenii, Sat 21 Nov) |
| B1 `api.js` | 1 | Only door to the backend; live → `localStorage` cache → `mock/`; `source: live\|cache\|mock`; maps the real routes to SPEC shapes; offline report queue sent on `online` | card to write |
| B2 Works adapters | 2 | Διαύγεια + ΚΗΜΔΗΣ, join on ΑΔΑ/ΑΔΑΜ, curated geocoding; `/api/works/geojson` gains SPEC fields (`amount_paid_eur`, `guarantee_end`, `reports_count`, …) | card to write |
| B3 `/api/transit` | 2 | ΟΑΣΑ telematics (buses), GTFS/OSM metro + suburban lines and stations | card to write |
| B4 On-duty pharmacies/hospitals | 2 | New endpoint (path decision: `/api/health` is taken, see Q-1) | card to write |
| B5 Env grid | 2 | Open-Meteo forecast + air-quality on a grid over the Δήμος, `temp_c`, `aqi`, `pm25` per point | card to write |
| B6 Report flow «+» | 2 | `ui/report.js`; `/api/report` accepts `category`, `work_id`, optional photo; plate blur; public location rounded ~10 m; points per SPEC rules | card to write |
| B7 Points pill + panel | 2 | `ui/points.js`, pulse + «+N»; SPEC rewards; `/points/redeem` (Nice) | card to write |
| B8 Stoa citations + flyTo | 2 | `/api/stoa/ask` returns `citations[{label, lon, lat, kind}]`; `ui/stoa.js` | card to write |
| B9 Route cost per profile | 2 | wheelchair / stroller / cool from the same layers the map shows; `reasons[{text, layer, feature_id}]` | card to write |
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
