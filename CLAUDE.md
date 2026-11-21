# AthensOne AI: rules and multi-agent workflow

Read this whole file before you change anything. It applies to every AI agent (Claude, Gemini or any other)
and to every task. The workflow is the one we used on Panopticon (card → tests → code → review → merge, one
worktree per task, several agents in parallel), cut down to fit a hackathon night.

**Context.** Apps4Athens 3.0 Gov Hackathon, 21–22 Nov 2026, Serafio, track Η (AthensGov AI Transformation).
**Feature freeze: Sun 22 Nov, 12:00.** Sources: `AthensOne_Proposal.pdf` (concept, modules, Πόντοι Γειτονιάς,
economics), `AthensOne_Build_Plan.pdf` (tonight's features, repo licence verdicts, team split), and the app's
`README.md`. The app lives in `athensone/` (unpacked from `athensone-full.zip`). All paths below are relative to
`athensone/` unless they start with `.worktrees/`.

## What the product is

**AthensOne is a map app for Athens: an open alternative to Google Maps, built on the City's own data (A-26).**
The map is the home screen. Search (streets, addresses, places, City services), the place panel and directions are
the core. Every other feature is something on that map: a layer (reports, works, air, shade, accessibility points),
a place panel (a report's timeline, a works card, an event), or a route (step-free, shaded, around hazards). When you
design a feature, first answer: what does it put on the map, what opens when it's clicked, and does it change routes?

The demo loop on top of it: a resident asks a question and gets an answer with official sources, walks a step-free
route to a Friendship Club, the route changes around a blocked ramp someone just photographed (faces blurred), and a
municipal officer approves the fix, which the resident sees live. Stoa adds the works memory: before a crew goes
out, the operator sees whether the street may still be under the contractor's guarantee.

| File | Job |
|---|---|
| `app/main.py` | All HTTP endpoints, duplicate check, hazard list, operator clustering, `/api/equity` |
| `app/sandbox.py` | AthensGov Sandbox client + a mock with the same responses (no key = mock) |
| `app/privacy.py` | `process_photo()`: GPS from EXIF, face blur (OpenCV Haar), re-encode without EXIF |
| `app/vision.py` | Photo → category / severity / confidence / draft reply (anthropic, openai-compatible, mock) |
| `app/routing.py`, `app/env.py` | Valhalla pedestrian/wheelchair routes, hazards excluded; shade / traffic / rest scoring |
| `app/works.py` | Stoa: `all_cards()`, `clock()`, `radar()`, `for_report()`, `dossier()`; rules, not AI |
| `app/ckan.py` | City open data: `districts()`, `district_of()`, `nearest_air()` |
| `app/store.py` | SQLite: blurred photos + AI results (the sandbox has no photo field and wipes on restart) |
| `app/config.py` | Every setting from env vars |
| `web/*.html` | Plain HTML + MapLibre, no build step: `citizen.html`, `operator.html`, `ai-register.html` |
| `tests/test_smoke.py` | The whole 7-step loop offline |

## Who does what

| Role | Who | Does | Never does |
|---|---|---|---|
| **Owner** | Evgenii | Approves every card and test list, makes architecture decisions, says "merge T<n>", runs the live demo | |
| **Teammates A–E** | humans | Own a feature each (split below); answer questions on their feature | |
| **Advisor** | One Claude Code session working with Evgenii | Writes cards, proposes decisions with trade-offs, creates worktrees, writes prompts, starts and watches the other agents, walks Evgenii through each change, merges on his word, keeps `docs/` current | Merges without his word, decides architecture alone |
| **Test writer** | Gemini (Antigravity, `agy`) | Writes exactly the approved tests for one task, before any code | Writes the implementation |
| **Implementer** | Gemini 4 Neon in Antigravity while the Antigravity Opus quota is out (until ~27 Nov), else Claude Opus 5.5 inside Antigravity; Claude CLI only as fallback. **Not** that task's test writer | Makes that task's tests pass | Edits that task's tests, decides open questions |
| **Reviewer** | A **different model** from the implementer (Gemini 4 Argon in Antigravity) | Checks the diff against the card and this file, runs its own experiments | Changes any file except its review |

The test writer and the implementer are different agents, so the tests check the card, not the code.

## The loop for every task

```
 card ──▶ approval ──▶ tests ──▶ code ──▶ review ──▶ walkthrough ──▶ merge
(advisor)  (Evgenii)   (Gemini,   (Opus,     (Gemini,                (Evgenii's word)
                       must fail) makes them reads the diff)
                                  pass)
```

1. **Card.** The advisor adds the task to `docs/TASKS.md`: goal, files it may touch, interface, decisions it relies
   on (`docs/DECISIONS.md`), and a **test list**, one line per test with its name, Given and Expected.
2. **Approval.** Evgenii approves the test list. Nothing is written before that. To save time tonight, approve all
   cards of a round in one go.
3. **Tests.** The test writer writes exactly those tests and runs them. They must **fail** first (normally 404,
   `ImportError` or `AttributeError`). A test that passes before the code exists tests nothing.
4. **Code.** The implementer makes them pass. If a test looks wrong, **stop and report**; don't edit it. The question
   goes to Evgenii and the test writer makes the change.
5. **Review.** The reviewer reads `git diff main...HEAD`, runs experiments in a scratch folder outside the worktree,
   and writes a verdict with `file:line` findings. **Privacy first** (see hard rules).
6. **Fix round** when needed: new tests for the findings, then code, then a second review. Max one fix round
   tonight; anything left goes to `docs/BACKLOG.md`.
7. **Walkthrough.** The advisor runs through the change with Evgenii in plain words, in the order the code runs,
   with `file:line` pointers: what changed, why, and what it did not do.
8. **Merge.** Evgenii says "merge T<n>". Before merging: the full test command and the a11y check are green on the
   merged result.

**Architecture decisions are Evgenii's. Ask; don't decide.** Before writing code, ask about anything that shapes the
design: endpoint shape, table schema, what is stored and where, a new dependency, failure behaviour, anything
touching privacy or points. Give the options, one-line trade-off each, and a recommendation, then wait. Record the
answer in `docs/DECISIONS.md` as `A-n`; open questions are `Q-n`. If you would have to make a choice
`DECISIONS.md` doesn't cover, put it under "Questions for Evgenii" in your report. Don't pick one quietly.

## Branches, worktrees and files

- One task = one branch `agent/T<n>-<short-name>` = one worktree in `.worktrees/T<n>` (repo root).
  Prompts, reports and reviews live next to them: `.worktrees/T<n>-{tests,code,review}-{prompt,report}.md`,
  `.worktrees/T<n>-review.md`. `.worktrees/` is git-ignored.
- Planning files in `athensone/docs/`: `TASKS.md` (board and cards), `DECISIONS.md` (`A-n`, `Q-n`), `BACKLOG.md`.
  The **main checkout's** copy is current; agents read cards from there, not from their worktree.
- Agents may commit to their task branch. **Never commit to `main`, never push, never merge.**
- Only edit the files your card lists. The test writer edits only the test files on the card.
- Shared files (`app/main.py`, `app/store.py`, `web/citizen.html`, `web/operator.html`) are touched by several
  tasks. Each task adds its code in its own clearly marked block (`# --- T<n>: ... ---`) and doesn't reformat or
  move other code, so merges stay mechanical. The advisor merges in card order and reruns tests after each.

## Hard rules

**Trust rules from the organisers' brief (they are judged)**
- **A source on every answer.** Anything that answers a question returns `sources[]` (or `[ΑΔΑ …]` for Stoa).
  No source → say so ("Δεν βρήκα τεκμηριωμένα στοιχεία…"). Never guess. A fact we can't prove shows as UNKNOWN.
- **Personal data stays protected.** Every photo goes through `privacy.process_photo()` (blur → strip EXIF) before
  it is stored or sent to any model; the original is never written to disk. No login. The points token is a random
  pseudonym in a cookie, stored only in our DB, **never sent to the sandbox**, never logged. No location tracking.
- **A human decides.** AI never dispatches a crew, sends a claim or pays points. Operator approves; < 85 %
  confidence is flagged "check category". Stoa wording is always "possibly within the guarantee period".
- Demo switches that fake data (`HEAT_FORCE=1`, SEED works) must label it on screen ("δοκιμαστικό", "SEED").

**Running things**
- Never run `sudo`, `docker` or `ssh`, never change network settings, never start ngrok/cloudflared.
- Don't start `uvicorn` as a long-running process; test through FastAPI's `TestClient`. Evgenii runs the live demo.
  (The a11y check needs a running server: only the advisor runs it, on main, before a push.)
- Never read or print `.env`, API keys or tokens. Never commit `.env`.
- Tests run fully offline: no real sandbox, Valhalla, Open-Meteo, CKAN or model call.

**Licences (our repo is MIT and public; breaking a licence is the easiest way to lose points)**
- MIT / BSD / Apache: add as a dependency or copy with the notice kept (deface, SunCalc, Turf.js, H3,
  scikit-learn, Instructor, faster-whisper, OSMnx, Kepler.gl, Aequitas, Project Sidewalk label types).
- LGPL (mat2, OpenTripPlanner): call as a library or tool, never paste its code.
- GPL / AGPL (FixMyStreet, Mark-a-Spot, Decidim, Karrot, StreetComplete, PostGIS): ideas only or a separate service.
- No licence / proprietary (citation-rag, loyalty-ledger, Shaadiest): don't copy anything.
- Every new dependency needs Evgenii's approval and a line in `THIRD_PARTY.md`.

**Code**
- Stack (A-22, Sat 21 Nov evening): Python 3.11+, FastAPI routers, SQLAlchemy 2 + Alembic (`DATABASE_URL`; SQLite in
  tests, PostgreSQL 16 + PostGIS in Docker Compose), React 18 + Vite + TypeScript + MapLibre in `frontend/`.
  New modules are self-contained (A-23): backend `app/modules/<name>/{models,service,router}.py`, frontend
  `frontend/src/modules/<name>/index.tsx`; both are discovered automatically, so no shared file needs editing.
  No other framework without Evgenii's approval. Agents never run `docker`; Compose files are written and read only.
- Type hints on new functions. Pure functions where possible (like `works.clock()`); keep I/O thin around them.
- Every constant and claim gets a comment saying where it comes from and how sure you are; "unverified" if guessing.
- Greek UI strings stay Greek; code, comments and docs in English.
- New UI passes WCAG 2.x A/AA (labels, contrast, keyboard). Run `scripts/a11y_check.py` before merge.
- Plain code Evgenii can explain line by line to judges beats clever code.

**Tests**
- One behaviour per test, a name that says it (`test_confirm_false_reopens_report`). Test through HTTP endpoints
  or public functions. Reset state with `/api/admin/reset` or `store.clear()` as `tests/test_smoke.py` does.
- New tests go in `tests/test_T<n>_<name>.py` (one file per task, so parallel tasks don't conflict).

## Commands (from `athensone/`)

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt     # once per worktree
MOCK=1 VISION_PROVIDER=mock VALHALLA_URL=http://127.0.0.1:9 WEATHER=off CKAN_MODE=off STOA_TODAY=2026-11-21 \
  .venv/bin/python -m pytest -q                                       # all tests, offline
... -m pytest tests/test_T1_fixed.py -x                               # one file, stop at first failure
npm install && python scripts/a11y_check.py                           # a11y (server running; advisor only)
```

## Tonight's tasks (from the Build Plan)

Run T1–T4 in parallel (one worktree each). T5 only if time. Each card below is the draft; the advisor copies it to
`docs/TASKS.md` and Evgenii approves the test list.

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

### Not code (owner E)
Pitch deck (4–5 slides) in `docs/`, `THIRD_PARTY.md` with every dependency and licence, run
`scripts/fetch_env.py`, check `/api/city/air` fields. Not built tonight (pitch only, with the library named): swipe
verification, predictive maintenance (H3 + scikit-learn), weekly district brief (Instructor), Greek voice reports
(faster-whisper + Krikri), heat-buddy matching, building shadows (SunCalc), Aequitas audit.

## Driving the agents (advisor)

The agents run side by side in background terminal sessions via `hc` (`~/.local/bin/hc`), one worktree per task.

```bash
# 1. worktree + venv per task
git worktree add .worktrees/T1 -b agent/T1-fixed-loop
(cd .worktrees/T1/athensone && python -m venv .venv && .venv/bin/pip install -qr requirements.txt)

# 2. write .worktrees/T1-{tests,code,review}-prompt.md (templates below)

# 3. chain tests (Gemini) -> code (Opus 5.5 in Antigravity) -> review (Gemini), all four tasks at once
for n in T1 T2 T3 T4; do .worktrees/drive.sh $n & done

# watch / nudge
hc read t1-code            # last screen of a session
hc send t1-code "..."      # answer a question, resume a stopped chain
hc get t1-code --json      # state
```

**Usage budget (Sat 21 Nov): the Claude Code account is at ~89 % of its weekly limit.** So every agent step runs
in **Antigravity** (`agy`): tests on Gemini 4 Hydrogen, code on Claude Opus 5.5 *inside Antigravity*, review on
Gemini 4 Argon. The advisor session itself stays short: write cards and prompts, start chains, read reports, and
don't do the agents' work inline. The Claude CLI (`code2` step) is only a fallback when Antigravity is down or out
of quota. If the Claude account runs out, the advisor role moves to the second account (`/login` there) and
continues from `docs/TASKS.md`, `docs/DECISIONS.md` and the `.worktrees/T<n>-*` reports, which hold all state.

`.worktrees/drive.sh` (same as Panopticon's `drive-agy.sh`; stops if the code step made no `T<n>:` commit, so an
implementer that stopped with questions is never reviewed):

```zsh
#!/bin/zsh
# drive.sh <task> [steps…]: tests (Gemini Hydrogen) -> code (Opus 5.5 inside Antigravity) -> review (Gemini Argon).
# Step "code2" = fallback: Opus 5.5 through the Claude CLI (costs Claude Code usage).
n=$1; shift; steps=("$@"); (( $#steps )) || steps=(tests code review); t=${(L)n}
W=$(git rev-parse --show-toplevel)/.worktrees
for step in $steps; do
  case $step in
    *code2*)  model=claude-cli ;;
    *code*)   model=claude-opus-5-5-high ;;
    *review*) model=gemini-4-argon-high ;;
    *)        model=gemini-4-hydrogen-high ;;
  esac
  if [[ $model == claude-cli ]]; then cmd=(claude --model claude-opus-5-5 --permission-mode auto "Read $W/$n-${step%2}-prompt.md and do exactly what it says.")
  else cmd=(agy --model $model --dangerously-skip-permissions -i "Read $W/$n-$step-prompt.md and do exactly what it says."); fi
  hc kill $t-$step >/dev/null 2>&1; hc rm $t-$step >/dev/null 2>&1
  hc run --bg --outlive-parent --name $t-$step --cwd $W/$n "${cmd[@]}" >/dev/null
  for i in 1 2 3 4; do sleep 10; hc read $t-$step 2>/dev/null | grep -qiE "trust this folder|trust the files|trust the contents" && { hc keys $t-$step enter >/dev/null; break; }; done
  sleep 30
  while :; do s=$(hc get $t-$step --json | python3 -c "import json,sys;d=json.load(sys.stdin);st=d.get('status') or {};print(d['state'], st.get('state') if isinstance(st,dict) else st)")
    case "$s" in *error*) echo "$n $step: $s; chain stopped, resume with hc send $t-$step"; exit 1;; *done*|*idle*|finished*) break;; esac; sleep 20; done
  echo "$n $step: $s"
  if [[ $step == *code* ]] && ! git -C $W/$n log -1 --format=%s | grep -q "^$n:"; then echo "$n $step: no code commit (questions?); chain stopped"; exit 2; fi
