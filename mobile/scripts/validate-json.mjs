#!/usr/bin/env node
// Fails (exit 1) when a .json file in the project is not valid JSON, or when the fixture manifest
// points to a file that does not exist. Plain Node:  node scripts/validate-json.mjs
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const SKIP = new Set(['node_modules', '.expo', '.git', 'dist', 'ios', 'android', 'coverage']);
const files = [];
(function walk(dir) {
  for (const name of readdirSync(dir)) {
    if (SKIP.has(name)) continue;
    const p = join(dir, name);
    if (statSync(p).isDirectory()) walk(p);
    else if (name.endsWith('.json')) files.push(p);
  }
})(ROOT);

const problems = [];
for (const f of files) {
  try {
    JSON.parse(readFileSync(f, 'utf8'));
  } catch (e) {
    problems.push(`${relative(ROOT, f)}: ${e.message}`);
  }
}

const manifestPath = join(ROOT, 'fixtures', '_manifest.json');
if (existsSync(manifestPath)) {
  const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'));
  for (const item of manifest.items ?? []) {
    if (!existsSync(join(ROOT, 'fixtures', item.file))) problems.push(`fixtures/_manifest.json lists missing file ${item.file}`);
  }
  // Fixtures must never contain real tokens.
  for (const item of manifest.items ?? []) {
    const text = readFileSync(join(ROOT, 'fixtures', item.file), 'utf8');
    for (const key of ['access_token', 'refresh_token', 'mfa_token']) {
      const m = text.match(new RegExp(`"${key}"\\s*:\\s*"([^"]*)"`));
      if (m && !m[1].startsWith('REDACTED_')) problems.push(`fixtures/${item.file} contains an unredacted ${key}`);
    }
  }
}

if (problems.length) {
  console.error(`JSON check FAILED:\n  - ${problems.join('\n  - ')}`);
  process.exit(1);
}
console.log(`JSON check OK: ${files.length} files valid.`);
