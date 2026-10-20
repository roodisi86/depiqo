-- Depiqo platform, migration 005 (version 0.3.1): fixes from the review of 0.3.0.
-- Runs statement by statement; no semicolons inside strings or comments.

-- Invoices from 0.2 with nothing to pay or that were void became payment_status 'open' in 004
-- and showed as overdue. Nothing is due on them.
UPDATE invoices SET payment_status = 'none'
  WHERE kind = 'invoice' AND payment_status = 'open' AND (total_cents = 0 OR status = 'void');

-- Bank events that were refused because of timing (unknown account, payout before the release
-- instruction was recorded) may be processed again when the bank retries or staff asks for it.
ALTER TABLE bank_events ADD COLUMN retryable INTEGER NOT NULL DEFAULT 0;
UPDATE bank_events SET retryable = 1 WHERE error IN ('onbekende rekening', 'uitbetaling zonder vrijgave-opdracht');

-- Per session: when the second factor was passed. Staff pages require it when REQUIRE_2FA_FOR_STAFF is on.
ALTER TABLE sessions ADD COLUMN mfa_at TEXT
