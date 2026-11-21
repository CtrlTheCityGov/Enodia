// Municipal work map popup UI (SPEC.md F4, "Φούσκα έργου (map popup)"; TASKS_A.md A3).
// Pure helpers + MapLibre Popup wiring on works line click.
// Does not touch document or maplibregl at import time so Node can import it safely.

import { WORKS_LINE_LAYER_ID } from "../layers/works.js";

// Fallback text for unknown or missing fields; never display 0 or a guess
// (source: CLAUDE.md Hard rules & TASKS_A.md A3, certainty: verified).
const UNKNOWN_LABEL = "άγνωστο";

// Greek work status labels (source: SPEC.md "Φούσκα έργου (map popup)" & TASKS_A.md A3, certainty: verified).
const STATUS_LABELS = {
  planned: "Προγραμματισμένο",
  in_progress: "Σε εξέλιξη",
  completed: "Ολοκληρωμένο",
};

// Base URL for Diavgeia decision pages (source: SPEC.md "Φούσκα έργου (map popup)" & TASKS_A.md A3;
// external URL reachability unverified in offline test environment).
const DIAVGEIA_BASE_URL = "https://diavgeia.gov.gr/decision/view/";

// Synthetic SEED work prefix and Greek badge label (source: DECISIONS.md A-14 & TASKS_A.md A6, certainty: verified).
const SEED_ADA_PREFIX = "SEED-";
const SEED_BADGE_LABEL = "SEED · δοκιμαστικό";

// Allowed characters in a Diavgeia ADA code: Unicode letters (Greek/Latin), digits, and hyphens,
// with at least one alphanumeric character; rejects quotes, angle brackets, spaces, slashes, and query/fragment chars
// (source: Diavgeia ADA format e.g. Ψ1ΑΒΩ6Μ-123, certainty: high).
const SAFE_ADA_RE = /^(?=[\p{L}\p{N}-]*[\p{L}\p{N}])[\p{L}\p{N}-]+$/u;

// Milliseconds in one UTC calendar day: 24 * 60 * 60 * 1000 (source: standard calendar math, certainty: verified).
const MS_PER_DAY = 86_400_000;

// ISO calendar date prefix YYYY-MM-DD (source: ISO 8601 / SPEC.md works contract dates, certainty: verified).
const ISO_DATE_PREFIX_RE = /^(\d{4})-(\d{2})-(\d{2})(?:$|T)/;

// Popup CSS classes combining SPEC .glass surface with A3 layout hook
// (source: SPEC.md "Φούσκα έργου (map popup)" & A3 card, certainty: verified).
const POPUP_CLASS_NAME = "glass work-popup";

// Action button label for opening Dev B's progress report flow
// (source: SPEC.md "Φούσκα έργου (map popup)" & TASKS_A.md A3, certainty: verified).
const REPORT_BUTTON_LABEL = "Ανέφερε πρόοδο";

