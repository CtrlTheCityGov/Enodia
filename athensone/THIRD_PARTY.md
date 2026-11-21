# Third-Party Dependencies and Licences

AthensOne is released under the MIT licence. All third-party packages and assets used by the application are listed below with their licences.

## Python backend (`requirements.txt`)

| Package | Version / Pin | Licence | Role | Source |
|---|---|---|---|---|
| `fastapi` | `>=0.110` | MIT | HTTP API framework | https://github.com/fastapi/fastapi |
| `uvicorn` | `>=0.29` | BSD-3-Clause | ASGI server | https://github.com/Kludex/uvicorn |
| `httpx` | `>=0.27` | BSD-3-Clause | HTTP client (sandbox, Valhalla, CKAN, Open-Meteo, vision) | https://github.com/encode/httpx |
| `python-multipart` | `>=0.0.9` | Apache-2.0 | Multipart form/photo upload parsing | https://github.com/Kludex/python-multipart |
| `pillow` | `>=10` | MIT-CMU (HPND) | Image decoding, EXIF GPS extraction, orientation transpose | https://github.com/python-pillow/Pillow |
| `opencv-python-headless` | `>=4.9,<5` | Apache-2.0 | Image encoding, Gaussian blur, `cv2.dnn` inference, Haar cascade fallback | https://github.com/opencv/opencv-python |
| `numpy` | `>=1.26` | BSD-3-Clause | Array operations for photo processing and face detection | https://github.com/numpy/numpy |
| `python-dotenv` | `>=1.0` | BSD-3-Clause | `.env` configuration loading | https://github.com/theskumar/python-dotenv |
| `pytest` | `>=8` | MIT | Offline test suite | https://github.com/pytest-dev/pytest |
| `scikit-image` | `>=0.22` | BSD-3-Clause | Bundled offline face test fixture (`skimage.data.astronaut`) in `tests/test_T5_blur.py` | https://github.com/scikit-image/scikit-image |

### T5: Face detection (`deface` / CenterFace)

| Package | Version / Pin | Licence | Role | Source |
|---|---|---|---|---|
| `deface` (bundles `centerface.onnx`) | `==1.5.0` (installed with `pip install --no-deps deface==1.5.0`) | MIT (`Copyright (c) 2020 Martin Drawitsch`, verified in installed `deface-1.5.0` metadata) | Primary face detector (`deface.centerface.CenterFace`) in `app/privacy.py`, with automatic fallback to OpenCV Haar cascades. Runs on OpenCV `cv2.dnn` without `onnxruntime`. | https://github.com/ORB-HD/deface |

