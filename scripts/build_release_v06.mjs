/**
 * Build the EcoSim V0.6 single-file HTML release.
 *
 * Packaging only: the economic logic lives in the ES modules under
 * web/release/src. This zero-dependency Node script bundles those modules
 * (restricted import/export style), inlines CSS and the Python golden-oracle
 * data, and writes one HTML file that runs from file:// with no network,
 * CDN, external fonts/images or Python runtime.
 *
 * Usage:
 *   node scripts/build_release_v06.mjs
 *   node scripts/build_release_v06.mjs --check
 */
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const SRC = path.join(ROOT, "web", "release", "src");
const TEMPLATE = path.join(ROOT, "web", "release", "release.template.html");
const OUT = path.join(ROOT, "web", "release", "ecosim-v06.html");
const ENTRY = path.join(SRC, "60-ui.js");
const GOLDEN = path.join(SRC, "golden_v06.json");
const CHECK_ONLY = process.argv.includes("--check");
const readText = (file) => fs.readFileSync(file, "utf8").replace(/\r\n/g, "\n");

const IMPORT_RE = /import\s*\{([\s\S]*?)\}\s*from\s*["']([^"']+)["']\s*;?/gm;
const EXPORT_RE = /export\s*\{([\s\S]*?)\}\s*;?/gm;

function parseNames(raw) {
  return raw.split(",").map((item) => item.trim()).filter(Boolean).map((item) => {
    const match = /^([A-Za-z_$][\w$]*)(?:\s+as\s+([A-Za-z_$][\w$]*))?$/.exec(item);
    if (!match) throw new Error(`unsupported import/export item: ${item}`);
    return { exported: match[1], local: match[2] || match[1] };
  });
}
function moduleKey(file) {
  return path.relative(SRC, file).split(path.sep).join("/");
}
function loadModule(file, seen) {
  const key = moduleKey(file);
  if (seen.has(key)) return;
  const text = readText(file);
  const imports = [];
  IMPORT_RE.lastIndex = 0;
  let match;
  while ((match = IMPORT_RE.exec(text)) !== null) {
    const spec = match[2];
    if (!spec.startsWith(".")) throw new Error(`${key}: only relative imports are supported (${spec})`);
    const depPath = path.resolve(path.dirname(file), spec);
    imports.push({ names: parseNames(match[1]), dep: moduleKey(depPath), depPath });
  }
  const exports = [];
  EXPORT_RE.lastIndex = 0;
  while ((match = EXPORT_RE.exec(text)) !== null) exports.push(...parseNames(match[1]));
  const cleaned = text.replace(IMPORT_RE, "").replace(EXPORT_RE, "");
  if (/^\s*(import|export)\s/m.test(cleaned)) throw new Error(`${key}: unhandled import/export statement`);
  seen.set(key, { key, file, imports, exports, code: cleaned });
  for (const item of imports) loadModule(item.depPath, seen);
}
function bundle(entry) {
  const modules = new Map();
  loadModule(entry, modules);
  const visited = new Set();
  const ordered = [];
  const visit = (key) => {
    if (visited.has(key)) return;
    visited.add(key);
    for (const item of modules.get(key).imports) visit(item.dep);
    ordered.push(modules.get(key));
  };
  visit(moduleKey(entry));
  for (const module of ordered) {
    for (const item of module.imports) {
      const dep = modules.get(item.dep);
      const available = new Set(dep.exports.map((entry) => entry.exported));
      for (const { exported } of item.names) {
        if (!available.has(exported)) {
          throw new Error(`${module.key}: import ${exported} not exported by ${item.dep}`);
        }
      }
    }
  }
  const chunks = [];
  for (const module of ordered) {
    const lines = [`__modules[${JSON.stringify(module.key)}] = (function () {`];
    for (const item of module.imports) {
      const bindings = item.names.map(({ exported, local }) =>
        exported === local ? exported : `${exported}: ${local}`).join(", ");
      lines.push(`  const { ${bindings} } = __modules[${JSON.stringify(item.dep)}];`);
    }
    lines.push(module.code.trimEnd());
    const exportBindings = module.exports.map(({ exported, local }) =>
      exported === local ? exported : `${exported}: ${local}`).join(", ");
    lines.push(`  return { ${exportBindings} };`);
    lines.push("})();");
    chunks.push(lines.join("\n"));
  }
  const code = "(function () {\n\"use strict\";\nconst __modules = Object.create(null);\n" +
    chunks.join("\n") + "\n})();\n";
  return { code, stats: { moduleCount: ordered.length, jsBytes: Buffer.byteLength(code) } };
}
function main() {
  const { code: js, stats } = bundle(ENTRY);
  const css = readText(path.join(SRC, "styles.css"));
  const golden = readText(GOLDEN).replaceAll("</", "<\\/");
  let template = readText(TEMPLATE);
  for (const [marker, replacement] of [
    ["/*__STYLES__*/", css],
    ["/*__GOLDEN__*/", golden],
    ["/*__BUNDLE__*/", js],
  ]) {
    if (!template.includes(marker)) throw new Error(`template marker missing: ${marker}`);
    template = template.replace(marker, replacement);
  }
  if (/(src|href)\s*=\s*["']https?:\/\//i.test(template)) throw new Error("release still contains an external http(s) asset");
  if (/<link\b[^>]*href=/i.test(template)) throw new Error("release still contains a <link> asset");
  if (/@import/.test(css)) throw new Error("CSS still contains @import");
  if (/<script\b[^>]*src=/i.test(template)) throw new Error("release still contains an external script");
  if (!CHECK_ONLY) fs.writeFileSync(OUT, template, "utf8");
  const digest = crypto.createHash("sha256").update(template, "utf8").digest("hex").slice(0, 16);
  console.log(
    `bundled ${stats.moduleCount} modules · JS ${(stats.jsBytes / 1024).toFixed(1)} KiB · ` +
    `CSS ${(Buffer.byteLength(css) / 1024).toFixed(1)} KiB · golden ${(Buffer.byteLength(golden) / 1024).toFixed(1)} KiB`,
  );
  console.log(
    `release ${(Buffer.byteLength(template) / 1024).toFixed(1)} KiB · sha256:${digest} · ` +
    `${CHECK_ONLY ? "(check only)" : OUT}`,
  );
}
try {
  main();
} catch (error) {
  console.error(`build failed: ${error.message}`);
  process.exitCode = 1;
}
