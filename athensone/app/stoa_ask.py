"""Ask Stoa: retrieve-then-verify cited answers over municipal public-works cards.

Our own retrieve-then-verify rule (no external RAG library). Every fact comes
from `works.all_cards()`; every sentence ends with `[ΑΔΑ …]`. If no record
matches, refuses rather than guessing. An optional Krikri text model can
rephrase the template answer, but any output that drops a citation or invents
an ΑΔΑ or number not present in the matched cards falls back to the template.
"""
from __future__ import annotations

import os
import re
import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation

import httpx

from . import config, works

# Refusal string when no works card matches the query.
# Source: docs/TASKS.md (T4 card) and CLAUDE.md hard rule; certainty: exact requirement.
REFUSAL_TEXT = "Δεν βρήκα τεκμηριωμένα στοιχεία για αυτό."

# Maximum works cards retrieved and cited per question.
# Source: docs/TASKS.md (T4 card: "up to 3 cards"); certainty: exact requirement.
MAX_CARDS = 3

# HTTP timeout (seconds) for optional Krikri OpenAI-compatible rephrasing.
# Source: operational heuristic (shorter than vision.py's 60 s image timeout); certainty: unverified.
LLM_TIMEOUT_S = 15.0

# Default Greek open text model name when TEXT_LLM_BASE_URL is configured.
# Source: .env.example (Llama-Krikri-8B-Instruct, ILSP); certainty: verified from .env.example.
DEFAULT_TEXT_LLM_MODEL = "krikri-8b-instruct"

# Minimum token length for partial-query street matching so single stray letters don't match broadly.
# Source: local retrieval heuristic; certainty: unverified.
MIN_PARTIAL_TOKEN_LEN = 3

# Priority order when breaking retrieval ties (same priority as works.for_report).
# Source: app/works.py:168; certainty: verified against works.py.
STATUS_ORDER: dict[str, int] = {"ACTIVE": 0, "UNKNOWN": 1, "ENDED": 2}

# Generic Greek/English street-type prefixes that must not trigger a street match on their own.
# Source: standard Greek/English street naming + test_ask_unknown_street_refuses ("Οδός Ανύπαρκτη 12"); certainty: verified.
STREET_PREFIXES: frozenset[str] = frozenset({
    "οδοσ", "οδου", "οδο", "οδων",
    "πλατεια", "πλατειασ",
    "λεωφοροσ", "λεωφορου",
    "δρομοσ", "δρομου",
    "street", "road", "avenue", "square",
})

# Common Greek question words ignored when checking if query tokens form a subset of a street name.
# Source: common Greek interrogatives/articles/prepositions; certainty: unverified heuristic.
QUERY_STOPWORDS: frozenset[str] = frozenset({
    "τι", "ποιοσ", "ποια", "ποιο", "ποιεσ", "ποιοι", "που", "ποτε", "ποσο",
    "εγινε", "εγιναν", "υπαρχει", "υπαρχουν", "εχουν",
    "εργα", "εργο", "εργασια", "εργασιεσ",
    "στη", "στην", "στο", "στον", "στισ", "στουσ",
    "ο", "η", "οι", "τη", "την", "το", "τον", "τησ", "του", "των", "τα",
    "για", "με", "και", "σε", "απο", "εχει", "ειναι",
    "εγγυηση", "εγγυησησ", "αναδοχοσ", "κοστοσ", "ημερομηνια",
})

# Normalized Greek/English stems per works_type so inflected Greek queries match works types.
# Source: works.WORKS_EL keys in app/works.py:38-39; certainty: verified against works.py.
WORKS_TYPE_TERMS: dict[str, tuple[str, ...]] = {
    "sidewalk": ("sidewalk", "πεζοδρομ"),
    "ramp": ("ramp", "ραμπ", "αμεα"),
    "paving": ("paving", "πλακοστρωσ", "πλακεσ", "πλακα"),
    "asphalt": ("asphalt", "ασφαλτοστρωσ", "ασφαλτ"),
    "lighting": ("lighting", "ηλεκτροφωτισμ", "φωτισμ", "φανοστατ"),
}

