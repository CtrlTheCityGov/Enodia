# AthensOne AI: rules and agent workflow

Read this whole file before you change anything. It applies to every AI agent (Claude, Gemini or any other), on both
tracks and every task.

**Context.** Apps4Athens 3.0 Gov Hackathon, 21–22 Nov 2026, Serafio, track Η (AthensGov AI Transformation).
**Feature freeze: Sun 22 Nov, 12:00.** The app lives in `athensone/`; all paths below are relative to it unless they
start with `.worktrees/` or `agents/`.

## The canon: `athensone/docs/SPEC.md`

**[`athensone/docs/SPEC.md`](athensone/docs/SPEC.md) (from `SPEC.pdf`, «Προδιαγραφές Citizen Map») is the project's
spec. If this file, a card, a decision or the code disagrees with it, the spec wins**; say so in your report. Read it
before every task. In short: `web/citizen.html` becomes a full-screen 3D map of Athens (Google Maps + Waze style),
MapLibre GL JS 5.3.0 + OpenFreeMap, plain ES modules with **no build step**, every data source behind `web/js/api.js`
with a mock in `web/mock/`, and the whole app works offline.

## Two tracks, two people

| Track | Who | Owns (SPEC «Ιδιοκτησία αρχείων») | Board | Base branch |
|---|---|---|---|---|
| **Dev A — Χάρτης & HUD** | Αναστάσης | `web/citizen.html`, `web/css/hud.css`, `web/js/{main,map}.js`, `web/js/layers/*`, `web/js/ui/{layerbar,workpopup,routing}.js`, `web/tests/A*` | `docs/TASKS_A.md` | `dev-a` |
| **Dev B — Δεδομένα & backend** | Evgenii | `web/js/api.js`, `web/mock/*`, `web/js/ui/{report,points,stoa,workstab}.js`, `app/`, `tests/`, `scripts/`, `data/`, `web/tests/B*` | `docs/TASKS_B.md` | `dev-b` |

The contact point is the **contracts** (SPEC «Backend contracts») and the files in `web/mock/`. Dev A builds on the
mocks until Dev B's live endpoints arrive, so nobody waits. **Never edit the other track's files.** If you need a
change there (a contract field, a mock shape, an export), write it under "Questions for the owner" in your report;
the two owners agree and the owning track makes it. Contract changes are recorded in `docs/DECISIONS.md`.

`operator.html`, `ai-register.html` and the existing backend features stay as they are (SPEC: no existing call may
break). The old citizen page is kept as `web/citizen-legacy.html` until freeze.

## Roles inside a track

Each track runs the same loop with its own agents. The owner is the human of that track.

| Role | Who | Does | Never does |
|---|---|---|---|
| **Owner** | the track's human | Approves every card and test list, decides anything the spec leaves open, says "merge A<n>"/"merge B<n>" | |
| **Advisor** | One Claude Code session with the owner | Writes cards, proposes decisions with trade-offs, creates worktrees, generates prompts, starts and watches the agents, walks the owner through each change, merges into the track branch on the owner's word, keeps the board current | Merges without the owner's word, decides open questions alone, edits the other track |
| **Test writer** | an agent (Gemini Hydrogen in Antigravity, or Claude Sonnet) | Writes exactly the approved tests for one task, before any code | Writes the implementation |
| **Implementer** | an agent (Gemini Neon / Claude Opus in Antigravity, or Claude Opus via CLI), **not** that task's test writer | Makes that task's tests pass | Edits that task's tests, decides open questions |
| **Reviewer** | a **different model** from the implementer (Gemini Argon, or Claude Sonnet) | Checks the diff against the card, the spec and this file; runs its own experiments | Changes any file except its review |

## The loop for every task

```
 card ──▶ approval ──▶ tests ──▶ code ──▶ review ──▶ walkthrough ──▶ merge into dev-a / dev-b
(advisor)  (owner)    (must fail) (make them (reads the               (owner's word)
                                   pass)      diff)
```

1. **Card.** The advisor adds the task to the track's board (`docs/TASKS_A.md` or `docs/TASKS_B.md`): goal, the SPEC
   sections it implements, files it may touch (only the track's own), interface, decisions it relies on, and a
   **test list**: one line per test with name, Given and Expected.
2. **Approval.** The owner approves the test list. Nothing is written before that. Approve a whole phase in one go.
3. **Tests.** The test writer writes exactly those tests and runs them. They must **fail** first. A test that passes
   before the code exists tests nothing.
4. **Code.** The implementer makes them pass. If a test looks wrong, **stop and report**; don't edit it.
5. **Review.** The reviewer reads `git diff dev-<a|b>...HEAD`, runs experiments in a scratch folder outside the
   worktree, and writes a verdict with `file:line` findings. **Privacy first.**
6. **Fix round** when needed: new tests for the findings, then code, then a second review. Max one fix round; the
   rest goes to `docs/BACKLOG.md`.
7. **Walkthrough.** The advisor explains the change to the owner in plain words, in the order the code runs, with
   `file:line` pointers, plus the SPEC acceptance criteria it ticks and what was checked by hand in a browser.
8. **Merge.** The owner says "merge A<n>". The advisor merges into the track branch; all tests green after.
   Phase 4 (freeze, both owners together): `dev-a` and `dev-b` into `main`, mobile check, offline check, two demo
   rehearsals.

**Decisions belong to the owner. Ask; don't decide.** Anything the spec leaves open (endpoint path, a field not in a
contract, a stored value, a new dependency, failure behaviour, privacy, points) goes to the owner with options, a
one-line trade-off each and a recommendation. The answer goes into `docs/DECISIONS.md` as `A-n`; open questions
are `Q-n`. Anything that touches the contracts or `web/mock/` needs **both** owners.

