# Enodia · Η Ζωντανή Ψηφιακή Λογοδοσία & Πλοήγηση της Αθήνας

**Enodia — The living digital accountability and navigation layer of Athens.**

Apps4Athens 3.0 Gov Hackathon · 21–22 Nov 2026 · Serafio · Track: AthensGov AI Transformation (Η)

Enodia connects public-works accountability, inclusive urban routing, and a closed citizen-to-operator municipal loop on one 3D map of Athens:

- **Stoa (Public Works Accountability)**: Verified municipal works on each street (Diavgeia org 6013 + clearly marked `DEMO` seed records), 15-month guarantee clock (ν. 4412/2016 art. 171), cited answers `[ΑΔΑ …]`, live ΑΔΑ lookup, and one-click contractor defect dossiers.
- **Accessible & Heat-Aware Navigation**: `wheelchair`, `stroller`, and `cool` profiles (Valhalla + OSM shade/traffic/rest scoring), ghost baseline comparison, why-this-route scoreboard, live GPS route-snapping, and hazard avoidance around open reports and active works. See [docs/NAVIGATION.md](docs/NAVIGATION.md).
- **Closed Citizen ↔ Operator Loop**: Citizens submit blurred-photo reports (faces blurred + EXIF stripped in memory before storage); duplicates within 50 m merge; municipal operators triage, approve/dispatch, or resolve in `operator.html`; citizen pins reflect live status updates (`Νέα` → `Σε εξέλιξη` → `Επιλύθηκε`).
- **City & Mobility Layers**: Live Open-Meteo temperature/AQI/PM2.5/UV grid, OASA bus positions & stop arrivals, static Metro/Proastiakos lines & stations, on-duty pharmacies & hospitals, and AthensGov CKAN air-quality & WiFi layers.
- **Πόντοι Γειτονιάς**: Points for verified civic actions, tracked by municipal district (never by personal identity), with district leaderboard.
- **Operator Control Room & AI Register**: Dedicated `operator.html` triage workspace with Stoa Guarantee Claim alerts, service equity table, CSV export, and `ai-register.html` transparency log.

### Data Provenance (Live / Cached / Demo)

| Layer | Live Source | Cached / Snapshot Fallback | Demo / Seed |
|---|---|---|---|
| Public works | Diavgeia OpenData API (`/api/map/works/lookup`) | `data/stoa/works.json` (`LIVE-CACHE` / `DIAVGEIA+SEED`) | `data/works_seed.json` (`DEMO` / `SEED`) |
| Environment grid | Open-Meteo Forecast + Air Quality + CKAN stations | `data/envgrid/last.json` (`CACHED`) | `web/mock/env.json` (`DEMO`) |
| Transit | OASA Telematics (`getBusLocation`, `getStopArrivals`) | `data/transit/static.json` + `data/transit/last.json` (`CACHED`) | `web/mock/transit.geojson` (`DEMO`) |
| On-duty health | Pharmacy associations + Ministry of Health | `data/onduty/last.json` (`CACHED`) | `web/mock/health.geojson` (`DEMO`) |
| City requests / Ask | AthensGov Sandbox (when `SANDBOX_KEY` is set) | Local SQLite (`map_reports`, `athensone.db`) | Mock Sandbox (`DEMO` when `SANDBOX_KEY` unset) |

> Enodia puts the whole city on one accountable map and closes the loop — from a citizen's photo on the sidewalk to a crew dispatched by an operator, with a source on every answer, faces blurred, and a human deciding.

## Quick start (5 minutes)

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install --no-deps deface==1.5.0                      # better face blur (T5); --no-deps keeps OpenCV 4
cp .env.example .env                                     # leave SANDBOX_KEY empty = mock mode
uvicorn app.main:app --reload --port 8000
python seed.py --reset                                   # in a second terminal
python scripts/fetch_env.py --bbox 37.955,23.725,37.980,23.760   # once: real trees/benches/busy roads (OSM)
```

Open:
- Citizen app (phone view): http://localhost:8000/web/citizen.html
- Operator screen (laptop): http://localhost:8000/web/operator.html
- AI register: http://localhost:8000/web/ai-register.html
- API docs: http://localhost:8000/docs

Test on a phone in the same Wi-Fi: `uvicorn app.main:app --host 0.0.0.0 --port 8000` and open
`http://<laptop-ip>:8000`. (The camera and microphone need HTTPS on most phones except on localhost;
use `ngrok http 8000` or `cloudflared tunnel --url http://localhost:8000` for the demo phone.)

### Switch to the real sandbox
1. Get the API key from the organizers (Slack).
2. Put it in `.env` as `SANDBOX_KEY=...` and restart. The header pill changes from "MOCK" to "AthensGov Sandbox".
3. Check the real Friendship Club near Pangrati and place the ramp on Maria's route:
   `curl "localhost:8000/api/cool-places?lat=37.9667&lng=23.7437"` then
   `python seed.py --reset --ramp <lat>,<lng>` with a point halfway along the route.