done
```

### Prompt templates

`M` = main checkout, `W` = `.worktrees`, `PY` = the offline test command run with the worktree's venv.

**Tests prompt**
> You are the TEST WRITER for task T<n> (<title>) of AthensOne. Evgenii approved the card's test list.
> Work ONLY in the worktree $W/T<n> (branch agent/T<n>-…).
> 1. Read CLAUDE.md fully. No test calls a real network service or starts a server.
> 2. Read the card "### T<n>:" in $M/athensone/docs/TASKS.md (the main checkout's copy is current) and the
>    decisions it names in DECISIONS.md. Read the code the card names for current names and signatures, and
>    `tests/test_smoke.py` for style and fixtures.
> 3. Write exactly the tests of the card's table, with its names, Given and Expected, in
>    `tests/test_T<n>_<name>.py`. A short comment per test. Change no existing test and no non-test file.
> 4. Run $PY from athensone/. New tests must fail until the code exists; report for each whether it failed or
>    passed and why. Existing tests still pass. Do not bend a test.
> 5. Commit only the test file: "T<n> tests". Never push, never merge, never commit to main.
> 6. Write your report (template below) to $W/T<n>-tests-report.md and print it.

**Code prompt**
> You are the IMPLEMENTER for task T<n> (<title>) of AthensOne. The tests (by Gemini) are the last commit on the branch.
> Work ONLY in the worktree $W/T<n>.
> 1. Read CLAUDE.md, the card in $M/athensone/docs/TASKS.md, the decisions it names, $W/T<n>-tests-report.md and the new tests.
> 2. Implement the card, touching only the files it lists, inside a `# --- T<n> ---` block in shared files. Keep the change small.
> 3. Don't edit tests. If a test looks wrong, STOP and report.
> 4. Run $PY from athensone/; all tests pass.
> 5. Commit: "T<n>: <title>". Never push, never merge, never commit to main.
> 6. Write your report to $W/T<n>-code-report.md and print it. Choices the card doesn't cover go under "Questions for Evgenii".

