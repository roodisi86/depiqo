-- Depiqo platform, migration 004 (version 0.3.0).
-- Evidence levels for deposits held elsewhere, a transactional outbox for bank instructions,
-- plan history, invoice payment status and credit notes, staff settings, two-factor
-- authentication, CSV import batches and mail per dossier.
-- Runs statement by statement; no semicolons inside strings or comments.

-- ---------------------------------------------------------------- evidence levels
-- Only for holding = 'external'. NULL until the receipt is declared.
--   declared  verklaard door beheerder
--   document  bankdocument ontvangen (an uploaded document of kind 'bankbewijs')
--   verified  extern geverifieerd door Depiqo (staff only, with a note)
--   legal     juridische zekerheid bevestigd (staff only, with a document)
ALTER TABLE deposits ADD COLUMN evidence_level TEXT CHECK (evidence_level IN ('declared', 'document', 'verified', 'legal'));
ALTER TABLE deposits ADD COLUMN evidence_set_at TEXT;
ALTER TABLE deposits ADD COLUMN import_batch_id INTEGER;

CREATE TABLE deposit_evidence (
  id INTEGER PRIMARY KEY,
  deposit_id INTEGER NOT NULL REFERENCES deposits(id),
  org_id INTEGER NOT NULL REFERENCES organizations(id),
  level TEXT NOT NULL CHECK (level IN ('declared', 'document', 'verified', 'legal')),
  note TEXT,
  document_id INTEGER REFERENCES documents(id),
  set_by INTEGER REFERENCES users(id),
  set_by_staff INTEGER NOT NULL DEFAULT 0,
  at TEXT NOT NULL
);
CREATE INDEX idx_deposit_evidence_deposit ON deposit_evidence (deposit_id, id);

-- Backfill: until 0.3.0 one click by a finance user marked an external deposit as fully covered.
-- That click is a declaration by the manager and nothing more.
UPDATE deposits SET evidence_level = 'declared', evidence_set_at = COALESCE(secured_at, updated_at)
  WHERE holding = 'external' AND secured_at IS NOT NULL;
UPDATE deposits SET eligible_value_cents = NULL
  WHERE holding = 'external' AND evidence_level = 'declared' AND status NOT IN ('closed', 'cancelled');
INSERT INTO deposit_evidence (deposit_id, org_id, level, note, at)
  SELECT id, org_id, 'declared', 'Overgenomen uit versie 0.2: ontvangst bevestigd door een medewerker van de beheerder', evidence_set_at
  FROM deposits WHERE evidence_level = 'declared';

-- ---------------------------------------------------------------- bank instruction outbox
-- Written in the same transaction as the state change. A dispatcher sends pending rows to the
-- partner with the idempotency key and records the answer.
CREATE TABLE bank_instructions (
  id INTEGER PRIMARY KEY,
  deposit_id INTEGER NOT NULL REFERENCES deposits(id),
  bank_account_id INTEGER REFERENCES bank_accounts(id),
  provider TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('open', 'block', 'release')),
  idempotency_key TEXT NOT NULL UNIQUE,
  payload_json TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('pending', 'sent', 'acknowledged', 'failed', 'confirmed')),
  attempts INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  created_at TEXT NOT NULL,
  sent_at TEXT,
  confirmed_at TEXT,
  provider_ref TEXT
);
CREATE INDEX idx_bank_instructions_status ON bank_instructions (status, created_at);
CREATE INDEX idx_bank_instructions_deposit ON bank_instructions (deposit_id);

-- Backfill: payouts already at the bank get an acknowledged release instruction with the amounts
-- recorded in the audit trail, so the payout confirmation can be checked against it.
INSERT INTO bank_instructions (deposit_id, bank_account_id, provider, kind, idempotency_key, payload_json, status, attempts, created_at, sent_at)
  SELECT b.deposit_id, b.id, b.provider, 'release', 'release:' || b.id,
    json_object(
      'tenant_cents', (SELECT json_extract(e.data_json, '$.huurder') FROM deposit_events e WHERE e.deposit_id = b.deposit_id AND e.to_status = 'payout_pending' ORDER BY e.id DESC LIMIT 1),
      'landlord_cents', (SELECT json_extract(e.data_json, '$.verhuurder') FROM deposit_events e WHERE e.deposit_id = b.deposit_id AND e.to_status = 'payout_pending' ORDER BY e.id DESC LIMIT 1),
      'reference', (SELECT d.reference FROM deposits d WHERE d.id = b.deposit_id)),
    'acknowledged', 1, datetime('now'), datetime('now')
  FROM bank_accounts b WHERE b.status = 'release_requested';

-- Sandbox side: what the simulated bank was asked to pay out, and idempotent request memory.
ALTER TABLE sandbox_bank_accounts ADD COLUMN release_tenant_cents INTEGER;
ALTER TABLE sandbox_bank_accounts ADD COLUMN release_landlord_cents INTEGER;
UPDATE sandbox_bank_accounts SET
  release_tenant_cents = (SELECT json_extract(i.payload_json, '$.tenant_cents') FROM bank_instructions i JOIN bank_accounts b ON b.id = i.bank_account_id
                          WHERE b.external_id = sandbox_bank_accounts.external_id AND i.kind = 'release'),
  release_landlord_cents = (SELECT json_extract(i.payload_json, '$.landlord_cents') FROM bank_instructions i JOIN bank_accounts b ON b.id = i.bank_account_id
                            WHERE b.external_id = sandbox_bank_accounts.external_id AND i.kind = 'release');