# Evidence-wrapped fields on a works card whose values and ADAs are cited in answers.
# Source: data/works_seed.json schema and app/works.py:199-223; certainty: verified.
EVIDENCE_FIELDS: tuple[str, ...] = (
    "street", "title", "contractor", "amount_paid_eur", "completion_date", "guarantee_months",
)

# --- T9: Ask Stoa verify fixes ---
# Accent-folded Greek legal/reference/title abbreviations ending in a period that do not end a sentence.
# Source: app/works.py:93 ("άρθ. 171 ν. 4412/2016"), app/works.py:205 ("σελ."),
# docs/TASKS.md T9 card, and standard Athens street/title prefixes; certainty: verified.
_SENTENCE_ABBREV: frozenset[str] = frozenset({
    "αρθ", "σελ", "αρ", "ν",
    "αγ", "βασ", "λεωφ", "πλ", "ελ", "εθν", "στρ", "δρ", "καθ",
    "δηλ", "βλ", "κλπ",
})

# Multi-part dotted abbreviations (e.g. Α.Ε., Ο.Ε., Ε.Π.Ε., Ι.Κ.Ε., Α.Τ.Ε., π.χ., κ.λπ.).
# Source: docs/TASKS.md T9 card ("Α.Ε., Ο.Ε., initials") and Greek corporate forms; certainty: verified.
_DOTTED_ABBREV_RE = re.compile(r"(?<!\w)(?:[A-Za-zΑ-Ωα-ωάέήίόύώϊϋΐΰ]{1,4}\.){2,}$")

# Whole-date patterns (ISO YYYY-MM-DD / YYYY/MM/DD and Greek DD/MM/YYYY / DD-MM-YYYY / DD.MM.YYYY)
# with matching separators so dates are verified whole rather than split into digit pieces.
# Source: docs/TASKS.md T9 card and app/works.py:95,97,119-122; certainty: verified.
_ISO_DATE_RE = re.compile(r"(?<!\d)(\d{4})([/-])(\d{1,2})\2(\d{1,2})(?!\d)")
_DMY_DATE_RE = re.compile(r"(?<!\d)(\d{1,2})([/.-])(\d{1,2})\2(\d{4})(?!\d)")

# Currency amount patterns (number next to €, ευρώ/ευρω, or EUR) so amounts are verified against
# card amounts only, never against date years or other card numbers.
# Source: docs/TASKS.md T9 card and app/stoa_ask.py:217 ("_fmt_eur(amt) €"); certainty: verified.
_CURRENCY_PAT = r"(?:\u20ac|ευρ[ωώ](?!\w)|(?<![A-Za-z])eur(?![A-Za-z]))"
_AMOUNT_AFTER_RE = re.compile(rf"(?<!\d)(\d+(?:[.,]\d+)*)\s*{_CURRENCY_PAT}", re.IGNORECASE)
_AMOUNT_BEFORE_RE = re.compile(rf"{_CURRENCY_PAT}\s*(\d+(?:[.,]\d+)*)(?!\d)", re.IGNORECASE)

# Slash-joined numeric identifiers (e.g. Greek law number 4412/2016) kept whole instead of split.
# Source: app/works.py:93 ("άρθ. 171 ν. 4412/2016"); certainty: verified.
_SLASH_NUM_RE = re.compile(r"(?<!\d)\d+/\d+(?!\d)")

# Normalized mandatory hedging phrase for ACTIVE guarantee cards ("πιθανώς εντός").
# Source: CLAUDE.md hard rule, docs/TASKS.md T9 card, and app/works.py:121-122; certainty: exact requirement.
_GUARANTEE_CAUTION_NORM = "πιθανωσ εντοσ"
# --- end T9 ---

_CITATION_RE = re.compile(r"\[ΑΔΑ\s+([^\]]+)\]")
_END_CITATION_RE = re.compile(r"\[ΑΔΑ\s+[^\]]+\]\.?$")
_LOOSE_ADA_RE = re.compile(r"ΑΔΑ\s+([^\s\].,;)]+)")
_NUM_RE = re.compile(r"\d+(?:[.,]\d+)*")


def normalize(text: str) -> str:
    """Return accent-insensitive, case-folded text with punctuation collapsed to single spaces."""
    decomposed = unicodedata.normalize("NFD", text or "")
    no_marks = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    folded = no_marks.casefold()
    cleaned = re.sub(r"[^\w]+", " ", folded, flags=re.UNICODE)
    return " ".join(cleaned.split())