### Turn on real photo AI
`VISION_PROVIDER=anthropic` + `ANTHROPIC_API_KEY`, or `VISION_PROVIDER=openai` with any
OpenAI-compatible server running a vision model (vLLM, Ollama `llava`, LM Studio). If the model call
fails, the app falls back to mock and labels it, so the demo never breaks.

### AthensGov open data (CKAN)
No key needed. `CKAN_MODE=live` (default) calls https://opendata.cityofathens.gr and saves snapshots to
`data/ckan/`; set `CKAN_MODE=snapshot` on stage to run from those snapshots offline. Check what was matched:
`curl localhost:8000/api/city/status` and `curl localhost:8000/api/city/air` (the `fields` key shows which
columns were used; override with `CKAN_FIELD_AQI=...` etc. in `.env`). API docs:
[Postman](https://documenter.getpostman.com/view/51309911/2sBXinJWVo) ·
[portal guide](https://opendata-cityofathens-gr.gitbook.io/guides).

### Open standards out
`/open311/v2/requests.json` (Open311 GeoReport v2) · `/ngsi-ld/v1/entities?type=ServiceRequest` (FIWARE NGSI-LD) ·
`/dcat/catalog.jsonld` (DCAT-AP, harvestable by CKAN) · `/openapi.json` (for the AthensGov AI assistant).

### Accessibility check
`npm install && python scripts/a11y_check.py` (axe-core, WCAG 2.x A/AA, needs the server running).

### Tests
```bash
# Backend (offline, full privacy / TTS / NLU / routing / Stoa / operator loop)
MOCK=1 VISION_PROVIDER=mock VALHALLA_URL=http://127.0.0.1:9 WEATHER=off CKAN_MODE=off STOA_TODAY=2026-11-21 pytest -q

# Frontend (Node built-in test runner, zero build step)
node --test web/tests/

# Privacy face & Greek/EU plate benchmark
python scripts/benchmark_privacy.py
```

### Privacy, Greek Speech & Operator Security Configuration
- **Multi-detector fail-closed privacy (`app/privacy.py`):** combines **OpenCV Zoo YuNet** (`models/face_detection_yunet_2023mar.onnx`, MIT, 232 KB) + **CenterFace** (`deface`, MIT) + Haar fallback for faces, plus **Greek/EU structural + Haar** (+ optional `PLATE_ONNX_PATH`) for licence plates, with two-stage pixelation + Gaussian blur and complete EXIF removal. Fails closed (`HTTP 503`) if detectors fail—unprocessed originals never touch disk or AI. Flags `review_required` (`NEEDS REVIEW`) if no neural face detector was available.
- **Neural Greek & English TTS (`app/tts.py`, `POST /api/tts`):** uses `edge-tts` (`el-GR-AthinaNeural` for Greek & mixed Greek-English, `en-US-AriaNeural` for English; configurable via `TTS_VOICE_EL`, `TTS_VOICE_EN`, `TTS_PROVIDER=off`). Speech normalisation preserves Greek Unicode + tonos and expands Greek municipal abbreviations without altering displayed text. Offline browser fallback uses ONLY verified `el-*` voices and refuses to speak Greek with an English voice.
- **Operator endpoint guard:** set `OPERATOR_KEY=...` in `.env` to require `X-Operator-Key` on `/api/reports/{id}/approve`, `/resolve`, `/reject`. Leave unset for local demo/test mode.

## The 7-step demo

| # | What the judges see | Endpoint (ours → sandbox) |
|---|---|---|
| 1 | Maria (persona **p2**, retiree in Pangrati) asks by voice in Greek | browser speech, `el-GR` |
| 2 | Answer with clickable official sources + service details | `POST /api/ask` → `GET /v1/search`, `/v1/registry/services` |
| 3 | Nearest Friendship Club + step-free route | `/api/cool-places` → `GET /v1/pois?category=friendship_club`; `/api/route` → Valhalla wheelchair |
| 4 | Photo of a blocked ramp, face blurred on screen, AI category | `POST /api/report` → privacy.py → vision.py → `POST /v1/requests` |
| 5 | "Already reported" (upvote) or new report; route redraws around it | `GET /v1/requests?lat&lng&radius_km=0.05` → `POST /v1/requests/{id}/upvote` |
| 6 | Operator: grouped reports, AI draft reply, **Approve & Dispatch** | `POST /api/reports/{id}/approve` → `PATCH /v1/requests/{id}` |
| 7 | Maria's phone: "Crew on the way" timeline | `GET /api/reports/{id}` → `GET /v1/requests/{id}` (`history[]`) |
| 8 | Operator opens the cracked-sidewalk report: **Stoa card**, "possibly under guarantee", quote + formula, draft dossier | `GET /api/reports/{id}` (`guarantee`) · `POST /api/reports/{id}/dossier` · `/api/works/radar` |

Demo script for the new citizen map: [docs/SPEC.md](docs/SPEC.md#demo-script-3-λεπτά)

## Architecture

```
Citizen app (phone)          Operator screen (laptop)
         \                        /
        FastAPI backend  (API key lives only here; caches GETs; 100 req/min limit)
   ┌──────────┬──────────┬──────────┬───────────────┐
 privacy.py  vision.py  routing.py  sandbox.py       store.py
 blur faces  category,  Valhalla    AthensGov        SQLite: blurred photos
 strip EXIF  severity,  wheelchair  Sandbox client   + AI results (sandbox has
 read GPS    draft reply exclude     (mock mode      no photo field and wipes
                         hazards      without key)    on restart)
```

| File | What it does |
|---|---|
| `app/main.py` | All HTTP endpoints, duplicate check, hazard list, clustering for the operator |
| `app/sandbox.py` | AthensGov Sandbox client + a mock with the same responses |
| `app/privacy.py` | GPS from EXIF, face blur (OpenCV), re-encode without EXIF |
| `app/vision.py` | Photo → category/severity/confidence/draft reply (Anthropic, OpenAI-compatible, or mock) |
| `app/routing.py` | Valhalla pedestrian route, `type: wheelchair`, `exclude_locations` = open hazards |
| `app/store.py` | SQLite (swap for PostGIS in production) |
| `app/env.py` | Shade / busy-road / rest-point scoring along a route (OSM, grid index) |
| `scripts/fetch_env.py` | Pulls trees, parks, benches, water, accessible toilets, busy roads from Overpass |
| `app/works.py` | Stoa: works records, guarantee clock (rules, not AI), radar, report↔works link, dossier draft |
| `data/works_seed.json` | Fictional SEED works records; real ones go in `data/stoa/works.json` |
| `web/` | Plain HTML + MapLibre, no build step |
| `seed.py` | Recreates the "older" demo reports in one command |

## Trust rules (from the organizers' brief) and where they live

| Rule | In the code |
|---|---|
| Show the source of every answer | `/api/ask` returns `sources[]`; the app shows them as links; "no source → say so" |
| Protect personal data | `privacy.py` runs before storage or AI; original photo never saved; EXIF removed; no login needed |
| A human makes the final decision | AI never dispatches; operator approves; < 85% confidence flagged "check category" |

Plus a public [AI register page](web/ai-register.html), following Amsterdam and Helsinki.

## Gotchas
- **Sandbox reports advance on their own** (received 2′, in progress 10′, resolved 30′). Create the demo report live on stage.
- **Sandbox data is in memory.** Run `python seed.py --reset` ~5 minutes before the pitch.
- **Limits:** 100 requests/min per key, 1000 AI messages/day. The backend caches and the screens poll every 4–5 s.
- **CKAN / OpenCouncil** block browser calls (CORS). Call them from the backend if you add them.
- **Licence plates** are not blurred in this prototype (faces are). Say so if asked; production adds a plate detector.
- **Never commit `.env`.**

## What's not built (pitch only)
Novoville / 1595 / TaxisNet / Athens Civil Alert / Smart Sense integration, waste routing, streetlight
maintenance. The sandbox stands in for the real AthensGov services during the hackathon.

## Docs
- [docs/SPEC.md](docs/SPEC.md) ([PDF](docs/SPEC.pdf)): **the spec** — 3D citizen map, contracts, offline, privacy, work split, acceptance criteria, demo script
- [docs/TASKS_A.md](docs/TASKS_A.md), [docs/TASKS_B.md](docs/TASKS_B.md): boards of the two tracks; [docs/DECISIONS.md](docs/DECISIONS.md), [docs/BACKLOG.md](docs/BACKLOG.md)
- [docs/INTEGRATIONS.md](docs/INTEGRATIONS.md): every API, open standard and toolkit item we use, and the themes covered
- [docs/NAVIGATION.md](docs/NAVIGATION.md): accessible + environmental route ranking
- [docs/economics_model.py](docs/economics_model.py): the savings / payback / NPV model
- [docs/screenshots/](docs/screenshots): operator screen with Stoa, citizen map layers, navigation
- [docs/PITCH.md](docs/PITCH.md): 5 slides, timing, judge Q&A
- [docs/SAVINGS.md](docs/SAVINGS.md): how much the city saves, with sources
- [docs/BUSINESS_MODEL_CANVAS.md](docs/BUSINESS_MODEL_CANVAS.md)

Licence: MIT (open source, as the organizers encourage).
