"""B13: the official registry service for a report category («what do I do now»).

The sandbox registry (`GET /v1/registry/services?q=`, ~570 services) was used only by POST /api/ask. Here each
sandbox category gets one curated Greek query; the first hit with a positive score is the category's service.
Pure apart from the two `sb` calls; the router turns SandboxError into 503.
"""
from __future__ import annotations

from . import categories

# One curated registry query per sandbox category (card B13, approved by the owner). `other` has no query on
# purpose: it covers anything, so a registry hit would be a guess. Certainty: the wording is ours; whether the live
# registry ranks the right service first for each query is unverified until checked against the sandbox.
QUERIES: dict[str, str | None] = {
    "pothole": "λακκούβα οδόστρωμα",
    "streetlight": "βλάβη ηλεκτροφωτισμού",
    "garbage": "αποκομιδή απορριμμάτων",
    "bulky_waste": "αποκομιδή ογκωδών αντικειμένων",
    "graffiti": "καθαρισμός γκράφιτι",
    "tree": "κλάδεμα δέντρων",
    "sidewalk": "επισκευή πεζοδρομίου",
    "abandoned_vehicle": "εγκαταλελειμμένα οχήματα",
    "noise": "ηχορύπανση",
    "stray_animals": "αδέσποτα ζώα",
    "water_leak": "διαρροή νερού",
    "other": None,
}

# How many hits to ask for: we only use the first with score > 0. Card B13. Certainty: our choice.
SEARCH_SIZE = 3


def _service_view(detail: dict) -> dict:
    """The fields the citizen sees; anything the registry left out becomes None / []. Field names follow the
    sandbox registry detail as used by POST /api/ask; `where`, `when`, `faq` are unverified on the live sandbox."""
    return {
        "id": detail.get("id"),
        "title": detail.get("title"),
        "documents": list(detail.get("documents") or []),
        "cost_eur": detail.get("cost_eur"),
        "online_url": detail.get("online_url"),
        "where": detail.get("where"),
        "when": detail.get("when"),
        "faq": list(detail.get("faq") or []),
    }


def guide(sb, category: str) -> dict:
    """The registry service for a sandbox category. Raises ValueError for an unknown category; lets SandboxError
    through. `service` is None when the category is `other` or the registry has no positive-score hit."""
    if category not in QUERIES:
        raise ValueError(f"unknown category: {category}")
    query = QUERIES[category]
    service = None
    if query:
        items = (sb.services(query, size=SEARCH_SIZE) or {}).get("items") or []
        hit = next((it for it in items if (it.get("score") or 0) > 0), None)
        if hit:
            service = _service_view(sb.service(hit["id"]) or {})
    return {
        "category": category,
        "label_el": categories.LABEL_EL[category],
        "query": query,
        "service": service,
        "source": "mock" if sb.mock else "sandbox",
    }