**Review prompt**
> You are the REVIEWER for task T<n> (<title>) of AthensOne. Tests by Gemini, code by Claude Opus 5.5. You change
> NO file in the repository and make no commit; the only file you write is your review. Diff: `git diff main...HEAD`.
> 1. Read CLAUDE.md, the card, the decisions, and both reports.
> 2. Check with experiments in a scratch folder OUTSIDE the worktree: PRIVACY FIRST (can a points token, an
>    un-blurred photo, EXIF or GPS reach the sandbox, a log, an error or disk?); sources on every answer; no AI
>    action without a human; licences of anything new; <task-specific checks>. Also: the code commit changed no
>    test (`git diff <tests commit> HEAD -- tests` is empty).
> 3. Run $PY from athensone/.
> 4. Write the review (template below) to $W/T<n>-review.md and print it. Verdict: approve / approve with
>    leftovers / changes needed. Every finding: file:line, what is wrong, how you know (ran it / read it), how bad.

## Report template (test writer and implementer)

```markdown
## T<n>: <name>
**Branch:** agent/T<n>-...
**Files changed:** ...
**Tests:** <passed>/<total> (paste the last line of pytest)

### What it does
3–5 sentences Evgenii could say to a judge.

### Walkthrough
What changed, file by file, in the order the code runs, and why.

### Constants and claims
| What | Value | Source | Sure? |

### Choices I had to make
Anything not covered by docs/DECISIONS.md. Should be empty; if not, explain.

### Questions for Evgenii
Options and your recommendation.
```