def _field_val(card: dict, key: str):
    return (card.get(key) or {}).get("value")


def _field_ada(card: dict, key: str) -> str | None:
    src = (card.get(key) or {}).get("source") or {}
    ada = src.get("ada")
    return str(ada).strip() if ada else None


def _card_adas(card: dict) -> list[str]:
    """Ordered unique ΑΔΑ identifiers present on a single works card."""
    seen: list[str] = []
    for key in EVIDENCE_FIELDS:
        ada = _field_ada(card, key)
        if ada and ada not in seen:
            seen.append(ada)
    return seen


def _unique_adas(*adas: str | None, fallback: str | None = None) -> list[str]:
    seen: list[str] = []
    for ada in adas:
        if ada and ada not in seen:
            seen.append(ada)
    if not seen and fallback:
        seen.append(fallback)
    return seen


def _cite(adas: list[str]) -> str:
    return f"[ΑΔΑ {', '.join(adas)}]"


def _fmt_eur(amount: float | int) -> str:
    val = float(amount)
    if val.is_integer():
        return f"{int(val):,}".replace(",", ".")
    return f"{val:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _fmt_iso_date(iso_str: str) -> str:
    try:
        return f"{date.fromisoformat(iso_str):%d/%m/%Y}"
    except ValueError:
        return iso_str


# --- T9: Ask Stoa verify fixes ---
def _works_type_vocab(cards: list[dict]) -> set[str]:
    """Normalized works-type tokens across known works labels and loaded cards."""
    vocab: set[str] = set()
    for wtype, label in works.WORKS_EL.items():
        vocab.add(normalize(wtype))
        vocab.update(normalize(label).split())
    for card in cards:
        wt = normalize(card.get("works_type") or "")
        if wt:
            vocab.add(wt)
        wt_el = normalize(card.get("works_type_el") or "")
        if wt_el:
            vocab.update(wt_el.split())
    return vocab


def _is_works_type_token(tok: str, vocab: set[str]) -> bool:
    """True if a normalized query token refers to a works type rather than a street/location."""
    if tok in vocab:
        return True
    return any(tok.startswith(stem) for stems in WORKS_TYPE_TERMS.values() for stem in stems)
# --- end T9 ---


def retrieve(q: str, cards: list[dict] | None = None, limit: int = MAX_CARDS) -> list[dict]:
    """Accent-insensitive retrieval on street names and works types, capped at `limit` cards."""
    qn = normalize(q)
    if not qn:
        return []
    q_tokens = qn.split()
    q_token_set = set(q_tokens)
    q_core = [t for t in q_tokens if t not in STREET_PREFIXES and t not in QUERY_STOPWORDS]

    all_items = works.all_cards() if cards is None else cards
    # --- T9: Ask Stoa verify fixes ---
    wtype_vocab = _works_type_vocab(all_items)
    q_street_tokens = [t for t in q_core if not _is_works_type_token(t, wtype_vocab)]
    has_street_target = bool(q_street_tokens)
    # --- end T9 ---
    scored: list[tuple[int, int, int, dict]] = []

    for idx, card in enumerate(all_items):
        if not _card_adas(card):
            continue
        street_score = 0

        street = normalize(_field_val(card, "street") or "")
        street_tokens = street.split()
        street_core = [t for t in street_tokens if t not in STREET_PREFIXES]
        if street and re.search(rf"(?<!\w){re.escape(street)}(?!\w)", qn):
            street_score = 100
        elif street_core and set(street_core).issubset(q_token_set):
            street_score = 80
        elif (
            q_street_tokens
            and street_core
            and set(q_street_tokens).issubset(set(street_core))
            and any(len(t) >= MIN_PARTIAL_TOKEN_LEN for t in q_street_tokens)
        ):
            street_score = 60

        # --- T9: Ask Stoa verify fixes ---
        # If the query specifies a street/location name, do not match a card on works type alone.
        if has_street_target and street_score == 0:
            continue
        # --- end T9 ---

        score = street_score

        wtype = normalize(card.get("works_type") or "")
        wtype_el = normalize(card.get("works_type_el") or "")
        stems = WORKS_TYPE_TERMS.get(wtype, ())
        works_match = (
            (bool(wtype) and wtype in q_token_set)
            or (bool(wtype_el) and wtype_el in qn)
            or any(qt.startswith(stem) for qt in q_tokens for stem in stems)
        )
        if works_match:
            score += 40

        if score > 0:
            status = (card.get("clock") or {}).get("status", "UNKNOWN")
            scored.append((-score, STATUS_ORDER.get(status, 9), idx, card))

    scored.sort(key=lambda item: (item[0], item[1], item[2]))
    return [item[3] for item in scored[:limit]]


