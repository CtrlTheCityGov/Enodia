# Tasks

Board and cards. The main checkout's copy is current. Workflow and rules: `../../CLAUDE.md`.

| Task | Owner | State |
|---|---|---|
| T1 "Is it fixed?" loop | A | approved, running |
| T2 Points wallet, earn side | B | approved, running |
| T3 Heat alert banner | C | approved, running |
| T4 Ask Stoa, cited answers | D | approved, running |
| T5 Better face blur | B | waiting: deface dependency needs approval (Q-1) |

Baseline before T1–T4: `8 passed` (Python 3.14, offline test command).

### T1: "Is it fixed?" loop (owner A)
Idea from FixMyStreet's questionnaire (AGPL: state design only, no code). The sandbox only knows
submitted / received / in_progress / resolved / rejected, so the confirmation lives in our SQLite.
**Files:** `app/store.py`, `app/main.py`, `web/citizen.html`, `docs/DEMO_SCRIPT.md`, `tests/test_T1_fixed.py`.
- `store.py`: table `confirmations(request_id, asked_at, answered_at, fixed INTEGER, photo TEXT)`.
- `POST /api/reports/{id}/resolve` inserts a row with `asked_at`; the citizen's status card shows "Is it fixed? Yes / No, photo".
- New `POST /api/reports/{id}/confirm` with `fixed` (bool) and optional photo, which goes through `privacy.py` first.
- `fixed=false` → `sb.update_request(id, status="in_progress", note="Ο πολίτης αναφέρει ότι δεν διορθώθηκε")`; the hazard comes back into routing.
- `/api/equity` adds `reopen_rate` per district.

| Test | Given | Expected |
|---|---|---|
| `test_resolve_asks_confirmation` | a report, resolved | a confirmation row with `asked_at`, `answered_at` null |
| `test_confirm_false_reopens_report` | resolved report, confirm `fixed=false` | status `in_progress`, note as above |
| `test_confirm_false_hazard_back` | same | the report is in `/api/hazards` again |
| `test_reopen_rate_in_equity` | one report in a district, reopened | that district's `reopen_rate` is 1.0 (100 %) |
| `test_confirm_true_keeps_resolved` | resolved, confirm `fixed=true` | status stays `resolved`, hazard stays gone |
| `test_confirm_photo_blurred_no_exif` | confirm with a JPEG carrying EXIF GPS | stored photo has no EXIF |
| `test_confirm_unknown_report_404` | unknown id | 404 |

### T2: Points wallet, earn side (owner B)
Append-only ledger we write ourselves (loyalty-ledger has no licence: idea only).
**Files:** `app/store.py`, `app/main.py`, new `app/points.py`, `web/citizen.html`, `tests/test_T2_points.py`.
- Table `points_ledger(id, account, district, action, ref_id, points, verified_by, created_at, UNIQUE(account, action, ref_id))`.
- No login: random pseudonymous token in a cookie on first use. Report creation stores the token next to the report, only in our DB.
- Grants inside existing actions: operator approve **+10**, engineer opens the Stoa dossier **+30**, citizen confirms the fix **+5** (after T1). Daily cap: 3 approved reports per account.
- `GET /api/points/me` → balance (`SUM(points)`), tier (Γείτονας 0+, Φίλος της Γειτονιάς 500/12 months, Πρέσβης 2,000), last 10 entries. `GET /api/points/districts` → total per district vs the shared target.
- Citizen page: balance chip in the header, district progress bar. Rankings only by district, never by person.

| Test | Given | Expected |
|---|---|---|
| `test_approve_twice_pays_once` | approve the same report twice | one +10 row |
| `test_balance_is_ledger_sum` | several grants | balance = sum of rows |
| `test_daily_cap_three_reports` | 4 approved reports, one account, one day | 30 points, not 40 |
| `test_dossier_bonus_30` | dossier opened for a report | +30 to the reporter |
| `test_token_never_sent_to_sandbox` | create a report with a cookie token | the sandbox mock never receives the token |
| `test_points_me_without_cookie` | no cookie | a new token is set, balance 0, tier Γείτονας |
| `test_districts_totals` | grants in two districts | per-district totals, no account ids |

