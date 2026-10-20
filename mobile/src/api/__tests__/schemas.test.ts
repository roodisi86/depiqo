/**
 * The zod schemas against real responses captured from the Depiqo dev server (fixtures/, see
 * scripts/capture-fixtures.mjs). Every fixture must have a schema here and must parse.
 */
import { readFileSync } from 'fs';
import { join } from 'path';
import type { ZodTypeAny } from 'zod';

import * as S from '../schemas';

const DIR = join(__dirname, '..', '..', '..', 'fixtures');

interface ManifestItem {
  file: string;
  method: string;
  path: string;
  status: number;
}

const manifest = JSON.parse(readFileSync(join(DIR, '_manifest.json'), 'utf8')) as { items: ManifestItem[] };
const load = (file: string): unknown => JSON.parse(readFileSync(join(DIR, file), 'utf8'));

/** Which schema validates which fixture (by file name). */
function schemaFor(file: string): ZodTypeAny | null {
  const name = file.replace(/\.json$/, '');
  if (name.startsWith('error-')) return S.ErrorBodySchema;
  const exact: Record<string, ZodTypeAny> = {
    config: S.ConfigSchema,
    invite: S.InviteSchema,
    'login-session': S.LoginResponseSchema,
    'refresh-token-pair': S.TokenPairSchema,
    'invest-portfolios': S.PortfoliosSchema,
    'invest-deposit-instructions': S.DepositInstructionsSchema,
    'invest-orders': S.OrdersPageSchema,
    'invest-withdrawals': S.WithdrawalsPageSchema,
    'invest-transactions': S.InvestTransactionsPageSchema,
    'invest-statements': S.StatementsSchema,
    'invest-fee-change': S.FeeChangeSchema,
    'invest-mila': S.InvestOverviewSchema,
    'payout-choice': S.PayoutChoiceSchema,
  };
  if (exact[name]) return exact[name] as ZodTypeAny;
  const prefixes: [string, ZodTypeAny][] = [
    ['me-', S.MeSchema],
    ['deposits-', S.DepositsPageSchema],
    ['deposit-events-', S.DepositEventsPageSchema],
    ['deposit-', S.DepositDetailSchema],
    ['documents-', S.DocumentsSchema],
    ['settlement-', S.SettlementResponseSchema],
    ['invest-overview-', S.InvestOverviewSchema],
    ['invest-appropriateness-', S.AppropriatenessQuestionsSchema],
    ['invest-terms-', S.TermsSchema],
    ['invest-quote-', S.QuoteSchema],
    ['activity-', S.ActivityPageSchema],
    ['notifications-', S.NotificationsPageSchema],
    ['support-', S.SupportPageSchema],
    ['devices-', S.DevicesSchema],
    ['delete-request-', S.DeletionInfoSchema],
  ];
  for (const [p, schema] of prefixes) if (name.startsWith(p)) return schema;
  return null;
}

describe('fixtures from the live dev server', () => {
  it('has fixtures to test', () => {
    expect(manifest.items.length).toBeGreaterThan(30);
  });

  for (const item of manifest.items) {
    it(`${item.file} (${item.method} ${item.path} -> ${item.status}) matches its schema`, () => {
      const schema = schemaFor(item.file);
      expect(schema).not.toBeNull();
      const result = (schema as ZodTypeAny).safeParse(load(item.file));
      if (!result.success) {
        // Show the zod issues in the test output (paths only, no values).
        throw new Error(`${item.file}: ${result.error.issues.map((i) => `${i.path.join('.')}: ${i.message}`).join('; ')}`);
      }
    });
  }
});

describe('contract details that matter for money', () => {
  const depositFixtures = manifest.items.map((i) => i.file).filter((f) => /^deposit-(?!events)/.test(f));

  it('never sends an amount that is unknown as a number: value null <=> known false', () => {
    for (const file of depositFixtures) {
      const d = S.DepositDetailSchema.parse(load(file));
      for (const a of d.amounts) {
        expect(a.value === null).toBe(!a.known);
      }
      expect(d.amounts.map((a) => a.key)).toEqual(['obligation', 'received', 'locked', 'interest']);
    }
  });

  it('shows a guarantee as "nothing received", not as the required amount', () => {
    const d = S.DepositDetailSchema.parse(load('deposit-guarantee.json'));
    const received = d.amounts.find((a) => a.key === 'received');
    expect(received?.value).toBeNull();
    expect(received?.explanation_key).toBe('guarantee_no_money');
    expect(d.location.guarantee?.kind).toBe('borggarantie');
  });

  it('refuses money in another currency', () => {
    const d = load('deposit-guarantee.json') as { amounts: { value: { currency: string } | null }[] };
    const bad = JSON.parse(JSON.stringify(d)) as typeof d;
    const first = bad.amounts[0];
    if (first?.value) first.value.currency = 'USD';
    expect(S.DepositDetailSchema.safeParse(bad).success).toBe(false);
  });

  it('parses a login without 2FA as a session, and an MFA challenge as a challenge', () => {
    const session = S.LoginResponseSchema.parse(load('login-session.json'));
    expect('access_token' in session).toBe(true);
    const challenge = S.LoginResponseSchema.parse({ mfa_required: true, mfa_token: 'x'.repeat(20), mfa_expires_at: '2026-10-20T12:00:00+00:00', message: 'Vul de code in' });
    expect(challenge.mfa_required).toBe(true);
  });

  it('keeps the quote risk acknowledgement mandatory', () => {
    const q = load('invest-quote-buy.json') as Record<string, unknown>;
    expect(S.QuoteSchema.safeParse({ ...q, requires_risk_acknowledgement: false }).success).toBe(false);
  });

  it('never stores tokens in fixtures', () => {
    const text = readFileSync(join(DIR, 'login-session.json'), 'utf8') + readFileSync(join(DIR, 'refresh-token-pair.json'), 'utf8');
    expect(text).toContain('REDACTED_ACCESS_TOKEN');
    expect(text).toContain('REDACTED_REFRESH_TOKEN');
  });
});
