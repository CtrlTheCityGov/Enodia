/**
 * Tests for B8: Stoa AI UI module (web/js/ui/stoa.js).
 *
 * Expected pure exports from web/js/ui/stoa.js (implementer builds to match):
 *   - renderAnswerHtml(answerMd, citations): escapes raw HTML, renders safe Markdown
 *     (links only), and replaces each citation label with an <a> link carrying
 *     data-lon and data-lat attributes.
 *   - handleCitationClick(event, bus): reads data-lon / data-lat / label from the
 *     clicked citation link and dispatches CustomEvent("map:flyto", { detail: { lon, lat, label } })
 *     on bus.
 *   - mount(ctx): mounts the Stoa bubble/panel into ctx.root using ctx.api and ctx.bus.
 */
import test from "node:test";
import assert from "node:assert/strict";

import { renderAnswerHtml, handleCitationClick } from "../js/ui/stoa.js";

// Checks that answer_md + 2 citations produces HTML with 2 links carrying data-lon/data-lat while escaping raw HTML text.
test("test_js_link_citations", () => {
  const answerMd = "Ενεργά έργα: Οδός Ερμού <img src=x> και Οδός Πανεπιστημίου.";
  const citations = [
    { label: "Οδός Ερμού", lon: 23.7312, lat: 37.9759, kind: "work" },
    { label: "Οδός Πανεπιστημίου", lon: 23.7336, lat: 37.9794, kind: "work" },
  ];

  const html = renderAnswerHtml(answerMd, citations);

  const anchorTags = html.match(/<a\b[^>]*>/gi) ?? [];
  const citationLinks = anchorTags.filter(
    (tag) => /\bdata-lon=/.test(tag) && /\bdata-lat=/.test(tag),
  );
  assert.equal(citationLinks.length, 2);
  assert.match(html, /data-lon="23\.7312"/);
  assert.match(html, /data-lat="37\.9759"/);
  assert.match(html, /data-lon="23\.7336"/);
  assert.match(html, /data-lat="37\.9794"/);
  assert.ok(html.includes("Οδός Ερμού"));
  assert.ok(html.includes("Οδός Πανεπιστημίου"));
  assert.ok(!html.includes("<img"), "Raw HTML tag must be escaped");
  assert.ok(html.includes("&lt;img"), "Raw HTML tag must appear escaped as text");
});

// Checks that a <script> payload in answer_md is escaped as text and never creates a <script> element.
test("test_js_markdown_escapes_html", () => {
  const answerMd = 'Απάντηση <script>alert("xss")</script> τέλος.';

  const html = renderAnswerHtml(answerMd, []);

  assert.ok(!/<script\b/i.test(html), "Must not emit any <script> element");
  assert.ok(html.includes("&lt;script&gt;"), "Must render <script> escaped as text");
});

// Checks that clicking a citation link emits map:flyto on the bus with that link's lon, lat, and label.
test("test_js_click_emits_flyto", () => {
  const bus = new EventTarget();
  const emitted = [];
  bus.addEventListener("map:flyto", (ev) => emitted.push(ev.detail));

  const fakeLink = {
    dataset: { lon: "23.7312", lat: "37.9759", label: "Οδός Ερμού" },
    textContent: "Οδός Ερμού",
    closest(selector) {
      return selector.includes("data-lon") ? this : null;
    },
  };
  let prevented = false;
  const fakeEvent = {
    target: fakeLink,
    preventDefault() {
      prevented = true;
    },
  };

  handleCitationClick(fakeEvent, bus);

  assert.equal(prevented, true);
  assert.equal(emitted.length, 1);
  assert.deepEqual(emitted[0], {
    lon: 23.7312,
    lat: 37.9759,
    label: "Οδός Ερμού",
  });
});