## Branches, worktrees and files

- `main` ← `dev-a`, `dev-b` (at freeze) ← `agent/A<n>-<name>` / `agent/B<n>-<name>` (one per task).
- One task = one branch = one worktree in `.worktrees/<task>` (repo root). Prompts, reports and reviews live next to
  them: `.worktrees/<task>-{tests,code,review}-prompt.md`, `<task>-{tests,code}-report.md`, `<task>-review.md`.
  `.worktrees/` is git-ignored; it is local to each person's machine.
- Boards and decisions: read them from the **main checkout** (it's current), not from the worktree.
- Agents may commit to their task branch only. **Never commit to `main`/`dev-a`/`dev-b`, never push, never merge.**
  The owner pushes `dev-a`/`dev-b` so the other track can pull.
- Only edit the files your card lists.

## Start a task (advisor)

```bash
cd <repo root>
git switch dev-a && git pull                       # (dev-b for track B)
git worktree add .worktrees/A1 -b agent/A1-map-core dev-a
(cd .worktrees/A1/athensone && python -m venv .venv && .venv/bin/pip install -qr requirements.txt)   # track B only
agents/gen-prompts.sh A1 "Map core: 3D, Light/Dark, offline style" "the 6 s timeout really fires; overlays survive setStyle"
agents/drive.sh A1                                  # tests -> code -> review; or: agents/drive.sh A1 code review
# several tasks of the same phase in parallel:
for n in A2 A3 A4; do agents/drive.sh $n & done
```

`agents/drive.sh` has two runners. **`RUNNER=agy`** (default when `agy` and `hc` are installed) runs every step in
Antigravity in a background `hc` session (`hc read a1-code`, `hc send a1-code "..."`, `hc get a1-code --json`).
**`RUNNER=claude`** (default otherwise) runs the steps one after another with the Claude Code CLI
(`claude -p`): tests and review on Sonnet, code on Opus; override with `TESTS_MODEL`, `CODE_MODEL`,
`REVIEW_MODEL`. **Mixed:** `CLAUDE_STEPS="code"` sends only the listed steps to the Claude CLI and the rest to
Antigravity (tests and review stay on Gemini, so they are still a different model from the implementer). Track B uses
this for the code step of its harder tasks (A-31). The chain stops if the code step made no `<task>:` commit (the implementer stopped with questions:
read `.worktrees/<task>-code-report.md`).

After the review: the advisor reads the three reports, walks the owner through, and on "merge A1":
`git switch dev-a && git merge --no-ff agent/A1-map-core && node --test web/tests/` (from `athensone/`), then
`git worktree remove .worktrees/A1`.

## Hard rules

**Trust rules from the organisers' brief (they are judged)**
- **A source on every answer.** Anything that answers a question returns `sources[]`/`citations[]` (or `[ΑΔΑ …]`
  for Stoa). No source → say so («Δεν βρήκα τεκμηριωμένα στοιχεία…»). Never guess. Unknown values show as
  «άγνωστο»/UNKNOWN, never as 0 or a made-up number.
- **Personal data stays protected** (SPEC «Privacy»). Faces and plates are blurred in the backend before anything is
  stored or sent to a model (`privacy.process_photo()`); the original is never written to disk; EXIF stripped; the
  public location of a report is rounded to ~10 m. The frontend shows only `photo_url_blurred`. The user is
  anonymous: a random `user_id`/points token, never sent to the sandbox or a third party, never logged. No location
  tracking.
- **A human decides.** AI never dispatches a crew, sends a claim or pays points. Stoa wording is always "possibly
  within the guarantee period".
- **Mock data is labelled.** Whatever comes from `web/mock/` or SEED shows its `source` (badge «Offline λειτουργία»,
  «δοκιμαστικό», «SEED»). Mock works are real works (SPEC), but marked as a snapshot.

**Running things**
- Never run `sudo`, `docker` or `ssh`, never change network settings, never start ngrok/cloudflared.
- Don't start `uvicorn` as a long-running process; test backend through FastAPI's `TestClient`. The owners run the
  live demo and the browser checks.
- Never read or print `.env`, API keys or tokens. Never commit `.env`.
- Tests run fully offline: no real sandbox, Valhalla, Open-Meteo, CKAN, Διαύγεια, ΚΗΜΔΗΣ, ΟΑΣΑ, Overpass,
  OpenFreeMap or model call.

**Licences (our repo is MIT and public)**
- MIT / BSD / Apache: add as a dependency or copy with the notice kept.
- LGPL: call as a library or tool, never paste its code. GPL / AGPL: ideas only or a separate service.
- No licence / proprietary: don't copy anything.
- Every new dependency needs the owner's approval and a line in `THIRD_PARTY.md`. The frontend loads only MapLibre
  GL JS 5.3.0 from jsDelivr and OpenFreeMap styles (SPEC); anything else needs both owners.

**Code**
- Frontend (SPEC «Αρχιτεκτονική»): plain ES modules under `web/js/`, CDN only, **no build step, no framework, no
  npm runtime dependency**. Modules don't touch `document`/`maplibregl` at import time (so Node can test them);
  `main.js` wires them. All data goes through `api.js`; no other file calls `fetch`.
- Backend: Python 3.11+, FastAPI. Existing routes keep their path and shape; new routes are added next to them.
  (This replaces the React/Vite/SQLAlchemy plan of A-22/A-23; see A-30.)
- Type hints on new Python functions; pure functions where possible; keep I/O thin around them.
- Every constant and claim gets a comment saying where it comes from and how sure you are; "unverified" if guessing.
  External URLs in the spec were written without an online check: verify them before relying on them.
- Greek UI strings stay Greek; code, comments and docs in English.
- New UI passes WCAG 2.x A/AA (labels, contrast, keyboard, `aria-pressed` on toggles). `scripts/a11y_check.py`
  before freeze.
- Plain code the owner can explain line by line to judges beats clever code.

**Tests**
- One behaviour per test, a name that says it. Backend: `tests/test_B<n>_<name>.py`, through HTTP endpoints or public
  functions, state reset with `/api/admin/reset` or `store.clear()` as `tests/test_smoke.py` does. Frontend:
  `web/tests/<task>_<name>.test.js` with `node:test` + `node:assert`, fake `map`/DOM/`localStorage` objects, mocked
  timers; no browser, no network.
- Existing tests (`tests/test_smoke.py`, `tests/test_T*.py`) must keep passing.

## Commands (from `athensone/`)

```bash
node --test web/tests/                                                # frontend tests (Node 20+)
python -m venv .venv && .venv/bin/pip install -r requirements.txt     # backend, once per worktree
MOCK=1 VISION_PROVIDER=mock VALHALLA_URL=http://127.0.0.1:9 WEATHER=off CKAN_MODE=off STOA_TODAY=2026-11-21 \
  .venv/bin/python -m pytest -q                                       # backend tests, offline
uvicorn app.main:app --reload --port 8000                             # humans only: http://localhost:8000/web/citizen.html
```

## Report template (test writer and implementer)

```markdown
## <task>: <name>
**Branch:** agent/<task>-...
**Files changed:** ...
**Tests:** <passed>/<total> (paste the last line of the test run)

### What it does
3–5 sentences the owner could say to a judge.

### Walkthrough
What changed, file by file, in the order the code runs, and why.

### SPEC acceptance criteria
Which ones this ticks, and how each was checked (test name / by hand in a browser / not checked).

### Constants and claims
| What | Value | Source | Sure? |

### Choices I had to make
Anything not covered by SPEC.md or DECISIONS.md. Should be empty; if not, explain.

### Questions for the owner
Options and your recommendation.
```

## Review template (reviewer)

```markdown
## Review of <task>
**Verdict:** approve / approve with leftovers / changes needed
1. Does the code match the card, SPEC.md and DECISIONS.md? Where not?
2. Bugs and edge cases the tests miss (each: input → wrong result).
3. Rules from CLAUDE.md that are broken (privacy first, then sources, human decision, licences, file ownership).
4. Anything the owner would struggle to explain to a judge.
```

## Before every push (owner)

1. All tests green (`node --test web/tests/`, and pytest on track B).
2. No `.env`, key, token or real photo in the diff (`git diff --cached --stat`, then read it).
3. No file of the other track changed (`git diff --stat origin/main...HEAD`).
4. `THIRD_PARTY.md` lists every dependency and data source with its licence.

## Gotchas
- CKAN, Διαύγεια, ΚΗΜΔΗΣ, ΟΑΣΑ and OpenCouncil block or limit browser calls (CORS, rate limits): backend adapters
  with cache only (SPEC).
- `GET /api/health` already exists (server status); the on-duty pharmacies/hospitals endpoint needs another path (Q-1).
- `setStyle()` drops custom sources/layers: everything goes back through `addOverlays()` on `style.load`.
- Sandbox data is in memory: `python seed.py --reset` ~5 minutes before the pitch.
- Valhalla has no `use_stairs` or `max_grade`; use `type: wheelchair`, `step_penalty`, `exclude_polygons`.
