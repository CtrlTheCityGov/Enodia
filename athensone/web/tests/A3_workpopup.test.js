// A3 Work popup tests (TASKS_A.md "### A3", SPEC.md F4 & "Φούσκα έργου (map popup)").
import test from "node:test";
import assert from "node:assert/strict";
import * as workpopup from "../js/ui/workpopup.js";

// Verify statusLabel maps planned, in_progress, and completed to their exact Greek labels.
test("test_status_labels_greek", () => {
  assert.equal(workpopup.statusLabel("planned"), "Προγραμματισμένο");
  assert.equal(workpopup.statusLabel("in_progress"), "Σε εξέλιξη");
  assert.equal(workpopup.statusLabel("completed"), "Ολοκληρωμένο");
});

// Verify paidPct computes the percentage paid out of the contract amount.
test("test_paid_pct", () => {
  assert.equal(workpopup.paidPct(30000, 120000), 25);
});

// Verify guaranteeCountdown returns 183 daysLeft and ~50 pctLeft at midpoint of a 1-year guarantee.
test("test_guarantee_countdown_mid", () => {
  const res = workpopup.guaranteeCountdown("2026-01-01", "2027-01-01", "2026-07-02");
  assert.ok(res && typeof res === "object", "guaranteeCountdown must return an object");
  assert.equal(res.daysLeft, 183);
  assert.ok(
    typeof res.pctLeft === "number" && Math.abs(res.pctLeft - 50) <= 1,
    `expected pctLeft ≈ 50, got ${res.pctLeft}`,
  );
});

// Verify guaranteeCountdown clamps daysLeft and pctLeft to 0 once today is past guaranteeEnd.
test("test_guarantee_countdown_expired", () => {
  const res = workpopup.guaranteeCountdown("2024-01-01", "2025-01-01", "2026-07-02");
  assert.ok(res && typeof res === "object", "guaranteeCountdown must return an object");
  assert.equal(res.daysLeft, 0);
  assert.equal(res.pctLeft, 0);
});

// Verify missing guarantee_end (and unknown paid amount) renders «άγνωστο» with no bar and never 0.
test("test_guarantee_unknown", () => {
  const countdown = workpopup.guaranteeCountdown("2026-01-01", null, "2026-07-02");
  assert.ok(
    countdown == null || (countdown.daysLeft !== 0 && countdown.pctLeft !== 0),
    "unknown guarantee_end must not return 0",
  );

  const html = workpopup.popupHtml(
    {
      id: "work-unknown",
      title: "Συντήρηση οδοστρώματος",
      status: "completed",
      contractor: "ΑΚΤΩΡ Α.Τ.Ε.",
      amount_contract_eur: 120000,
      amount_paid_eur: null,
      ada: "Ψ1ΑΒΩ6Μ-123",
      end_date: "2026-01-01",
      guarantee_end: null,
    },
    "2026-07-02",
  );

  assert.equal(typeof html, "string");
  assert.ok(html.includes("άγνωστο"), "expected unknown guarantee/paid to display «άγνωστο»");
  assert.ok(!/<progress\b/i.test(html), "unknown guarantee/paid must not render a <progress> bar");
  assert.ok(
    !/role\s*=\s*["']progressbar["']/i.test(html),
    "unknown guarantee/paid must not render a progressbar role",
  );
  assert.ok(
    !/width\s*:\s*\d+(?:\.\d+)?%/i.test(html) &&
      !/class\s*=\s*["'][^"']*(?:progress-bar|guarantee-bar|countdown-bar|bar-fill)[^"']*["']/i.test(html),
    "unknown guarantee/paid must not render a bar element",
  );
  assert.ok(!/μέρες\s+ακόμα/i.test(html), "unknown guarantee must not guess days remaining");
  assert.ok(!/\b0\s*€/.test(html), "unknown paid amount must not display 0 €");
});

// Verify diavgeiaUrl builds the Diavgeia decision URL for an ADA code.
test("test_diavgeia_link", () => {
  assert.equal(
    workpopup.diavgeiaUrl("Ψ1ΑΒΩ6Μ-123"),
    "https://diavgeia.gov.gr/decision/view/Ψ1ΑΒΩ6Μ-123",
  );
});

// Verify popupHtml renders contractor, paid and contract € amounts, and the Diavgeia ADA link.
test("test_popup_has_contractor_euros_ada", () => {
  const html = workpopup.popupHtml(
    {
      id: "work-1",
      title: "Ανάπλαση οδού Ερμού",
      status: "in_progress",
      contractor: "ΤΕΡΝΑ Α.Ε.",
      amount_contract_eur: 120000,
      amount_paid_eur: 30000,
      ada: "Ψ1ΑΒΩ6Μ-123",
      start_date: "2026-01-01",
      end_date: "2026-06-01",
      guarantee_end: "2027-06-01",
    },
    "2026-07-02",
  );

  assert.equal(typeof html, "string");
  assert.ok(html.includes("ΤΕΡΝΑ Α.Ε."), "popup HTML must contain the contractor");
  assert.ok(html.includes("€"), "popup HTML must show the € symbol");
  assert.match(html, /30[.,\s\u00a0\u202f]?000/, "popup HTML must contain paid € amount");
  assert.match(html, /120[.,\s\u00a0\u202f]?000/, "popup HTML must contain contract € amount");
  assert.ok(
    html.includes("https://diavgeia.gov.gr/decision/view/Ψ1ΑΒΩ6Μ-123"),
    "popup HTML must contain the Diavgeia link",
  );
  assert.ok(html.includes("Ψ1ΑΒΩ6Μ-123"), "popup HTML must contain the ΑΔΑ text");
});

// Verify popupHtml escapes HTML injection in contractor, title, and ada so no <img> element is created.
test("test_popup_escapes_html", () => {
  const html = workpopup.popupHtml(
    {
      id: "work-xss",
      title: '<img src=y onerror="alert(2)">',
      status: "planned",
      contractor: '<img src=x onerror="alert(1)">',
      amount_contract_eur: 50000,
      amount_paid_eur: 10000,
      ada: 'Ψ1ΑΒΩ6Μ-123"<img src=z onerror=alert(3)>',
    },
    "2026-07-02",
  );

  assert.equal(typeof html, "string");
  assert.ok(!/<img\b/i.test(html), "HTML injection must not produce an unescaped <img element");
  assert.ok(html.includes("&lt;img"), "injected HTML must be escaped as text (&lt;img)");
  assert.ok(!/<a\b[^>]*\bonerror=/i.test(html), "ADA link attributes must not allow attribute breakout");
});
