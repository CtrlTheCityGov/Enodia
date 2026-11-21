# Enodia · AthensOne

**An open map app for Athens: an alternative to Google Maps, built on the City's own data.**

Apps4Athens 3.0 Gov Hackathon · 21–22 Nov 2026 · Track Η (AthensGov AI Transformation) · Team CtrlTheCityGov

AthensOne is one map for everyone who lives in or visits Athens. You search for a street, a place or a City
service, and the map takes you there. Every other feature lives on that map, as a layer you switch on, a place
you open, or a route you follow:

| On the map | What it does | Status |
|---|---|---|
| **Search** | Streets, addresses, places and City services, in Greek, Greeklish or English, with or without accents | building (T22) |
| **Place panel** | Opening hours, wheelchair access, phone, website, plus what the City knows about the spot | building (T22) |
| **Directions** | Step-free walking routes per profile (wheelchair, walker, stroller, visually impaired), ranked on shade, traffic and rest stops; heat mode; avoids reported obstacles | built |
| **Ask the City** | Questions in Greek by text or voice; every answer links to its official source | built |
| **Reports** | Photo of a problem, faces blurred and location data removed before anything is stored; duplicates merge; a status timeline until it's fixed; "Is it fixed?" afterwards | built |
| **Stoa: public works** | Every works contract on its street; guarantee clock; cited answers `[ΑΔΑ …]`; a draft claim for the engineer | built (SEED data) |
| **Heat** | Heat banner with the nearest cool place and a shaded route | built |
| **City data layers** | Air-quality stations, municipal WiFi, districts (AthensGov CKAN); trees, benches, busy roads (OpenStreetMap) | built, district/air fix in T10 |
| **Πόντοι Γειτονιάς** | Points for verified civic actions; rewards in kind and from partners; ranked by district, never by person | earn side built, spend side T18 |
| **Χαρτογράφοι** | Residents map ramps, benches and obstacles; a second resident verifies; Directions uses them | T14 |
| **Your Voice · Give & Share · What's On** | Proposals and votes, item hand-overs at partner points, events with verified accessibility | T15–T17 |
| **Smart Clean · Smart Parking** | Collection, bulky pickup, recycling; garages and disabled spaces. Shown as "σύντομα" until the City data exists, never guessed | T19–T20 |
| **Operator console** | The same map for City staff: triage, approve, dispatch, Stoa radar, KPIs per district | built, KPIs in T21 |

Three rules run through all of it: **a source on every answer**, **personal data protected** (faces blurred, no
location tracking, no login except the points wallet), and **a human decides** (the AI suggests; staff approve).

## Repository

| Path | What's there |
|---|---|
| [`athensone/`](athensone/README.md) | The app: FastAPI backend, map frontend, data scripts, tests |
| [`athensone/docs/SPEC.md`](athensone/docs/SPEC.md) | **The spec** (canon): 3D citizen map, contracts, work split, acceptance criteria, demo script |
| [`athensone/docs/`](athensone/docs) | Boards (`TASKS_A.md` map & HUD, `TASKS_B.md` data & backend), decisions, backlog, pitch, economics |
| [`agents/`](agents) | `gen-prompts.sh` + `drive.sh`: the tests → code → review agent chain per task |
| [`athensone/THIRD_PARTY.md`](athensone/THIRD_PARTY.md) | Every dependency, data source and model, with its licence |
| [`CLAUDE.md`](CLAUDE.md) | How the two devs and their AI agents work: tracks, the task loop, hard rules |

## Run it

```bash
cd athensone
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install --no-deps deface==1.5.0          # better face blur; --no-deps keeps OpenCV 4
cp .env.example .env                          # no SANDBOX_KEY = mock mode
uvicorn app.main:app --reload --port 8000
```

Open http://localhost:8000/web/citizen.html (map app) and http://localhost:8000/web/operator.html (City staff).
The citizen page is being rebuilt as the 3D map of [`SPEC.md`](athensone/docs/SPEC.md) (plain ES modules, no
build step; frontend tests: `node --test web/tests/`). See [`athensone/README.md`](athensone/README.md) for the full
guide, tests and data scripts.

## How it's built

Two developers, two tracks from the spec: **Dev A** (map & HUD, branch `dev-a`) and **Dev B** (data & backend,
branch `dev-b`); they meet at the API contracts and the mock files, and merge into `main` at feature freeze. Inside
each track, AI agents work in parallel, one git worktree per task: one model writes the tests from an approved card,
a second writes the code, a third reviews it, and the track's owner approves every merge. Rules in
[`CLAUDE.md`](CLAUDE.md); boards in [`TASKS_A.md`](athensone/docs/TASKS_A.md) and
[`TASKS_B.md`](athensone/docs/TASKS_B.md).

## Licence and data

Code: MIT. Map data © OpenStreetMap contributors (ODbL). City data: AthensGov open data (CC BY 4.0).
Works records in this repo are fictional SEED examples and are labelled as such wherever they appear.