CREATE TABLE sandbox_requests (
  idempotency_key TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  response_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

-- ---------------------------------------------------------------- plan history
-- One row per plan change. An invoice uses the plan in force on the first day of its month.
-- The amount columns are Enterprise overrides (NULL = same as Professional).
CREATE TABLE organization_plan_history (
  id INTEGER PRIMARY KEY,
  org_id INTEGER NOT NULL REFERENCES organizations(id),
  plan TEXT NOT NULL CHECK (plan IN ('essential', 'professional', 'enterprise')),
  base_cents INTEGER,
  included INTEGER,
  extra_external_cents INTEGER,
  extra_depiqo_cents INTEGER,
  new_dossier_cents INTEGER,
  valid_from TEXT NOT NULL,
  created_at TEXT NOT NULL,
  created_by INTEGER REFERENCES users(id)
);
CREATE INDEX idx_plan_history_org ON organization_plan_history (org_id, valid_from);
INSERT INTO organization_plan_history (org_id, plan, base_cents, included, extra_external_cents, extra_depiqo_cents, new_dossier_cents, valid_from, created_at)
  SELECT id, plan, ent_base_cents, ent_included, ent_extra_external_cents, ent_extra_depiqo_cents, ent_new_dossier_cents,
         substr(created_at, 1, 7) || '-01', created_at
  FROM organizations;

-- ---------------------------------------------------------------- invoices: payment status and credit notes
-- SQLite cannot change a CHECK constraint, so the table is rebuilt. Old status 'paid' becomes
-- status 'issued' with payment_status 'paid'.
CREATE TABLE invoices_new (
  id INTEGER PRIMARY KEY,
  org_id INTEGER NOT NULL REFERENCES organizations(id),
  period TEXT NOT NULL,
  number TEXT NOT NULL UNIQUE,
  kind TEXT NOT NULL DEFAULT 'invoice' CHECK (kind IN ('invoice', 'credit')),
  status TEXT NOT NULL CHECK (status IN ('issued', 'credited', 'void')),
  payment_status TEXT NOT NULL DEFAULT 'open' CHECK (payment_status IN ('open', 'paid', 'none')),
  credit_for_id INTEGER REFERENCES invoices(id),
  plan TEXT,
  subtotal_cents INTEGER NOT NULL,
  vat_cents INTEGER NOT NULL,
  total_cents INTEGER NOT NULL,
  lines_json TEXT NOT NULL,
  issued_at TEXT NOT NULL,
  due_at TEXT,
  paid_at TEXT,
  note TEXT
);
INSERT INTO invoices_new (id, org_id, period, number, kind, status, payment_status, subtotal_cents, vat_cents, total_cents, lines_json, issued_at, due_at, paid_at)
  SELECT id, org_id, period, number, 'invoice',
         CASE WHEN status = 'paid' THEN 'issued' ELSE status END,
         CASE WHEN status = 'paid' THEN 'paid' ELSE 'open' END,
         subtotal_cents, vat_cents, total_cents, lines_json, issued_at, date(issued_at, '+14 days'),
         CASE WHEN status = 'paid' THEN issued_at END
  FROM invoices;
DROP TABLE invoices;
ALTER TABLE invoices_new RENAME TO invoices;
CREATE UNIQUE INDEX idx_invoices_one_per_period ON invoices (org_id, period) WHERE kind = 'invoice' AND status = 'issued';
CREATE INDEX idx_invoices_org ON invoices (org_id, period);

-- ---------------------------------------------------------------- staff settings (assumptions for unit economics)
CREATE TABLE staff_settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  updated_by INTEGER REFERENCES users(id)
);

-- ---------------------------------------------------------------- two-factor authentication (TOTP, RFC 6238)
ALTER TABLE users ADD COLUMN totp_secret TEXT;
ALTER TABLE users ADD COLUMN totp_pending_secret TEXT;
ALTER TABLE users ADD COLUMN totp_enabled_at TEXT;
ALTER TABLE users ADD COLUMN totp_last_step INTEGER;
CREATE TABLE recovery_codes (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id),
  code_hash TEXT NOT NULL UNIQUE,
  used_at TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX idx_recovery_codes_user ON recovery_codes (user_id);

-- ---------------------------------------------------------------- CSV import of existing deposits
CREATE TABLE import_batches (
  id INTEGER PRIMARY KEY,
  org_id INTEGER NOT NULL REFERENCES organizations(id),
  user_id INTEGER NOT NULL REFERENCES users(id),
  filename TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('preview', 'committed', 'discarded')),
  row_count INTEGER NOT NULL,
  error_count INTEGER NOT NULL,
  rows_json TEXT NOT NULL,
  send_invites INTEGER NOT NULL DEFAULT 0,
  imported_count INTEGER,
  created_at TEXT NOT NULL,
  committed_at TEXT
);

-- ---------------------------------------------------------------- mail per dossier
ALTER TABLE outbox_emails ADD COLUMN deposit_id INTEGER REFERENCES deposits(id);
UPDATE outbox_emails SET deposit_id = (SELECT d.id FROM deposits d WHERE outbox_emails.body_text LIKE '%' || d.reference || '%' ORDER BY d.id LIMIT 1);
CREATE INDEX idx_outbox_deposit ON outbox_emails (deposit_id, id)
