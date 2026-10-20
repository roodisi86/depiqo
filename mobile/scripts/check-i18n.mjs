#!/usr/bin/env node
// Fails (exit 1) when the locale files differ: missing or extra keys, different {placeholders},
// empty texts, keys used in the code that do not exist, or backend machine keys without a translation.
// Plain Node, no dependencies:  node scripts/check-i18n.mjs
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const LOCALES = join(ROOT, 'src', 'i18n', 'locales');
const LANGS = ['nl', 'fr', 'en'];
const BASE = 'nl';
const problems = [];

function flatten(obj, prefix = '', out = {}) {
  for (const [k, v] of Object.entries(obj)) {
    const key = prefix ? `${prefix}.${k}` : k;
    if (typeof v === 'string') out[key] = v;
    else if (v && typeof v === 'object' && !Array.isArray(v)) flatten(v, key, out);
    else problems.push(`${key}: value must be a string or an object`);
  }
  return out;
}

const dicts = {};
for (const lang of LANGS) {
  try {
    dicts[lang] = flatten(JSON.parse(readFileSync(join(LOCALES, `${lang}.json`), 'utf8')));
  } catch (e) {
    console.error(`Cannot read ${lang}.json: ${e.message}`);
    process.exit(1);
  }
}

const placeholders = (s) => [...s.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort().join(',');
const base = dicts[BASE];

for (const lang of LANGS) {
  const d = dicts[lang];
  for (const key of Object.keys(base)) {
    if (!(key in d)) problems.push(`${lang}: missing key ${key}`);
  }
  for (const key of Object.keys(d)) {
    if (!(key in base)) problems.push(`${lang}: extra key ${key} (not in ${BASE})`);
    else if (placeholders(d[key]) !== placeholders(base[key])) problems.push(`${lang}: placeholders of ${key} differ from ${BASE} ({${placeholders(d[key])}} vs {${placeholders(base[key])}})`);
    if (!d[key].trim()) problems.push(`${lang}: empty text for ${key}`);
  }
}

// Keys used literally in the code: t('a.b') and t("a.b").
function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    if (name === 'node_modules' || name.startsWith('.')) continue;
    const p = join(dir, name);
    if (statSync(p).isDirectory()) walk(p, out);
    else if (/\.(ts|tsx)$/.test(name) && !p.includes('__tests__')) out.push(p);
  }
  return out;
}
const used = new Set();
for (const dir of ['app', 'src']) {
  for (const file of walk(join(ROOT, dir))) {
    const text = readFileSync(file, 'utf8');
    for (const m of text.matchAll(/\bt\(\s*['"]([A-Za-z0-9_.]+)['"]/g)) used.add(m[1]);
  }
}
for (const key of used) {
  if (!(key in base)) problems.push(`code uses t('${key}') but ${BASE}.json has no such key`);
}

// Backend machine keys (src/i18n/machineKeys.ts): every key needs a translation.
const mk = readFileSync(join(ROOT, 'src', 'i18n', 'machineKeys.ts'), 'utf8');
let machineCount = 0;
for (const block of mk.matchAll(/^\s*(\w+):\s*\[([\s\S]*?)\]/gm)) {
  const ns = block[1];
  for (const k of block[2].matchAll(/'([^']+)'/g)) {
    machineCount += 1;
    const key = `${ns}.${k[1]}`;
    if (!(key in base) && !(`${key}.title` in base)) problems.push(`machine key ${key} has no translation in ${BASE}.json`);
  }
}

if (problems.length) {
  console.error(`i18n check FAILED (${problems.length} problems):`);
  for (const p of problems) console.error(`  - ${p}`);
  process.exit(1);
}
console.log(`i18n check OK: ${Object.keys(base).length} keys in ${LANGS.join(', ')}; ${used.size} keys used in code; ${machineCount} backend machine keys translated.`);