// Greek number formatter for euro amounts (source: el-GR locale convention, certainty: design default).
const EUR_FORMATTER = new Intl.NumberFormat("el-GR", { maximumFractionDigits: 2 });

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function toFiniteNumber(value) {
  if (typeof value === "number") {
    return Number.isFinite(value) ? value : null;
  }
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function parseUtcDayMs(value) {
  if (value instanceof Date) {
    if (Number.isNaN(value.getTime())) {
      return null;
    }
    return Date.UTC(value.getUTCFullYear(), value.getUTCMonth(), value.getUTCDate());
  }
  if (typeof value !== "string") {
    return null;
  }
  const trimmed = value.trim();
  const match = trimmed.match(ISO_DATE_PREFIX_RE);
  if (!match) {
    return null;
  }
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const utcMs = Date.UTC(year, month - 1, day);
  const check = new Date(utcMs);
  if (
    check.getUTCFullYear() !== year ||
    check.getUTCMonth() !== month - 1 ||
    check.getUTCDate() !== day
  ) {
    return null;
  }
  return utcMs;
}

function formatEur(value) {
  const num = toFiniteNumber(value);
  if (num === null || num < 0) {
    return null;
  }
  return `${EUR_FORMATTER.format(num)} €`;
}

function getReportOpener(reportModule) {
  if (typeof reportModule === "function") {
    return reportModule;
  }
  if (!reportModule || typeof reportModule !== "object") {
    return null;
  }
  const candidates = [
    reportModule.openReport,
    reportModule.openReportFlow,
    reportModule.open,
    reportModule.startReport,
    reportModule.reportProgress,
    reportModule.default,
  ];
  return candidates.find((fn) => typeof fn === "function") ?? null;
}

export function statusLabel(status) {
  if (typeof status !== "string") {
    return UNKNOWN_LABEL;
  }
  const key = status.trim().toLowerCase();
  return Object.hasOwn(STATUS_LABELS, key) ? STATUS_LABELS[key] : UNKNOWN_LABEL;
}

export function paidPct(paid, contract) {
  const paidNum = toFiniteNumber(paid);
  const contractNum = toFiniteNumber(contract);
  if (paidNum === null || contractNum === null || paidNum < 0 || contractNum <= 0) {
    return null;
  }
  const rawPct = Math.round((paidNum / contractNum) * 100);
  return Math.min(100, Math.max(0, rawPct));
}

function isSeedWork(data) {
  if (!data || typeof data !== "object") {
    return false;
  }
  if (data.seed) {
    return true;
  }
  const ada = typeof data.ada === "string" ? data.ada.trim() : "";
  return ada.toUpperCase().startsWith(SEED_ADA_PREFIX);
}

function formatUpdatedAt(value) {
  if (value == null || value === "") {
    return null;
  }
  if (value instanceof Date) {
    return Number.isNaN(value.getTime()) ? null : value.toLocaleString("el-GR");
  }
  if (typeof value === "string") {
    const trimmed = value.trim();
    if (!trimmed) return null;
    const parsed = new Date(trimmed);
    return Number.isNaN(parsed.getTime()) ? trimmed : parsed.toLocaleString("el-GR");
  }
  return null;
}

function buildProvenanceHtml(data, options, isSeed) {
  const rawSource = data?.source ?? data?.data_source ?? options?.source ?? null;
  const norm = typeof rawSource === "string" ? rawSource.trim().toLowerCase() : "";
  let prov = null;
  if (norm === "live") {
    prov = { key: "live", label: "LIVE" };
  } else if (norm === "cache" || norm === "cached") {
    prov = { key: "cached", label: "CACHED" };
  } else if (norm === "mock" || norm === "demo" || norm === "seed" || isSeed) {
    prov = { key: "demo", label: "DEMO" };
  }
  const updatedStr = formatUpdatedAt(data?.updated_at ?? options?.updated_at);
  if (!prov && !updatedStr) {
    return "";
  }
  const pillHtml = prov
    ? `<span class="prov-pill prov-pill--${prov.key}">${prov.label}</span>`
    : "";
  const updatedHtml = updatedStr
    ? `<span class="prov-updated">${escapeHtml(updatedStr)}</span>`
    : "";
  return `<div class="work-popup__prov">${pillHtml}${updatedHtml}</div>`;
}

export function guaranteeCountdown(handover, guaranteeEnd, today = new Date()) {
  const handoverMs = parseUtcDayMs(handover);
  const endMs = parseUtcDayMs(guaranteeEnd);
  const todayMs = parseUtcDayMs(today);

  if (handoverMs === null || endMs === null || todayMs === null) {
    return null;
  }

  const totalMs = endMs - handoverMs;
  if (totalMs <= 0) {
    return null;
  }

  const remainingMs = endMs - todayMs;
  if (remainingMs <= 0) {
    return { daysLeft: 0, pctLeft: 0 };
  }

  // Clamp remaining time to the guarantee window when today precedes handover
  // so future-start works do not inflate daysLeft beyond the guarantee period (TASKS_A.md A6).
  const effectiveRemainingMs = todayMs < handoverMs ? totalMs : remainingMs;
  const daysLeft = Math.round(effectiveRemainingMs / MS_PER_DAY);
  const pctLeft = Math.min(100, Math.max(0, Math.round((effectiveRemainingMs / totalMs) * 100)));
  return { daysLeft, pctLeft };
}

export function diavgeiaUrl(ada) {
  if (typeof ada !== "string") {
    return null;
  }
  const cleaned = ada.trim();
  if (cleaned.toUpperCase().startsWith(SEED_ADA_PREFIX)) {
    return null;
  }
  if (!SAFE_ADA_RE.test(cleaned)) {
    return null;
  }
  return `${DIAVGEIA_BASE_URL}${cleaned}`;
}

export function popupHtml(props, today = new Date(), options = {}) {
  const data = props && typeof props === "object" ? props : {};

  const titleText =
    typeof data.title === "string" && data.title.trim() !== ""
      ? data.title.trim()
      : UNKNOWN_LABEL;

  const rawStatusKey = typeof data.status === "string" ? data.status.trim().toLowerCase() : "";
  const statusClass = Object.hasOwn(STATUS_LABELS, rawStatusKey) ? rawStatusKey : "unknown";
  const statusText = statusLabel(data.status);

  const contractorText =
    typeof data.contractor === "string" && data.contractor.trim() !== ""
      ? data.contractor.trim()
      : UNKNOWN_LABEL;

  const paidStr = formatEur(data.amount_paid_eur);
  const contractStr = formatEur(data.amount_contract_eur);
  const pct = paidPct(data.amount_paid_eur, data.amount_contract_eur);

  let paymentSummary;
  if (paidStr !== null && contractStr !== null) {
    paymentSummary = `${paidStr} / ${contractStr}${pct !== null ? ` (${pct}%)` : ""}`;
  } else if (paidStr !== null) {
    paymentSummary = `${paidStr} / ${UNKNOWN_LABEL}`;
  } else if (contractStr !== null) {
    paymentSummary = `${UNKNOWN_LABEL} / ${contractStr}`;
  } else {
    paymentSummary = UNKNOWN_LABEL;
  }

  const paidBarHtml =
    pct !== null
      ? `<div class="work-popup__bar" role="progressbar" aria-label="Ποσοστό πληρωμής" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${pct}"><div class="work-popup__bar-fill work-popup__bar-fill--paid" style="width: ${pct}%"></div></div>`
      : "";

  const handoverDate = data.handover_date ?? data.end_date ?? null;
  const countdown = guaranteeCountdown(handoverDate, data.guarantee_end, today);

  let guaranteeText;
  if (countdown === null) {
    guaranteeText = UNKNOWN_LABEL;
  } else if (countdown.daysLeft === 0) {
    guaranteeText = "Έληξε";
  } else if (countdown.daysLeft === 1) {
    guaranteeText = "1 μέρα ακόμα";
  } else {
    guaranteeText = `${countdown.daysLeft} μέρες ακόμα`;
  }

  const guaranteeBarHtml =
    countdown !== null
      ? `<div class="work-popup__bar" role="progressbar" aria-label="Υπόλοιπο εγγύησης" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${countdown.pctLeft}"><div class="work-popup__bar-fill work-popup__bar-fill--guarantee" style="width: ${countdown.pctLeft}%"></div></div>`
      : "";

  const adaText = typeof data.ada === "string" ? data.ada.trim() : "";
  const isSeed = isSeedWork(data);
  const adaHref = !isSeed && adaText !== "" ? diavgeiaUrl(adaText) : null;
  let adaContentHtml;
  if (isSeed) {
    const plainAdaHtml =
      adaText !== ""
        ? `<span class="work-popup__ada-text">${escapeHtml(adaText)}</span> `
        : `<span class="work-popup__unknown">${UNKNOWN_LABEL}</span> `;
    adaContentHtml = `${plainAdaHtml}<span class="work-popup__seed-badge">${SEED_BADGE_LABEL}</span>`;
  } else if (adaHref !== null) {
    adaContentHtml = `<a class="work-popup__ada-link" href="${escapeHtml(adaHref)}" target="_blank" rel="noopener noreferrer">${escapeHtml(adaText)}</a>`;
  } else if (adaText !== "") {
    adaContentHtml = `<span class="work-popup__ada-text">${escapeHtml(adaText)}</span>`;
  } else {
    adaContentHtml = `<span class="work-popup__unknown">${UNKNOWN_LABEL}</span>`;
  }

  const hasBus = Boolean(options?.bus && typeof options.bus.dispatchEvent === "function");
  const hasReportFlow = hasBus || getReportOpener(options?.reportModule) !== null;
  const workId = data.id != null ? String(data.id).trim() : "";
  const reportBtnHtml =
    hasReportFlow && workId !== ""
      ? `<div class="work-popup__actions"><button type="button" class="work-popup__report-btn" data-work-id="${escapeHtml(workId)}">${REPORT_BUTTON_LABEL}</button></div>`
      : "";

  const provHtml = buildProvenanceHtml(data, options, isSeed);

  return [
    `<article class="work-popup__card" aria-label="Στοιχεία έργου">`,
    `<header class="work-popup__header">`,
    `<h3 class="work-popup__title">${escapeHtml(titleText)}</h3>`,
    `<span class="work-popup__status work-popup__status--${statusClass}">${escapeHtml(statusText)}</span>`,
    `</header>`,
    provHtml,
    `<dl class="work-popup__details">`,
    `<div class="work-popup__row">`,
    `<dt class="work-popup__label">Ανάδοχος</dt>`,
    `<dd class="work-popup__value">${escapeHtml(contractorText)}</dd>`,
    `</div>`,
    `<div class="work-popup__row">`,
    `<dt class="work-popup__label">Πληρωμή / Σύμβαση</dt>`,
    `<dd class="work-popup__value">${escapeHtml(paymentSummary)}${paidBarHtml}</dd>`,
    `</div>`,
    `<div class="work-popup__row">`,
    `<dt class="work-popup__label">Εγγύηση</dt>`,
    `<dd class="work-popup__value">${escapeHtml(guaranteeText)}${guaranteeBarHtml}</dd>`,
    `</div>`,
    `</dl>`,
    `<blockquote class="work-popup__ada"><span class="work-popup__ada-label">ΑΔΑ</span> ${adaContentHtml}</blockquote>`,
    reportBtnHtml,
    `</article>`,
  ].join("");
}

export function initWorkPopup(map, options = {}) {
  if (!map || typeof map.on !== "function") {
    return null;
  }

  const layerId =
    typeof options?.layerId === "string" && options.layerId.trim() !== ""
      ? options.layerId
      : WORKS_LINE_LAYER_ID;

  let activePopup = null;

  function setCursor(cursor) {
    const canvas = typeof map.getCanvas === "function" ? map.getCanvas() : null;
    if (canvas?.style) {
      canvas.style.cursor = cursor;
    }
  }

  function onMouseEnter() {
    setCursor("pointer");
  }

  function onMouseLeave() {
    setCursor("");
  }

  function onWorkClick(event) {
    const feature = event?.features?.[0];
    if (!feature || !event?.lngLat) {
      return;
    }

    const PopupCtor = options?.maplibregl?.Popup ?? globalThis.maplibregl?.Popup;
    if (typeof PopupCtor !== "function") {
      return;
    }

    const props = { ...(feature.properties ?? {}) };
    if (props.id == null && feature.id != null) {
      props.id = feature.id;
    }

    const today =
      typeof options?.getToday === "function"
        ? options.getToday()
        : (options?.today ?? new Date());

    const bus = options?.bus && typeof options.bus.dispatchEvent === "function" ? options.bus : null;
    const html = popupHtml(props, today, {
      reportModule: options?.reportModule,
      bus,
    });

    if (activePopup && typeof activePopup.remove === "function") {
      activePopup.remove();
    }

    const popup = new PopupCtor({ className: POPUP_CLASS_NAME });
    popup.setLngLat(event.lngLat).setHTML(html).addTo(map);
    activePopup = popup;

    const reportOpener = getReportOpener(options?.reportModule);
    const reportHasMount = Boolean(
      options?.reportModule &&
        typeof options.reportModule === "object" &&
        typeof options.reportModule.mount === "function",
    );
    if ((bus || reportOpener) && typeof popup.getElement === "function") {
      const rootEl = popup.getElement();
      const reportBtn = rootEl?.querySelector?.(".work-popup__report-btn");
      if (reportBtn && typeof reportBtn.addEventListener === "function") {
        reportBtn.addEventListener("click", () => {
          const workId = props.id != null ? String(props.id).trim() : null;
          if (!workId) {
            return;
          }
          const clickLngLat = event.lngLat;
          if (bus) {
            bus.dispatchEvent(
              new CustomEvent("report:open", { detail: { work_id: workId, lngLat: clickLngLat } }),
            );
          }
          if (reportOpener && !reportHasMount) {
            reportOpener({ work_id: workId, lngLat: clickLngLat });
          }
        });
      }
    }
  }

  map.on("click", layerId, onWorkClick);
  map.on("mouseenter", layerId, onMouseEnter);
  map.on("mouseleave", layerId, onMouseLeave);

  return {
    layerId,
    destroy() {
      if (typeof map.off === "function") {
        map.off("click", layerId, onWorkClick);
        map.off("mouseenter", layerId, onMouseEnter);
        map.off("mouseleave", layerId, onMouseLeave);
      }
      if (activePopup && typeof activePopup.remove === "function") {
        activePopup.remove();
        activePopup = null;
      }
      setCursor("");
    },
  };
}
