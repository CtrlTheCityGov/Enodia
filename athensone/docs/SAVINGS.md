# How much the city saves

**About €0.5M a year (range €0.29M–€0.74M). Payback about 6 months in the base case.**
These are our estimates from public numbers, not measured Athens figures. We only count what the
demo loop does; waste routing and streetlights (in the first concept report) are not built, so not claimed.

## Inputs
- **~195,000 requests/year** via Novoville and 1595 (259,000 from Jan 2024 to Apr 2025, per the Crowdpolicy article on Apps4Athens 3.0).
- **Staff cost ≈ €17/hour:** university-educated public employee, 20 years' service, €1,902 gross/month in Dec 2025
  ([Parapolitika](https://en.parapolitika.gr/?p=185212)) × 12 months × 1.2179 employer contribution
  ([PwC](https://taxsummaries.pwc.com/Greece/Individual/Other-taxes)) ÷ 1,600 working hours.
- **Duplicates:** 5.5% of NYC 311 cases in 2018 were closed as duplicates ([NYC Council](https://council.nyc.gov/data/311-agency/)).
- **Phone cost:** $3.39 average per 311 call across 15 US cities ([Pew](https://www.pew.org/-/media/assets/2010/03/02/final-311-report-030210.pdf));
  70–80% of it is staff pay ([Governing](https://www.governing.com/topics/public-justice-safety/gt-cities-aim-to-cut-311-costs.html)).
  With Greek pay we use €1.90 per call and €0.20 per digital answer.

## Model

| Source of savings | Assumption (low / base / high) | Low | Base | High |
|---|---|---|---|---|
| Faster triage | 2 / 3 / 4 min saved per request → 6,500 / 9,750 / 13,000 h × €17 | €110k | €166k | €221k |
| Duplicate crew trips avoided | 4 / 6 / 8% duplicates; half of requests send a crew; €40 / €50 / €60 per visit | €156k | €293k | €468k |
| Calls moved to the app | 40% of requests by phone; 15 / 25 / 35% move; €1.90 → €0.20 | €20k | €33k | €46k |
| **Total** | | **€286k** | **€491k** | **€735k** |

Formulas: triage = 195,000 × minutes ÷ 60 × €17 · duplicates = 195,000 × dup% × 0.5 × € per visit ·
calls = 195,000 × 0.4 × shift% × €1.70.

**Payback** (costs from the concept report: €150–280k build, €70–110k/year to run):
base ≈ 6 months · worst case (low savings, high cost) ≈ 19 months · best case < 3 months.

**Comparable results elsewhere:** Bernalillo County's AI self-service cut cost per contact from $4.59 to $0.99
([case study](https://customgpt.ai/wp-content/uploads/2025/08/Bernalillo-County-Case-Study.pdf)); Philadelphia's
311 app reduced calls by 15% ([Governing](https://governing.com/archive/gov-tulsa-technology-311.html)).

**Not counted in euros:** older residents kept out of the heat, wheelchair users avoiding blocked ramps,
residents who see their report get fixed.

**Verify with DAEM first:** phone share at 1595, duplicate rate, cost of one crew visit.
