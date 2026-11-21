# Integrations: what we use from the Apps4Athens 3.0 toolkit

Mapped against the organisers' "Τεχνικές Προδιαγραφές" (v0.9). **Built** = in this repo and tested;
**Ready** = code in place, switch on with config; **Pitch** = roadmap only.

## AthensGov (Δήμος Αθηναίων)

| Toolkit item | How AthensOne uses it | Status |
|---|---|---|
| AthensGov Sandbox API (search, 570-service registry, POIs, requests) | Ask with sources, cool places, reports, status timeline (`app/sandbox.py`) | Built |
| Open data portal (CKAN, opendata.cityofathens.gr, CC BY 4.0, no key) | `app/ckan.py`: `package_show` → `datastore_info/search`, columns matched from the schema at runtime, snapshots to `data/ckan/` for offline demos | Built (tested with a fake portal; verify column guesses on the day via `/api/city/air` → `fields`) |
| `municipal-districts-athens`, `neighbourhoods-athens` | Every report gets its Δημοτική Κοινότητα (`district_name`); equity table; collective points goals per district | Built |
| `env-stations-registry` + `env-all-stations` (AQI 1–6, °C, µg/m³) | Air-quality map layer; navigation says the AQI of the nearest City station and weighs busy roads more when AQI ≥ 4; station temperature switches heat mode on before the forecast does | Built |
| `wifi-stations-registry` | "Δημοτικό WiFi" map layer | Built |
| AI digital assistant (my.cityofathens.gr) | FastAPI publishes an OpenAPI spec (`/openapi.json`); the assistant can call `/api/works`, `/api/navigate`, `/open311/...` as tools | Ready |
| Postman docs / portal guide | Linked in README for the team | — |

## Open standards and tools

| Toolkit item | How AthensOne uses it | Status |
|---|---|---|
| FixMyStreet / mySociety | Reports also exposed as **Open311 GeoReport v2** (`/open311/v2/services.json`, `/requests.json`), the format FixMyStreet speaks | Built (read-only) |
| FIWARE / NGSI-LD | `/ngsi-ld/v1/entities?type=ServiceRequest|WorksRecord|AirQualityObserved` (AirQualityObserved named after Smart Data Models) for an Orion-LD broker | Built (read-only) |
| CKAN / DCAT-AP | `/dcat/catalog.jsonld` so the City's CKAN can harvest our 5 datasets | Built |
| OpenStreetMap | Base map, walking graph (Valhalla), trees, parks, benches, water, busy roads (`scripts/fetch_env.py`) | Built |
| Wheelmap | Same source Wheelmap uses: OSM `wheelchair=yes` places as an accessible-places layer | Built |
| axe-core | `scripts/a11y_check.py` runs WCAG 2.x A/AA rules on every page; 0 violations at the time of writing | Built |
| Aequitas (fair AI) | Equity table: reports, % resolved and hours to first action per district (`/api/equity`, operator screen) | Built (simple version) |
| Meltemi / Llama-Krikri (ILSP) | Text model slot for Greek replies and Ask via any OpenAI-compatible server (`.env.example`) | Ready |
| Amsterdam / Helsinki AI registers | Public AI register page (`web/ai-register.html`), 7 entries | Built |
| Decidim | "Your Voice" proposals/votes: run Decidim and link from the app rather than rebuild it | Pitch |
| OpenTripPlanner + GTFS | Walk + public transport legs to a cool place (OASA GTFS) | Pitch |
| OpenAQ, Copernicus | Fallback air data when no City station is near; heat-island map for tree planting | Pitch |
| Europeana | "What's On" cultural content | Pitch |
| WCAG | App: big-text and voice mode, screen-reader labels, axe-checked | Built |

## Hackathon themes covered

| Theme | Where |
|---|---|
| Ανοικτά Δεδομένα & Διαλειτουργικότητα | CKAN in, Open311 / NGSI-LD / DCAT / GeoJSON out, Stoa over Diavgeia + ΚΗΜΔΗΣ |
| Έξυπνη Πόλη & Ψηφιακές Υποδομές | One map with layers, City sensors in routing, operator console |
| Πολίτης & Ψηφιακές Υπηρεσίες | Ask with sources, Report It, status timeline, Points |
| Περιβάλλον & Βιωσιμότητα | Air quality, shade, recycling and reuse via Points, Give & Share |
| Προσβασιμότητα & Συμπερίληψη | Step-free profiles, accessible places, axe-checked UI, KEP card |
| Έξυπνη & Πράσινη Κινητικότητα | Walking routes ranked on shade, traffic and air |
| Ειδική πρόκληση AthensGov AI Transformation | Photo triage, Stoa document reading, AI register, human in the loop |

## Deliverables checklist (organisers' list)
Code ✔ · README with install + sample data ✔ · Mockups (`docs/screenshots/`) ✔ · Business Model Canvas
(`docs/BUSINESS_MODEL_CANVAS.md`) ✔ · Pitch deck 4–5 slides: to do · GitHub usernames to organisers: to do.
