-- Depiqo platform, migration 008 (version 0.5.2): fixes from the review of Depiqo Invest 0.5.0.
-- Runs statement by statement. No semicolons inside strings or comments.

-- The service fee agreed with the terms, per account. A staff change is only a proposal for an existing
-- account (pending_fee_bps) until the tenant accepts it. Remainders that could not be charged carry over.
ALTER TABLE invest_accounts ADD COLUMN fee_rate_bps INTEGER;
ALTER TABLE invest_accounts ADD COLUMN fee_rate_accepted_at TEXT;
ALTER TABLE invest_accounts ADD COLUMN pending_fee_bps INTEGER;
ALTER TABLE invest_accounts ADD COLUMN pending_fee_notified_at TEXT;
ALTER TABLE invest_accounts ADD COLUMN fee_carry_cents INTEGER NOT NULL DEFAULT 0;
UPDATE invest_accounts SET fee_rate_bps = COALESCE((SELECT CAST(value AS INTEGER) FROM staff_settings WHERE key = 'invest_fee_bps'), 25),
  fee_rate_accepted_at = terms_depiqo_at WHERE status != 'draft';

-- A portfolio switch in progress: the target, until the sale executed and the new purchase was placed.
ALTER TABLE invest_accounts ADD COLUMN pending_switch TEXT CHECK (pending_switch IN ('defensief', 'neutraal', 'offensief'));
ALTER TABLE invest_accounts ADD COLUMN switch_note TEXT;

-- Withdrawals only to the tenant's own registered account. Usable at once after a fresh 2FA code,
-- otherwise after a cooling-off period. The partner checks the account holder name.
ALTER TABLE invest_accounts ADD COLUMN own_iban TEXT;
ALTER TABLE invest_accounts ADD COLUMN own_iban_registered_at TEXT;
ALTER TABLE invest_accounts ADD COLUMN own_iban_usable_from TEXT;
ALTER TABLE invest_accounts ADD COLUMN own_iban_holder TEXT;

-- Events refused for a timing reason (account or instruction not known yet) are processed again on resend.
ALTER TABLE invest_events ADD COLUMN retryable INTEGER NOT NULL DEFAULT 0;

-- Doorbeleggen: two more outcomes. 'fallback' = Invest was not available when the payout started, the tenant's
-- share went to their own account. 'unrecorded' = the bank paid the partner but the investment side could not
-- record it yet (visible to Depiqo staff until it is). SQLite cannot change a CHECK, so the table is rebuilt.
CREATE TABLE invest_payout_choices_new (
  id INTEGER PRIMARY KEY,
  deposit_id INTEGER NOT NULL UNIQUE REFERENCES deposits(id),
  account_id INTEGER NOT NULL REFERENCES invest_accounts(id),
  user_id INTEGER NOT NULL REFERENCES users(id),
  destination_iban TEXT NOT NULL,
  reference TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('chosen', 'cancelled', 'fallback', 'paid', 'unrecorded')),
  chosen_at TEXT NOT NULL,
  cancelled_at TEXT,
  paid_cents INTEGER,
  paid_at TEXT,
  note TEXT
);
INSERT INTO invest_payout_choices_new (id, deposit_id, account_id, user_id, destination_iban, reference, status, chosen_at, cancelled_at, paid_cents, paid_at)
  SELECT id, deposit_id, account_id, user_id, destination_iban, reference, status, chosen_at, cancelled_at, paid_cents, paid_at FROM invest_payout_choices;
DROP TABLE invest_payout_choices;
ALTER TABLE invest_payout_choices_new RENAME TO invest_payout_choices
