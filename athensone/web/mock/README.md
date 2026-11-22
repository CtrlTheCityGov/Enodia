# Offline Mock Datasets (`web/mock/`)

**Snapshot date:** `2026-11-21`
**Builder script:** [`scripts/build_mocks.py`](../../scripts/build_mocks.py)
**Contract canon:** [`docs/SPEC.md`](../../docs/SPEC.md) («Backend contracts», «Offline fallback»)

All nine JSON/GeoJSON files match the exact response shapes expected by `web/js/api.js` (task B1) and Dev A's map layers so the full 3-minute demo runs offline without network access. Every GeoJSON file uses WGS84 coordinates inside the Municipality of Athens bounding box (`lon 23.68–23.80`, `lat 37.95–38.03`).

## Provenance summary

| File | Real data | Invented / demo-only | Licence |
|---|---|---|---|
| `env.json` | 91 Municipality of Athens CKAN air-quality sensors (`opendata.cityofathens.gr`, `2026-11-21T14:00:00Z`) placed at neighbourhood centroids (A-21), covering central Athens (Σύνταγμα, Μοναστηράκι, Ψυρρή, Κολωνάκι) and all 7 districts; faulty PM2.5 spike excluded | None (live snapshot) | CC BY 4.0 |
| `access.geojson` | OpenStreetMap accessibility features (`kerb=lowered`, `ramp=yes`, `tactile_paving=yes`, named `wheelchair=yes/limited` POIs) around Σύνταγμα–Μοναστηράκι–Πλάκα with exact OSM IDs | None | ODbL 1.0 |
| `works.geojson` | 10 real Municipality of Athens (`org 6013`) public-works decisions from `diavgeia.gov.gr` (real ADA, `source_url`, contractor, ADAM, payment amount, contract date; unknown fields kept `null`) | Representative street segments for district-wide framework contracts; 2 clearly marked `SEED-` works (`seed: true`) with contract/guarantee bars for UI testing | Diavgeia Open Data / SEED |
| `transit.geojson` | 18 real OSM station coordinates & IDs (`Σύνταγμα`, `Μοναστηράκι`, etc.); STASY/OASA official line colours | Simplified station-to-station line segments; simulated OASA bus positions, bearings & ETAs | ODbL 1.0 / Mock |
| `health.geojson` | 6 real central Athens public hospitals & 6 real OSM pharmacy locations (phones from OSM tags or `άγνωστο`) | `on_duty` flags, duty hours and demo specialties (ΦΣΑ / Ministry of Health lists not fetched live) | ODbL 1.0 / Mock |
| `reports.geojson` | None (all 10 reports are simulated citizen fixtures across all 5 SPEC categories) | Coordinates rounded to 4 decimals (~10 m, SPEC Privacy); no personal IDs, tokens or photos | Mock |
| `points.json` | Point rules (`+5/+2/+15/+20`) from SPEC.md; district goal `5000` (A-9) | Simulated anonymous wallet history & illustrative municipal rewards (no `user_id`) | Mock |
| `stoa.json` | Snapshot `2026-11-21` — top-level JSON array without a wrapper object (so `api.js` matches `POST /stoa_ask` entries directly). Citations align with `health.geojson` (0 m offset for the Syntagma demo pharmacy), `works.geojson`, `transit.geojson`, and `env.json`. | Pre-canned offline Q&A answers for the demo questions, including `«Ποιο φαρμακείο εφημερεύει κοντά μου;»`, using cautious Stoa wording («πιθανώς εντός περιόδου εγγύησης»). | Mock + cited sources |
| `services.json` | None. Generated from the fictional `_MockData` registry catalogue in `app/sandbox.py` through `app/service_guide.guide()` (B13), so it has the exact shape of `GET /api/map/services`; one entry per sandbox category (12) | All 5 services (`bulky_waste`, `streetlight`, `sidewalk`, `pothole`, `tree`) are invented, titles end in «(mock)», `cost_eur` is `null` (unknown); the other 7 categories have `service: null` | Mock |
| `base.geojson` | 7 Municipal District MultiPolygons from CKAN `neighbourhoods-athens` & `municipal-districts-athens` (simplified ~45 m, edge-clamped to bbox) | Simplified arterial road corridors for A1 offline style | CC BY 4.0 / ODbL 1.0 |
| `pois.geojson` | None (the 3 fictional POIs of the mock sandbox, `app/sandbox.py` `_MockData`; names end in «(mock)») | All 3 POIs; `distance_km` measured from Σύνταγμα `[23.7348, 37.9755]`; every feature `official: true`, `source: "mock"` (B14) | Mock |

**Value conventions (shared with the live endpoints):** report `category` ids are `congestion`, `incident`,
`obstacle`, `damage`, `work_progress` (B6; Greek labels in `ui/report.js`). Stoa citation `kind` is `work`,
`pharmacy`, `hospital`, `transit` or `env` (B8). Every env point has `aqi_scale`: `city_1_6` (AthensGov station
class 1–6) or `eaqi` (Open-Meteo European AQI 0–100+); the two don't compare, so colour by `pm25` (µg/m³ on both)
(A-37).
