// Enodia Speech Controller (Priority 2): natural Greek (el-GR) & English neural TTS
// via backend POST /api/tts (through api.js), with strict verified-voice Web Speech fallback.
// HARD RULE: Never silently pronounce Greek text with an English browser voice.
// Never touches document or fetch at import time so Node can import and test pure helpers safely.

const GREEK_CHAR_RE = /[\u0370-\u03ff\u1f00-\u1fff]/g;
const LATIN_CHAR_RE = /[A-Za-z]/g;

export const NO_GREEK_VOICE_MSG =
  "Δεν βρέθηκε ελληνική φωνή εκφώνησης εκτός σύνδεσης (δεν χρησιμοποιείται αγγλική φωνή για ελληνικά).";

/** Detect speech locale ('el-GR' or 'en-US'). Mixed Greek+English routes to 'el-GR'. */
export function detectSpeechLang(text) {
  const sample = String(text ?? "");
  const gr = (sample.match(GREEK_CHAR_RE) || []).length;
  const lat = (sample.match(LATIN_CHAR_RE) || []).length;
  const total = gr + lat;
  if (total === 0) return "el-GR";
  if (gr > 0 && gr / total >= 0.12) return "el-GR";
  return "en-US";
}

/**
 * Select a verified browser SpeechSynthesisVoice matching the target locale.
 * Returns null if no matching voice is installed — NEVER returns an English voice for Greek text.
 */
export function selectVerifiedBrowserVoice(voices, lang = "el-GR") {
  if (!Array.isArray(voices) || voices.length === 0) return null;
  const prefix = String(lang || "el-GR").toLowerCase().split(/[-_]/)[0];
  const exactRe = new RegExp(`^${prefix}([-_]|$)`, "i");
  const matches = voices.filter((v) => v && typeof v.lang === "string" && exactRe.test(v.lang.trim()));
  if (matches.length === 0) return null;
  // Prefer local/neural Greek voices (e.g. Microsoft Athina, Google ελληνικά, Nestoras) when available.
  const preferred = matches.find((v) => /neural|athina|nestoras|google|natural/i.test(String(v.name || "")));
  return preferred || matches[0];
}

let activeAudio = null;
let activeObjectUrl = null;

/** Stop any currently playing neural or browser speech audio cleanly. */
export function stopSpeech() {
  if (activeAudio) {
    try {
      activeAudio.pause();
      activeAudio.currentTime = 0;
    } catch {
      // ignore
    }
    activeAudio = null;
  }
  if (activeObjectUrl && typeof globalThis.URL?.revokeObjectURL === "function") {
    try {
      globalThis.URL.revokeObjectURL(activeObjectUrl);
    } catch {
      // ignore
    }
    activeObjectUrl = null;
  }
  if (globalThis.speechSynthesis && typeof globalThis.speechSynthesis.cancel === "function") {
    try {
      globalThis.speechSynthesis.cancel();
    } catch {
      // ignore
    }
  }
}

/**
 * Speak `text` using neural backend TTS (`api.tts`) first, falling back ONLY to a verified
 * same-language browser voice. Never falls back to an English voice for Greek text.
 */
export async function speakResponse({ text, api = null, onStatus = null, onEnd = null } = {}) {
  stopSpeech();
  const clean = String(text ?? "").trim();
  if (!clean) {
    onEnd?.();
    return { ok: false, mode: "empty" };
  }

  const lang = detectSpeechLang(clean);

  // 1. Primary: Backend Neural TTS (el-GR-AthinaNeural / en-US-AriaNeural) via api.tts
  if (api && typeof api.tts === "function" && typeof globalThis.Audio === "function") {
    try {
      const res = await api.tts({ text: clean, lang });
      if (res?.ok && res.blob && typeof globalThis.URL?.createObjectURL === "function") {
        const url = globalThis.URL.createObjectURL(res.blob);
        activeObjectUrl = url;
        const audio = new globalThis.Audio(url);
        activeAudio = audio;
        audio.onended = () => {
          stopSpeech();
          onEnd?.();
        };
        audio.onerror = () => {
          stopSpeech();
          onEnd?.();
        };
        await audio.play();
        return { ok: true, mode: "neural", lang: res.lang || lang, voice: res.voice || null };
      }
    } catch {
      // Fall through to strict verified browser voice check.
    }
  }

  // 2. Fallback: Web Speech API ONLY with a verified matching-locale voice.
  const synth = globalThis.speechSynthesis;
  const Utterance = globalThis.SpeechSynthesisUtterance;
  if (synth && typeof Utterance === "function" && typeof synth.getVoices === "function") {
    const voices = synth.getVoices() || [];
    const verified = selectVerifiedBrowserVoice(voices, lang);
    if (verified) {
      const u = new Utterance(clean);
      u.lang = verified.lang || lang;
      u.voice = verified;
      u.onend = () => onEnd?.();
      u.onerror = () => onEnd?.();
      synth.speak(u);
      return { ok: true, mode: "browser_verified", lang: u.lang, voice: verified.name || null };
    }
  }

  // 3. Hard refusal: never speak Greek with an English voice.
  if (lang.startsWith("el")) {
    onStatus?.(NO_GREEK_VOICE_MSG);
  } else {
    onStatus?.("No matching speech voice is available offline.");
  }
  onEnd?.();
  return { ok: false, mode: "unavailable", lang };
}
