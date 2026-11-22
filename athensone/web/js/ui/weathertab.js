// Weather & Environment tab ("Καιρός"): Athens microclimate summary, heatmap mode switcher,
// UV/AQI/PM2.5 metrics, provenance badge, and nearest cool spots.
// Follows A-35: export mount({map, api, root, bus}). No fetch, DOM or maplibregl at import time.

import { setMode as setEnvHeatmapMode } from "../layers/env.js";

const SOURCE_BADGE = {
  live: "LIVE",
  snapshot: "CACHED",
  cache: "CACHED",
  mock: "DEMO · δοκιμαστικό",
};

function statsFor(features) {
  const temps = [];
  const aqis = [];
  const pm25s = [];
  const uvs = [];
  for (const f of features || []) {
    const p = f?.properties || {};
    if (typeof p.temp_c === "number" && Number.isFinite(p.temp_c)) temps.push(p.temp_c);
    if (typeof p.aqi === "number" && Number.isFinite(p.aqi)) aqis.push(p.aqi);
    if (typeof p.pm25 === "number" && Number.isFinite(p.pm25)) pm25s.push(p.pm25);
    if (typeof p.uv_index === "number" && Number.isFinite(p.uv_index)) uvs.push(p.uv_index);
  }
  const avg = (arr) => (arr.length ? Math.round((arr.reduce((a, b) => a + b, 0) / arr.length) * 10) / 10 : null);
  return {
    count: (features || []).length,
    tempAvg: avg(temps),
    tempMin: temps.length ? Math.min(...temps) : null,
    tempMax: temps.length ? Math.max(...temps) : null,
    aqiAvg: avg(aqis),
    pm25Avg: avg(pm25s),
    uvMax: uvs.length ? Math.max(...uvs) : null,
  };
}

export async function mount({ map, api, root, container, bus }) {
  root = container || root;
  if (!root) return {};
  const doc = root.ownerDocument || globalThis.document;
  const el = (tag, props = {}, text) => {
    const node = doc.createElement(tag);
    for (const [k, v] of Object.entries(props)) {
      if (k === "class") node.className = v;
      else node.setAttribute(k, String(v));
    }
    if (text !== undefined) node.textContent = text;
    return node;
  };

  const panel = el("section", {
    id: "weathertab-panel",
    class: "glass workstab-panel",
    role: "tabpanel",
    "aria-labelledby": "tab-weather",
    hidden: "true",
  });
  panel.hidden = true;

  const header = el("div", { class: "workstab-header" });
  const heading = el("h2", { class: "workstab-heading" }, "Καιρός & Περιβάλλον Αθήνας");
  const sourceBadge = el("span", { class: "workstab-source" }, "");
  const closeBtn = el("button", { type: "button", class: "overlay-close-btn", "aria-label": "Κλείσιμο" }, "×");
  closeBtn.addEventListener("click", () => {
    const mTab = doc.getElementById?.("tab-map");
    if (mTab && typeof mTab.click === "function") mTab.click();
    else bus?.dispatchEvent?.(new CustomEvent("tab:change", { detail: { tab: "map" } }));
  });
  header.append(heading, sourceBadge, closeBtn);

  const modeBar = el("div", { class: "workstab-filters", role: "group", "aria-label": "Επίπεδο χάρτη περιβάλλοντος" });
  const modes = [
    { id: "temp", label: "Θερμοκρασία" },
    { id: "aqi", label: "Αέρας (AQI)" },
    { id: "pm25", label: "PM2.5" },
  ];
  let activeMode = "temp";
  const modeBtns = new Map();
  for (const m of modes) {
    const b = el("button", {
      type: "button",
      class: m.id === activeMode ? "workstab-filter is-active" : "workstab-filter",
      "aria-pressed": String(m.id === activeMode),
    }, m.label);
    b.addEventListener("click", () => {
      activeMode = m.id;
      for (const [id, btn] of modeBtns.entries()) {
        const on = id === activeMode;
        btn.setAttribute("aria-pressed", String(on));
        btn.classList.toggle("is-active", on);
      }
      if (map) {
        setEnvHeatmapMode(map, activeMode);
        if (typeof map.setLayoutProperty === "function" && (!map.getLayer || map.getLayer("env-heat"))) {
          map.setLayoutProperty("env-heat", "visibility", "visible");
        }
      }
    });
    modeBtns.set(m.id, b);
    modeBar.append(b);
  }

  const metricsEl = el("dl", { class: "workstab-card-meta" });
  const coolTitle = el("h3", { class: "workstab-card-title", style: "margin:8px 0 4px" }, "Δροσεροί χώροι δήμου");
  const coolList = el("ul", { class: "workstab-list" });
  panel.append(header, modeBar, metricsEl, coolTitle, coolList);
  root.append(panel);

  let loaded = false;
  async function loadWeather() {
    if (loaded) return;
    loaded = true;
    try {
      const res = await api?.env?.();
      const s = statsFor(res?.features);
      sourceBadge.textContent = SOURCE_BADGE[res?.source] || "CACHED";
      metricsEl.textContent = "";
      const rows = [
        ["Θερμοκρασία", s.tempAvg !== null ? `${s.tempAvg}°C (${s.tempMin}–${s.tempMax}°C)` : "άγνωστο"],
        ["Ευρωπαϊκός Δείκτης AQI", s.aqiAvg !== null ? `${s.aqiAvg}` : "άγνωστο"],
        ["Σωματίδια PM2.5", s.pm25Avg !== null ? `${s.pm25Avg} µg/m³` : "άγνωστο"],
        ["Δείκτης UV", s.uvMax !== null ? `${s.uvMax}` : "άγνωστο"],
        ["Σημεία πλέγματος", `${s.count} (Δήμος Αθηναίων)`],
      ];
      for (const [dt, dd] of rows) {
        metricsEl.append(el("dt", {}, dt), el("dd", {}, dd));
      }
    } catch {
      sourceBadge.textContent = "DEMO";
    }

    if (typeof api?.coolSpots === "function") {
      try {
        const spots = await api.coolSpots();
        coolList.textContent = "";
        for (const f of (spots?.features || []).slice(0, 6)) {
          const p = f.properties || {};
          const coords = f.geometry?.coordinates || [];
          const li = el("li", { class: "workstab-card" });
          const title = el("strong", {}, p.name || "Χώρος");
          const kind = el("div", { class: "workstab-status" }, p.kind || "");
          li.append(title, kind);
          if (coords.length >= 2) {
            const fly = el("button", { type: "button", class: "workstab-filter" }, "Στον χάρτη");
            fly.addEventListener("click", () => {
              bus?.dispatchEvent?.(new CustomEvent("map:flyto", { detail: { lon: coords[0], lat: coords[1], zoom: 16 } }));
            });
            li.append(fly);
          }
          coolList.append(li);
        }
      } catch {
        // optional
      }
    }
  }

  bus?.addEventListener?.("tab:change", (e) => {
    const open = e?.detail?.tab === "weather";
    panel.hidden = !open;
    if (open) loadWeather();
  });

  return { refresh: () => { loaded = false; return loadWeather(); } };
}