def format_card(card: dict) -> list[str]:
    """Build deterministic Greek sentences for one card; every sentence ends with `[ΑΔΑ …]`."""
    adas_all = _card_adas(card)
    fallback = adas_all[0]
    street = _field_val(card, "street") or "ΑΓΝΩΣΤΗ ΟΔΟΣ"
    wtype_el = card.get("works_type_el") or card.get("works_type") or "Έργο"
    contractor = _field_val(card, "contractor") or "ΑΓΝΩΣΤΟ"

    adas_intro = _unique_adas(
        _field_ada(card, "street"),
        _field_ada(card, "title"),
        _field_ada(card, "contractor"),
        fallback=fallback,
    )
    s1 = f"Στο σημείο {street} καταγράφεται έργο «{wtype_el}» με ανάδοχο {contractor} {_cite(adas_intro)}."

    amt = _field_val(card, "amount_paid_eur")
    adas_amt = _unique_adas(_field_ada(card, "amount_paid_eur"), fallback=fallback)
    if amt is not None:
        s2 = f"Οι καταγεγραμμένες πληρωμές ανέρχονται σε {_fmt_eur(amt)} € {_cite(adas_amt)}."
    else:
        s2 = f"Το ποσό πληρωμών είναι ΑΓΝΩΣΤΟ {_cite(adas_amt)}."

    comp_field = card.get("completion_date") or {}
    comp_val = comp_field.get("value")
    adas_comp = _unique_adas(_field_ada(card, "completion_date"), fallback=fallback)
    if comp_val and comp_field.get("label") != "UNKNOWN":
        s3 = f"Η βεβαιωμένη περάτωση είναι στις {_fmt_iso_date(str(comp_val))} {_cite(adas_comp)}."
    else:
        s3 = f"Η ημερομηνία περάτωσης είναι ΑΓΝΩΣΤΗ {_cite(adas_comp)}."

    clk = card.get("clock") or works.clock(card)
    hl = card.get("headline_el") or works.headline(card, clk)
    formula = clk.get("formula") or "ΑΓΝΩΣΤΟ"
    adas_clock = _unique_adas(
        _field_ada(card, "completion_date"),
        _field_ada(card, "guarantee_months"),
        fallback=fallback,
    )
    s4 = f"{hl} · τύπος: {formula} {_cite(adas_clock)}."

    return [s1, s2, s3, s4]


def format_answer(cards: list[dict]) -> str:
    """Format up to 3 matched works cards into a cited template answer."""
    if not cards:
        return REFUSAL_TEXT
    return "\n\n".join("\n".join(format_card(card)) for card in cards)


def rephrase(text: str, cards: list[dict]) -> str:
    """Optional Krikri rephrase over an OpenAI-compatible endpoint; returns `text` if unconfigured or on error."""
    base_url = os.getenv("TEXT_LLM_BASE_URL", "").strip().rstrip("/")
    if not base_url:
        return text
    model = os.getenv("TEXT_LLM_MODEL", DEFAULT_TEXT_LLM_MODEL).strip() or DEFAULT_TEXT_LLM_MODEL
    api_key = os.getenv("TEXT_LLM_API_KEY", config.OPENAI_API_KEY)
    system_prompt = (
        "Αναδιατύπωσε το παρακάτω κείμενο σε καθαρά, σύντομα ελληνικά για δημοτικό υπάλληλο. "
        "Μην αλλάξεις κανέναν αριθμό, καμία ημερομηνία και κανέναν ΑΔΑ. "
        "Κράτησε τη διατύπωση «πιθανώς εντός περιόδου εγγύησης». "
        "Κάθε πρόταση πρέπει να τελειώνει με [ΑΔΑ ...]."
    )
    try:
        r = httpx.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "temperature": 0,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text},
                ],
            },
            timeout=LLM_TIMEOUT_S,
        )
        r.raise_for_status()
        out = r.json()["choices"][0]["message"]["content"].strip()
        return out or text
    except Exception:
        return text