> **Install note (OpenCV 4.x compatibility):** `deface==1.5.0` declares `opencv-python` (unpinned, resolving to 5.x, which removes `cv2.CascadeClassifier`). Always install `deface` with `pip install --no-deps deface==1.5.0` after `requirements.txt` so `opencv-python-headless>=4.9,<5` remains intact. `deface.centerface.CenterFace` only imports `os`, `functools`, `numpy`, and `cv2`.
>
> **Model weights:** `centerface.onnx` comes from CenterFace (https://github.com/Star-Clouds/CenterFace), MIT licence
> (from memory, not re-checked tonight: open its LICENSE before the final push). `onnxruntime` (MIT) is not installed;
> the model runs on OpenCV `cv2.dnn`.

### B6: Licence-plate blur

| Asset | Version | Licence | Role | Source |
|---|---|---|---|---|
| `haarcascade_russian_plate_number.xml` (bundled in `opencv-python-headless`, `cv2.data.haarcascades`) | ships with the pinned `>=4.9,<5` (checked in 4.14.0) | Apache-2.0 (OpenCV ≥ 4.5; the XML has no header of its own) | Best-effort plate detection before blur in `app/privacy.py` (`blur.plates` in `POST /api/map/reports`). No new dependency. | https://github.com/opencv/opencv/tree/4.x/data/haarcascades |

## Frontend & accessibility (`web/`, `package.json`)

| Package / Asset | Version | Licence | Role | Source |
|---|---|---|---|---|
| `maplibre-gl` | `5.3.0` (jsDelivr CDN) / `4.7.1` (legacy & operator) | BSD-3-Clause | Interactive 3D map rendering (`web/citizen.html` uses `5.3.0`; `web/operator.html` and `web/citizen-legacy.html` use `4.7.1`) | https://github.com/maplibre/maplibre-gl-js |
| OpenFreeMap (`Liberty` / `Fiord` vector styles) | — | OpenStreetMap data © ODbL 1.0; OpenFreeMap public tiles (no API key) | 3D Light/Dark vector basemap styles in `web/js/map.js` (`tiles.openfreemap.org`) | https://openfreemap.org |
| OpenStreetMap tiles | — | ODbL 1.0 | Basemap tiles (`© OpenStreetMap` attribution shown) | https://www.openstreetmap.org/copyright |
| `axe-core` | `^4.10.0` | MPL-2.0 | Accessibility check dev dependency (`scripts/a11y_check.py`) | https://github.com/dequelabs/axe-core |

## Open Data Sources (Offline Mocks & Snapshots)

| Data Source | Snapshot / Access | Licence | Role | Source |
|---|---|---|---|---|
| Municipality of Athens Open Data Portal (CKAN) | Snapshot `2026-11-21` | CC BY 4.0 | Environmental sensor readings (`env-all-stations`), neighbourhood polygons & municipal districts (`neighbourhoods-athens`, `municipal-districts-athens`) used in `web/mock/env.json` and `web/mock/base.geojson` | https://opendata.cityofathens.gr |
| OpenStreetMap (OSM API 0.6 / Nominatim) | Snapshot `2026-11-21` | ODbL 1.0 | Accessibility features (`web/mock/access.geojson`), Metro/Suburban station coordinates (`web/mock/transit.geojson`), central Athens hospital & pharmacy locations (`web/mock/health.geojson`), and arterial street corridors (`web/mock/base.geojson`) | https://www.openstreetmap.org/copyright |
| Diavgeia OpenData API (Διαύγεια — Δήμος Αθηναίων, org `6013`) | Verified `2026-11-21` | Greek Public Sector Open Data (Law 4727/2020) | Real Municipality of Athens public-works decision metadata (ADA, contractor, payment amount, ADAM, contract date) in `web/mock/works.geojson` | https://diavgeia.gov.gr/opendata |

## External data sources (Track B)

| Source | Endpoint / Dataset | Licence | Role | URL |
|---|---|---|---|---|
| Open-Meteo Forecast API | `/v1/forecast` (`temperature_2m`) | CC BY 4.0 (free tier: non-commercial use; attribution: *Weather data by Open-Meteo.com*) | Temperature grid in `app/envgrid_src.py` (`GET /api/map/env`) and weather in `app/main.py` | https://open-meteo.com/en/terms |
| Open-Meteo Air Quality API | `/v1/air-quality` (`european_aqi`, `pm2_5`) | CC BY 4.0 (free tier: non-commercial use; attribution: *Weather data by Open-Meteo.com*) | European AQI and PM2.5 grid in `app/envgrid_src.py` (`GET /api/map/env`) | https://open-meteo.com/en/docs/air-quality-api |
| AthensGov Open Data (CKAN) | `env-stations-registry`, `env-all-stations` | CC BY 4.0 | Municipal environmental sensor overrides within 300 m in `app/envgrid_src.py` via `app/ckan.py` | https://opendata.cityofathens.gr |

### B2: Works data sources (`app/works_src.py`, `scripts/fetch_works.py`)

| Source | Licence / terms | Role | Source URL |
|---|---|---|---|
| Διαύγεια OpenData API | Public-sector open data (ν. 3861/2010, ν. 4727/2020 open-data reuse); licence text not re-checked tonight | Δήμος Αθηναίων decisions (αναθέσεις, αναλήψεις, πληρωμές): ΑΔΑ, subject, date, amount. Saved search in `tests/fixtures/B2/diavgeia.json` | https://diavgeia.gov.gr/opendata |
| ΚΗΜΔΗΣ OpenData API | Public-sector open data (ν. 4412/2016 art. 38, ν. 4727/2020); licence text not re-checked tonight | Contracts: ΑΔΑΜ, contractor, amounts, dates, linked ΑΔΑ. Saved page in `tests/fixtures/B2/khmdhs.json` (civil servants' e-mail and signer names removed) | https://cerpp.eprocurement.gov.gr/khmdhs-opendata |
| OpenStreetMap (via Overpass, once, by hand) | ODbL 1.0 | Street segments in the curated `STREETS` table of `scripts/fetch_works.py` | https://www.openstreetmap.org/copyright |

### B3: Transit data sources (`app/transit_src.py`, `scripts/fetch_transit.py`)

| Source | Licence / Terms | Role | URL |
|---|---|---|---|
| OpenStreetMap via Overpass API | ODbL 1.0 (`© OpenStreetMap contributors`) | Static Athens Metro (M1/M2/M3) and Suburban Railway (Προαστιακός A1–A4) line geometries, official line colours, stations, and wheelchair/elevator tags (`scripts/fetch_transit.py` → `data/transit/static.json`) | https://overpass-api.de/api/interpreter |
| OASA Telematics API | Public transit open telematics service by OASA S.A. (unverified formal licence file; accessed server-side only with 20 s cache, never redistributed as bulk dataset) | Live bus locations (`getBusLocation`) and stop arrival waits (`getStopArrivals`) in `app/transit_src.py` | https://telematics.oasa.gr/api/ |

### B4: On-duty pharmacies and hospitals (`app/onduty_src.py`)

| Source | Licence / Terms | Role | URL |
|---|---|---|---|
| Φαρμακευτικός Σύλλογος Αττικής (ΦΣΑ) | Public on-duty pharmacy directory (no formal open-data licence stated; cached daily, read-only attribution shown) | Daily on-duty pharmacies in Attica (`app/onduty_src.py`) | https://fsa-efimeries.gr/Home/FilteredHomeResults |
| Υπουργείο Υγείας — Εφημερίες Νοσοκομείων Αττικής | Public government daily duty announcements (Greek public sector information; read-only attribution shown) | Daily on-duty hospital clinics/specialties (`app/onduty_src.py`) | https://www.moh.gov.gr/articles/citizen/efhmeries-nosokomeiwn/68-efhmeries-nosokomeiwn-attikhs |
| OpenStreetMap / Nominatim | ODbL 1.0 (`© OpenStreetMap contributors`) | Curated hospital coordinates (`data/onduty/hospitals.json`) and cached address geocoding fallback (`app/onduty_src.py`) | https://nominatim.openstreetmap.org/search |
