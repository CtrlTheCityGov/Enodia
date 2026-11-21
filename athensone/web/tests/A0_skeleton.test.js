import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const WEB_DIR = path.resolve(__dirname, "..");

// Dev A ES modules required by TASKS_A.md A0 and SPEC.md "Αρχιτεκτονική" (verified in both docs).
const DEV_A_MODULES = [
  "js/main.js",
  "js/map.js",
  "js/layers/env.js",
  "js/layers/access.js",
  "js/layers/works.js",
  "js/layers/transit.js",
  "js/layers/health.js",
  "js/layers/reports.js",
  "js/ui/layerbar.js",
  "js/ui/workpopup.js",
  "js/ui/routing.js",
];

// MapLibre GL JS 5.3.0 CDN URLs from SPEC.md "Engine και στυλ" (verified in SPEC.md).
const MAPLIBRE_CDN_PREFIX = "https://cdn.jsdelivr.net/npm/maplibre-gl@5.3.0/dist/";

function stripHtmlComments(html) {
  return html.replace(/<!--[\s\S]*?-->/g, "");
}

function getAttr(attrs, name) {
  const re = new RegExp(`\\b${name}\\s*=\\s*(?:"([^"]*)"|'([^']*)')`, "i");
  const match = attrs.match(re);
  return match ? (match[1] ?? match[2] ?? "") : null;
}

// Verify every Dev A ES module loads cleanly in Node without touching DOM or maplibregl at import time.
test("test_all_dev_a_modules_import_in_node", async () => {
  assert.equal(typeof globalThis.document, "undefined");
  assert.equal(typeof globalThis.maplibregl, "undefined");

  for (const relPath of DEV_A_MODULES) {
    const modUrl = pathToFileURL(path.join(WEB_DIR, relPath)).href;
    const mod = await import(modUrl);
    assert.ok(mod && typeof mod === "object", `${relPath} must export an ES module namespace`);
  }
});

// Verify web/citizen.html loads MapLibre GL JS 5.3.0 script and CSS from jsDelivr CDN.
test("test_citizen_html_loads_maplibre_530", () => {
  const html = stripHtmlComments(
    fs.readFileSync(path.join(WEB_DIR, "citizen.html"), "utf8"),
  );

  const links = [...html.matchAll(/<link\b([^>]*)>/gi)].map((m) => m[1]);
  const hasMaplibreCss = links.some((attrs) => {
    const rel = getAttr(attrs, "rel");
    const href = getAttr(attrs, "href");
    return (
      rel?.toLowerCase() === "stylesheet" &&
      href === `${MAPLIBRE_CDN_PREFIX}maplibre-gl.css`
    );
  });
  assert.ok(
    hasMaplibreCss,
    `citizen.html must include a stylesheet link to ${MAPLIBRE_CDN_PREFIX}maplibre-gl.css`,
  );

  const scripts = [...html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/gi)];
  const hasMaplibreJs = scripts.some(
    ([, attrs]) => getAttr(attrs, "src") === `${MAPLIBRE_CDN_PREFIX}maplibre-gl.js`,
  );
  assert.ok(
    hasMaplibreJs,
    `citizen.html must include a script tag for ${MAPLIBRE_CDN_PREFIX}maplibre-gl.js`,
  );
});

// Verify web/citizen.html has exactly one <script type="module" src="js/main.js"> and no inline script logic.
test("test_citizen_html_has_single_module_entry", () => {
  const html = stripHtmlComments(
    fs.readFileSync(path.join(WEB_DIR, "citizen.html"), "utf8"),
  );

  const scripts = [...html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/gi)];

  for (const [, , body] of scripts) {
    assert.ok(
      body.trim() === "",
      "citizen.html must not contain inline script logic",
    );
  }

  const moduleScripts = scripts.filter(
    ([, attrs]) => getAttr(attrs, "type")?.toLowerCase() === "module",
  );
  assert.equal(
    moduleScripts.length,
    1,
    "citizen.html must have exactly one <script type=\"module\"> entry",
  );

  const src = getAttr(moduleScripts[0][1], "src");
  assert.ok(
    src === "js/main.js" || src === "./js/main.js",
    `module script src must be js/main.js, got ${src}`,
  );
});