def _sentences(text: str) -> list[str]:
    """Split text into sentences, keeping decimal/thousands dots and Greek abbreviations intact."""
    out: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        start = 0
        for i, ch in enumerate(line):
            if ch != ".":
                continue
            if i > 0 and line[i - 1].isdigit() and i + 1 < len(line) and line[i + 1].isdigit():
                continue
            if i + 1 < len(line) and not line[i + 1].isspace():
                continue
            # --- T9: Ask Stoa verify fixes ---
            if _DOTTED_ABBREV_RE.search(line[: i + 1]):
                continue
            word = re.findall(r"([A-Za-zΑ-Ωα-ωάέήίόύώϊϋΐΰ]+)$", line[:i])
            if word and (len(word[0]) == 1 or normalize(word[0]) in _SENTENCE_ABBREV):
                continue
            # --- end T9 ---
            seg = line[start : i + 1].strip()
            if seg:
                out.append(seg)
            start = i + 1
        tail = line[start:].strip()
        if tail:
            out.append(tail)
    return out


def _canonical_num(tok: str) -> str:
    """Normalize Greek (`48.200`, `12,5`) and English (`48,200`, `12.5`) numeric tokens."""
    if "." in tok and "," in tok:
        s = tok.replace(".", "").replace(",", ".") if tok.rfind(",") > tok.rfind(".") else tok.replace(",", "")
    elif "." in tok:
        parts = tok.split(".")
        s = (
            "".join(parts)
            if len(parts) >= 2 and all(len(p) == 3 for p in parts[1:]) and len(parts[0]) <= 3 and not parts[0].startswith("0")
            else tok
        )
    elif "," in tok:
        parts = tok.split(",")
        s = (
            "".join(parts)
            if len(parts) >= 2 and all(len(p) == 3 for p in parts[1:]) and len(parts[0]) <= 3 and not parts[0].startswith("0")
            else tok.replace(",", ".")
        )
    else:
        s = tok
    try:
        d = Decimal(s)
        if d == d.to_integral_value():
            return str(int(d))
        return format(d, "f").rstrip("0").rstrip(".")
    except InvalidOperation:
        return tok


# --- T9: Ask Stoa verify fixes ---
def _extract_facts(text: str) -> tuple[set[str], set[str], set[str]]:
    """Extract (whole_dates, whole_amounts, other_numbers) after removing `[ΑΔΑ …]` citation blocks."""
    s = _CITATION_RE.sub(" ", text)
    dates: set[str] = set()
    amounts: set[str] = set()
    others: set[str] = set()

    def _take_iso(m: re.Match[str]) -> str:
        y, mo, d = int(m.group(1)), int(m.group(3)), int(m.group(4))
        dates.add(f"{y:04d}-{mo:02d}-{d:02d}")
        return " "

    def _take_dmy(m: re.Match[str]) -> str:
        d, mo, y = int(m.group(1)), int(m.group(3)), int(m.group(4))
        dates.add(f"{y:04d}-{mo:02d}-{d:02d}")
        return " "

    def _take_amount(m: re.Match[str]) -> str:
        amounts.add(_canonical_num(m.group(1)))
        return " "

    def _take_slash(m: re.Match[str]) -> str:
        others.add(m.group(0))
        return " "

    s = _ISO_DATE_RE.sub(_take_iso, s)
    s = _DMY_DATE_RE.sub(_take_dmy, s)
    s = _AMOUNT_AFTER_RE.sub(_take_amount, s)
    s = _AMOUNT_BEFORE_RE.sub(_take_amount, s)
    s = _SLASH_NUM_RE.sub(_take_slash, s)
    for m in _NUM_RE.finditer(s):
        others.add(_canonical_num(m.group(0)))
    return dates, amounts, others


def _allowed_adas(cards: list[dict]) -> set[str]:
    return {ada for card in cards for ada in _card_adas(card)}


