"""Neural Greek & English Text-to-Speech pipeline (Priority 2).

Uses `edge-tts` (LGPL-3.0, Microsoft Azure Neural voices: `el-GR-AthinaNeural` for Greek,
`en-US-AriaNeural` for English) with a dedicated speech-only text normaliser that preserves
Greek Unicode & tonos, expands Greek municipal/street abbreviations, and NEVER transliterates
Greek to Latin or silently falls back to an English voice for Greek text.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass

# Default neural voices (configurable via environment variables).
# Resilient failover list per locale: NestorasNeural + AthinaNeural for Greek (never English for Greek!).
DEFAULT_VOICE_EL = os.getenv("TTS_VOICE_EL", "el-GR-NestorasNeural")
FALLBACK_VOICES_EL = ("el-GR-NestorasNeural", "el-GR-AthinaNeural")
DEFAULT_VOICE_EN = os.getenv("TTS_VOICE_EN", "en-US-AriaNeural")
FALLBACK_VOICES_EN = ("en-US-AriaNeural", "en-US-GuyNeural")
MAX_TTS_CHARS = int(os.getenv("TTS_MAX_CHARS", "2000"))

VOICE_MAP: dict[str, tuple[str, str]] = {
    "el": ("el-GR", DEFAULT_VOICE_EL),
    "el-gr": ("el-GR", DEFAULT_VOICE_EL),
    "en": ("en-US", DEFAULT_VOICE_EN),
    "en-us": ("en-US", DEFAULT_VOICE_EN),
    "en-gb": ("en-GB", os.getenv("TTS_VOICE_EN_GB", "en-GB-SoniaNeural")),
}

_GREEK_RE = re.compile(r"[\u0370-\u03ff\u1f00-\u1fff]")
_LATIN_RE = re.compile(r"[A-Za-z]")
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\((?:https?://[^\s)]+)\)")
_RAW_URL_RE = re.compile(r"https?://\S+")
_ISO_DATE_RE = re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b")
_GR_DATE_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(20\d{2})\b")
_TEMP_RE = re.compile(r"(-?\d+(?:[.,]\d+)?)\s*°\s*C\b", re.IGNORECASE)
_PCT_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*%")
_EUR_PREFIX_RE = re.compile(r"€\s*(\d+(?:[.,]\d+)*)")
_EUR_SUFFIX_RE = re.compile(r"(\d+(?:[.,]\d+)*)\s*€")
_DECIMAL_COMMA_RE = re.compile(r"(\d),(\d)")
_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0000FE0F"
    "]+",
    flags=re.UNICODE,
)

_GREEK_MONTHS_GEN: dict[int, str] = {
    1: "Ιανουαρίου",
    2: "Φεβρουαρίου",
    3: "Μαρτίου",
    4: "Απριλίου",
    5: "Μαΐου",
    6: "Ιουνίου",
    7: "Ιουλίου",
    8: "Αυγούστου",
    9: "Σεπτεμβρίου",
    10: "Οκτωβρίου",
    11: "Νοεμβρίου",
    12: "Δεκεμβρίου",
}

# Greek municipal, street, and unit abbreviations expanded ONLY for speech synthesis.
_EL_ABBREVS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bΛεωφ\.", re.IGNORECASE), "Λεωφόρος"),
    (re.compile(r"\bΠλ\.", re.IGNORECASE), "Πλατεία"),
    (re.compile(r"\bΑγ\.", re.IGNORECASE), "Αγίου"),
    (re.compile(r"\bΒασ\.", re.IGNORECASE), "Βασιλίσσης"),
    (re.compile(r"\bΕθν\.", re.IGNORECASE), "Εθνικής"),
    (re.compile(r"\bΔ\.Κ\.", re.IGNORECASE), "Δημοτική Κοινότητα"),
    (re.compile(r"\bπ\.χ\.", re.IGNORECASE), "παραδείγματος χάριν"),
    (re.compile(r"\bτηλ\.", re.IGNORECASE), "τηλέφωνο"),
    (re.compile(r"\bσελ\.", re.IGNORECASE), "σελίδα"),
    (re.compile(r"\bάρθ\.", re.IGNORECASE), "άρθρο"),
    (re.compile(r"\bΑ\.Ε\.", re.IGNORECASE), "Ανώνυμη Εταιρεία"),
    (re.compile(r"\bΟ\.Ε\.", re.IGNORECASE), "Ομόρρυθμη Εταιρεία"),
    (re.compile(r"\bχλμ\.", re.IGNORECASE), "χιλιόμετρα"),
    (re.compile(r"(?<=\d)\s*μ\.(?=\s|$|[,;)])"), " μέτρα"),
    (re.compile(r"(?<=\d)\s*m\b"), " μέτρα"),
    (re.compile(r"(?<=\d)\s*km\b", re.IGNORECASE), " χιλιόμετρα"),
    (re.compile(r"\bημ\.", re.IGNORECASE), "ημέρες"),
    (re.compile(r"\bΑΔΑ\b"), "Α Δ Α"),
    (re.compile(r"\bAQI\b"), "δείκτης αέρα"),
    (re.compile(r"\bPM2\.5\b", re.IGNORECASE), "σωματίδια Πι Εμ δύο κόμμα πέντε"),
    (re.compile(r"\bUV\b"), "δείκτης υπεριώδους"),
)


class TTSUnavailableError(RuntimeError):
    """Raised when the configured neural TTS provider cannot generate audio."""


@dataclass(frozen=True)
class TTSResult:
    audio: bytes
    media_type: str
    provider: str
    voice: str
    locale: str
    normalized_text: str


def detect_speech_language(text: str) -> str:
    """Detect whether speech text should be spoken in Greek ('el-GR') or English ('en-US').

    Mixed Greek + English sentences (e.g. Greek text containing 'Valhalla' or 'AQI') always
    route to 'el-GR' so Greek words are never read with an English voice.
    """
    sample = str(text or "")
    gr_count = len(_GREEK_RE.findall(sample))
    lat_count = len(_LATIN_RE.findall(sample))
    total = gr_count + lat_count
    if total == 0:
        return "el-GR"
    if gr_count > 0 and (gr_count / total) >= 0.12:
        return "el-GR"
    return "en-US"


def resolve_voice(text: str, lang: str | None = None, voice: str | None = None) -> tuple[str, str]:
    """Return (locale, neural_voice_name), guaranteeing Greek text never receives an English voice."""
    detected = detect_speech_language(text)
    if lang and lang.strip():
        key = lang.strip().lower().replace("_", "-")
        locale, default_v = VOICE_MAP.get(key, VOICE_MAP.get(key.split("-")[0], (detected, DEFAULT_VOICE_EL if detected.startswith("el") else DEFAULT_VOICE_EN)))
    else:
        locale = detected
        default_v = DEFAULT_VOICE_EL if locale.startswith("el") else DEFAULT_VOICE_EN

    # Hard safety guard: never assign a non-Greek voice to Greek text.
    if detected.startswith("el") and not locale.startswith("el"):
        locale, default_v = "el-GR", DEFAULT_VOICE_EL

    chosen_voice = voice.strip() if isinstance(voice, str) and voice.strip() else default_v
    if locale.startswith("el") and not chosen_voice.lower().startswith("el-"):
        chosen_voice = DEFAULT_VOICE_EL
    return locale, chosen_voice


def _format_greek_date(day: int, month: int, year: int) -> str:
    month_name = _GREEK_MONTHS_GEN.get(month)
    if not month_name or not (1 <= day <= 31):
        return f"{day}/{month}/{year}"
    return f"{day} {month_name} {year}"


def normalize_for_speech(text: str, locale: str | None = None) -> str:
    """Clean & normalise AI response text strictly for speech playback without altering visible text.

    Preserves Greek Unicode characters and tonos; never transliterates Greek to Latin.
    """
    raw = str(text or "").strip()
    if not raw:
        return ""
    loc = locale or detect_speech_language(raw)

    # 1. Strip Markdown links, raw URLs, formatting tokens, and emojis.
    s = _MD_LINK_RE.sub(r"\1", raw)
    s = _RAW_URL_RE.sub("", s)
    s = _EMOJI_RE.sub(" ", s)
    s = s.replace("→", " προς " if loc.startswith("el") else " to ")
    s = s.replace("·", ", ")
    s = re.sub(r"[•▪▸*_`#]+", " ", s)
    s = re.sub(r"(?m)^\s*-\s+", "", s)
    s = re.sub(r"\[|\]", " ", s)

    if loc.startswith("el"):
        # 2. Natural Greek dates, temperatures, percentages, currency, decimals, abbreviations.
        s = _ISO_DATE_RE.sub(lambda m: _format_greek_date(int(m.group(3)), int(m.group(2)), int(m.group(1))), s)
        s = _GR_DATE_RE.sub(lambda m: _format_greek_date(int(m.group(1)), int(m.group(2)), int(m.group(3))), s)
        s = _TEMP_RE.sub(lambda m: f"{m.group(1).replace('.', ',')} βαθμοί Κελσίου", s)
        s = _PCT_RE.sub(lambda m: f"{m.group(1).replace('.', ',')} τοις εκατό", s)
        s = _EUR_PREFIX_RE.sub(r"\1 ευρώ", s)
        s = _EUR_SUFFIX_RE.sub(r"\1 ευρώ", s)
        for pat, repl in _EL_ABBREVS:
            s = pat.sub(repl, s)
        s = _DECIMAL_COMMA_RE.sub(r"\1 κόμμα \2", s)
        # Replace Greek question mark ';' with '?' only if needed? Keep ';' AND '?' — Azure el-GR handles Greek ';' naturally.
    else:
        s = _TEMP_RE.sub(r"\1 degrees Celsius", s)
        s = _PCT_RE.sub(r"\1 percent", s)

    s = re.sub(r"\s*\n+\s*", ". ", s)
    s = re.sub(r"\s{2,}", " ", s).strip()
    s = re.sub(r"\.\s*\.", ".", s)
    return s[:MAX_TTS_CHARS]


async def synthesize_speech(
    text: str,
    *,
    lang: str | None = None,
    voice: str | None = None,
) -> TTSResult:
    """Synthesise natural neural speech MP3 via edge-tts with same-locale failover (never English for Greek)."""
    if os.getenv("TTS_PROVIDER", "edge-tts").strip().lower() == "off":
        raise TTSUnavailableError("TTS provider disabled via TTS_PROVIDER=off")

    locale, primary_voice = resolve_voice(text, lang=lang, voice=voice)
    spoken = normalize_for_speech(text, locale=locale)
    if not spoken:
        raise ValueError("Nothing to speak after normalisation")

    fallbacks = FALLBACK_VOICES_EL if locale.startswith("el") else FALLBACK_VOICES_EN
    candidates = [primary_voice] + [v for v in fallbacks if v != primary_voice]

    try:
        import edge_tts
    except Exception as exc:
        raise TTSUnavailableError(f"Neural TTS package unavailable: {type(exc).__name__}") from exc

    last_err: Exception | None = None
    for candidate_voice in candidates:
        try:
            comm = edge_tts.Communicate(spoken, candidate_voice)
            chunks: list[bytes] = []
            async for chunk in comm.stream():
                if chunk.get("type") == "audio" and chunk.get("data"):
                    chunks.append(chunk["data"])
            audio = b"".join(chunks)
            if audio:
                return TTSResult(
                    audio=audio,
                    media_type="audio/mpeg",
                    provider="edge-tts",
                    voice=candidate_voice,
                    locale=locale,
                    normalized_text=spoken,
                )
        except Exception as exc:
            last_err = exc
            continue

    raise TTSUnavailableError(f"Neural TTS failed: {type(last_err).__name__ if last_err else 'EmptyAudio'}") from last_err
