// A9 Regression tests for Greek Neural Speech controller (Priority 2) & verified-voice guard.
import test from "node:test";
import assert from "node:assert/strict";

import * as speech from "../js/speech.js";

test("test_detect_speech_lang_handles_greek_mixed_and_english", () => {
  assert.equal(speech.detectSpeechLang("Ποιο φαρμακείο εφημερεύει στην Αθήνα;"), "el-GR");
  assert.equal(speech.detectSpeechLang("Η διαδρομή Valhalla wheelchair έχει 62% σκιά και AQI 28."), "el-GR");
  assert.equal(speech.detectSpeechLang("Wheelchair route from Syntagma to Monastiraki avoids roadworks."), "en-US");
});

test("test_select_verified_browser_voice_never_returns_english_for_greek", () => {
  const englishOnly = [
    { name: "Microsoft David - English (United States)", lang: "en-US" },
    { name: "Google UK English Female", lang: "en-GB" },
  ];
  assert.equal(speech.selectVerifiedBrowserVoice(englishOnly, "el-GR"), null);

  const withGreek = [
    ...englishOnly,
    { name: "Microsoft Athina Online (Natural) - Greek (Greece)", lang: "el-GR" },
  ];
  const picked = speech.selectVerifiedBrowserVoice(withGreek, "el-GR");
  assert.ok(picked);
  assert.equal(picked.lang, "el-GR");
  assert.match(picked.name, /Athina/);
});

test("test_speak_response_refuses_english_voice_for_greek_when_offline", async () => {
  const spoken = [];
  const statuses = [];
  const prevSynth = globalThis.speechSynthesis;
  const prevUtt = globalThis.SpeechSynthesisUtterance;
  try {
    globalThis.speechSynthesis = {
      cancel() {},
      getVoices: () => [{ name: "Microsoft David", lang: "en-US" }],
      speak(u) {
        spoken.push(u);
      },
    };
    globalThis.SpeechSynthesisUtterance = class FakeUtt {
      constructor(t) {
        this.text = t;
      }
    };

    const res = await speech.speakResponse({
      text: "Καλημέρα Αθήνα, το έργο στην Ερμού είναι σε εξέλιξη.",
      api: { async tts() { return { ok: false, error: "offline" }; } },
      onStatus: (m) => statuses.push(m),
    });

    assert.equal(res.ok, false);
    assert.equal(res.mode, "unavailable");
    assert.equal(spoken.length, 0, "MUST NEVER pass Greek text to an English browser voice");
    assert.equal(statuses[0], speech.NO_GREEK_VOICE_MSG);
  } finally {
    globalThis.speechSynthesis = prevSynth;
    globalThis.SpeechSynthesisUtterance = prevUtt;
  }
});