def _allowed_facts(cards: list[dict]) -> tuple[set[str], set[str], set[str]]:
    """Allowed (whole_dates, whole_amounts, other_numbers) grounded in the matched cards."""
    dates: set[str] = set()
    amounts: set[str] = set()
    others: set[str] = set()
    for card in cards:
        amt = _field_val(card, "amount_paid_eur")
        if amt is not None:
            amounts.add(_canonical_num(str(amt)))

        comp = card.get("completion_date") or {}
        if comp.get("value") and comp.get("label") != "UNKNOWN":
            d, a, o = _extract_facts(str(comp["value"]))
            dates |= d
            amounts |= a
            others |= o

        gm = _field_val(card, "guarantee_months")
        if gm is not None:
            others.add(_canonical_num(str(gm)))

        for key in ("street", "title", "contractor"):
            val = _field_val(card, key)
            if val is not None:
                d, a, o = _extract_facts(str(val))
                dates |= d
                amounts |= a
                others |= o

        clk = card.get("clock") or works.clock(card)
        for k in ("until", "formula"):
            if clk.get(k) is not None:
                d, a, o = _extract_facts(str(clk[k]))
                dates |= d
                amounts |= a
                others |= o

        hl = card.get("headline_el") or works.headline(card, clk)
        for s in (hl, card.get("works_type_el")):
            if s:
                d, a, o = _extract_facts(str(s))
                dates |= d
                amounts |= a
                others |= o

    return dates, amounts, others


def _required_guarantee_cautions(cards: list[dict]) -> int:
    """Count matched cards whose deterministic headline carries the mandatory 'πιθανώς εντός' wording."""
    count = 0
    for card in cards:
        clk = card.get("clock") or works.clock(card)
        hl = card.get("headline_el") or works.headline(card, clk)
        if _GUARANTEE_CAUTION_NORM in normalize(hl):
            count += 1
    return count
# --- end T9 ---


def verify(text: str, cards: list[dict]) -> bool:
    """Verify every sentence is cited, ΑΔΑs/dates/amounts/numbers match `cards`, and guarantee hedging stays."""
    if not text or not text.strip():
        return False
    sents = _sentences(text)
    if not sents:
        return False
    for sent in sents:
        if not _END_CITATION_RE.search(sent):
            return False

    allowed_a = _allowed_adas(cards)
    cited_adas: list[str] = []
    for match in _CITATION_RE.finditer(text):
        for part in match.group(1).split(","):
            token = part.strip()
            if not token or token not in allowed_a:
                return False
            cited_adas.append(token)
    if not cited_adas:
        return False
    for match in _LOOSE_ADA_RE.finditer(text):
        if match.group(1).strip() not in allowed_a:
            return False

    # --- T9: Ask Stoa verify fixes ---
    allowed_d, allowed_amt, allowed_other = _allowed_facts(cards)
    found_d, found_amt, found_other = _extract_facts(text)
    if not found_d.issubset(allowed_d):
        return False
    if not found_amt.issubset(allowed_amt):
        return False
    if not found_other.issubset(allowed_other):
        return False

    required_cautions = _required_guarantee_cautions(cards)
    if required_cautions > 0:
        found_cautions = len(re.findall(rf"(?<!\w){_GUARANTEE_CAUTION_NORM}(?!\w)", normalize(text)))
        if found_cautions < required_cautions:
            return False
    # --- end T9 ---
    return True


def ask(q: str) -> dict:
    """Retrieve matching Stoa cards, format cited template, optionally rephrase, and verify."""
    meta = works.meta()
    cards = retrieve(q)
    if not cards:
        return {
            "q": q,
            "answer": REFUSAL_TEXT,
            "cards": [],
            "sources": [],
            "rephrased": False,
            "data_source": meta["source"],
            "snapshot": meta.get("snapshot"),
        }

    template = format_answer(cards)
    candidate = rephrase(template, cards).strip()
    if candidate != template and verify(candidate, cards):
        answer = candidate
        rephrased = True
    else:
        answer = template
        rephrased = False

    seen_adas: list[str] = []
    for card in cards:
        for ada in _card_adas(card):
            if ada not in seen_adas:
                seen_adas.append(ada)

    return {
        "q": q,
        "answer": answer,
        "cards": cards,
        "sources": [{"ada": ada} for ada in seen_adas],
        "rephrased": rephrased,
        "data_source": meta["source"],
        "snapshot": meta.get("snapshot"),
    }