### T3: Heat alert banner (owner C)
Everything exists: Open-Meteo, `ckan.nearest_air()`, cool places, `/api/navigate`.
**Files:** `app/main.py`, `app/config.py`, `web/citizen.html`, `tests/test_T3_heat.py`.
- `GET /api/heat?lat&lng` → `hot`, `temp_c`, the temperature source, nearest cool place, shaded minutes to it. Threshold `config.HEAT_C` (33 °C).
- Citizen page calls it on load; if hot, top banner "35°C now. Λέσχη Φιλίας, 6′ με σκιά" + "Take me there" → Navigate in heat mode.
- `HEAT_FORCE=1` for a winter demo; the banner then says "δοκιμαστικό".

| Test | Given | Expected |
|---|---|---|
| `test_heat_hot_from_station` | fake station 34.5 °C | `hot` true, source is the station |
| `test_heat_cool_place_matches` | same | cool place = first `/api/cool-places` item |
| `test_heat_not_hot` | fake 25 °C | `hot` false |
| `test_heat_force_labelled` | `HEAT_FORCE=1`, 18 °C | `hot` true, `forced` true |
| `test_heat_no_data` | weather off, no station | `hot` false, `temp_c` null, source UNKNOWN; no error |

### T4: Ask Stoa, cited answers (owner D)
Our own retrieve-then-verify rule (citation-rag is proprietary).
**Files:** `app/works.py` or new `app/stoa_ask.py`, `app/main.py`, `web/operator.html`, `tests/test_T4_stoa_ask.py`.
- `POST /api/stoa/ask` with `q`. Retrieve: accent-insensitive match on street names and works types in `works.all_cards()`, up to 3 cards.
- Answer by template from card fields (contractor, euros, completion, guarantee clock with its formula). Every sentence ends with `[ΑΔΑ …]`.
- Optional model rephrase (Krikri); afterwards check that every ΑΔΑ and number in the output exists in the cards, else return the template.
- No card → "Δεν βρήκα τεκμηριωμένα στοιχεία για αυτό." Refuses rather than guesses.
- Operator page: question box above the Stoa radar.

| Test | Given | Expected |
|---|---|---|
| `test_ask_sample_street_cites_ada` | "Δείγμα Οδός Α" | answer contains `SEED-ΑΔΑ-003` and `15/12/2026` |
| `test_ask_accent_insensitive` | same street without accents / upper case | same cards |
| `test_ask_unknown_street_refuses` | a street with no records | the refusal text, no ΑΔΑ |
| `test_every_sentence_cited` | any matched answer | every sentence ends with `[ΑΔΑ …]` |
| `test_rephrase_with_bad_number_falls_back` | fake rephraser adds a number not in the cards | template answer returned |
| `test_max_three_cards` | a works type matching many cards | ≤ 3 cards |

### T5: Better face blur (owner B, if time)
**Files:** `app/privacy.py`, `requirements.txt`, `THIRD_PARTY.md`, `tests/test_T5_blur.py`. Needs approval: new dependency `deface` (MIT).
- Try CenterFace through deface first, fall back to the current OpenCV Haar cascade.
- Order stays: blur → strip metadata → store → AI. The original is never written to disk. Plates: "next step" in the pitch.

| Test | Given | Expected |
|---|---|---|
| existing photo tests | | still pass |
| `test_face_image_faces_ge_1` | a test image with a face | `faces ≥ 1` |
| `test_deface_missing_falls_back` | deface import fails | Haar path used, no error |
| `test_original_never_on_disk` | a report with a photo | no un-blurred file in `data/photos/` |

