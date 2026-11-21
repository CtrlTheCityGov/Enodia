# Decisions

`A-n` = decided by Evgenii. `Q-n` = open; agents don't build on an open question.

- **A-1** (Sat 21 Nov) The cards T1–T4 in TASKS.md are approved as drafted from the Build Plan, test lists included
  ("ok start building stuff").
- **A-2** Agent steps run in Antigravity: tests Gemini 4 Hydrogen, code Claude Opus 5.5 inside Antigravity, review
  Gemini 4 Argon. Claude CLI only as fallback (Claude Code account at ~89 % weekly usage).
- **A-3** Each task adds its new tests in its own file `tests/test_T<n>_<name>.py` and its code in a marked
  `# --- T<n> ---` block in shared files, so the four parallel branches merge mechanically.
- **A-4** T2 does not wire the "+5 for confirming the fix" grant, because the confirm endpoint comes from T1. T2
  exposes a `points.grant(...)` helper; the +5 hook is added after both T1 and T2 are merged (follow-up T6).
- **A-5** Points token: random, set as an HttpOnly cookie `ao_token` on first use; stored only in our SQLite; never
  sent to the sandbox, never logged.

## Open

- **Q-1** T5: add `deface` (MIT) as a dependency? It pulls onnxruntime (~large). Recommendation: yes, with the
  OpenCV Haar fallback kept, only if T1–T4 are merged before ~02:00.
