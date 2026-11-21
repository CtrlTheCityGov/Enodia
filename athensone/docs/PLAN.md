# Build plan

Live version of this plan (with diagram and sources): https://claude.ai/artifact/Lc4qXXtXYPMME8CWBFMPUQ

## Who does what

| Person | Owns | Files |
|---|---|---|
| A: Backend | Sandbox key + real-mode check, duplicate check, approve flow, seed data | `app/main.py`, `app/sandbox.py`, `seed.py` |
| B: AI | Face blur on real photos, vision provider, Greek prompts, AI register page | `app/privacy.py`, `app/vision.py`, `web/ai-register.html` |
| C: Citizen screen | Map, route, voice, big-button mode, report flow, timeline | `web/citizen.html`, `app/routing.py` |
| D: Operator screen | List, map, grouped reports, approve/reject, (stretch) cooling-coverage map | `web/operator.html` |
| E: Pitch | Real data (Friendship Club in Pangrati, certificate service id), slides, canvas, video, rehearsals, Slack + forms | `docs/` |

With 3 people: A also takes D; C also takes E.

## Schedule

1. **Hours 0–2:** everyone runs the quick start in mock mode. A gets the sandbox key and switches to real mode. E sends GitHub usernames.
2. **Hours 2–8:** each person improves their part against mock data.
3. **Hour 8 checkpoint:** the 7 steps run in real mode end to end. If not, cut stretch items.
4. **Hours 8–20:** real photo AI, real Friendship Club, ramp placed on the real route, photo GPS tested on a phone.
5. **Hours 20–26:** Greek text polish, big-button mode, fallbacks. **Feature freeze Sunday ~12:00.**
6. **Sunday 12:00–16:00:** record backup video, 3 timed rehearsals, test on phone hotspot, final push.
7. **Sunday 16:30:** pitch (5–6 min, own laptop, order by draw).

## Stretch (only after the 8-hour checkpoint passes)
1. Mobility profile toggle: wheelchair / walking aid / stroller (`profile` param already on `/api/route`).
2. Cooling-coverage map for the operator: shade neighbourhoods by walking time to the nearest Friendship Club or library.
3. Air quality on the route from Athens Open Data (CKAN, server-side only).

## Submission checklist
- [ ] GitHub usernames sent; repo created in the Apps4Athens organisation
- [ ] Code + README (install, `seed.py`, sample data)
- [ ] Mockups / screenshots in `docs/`
- [ ] Business model canvas (`docs/BUSINESS_MODEL_CANVAS.md`)
- [ ] Pitch deck, 4–5 slides
- [ ] Milestone form 1 (watch Slack)
- [ ] Milestone form 2
- [ ] `.env` / API key not committed

## Questions for the DAEM mentors
- What share of requests come by phone to 1595?
- How many are closed as duplicates today?
- What does one crew visit cost?
- Will reports created through AthensGov flow into Novoville/1595 in production?
