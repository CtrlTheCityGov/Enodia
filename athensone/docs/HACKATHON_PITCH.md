# Pitch (3 minutes) · AthensOne / Stoa

**Problem (30 s).** A citizen reports broken paving. The city sends its own crew and pays. Months earlier, a
contractor resurfaced that street under a contract that obliges them to fix defects during the guarantee period.
Nobody connects the two, because the evidence is spread across Διαύγεια decisions, ΚΗΜΔΗΣ contracts and paper.

**What we built (60 s).** One flow, live in the demo:
citizen pin + photo (faces and plates blurred on the server) → the city's request system → duplicates *strengthen*
the case instead of vanishing → **Stoa** looks up public-works decisions near that point, explains *why* each is a
candidate and how sure it is, and computes the guarantee period deterministically from the contract term and the
completion certificate → a cited evidence dossier → engineer and Legal decide, every step on the record →
the citizen sees the outcome.

**Why trust it (45 s).** Real Διαύγεια decisions with real ΑΔΑ links. When the completion certificate isn't public,
Stoa says **UNKNOWN** and refuses to draft a claim: it tells the engineer which document to request. Proximity is
never presented as liability; district-wide contracts are labelled as such. AI suggests, rules check, people decide;
nothing is ever sent to a contractor by the system.

**Value (30 s).** Every defect fixed under guarantee is a repair the city doesn't pay for twice, and a contractor
held to the contract. The audit trail and the source on every fact make it usable by Legal Services, not just a
dashboard. (We don't quote a savings figure we can't source; `docs/SAVINGS.md` has the model and its assumptions.)

**Honest limits (15 s).** Data is a verified snapshot, not a live feed; real completion dates are rarely published;
no OCR of contract PDFs yet; operator login is a demo key. Next: PDF/OCR extraction with page-level quotes, municipal
SSO, PostGIS.
