-- Depiqo platform, migration 007 (version 0.5.0): Depiqo Invest.
-- Tenants invest their own money at a licensed investment partner. Nothing here refers to a deposit
-- as collateral: the only link to a deposit is the tenant's explicit choice to send their share of
-- a release to their own investment account (invest_payout_choices).
-- Accounts belong to a person (users.id), never to an organisation, so no organisation query can
-- reach them. Runs statement by statement. No semicolons inside strings or comments.

-- Per organisation: may its tenants see Invest in Depiqo Wallet (set by Depiqo staff).
ALTER TABLE organizations ADD COLUMN invest_enabled INTEGER NOT NULL DEFAULT 0;

-- Knowledge and experience test (appropriateness). The partner owns the assessment; Depiqo stores
-- what was answered, the outcome and, for a negative outcome, the explicit confirmation.
CREATE TABLE invest_appropriateness (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id),
  provider TEXT NOT NULL,
  questionnaire_version TEXT NOT NULL,
  answers_json TEXT NOT NULL,
  score INTEGER NOT NULL,
  result TEXT NOT NULL CHECK (result IN ('passend', 'niet_passend')),
  reasons_json TEXT NOT NULL,
  warning_confirmed_at TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX idx_invest_appr_user ON invest_appropriateness (user_id, id);

CREATE TABLE invest_accounts (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL UNIQUE REFERENCES users(id),
  provider TEXT NOT NULL,
  external_id TEXT,
  reference TEXT NOT NULL UNIQUE,
  status TEXT NOT NULL CHECK (status IN ('draft', 'pending', 'active', 'closed')),
  portfolio TEXT CHECK (portfolio IN ('defensief', 'neutraal', 'offensief')),
  appropriateness_id INTEGER REFERENCES invest_appropriateness(id),
  terms_partner_version TEXT,
  terms_partner_at TEXT,
  terms_depiqo_version TEXT,
  terms_depiqo_at TEXT,
  fee_accrued_micro INTEGER NOT NULL DEFAULT 0,
  fee_accrued_through TEXT,
  withdraw_iban TEXT,
  created_at TEXT NOT NULL,
  opened_at TEXT,
  activated_at TEXT,
  activated_day TEXT
);

CREATE TABLE invest_orders (
  id INTEGER PRIMARY KEY,
  account_id INTEGER NOT NULL REFERENCES invest_accounts(id),
  side TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
  portfolio TEXT NOT NULL,
  amount_cents INTEGER NOT NULL CHECK (amount_cents >= 0),
  sell_all INTEGER NOT NULL DEFAULT 0,
  purpose TEXT NOT NULL DEFAULT 'order' CHECK (purpose IN ('order', 'switch_sell', 'switch_buy')),
  switch_to TEXT,
  status TEXT NOT NULL CHECK (status IN ('pending', 'executed', 'failed')),
  executed_amount_cents INTEGER,
  error TEXT,
  created_day TEXT NOT NULL,
  executed_day TEXT,
  created_at TEXT NOT NULL,
  executed_at TEXT
);
CREATE INDEX idx_invest_orders_account ON invest_orders (account_id, id);

-- What changes units. units_1e4 is units times 10000 (4 decimals), signed: negative for a sale.
-- price_1e4 is the price in euro times 10000.
CREATE TABLE invest_fills (
  id INTEGER PRIMARY KEY,
  account_id INTEGER NOT NULL REFERENCES invest_accounts(id),
  order_id INTEGER REFERENCES invest_orders(id),
  kind TEXT NOT NULL CHECK (kind IN ('buy', 'sell', 'fee_sell')),
  fund TEXT NOT NULL,
  units_1e4 INTEGER NOT NULL,
  price_1e4 INTEGER NOT NULL,
  amount_cents INTEGER NOT NULL,
  day TEXT NOT NULL,
  external_ref TEXT NOT NULL,
  UNIQUE (account_id, external_ref, fund)
);
CREATE INDEX idx_invest_fills_account ON invest_fills (account_id, day);

-- Cash movements on the investment account, signed (positive adds cash). Cash = SUM(amount_cents).
CREATE TABLE invest_transactions (
  id INTEGER PRIMARY KEY,
  account_id INTEGER NOT NULL REFERENCES invest_accounts(id),
  kind TEXT NOT NULL CHECK (kind IN ('deposit', 'payout_in', 'withdrawal', 'buy', 'sell', 'fee')),
  amount_cents INTEGER NOT NULL,
  description TEXT NOT NULL,
  day TEXT NOT NULL,
  external_ref TEXT NOT NULL,
  order_id INTEGER REFERENCES invest_orders(id),
  at TEXT NOT NULL,
  UNIQUE (account_id, external_ref)
);
CREATE INDEX idx_invest_tx_account ON invest_transactions (account_id, day);

-- Outbox for instructions to the investment partner. Same pattern as bank_instructions, separate
-- table: another partner, other kinds, another dispatcher. See ARCHITECTUUR.md.
CREATE TABLE invest_instructions (
  id INTEGER PRIMARY KEY,
  account_id INTEGER NOT NULL REFERENCES invest_accounts(id),
  provider TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('open', 'order', 'withdraw', 'fee')),
  order_id INTEGER REFERENCES invest_orders(id),
  idempotency_key TEXT NOT NULL UNIQUE,
  payload_json TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('pending', 'sent', 'acknowledged', 'failed', 'confirmed')),
  attempts INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  created_at TEXT NOT NULL,
  created_day TEXT NOT NULL,
  sent_at TEXT,
  confirmed_at TEXT,
  provider_ref TEXT
);
CREATE INDEX idx_invest_instr_status ON invest_instructions (status, created_at);
CREATE INDEX idx_invest_instr_account ON invest_instructions (account_id);

CREATE TABLE invest_events (
  id INTEGER PRIMARY KEY,
  provider TEXT NOT NULL,
  external_event_id TEXT NOT NULL,
  type TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  received_at TEXT NOT NULL,
  processed_at TEXT,
  error TEXT,
  UNIQUE (provider, external_event_id)
);

-- The tenant's explicit choice to receive their share of a deposit release on their investment account.
CREATE TABLE invest_payout_choices (
  id INTEGER PRIMARY KEY,
  deposit_id INTEGER NOT NULL UNIQUE REFERENCES deposits(id),
  account_id INTEGER NOT NULL REFERENCES invest_accounts(id),
  user_id INTEGER NOT NULL REFERENCES users(id),
  destination_iban TEXT NOT NULL,
  reference TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('chosen', 'cancelled', 'paid')),
  chosen_at TEXT NOT NULL,
  cancelled_at TEXT,
  paid_cents INTEGER,
  paid_at TEXT
);

-- Sandbox only: the simulated partner's clock (days ahead of the real date) and its account state.
CREATE TABLE invest_sandbox_clock (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  offset_days INTEGER NOT NULL DEFAULT 0
);
INSERT INTO invest_sandbox_clock (id, offset_days) VALUES (1, 0)
