import { errorFromBody } from '../../api/errors';
import { boundsOf, linePath } from '../chart';
import { formatDate, formatPeriod, isValidIsoDate, normalizeBirthDate } from '../format';
import { formatIban, isValidIban, normalizeIban } from '../iban';
import { formatBps, formatPercent, parseAmountToCents } from '../money';
import { redact } from '../redact';
import { compareVersions, isBelowMinimum } from '../version';

const AMOUNT_CASES: [string, number][] = [
  ['25', 2500],
  ['25,5', 2550],
  ['25.50', 2550],
  ['1.234,56', 123456],
  ['1,234.56', 123456],
  ['€ 1 234,56', 123456],
  ['1.000', 100000],
  ['0,05', 5],
];

describe('amount input', () => {
  it.each(AMOUNT_CASES)('reads %s as %d cents', (input, cents) => {
    expect(parseAmountToCents(input)).toBe(cents);
  });

  it.each(['', 'abc', '-5', '1,234,5', '1.2.3,4.5', '12,34.56', '1.234,5,6', '25,5.5'])('rejects %s', (input) => {
    expect(parseAmountToCents(input)).toBeNull();
  });

  it('reads a single separator followed by three digits as thousands grouping', () => {
    // The confirmation dialogs always show the formatted amount before anything is sent.
    expect(parseAmountToCents('12,345')).toBe(1234500);
  });
});

describe('percentages', () => {
  it('formats basis points and percentages', () => {
    expect(formatBps(25, 'nl')).toBe('0,25%');
    expect(formatBps(25, 'en')).toBe('0.25%');
    expect(formatBps(25, 'fr')).toBe('0,25\u00A0%');
    expect(formatPercent(0.4425, 'en')).toBe('0.44%');
    expect(formatPercent(null, 'en')).toBe('—');
  });
});

describe('dates', () => {
  it('formats date-only values without time zone shifts', () => {
    expect(formatDate('2026-10-20', 'nl')).toBe('20 okt. 2026');
    expect(formatDate('2026-01-01', 'en')).toBe('1 Jan 2026');
    expect(formatPeriod('2026-10', 'fr')).toBe('octobre 2026');
    expect(formatDate(null, 'nl')).toBe('—');
  });

  it('validates and normalises birth dates', () => {
    expect(normalizeBirthDate('31-12-1990')).toBe('1990-12-31');
    expect(normalizeBirthDate('1/2/1985')).toBe('1985-02-01');
    expect(normalizeBirthDate('1990-12-31')).toBe('1990-12-31');
    expect(normalizeBirthDate('31-02-1990')).toBeNull();
    expect(isValidIsoDate('2024-02-29')).toBe(true);
    expect(isValidIsoDate('2023-02-29')).toBe(false);
  });
});

describe('IBAN', () => {
  it('checks the mod-97 checksum', () => {
    expect(isValidIban('NL91 ABNA 0417 1643 00')).toBe(true);
    expect(isValidIban('BE68 5390 0754 7034')).toBe(true);
    expect(isValidIban('NL91 ABNA 0417 1643 01')).toBe(false);
    expect(isValidIban('hello')).toBe(false);
    expect(normalizeIban('nl91 abna-0417 1643 00')).toBe('NL91ABNA0417164300');
    expect(formatIban('NL91ABNA0417164300')).toBe('NL91 ABNA 0417 1643 00');
  });
});

describe('versions', () => {
  it('compares like the backend', () => {
    expect(compareVersions('1.0.0', '1.0.1')).toBe(-1);
    expect(compareVersions('1.10.0', '1.9.9')).toBe(1);
    expect(compareVersions('1.0', '1.0.0')).toBe(0);
    expect(isBelowMinimum('1.0.0', '1.0.0')).toBe(false);
    expect(isBelowMinimum('1.0.0', '1.2.0')).toBe(true);
    expect(isBelowMinimum('1.0.0', null)).toBe(false);
  });
});

describe('redaction for logs', () => {
  it('removes tokens, e-mail addresses and IBANs', () => {
    const out = JSON.stringify(
      redact({ access_token: 'abc', nested: { refresh_token: 'def', note: 'mail daan@huurder.test, iban NL91ABNA0417164300, Bearer xyz.123' }, count: 3 }),
    );
    expect(out).not.toContain('abc');
    expect(out).not.toContain('def');
    expect(out).not.toContain('daan@huurder.test');
    expect(out).not.toContain('NL91ABNA0417164300');
    expect(out).not.toContain('xyz.123');
    expect(out).toContain('"count":3');
  });
});

describe('chart geometry', () => {
  it('draws a path across the full width', () => {
    const pts = [['2026-01-01', 100], ['2026-01-02', 200], ['2026-01-03', 150]] as const;
    const b = boundsOf(pts);
    expect(b).toEqual({ min: 100, max: 200 });
    const d = linePath(pts, 100, 50, b as { min: number; max: number }, 0);
    expect(d.startsWith('M0.0 50.0')).toBe(true);
    expect(d).toContain('L100.0 25.0');
    expect(boundsOf([])).toBeNull();
  });
});

describe('errorFromBody', () => {
  it('never throws on garbage', () => {
    expect(errorFromBody(500, 'not json').code).toBe('server_error');
    expect(errorFromBody(404, '{"error": 5}').code).toBe('not_found');
    expect(errorFromBody(422, '{"error":{"code":"weak_password","message":"m","fields":[]}}').fields).toEqual({});
  });
});
