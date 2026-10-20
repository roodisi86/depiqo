#!/usr/bin/env node
/**
 * Prints the Maestro environment for one language, one KEY=VALUE per line (used by .maestro/run-suite.sh).
 *
 *   node scripts/maestro-env.mjs nl|fr|en
 *
 * The values come from the real locale files, so the flows assert exactly the text the app shows. Maestro treats
 * `text:` selectors as regular expressions, so every value is regex-escaped. T_* is the run language; L_<LANG>_*
 * are fixed languages for the language-switch flow.
 */
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const LANGS = ['nl', 'fr', 'en'];
const lang = process.argv[2];
if (!LANGS.includes(lang)) {
  console.error(`usage: maestro-env.mjs ${LANGS.join('|')}`);
  process.exit(2);
}

const locales = Object.fromEntries(LANGS.map((l) => [l, JSON.parse(readFileSync(join(root, 'src', 'i18n', 'locales', `${l}.json`), 'utf8'))]));

function get(l, key) {
  let cur = locales[l];
  for (const part of key.split('.')) {
    if (cur === null || typeof cur !== 'object' || !(part in cur)) {
      console.error(`maestro-env: missing key ${key} in ${l}.json`);
      process.exit(1);
    }
    cur = cur[part];
  }
  if (typeof cur !== 'string' || !cur) {
    console.error(`maestro-env: ${key} in ${l}.json is not a non-empty string`);
    process.exit(1);
  }
  if (/[{}]/.test(cur)) {
    console.error(`maestro-env: ${key} has placeholders; flows cannot match it literally`);
    process.exit(1);
  }
  return cur;
}

const escape = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

// Keys the flows use for the run language.
const RUN_KEYS = {
  T_ERR_INVALID_CREDENTIALS: 'errors.invalid_credentials',
  T_AMOUNT_OBLIGATION: 'amount.obligation',
  T_AMOUNT_RECEIVED: 'amount.received',
  T_AMOUNT_LOCKED: 'amount.locked',
  T_AMOUNT_INTEREST: 'amount.interest',
  T_AMOUNT_UNKNOWN: 'amount.unknownA11y',
  T_PROFILE_LOGOUT: 'profile.logout',
  T_PROFILE_LANGUAGE: 'profile.language',
  T_SETTLEMENT_LINES: 'settlement.lines',
  T_SETTLEMENT_AGREE: 'settlement.agree',
  T_SETTLEMENT_DISPUTE: 'settlement.dispute',
  T_MFA_TITLE: 'mfa.title',
  T_ENV_SANDBOX: 'env.banner.SANDBOX',
  T_DEPOSITS_INTRO: 'deposits.intro',
  T_TAB_DEPOSITS: 'tabs.deposits',
};
// Keys every run needs in all three languages (language switch flow).
const ALL_LANG_KEYS = {
  PROFILE_LANGUAGE: 'profile.language',
  TAB_DEPOSITS: 'tabs.deposits',
  AMOUNT_RECEIVED: 'amount.received',
};

const lines = [`LANG_CODE=${lang}`];
for (const [name, key] of Object.entries(RUN_KEYS)) lines.push(`${name}=${escape(get(lang, key))}`);
for (const l of LANGS) {
  for (const [name, key] of Object.entries(ALL_LANG_KEYS)) lines.push(`L_${l.toUpperCase()}_${name}=${escape(get(l, key))}`);
}
for (const line of lines) {
  if (/[\r\n]/.test(line)) {
    console.error(`maestro-env: newline in ${line.split('=')[0]}`);
    process.exit(1);
  }
}
process.stdout.write(lines.join('\n') + '\n');
