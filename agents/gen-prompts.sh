#!/bin/zsh
# gen-prompts.sh <task> "<title>" "<review checks>"
#   Writes .worktrees/<task>-{tests,code,review}-prompt.md for drive.sh.
#   <task> = A<n> (Dev A: map & HUD, board docs/TASKS_A.md, base branch dev-a, tests with node --test)
#          | B<n> (Dev B: data & backend, board docs/TASKS_B.md, base branch dev-b, tests with pytest + node --test)
T=$1 TITLE=$2 CHK=$3
[[ $T == [AB]<-> && -n $TITLE ]] || { echo 'usage: gen-prompts.sh A<n>|B<n> "<title>" "<review checks>"'; exit 64; }
M=$(git rev-parse --show-toplevel); W=$M/.worktrees; mkdir -p $W
TRACK=${T[1]}; base=dev-${(L)TRACK}; BOARD=$M/athensone/docs/TASKS_$TRACK.md
JS="{ [ ! -d web/tests ] || node --test web/tests/; }"
PY="env MOCK=1 VISION_PROVIDER=mock VALHALLA_URL=http://127.0.0.1:9 WEATHER=off CKAN_MODE=off STOA_TODAY=2026-11-21 .venv/bin/python -m pytest -q"
if [[ $TRACK == A ]]; then RUN="$JS"; OWNER="Αναστάσης (Dev A)"
else RUN="$PY && $JS"; OWNER="Evgenii (Dev B)"; fi

cat > $W/$T-tests-prompt.md <<P
You are the TEST WRITER for task $T ($TITLE) of AthensOne. $OWNER approved the card's test list.
Work ONLY in the worktree $W/$T (branch agent/$T-*, based on $base). The app is in its athensone/ folder.

1. Read CLAUDE.md fully and athensone/docs/SPEC.md (the spec is the canon). No test calls a real network service,
   starts a server or opens a browser.
2. Read the card "### $T:" in $BOARD (the main checkout's copy is current) and athensone/docs/DECISIONS.md.
   Read the code and mock files the card names for current names, signatures and shapes.
3. Write exactly the tests of the card's table (names, Given, Expected) in the test file the card names.
   Python tests use FastAPI's TestClient like tests/test_smoke.py; JS tests use node:test + node:assert and import
   the ES modules from web/js/ directly, with plain fake objects for the map, DOM and localStorage.
   A short comment per test. Change no existing test and no non-test file.
4. Run from athensone/:  $RUN
   New tests must fail until the code exists; report for each whether it failed or passed and why. Existing tests
   still pass. Do not bend a test.
5. Commit only the test file: "$T tests". Never push, never merge, never commit to main or $base.
6. Write your report (CLAUDE.md "Report template") to $W/$T-tests-report.md and print it.
P

cat > $W/$T-code-prompt.md <<P
You are the IMPLEMENTER for task $T ($TITLE) of AthensOne. The tests (written by a different agent) are the last
commit on the branch. Work ONLY in the worktree $W/$T. The app is in its athensone/ folder.

1. Read CLAUDE.md fully, athensone/docs/SPEC.md, the card "### $T:" in $BOARD, athensone/docs/DECISIONS.md,
   $W/$T-tests-report.md and the new tests.
2. Implement the card, touching only the files it lists (and only files your track owns: SPEC "Ιδιοκτησία αρχείων").
   No build step, no new dependency, ES modules + CDN only. Small, plain code; a comment with source and certainty
   on every constant.
3. Don't edit tests. If a test looks wrong, STOP and report.
4. Run from athensone/:  $RUN
   All tests pass.
5. Commit: "$T: $TITLE". Never push, never merge, never commit to main or $base.
6. Write your report to $W/$T-code-report.md and print it. Choices the card doesn't cover go under
   "Questions for the owner"; don't guess.
P

cat > $W/$T-review-prompt.md <<P
You are the REVIEWER for task $T ($TITLE) of AthensOne. Tests and code were written by two other agents. You change
NO file in the repository and make no commit; the only file you write is your review. Start no long-running server.
Worktree: $W/$T. Diff: \`git diff $base...HEAD\`.

1. Read CLAUDE.md fully (review template, hard rules), athensone/docs/SPEC.md, the card "### $T:" in $BOARD,
   athensone/docs/DECISIONS.md, $W/$T-tests-report.md and $W/$T-code-report.md.
2. Check with small experiments in a scratch folder OUTSIDE the worktree:
   PRIVACY FIRST (can an un-blurred photo, EXIF, GPS, the user_id/points token reach a log, an error, disk or a
   third party?); sources on every answer; no AI action without a human; licences of anything new; files outside
   the card or outside this track's ownership; the app still works offline from web/mock/.
   Task-specific: $CHK
   Also: the code commit changed no test (\`git diff <tests commit> HEAD -- athensone/tests athensone/web/tests\` is empty).
3. Run from athensone/:  $RUN
4. Write the review with the CLAUDE.md review template to $W/$T-review.md and print it. Verdict: approve / approve
   with leftovers / changes needed. Every finding: file:line, what is wrong, how you know (ran it / read it), how bad.
P
echo "wrote $W/$T-{tests,code,review}-prompt.md"