## Review template (reviewer)

```markdown
## Review of T<n>
**Verdict:** approve / approve with leftovers / changes needed
1. Does the code match the card and docs/DECISIONS.md? Where not?
2. Bugs and edge cases the tests miss (each: input → wrong result).
3. Rules from CLAUDE.md that are broken (privacy first, then sources, human decision, licences).
4. Anything Evgenii would struggle to explain to a judge.
```

## Before every push (advisor, on main, Evgenii's word)

1. Full offline test command green; `scripts/a11y_check.py` zero violations.
2. `docs/DEMO_SCRIPT.md` updated for any new demo step; `THIRD_PARTY.md` lists every dependency and licence.
3. No `.env`, key, token or real photo in the diff (`git diff --cached --stat`, then read it).
4. README numbers and claims still match the code.

## Gotchas (from the README)
- Sandbox reports advance on their own (received 2′, in progress 10′, resolved 30′): create the demo report live.
- Sandbox data is in memory: `python seed.py --reset` ~5 minutes before the pitch.
- Limits: 100 req/min per key, 1,000 AI messages/day. The backend caches; screens poll every 4–5 s.
- CKAN / OpenCouncil block browser calls (CORS): call them from the backend.
- Licence plates are not blurred (faces are); say so if asked.
- Valhalla has no `use_stairs` or `max_grade`; use `type: wheelchair`, `step_penalty`, `use_lit`, `exclude_polygons`.
