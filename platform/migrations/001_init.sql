-- Depiqo platform, initial schema.
-- Written for SQLite; kept close to standard SQL so it ports to PostgreSQL
-- (INTEGER PRIMARY KEY -> BIGSERIAL, TEXT timestamps -> TIMESTAMPTZ).
-- All money is stored in euro cents as INTEGER.

CREATE TABLE organizations (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  registration_number TEXT,
  country TEXT NOT NULL DEFAULT 'NL',
  billing_email TEXT,
  vat_rate_bps INTEGER NOT NULL DEFAULT 2100,
  pilot_until TEXT,
  status TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL
);

CREATE TABLE users (
  id INTEGER PRIMARY KEY,
  email TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  password_hash TEXT,
  is_staff INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  last_login_at TEXT
);

CREATE TABLE memberships (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id),
  org_id INTEGER NOT NULL REFERENCES organizations(id),
  role TEXT NOT NULL CHECK (role IN ('admin', 'manager', 'finance', 'viewer')),
  created_at TEXT NOT NULL,
  UNIQUE (user_id, org_id)
);

CREATE TABLE sessions (
  id INTEGER PRIMARY KEY,
  token_hash TEXT NOT NULL UNIQUE,
  user_id INTEGER NOT NULL REFERENCES users(id),
  csrf_token TEXT NOT NULL,
  active_org_id INTEGER REFERENCES organizations(id),
  created_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  ip TEXT,
  user_agent TEXT
);

CREATE TABLE login_attempts (
  id INTEGER PRIMARY KEY,
  email TEXT NOT NULL,
  ip TEXT,
  ok INTEGER NOT NULL,
  at TEXT NOT NULL
);
CREATE INDEX idx_login_attempts_email ON login_attempts (email, at);
CREATE INDEX idx_login_attempts_ip ON login_attempts (ip, at);

CREATE TABLE invitations (
  id INTEGER PRIMARY KEY,
  org_id INTEGER NOT NULL REFERENCES organizations(id),
  email TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('admin', 'manager', 'finance', 'viewer')),
  token_hash TEXT NOT NULL UNIQUE,
  invited_by INTEGER REFERENCES users(id),
  expires_at TEXT NOT NULL,
  accepted_at TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE properties (
  id INTEGER PRIMARY KEY,
  org_id INTEGER NOT NULL REFERENCES organizations(id),
  address TEXT NOT NULL,
  postcode TEXT NOT NULL,
  city TEXT NOT NULL,
  region TEXT NOT NULL CHECK (region IN ('NL', 'VL', 'BRU')),
  created_at TEXT NOT NULL
);
CREATE INDEX idx_properties_org ON properties (org_id);

CREATE TABLE tenants (
  id INTEGER PRIMARY KEY,
  org_id INTEGER NOT NULL REFERENCES organizations(id),
  name TEXT NOT NULL,
  email TEXT NOT NULL,
  phone TEXT,
  user_id INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL
);
CREATE INDEX idx_tenants_org ON tenants (org_id);
CREATE INDEX idx_tenants_user ON tenants (user_id);

CREATE TABLE deposits (
  id INTEGER PRIMARY KEY,
  pid TEXT NOT NULL UNIQUE,
  reference TEXT NOT NULL,
  org_id INTEGER NOT NULL REFERENCES organizations(id),
  property_id INTEGER NOT NULL REFERENCES properties(id),
  tenant_id INTEGER NOT NULL REFERENCES tenants(id),
  region TEXT NOT NULL CHECK (region IN ('NL', 'VL', 'BRU')),
  holding TEXT NOT NULL CHECK (holding IN ('depiqo', 'external')),
  rent_cents INTEGER NOT NULL,
  amount_cents INTEGER NOT NULL,
  status TEXT NOT NULL,
  hold_previous_status TEXT,
  lease_start TEXT NOT NULL,
  lease_end TEXT,
  move_out_date TEXT,
  rule_version TEXT NOT NULL,
  external_iban TEXT,
  invite_token_hash TEXT UNIQUE,
  invite_expires_at TEXT,
  created_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  activated_at TEXT,
  secured_at TEXT,
  closed_at TEXT
);
CREATE INDEX idx_deposits_org_status ON deposits (org_id, status);
CREATE INDEX idx_deposits_tenant ON deposits (tenant_id);

CREATE TABLE deposit_events (
  id INTEGER PRIMARY KEY,
  deposit_id INTEGER NOT NULL REFERENCES deposits(id),
  org_id INTEGER NOT NULL REFERENCES organizations(id),
  at TEXT NOT NULL,
  actor_kind TEXT NOT NULL CHECK (actor_kind IN ('user', 'tenant', 'system', 'bank', 'staff')),
  actor_user_id INTEGER REFERENCES users(id),
  type TEXT NOT NULL,
  from_status TEXT,
  to_status TEXT,
  message TEXT,
  data_json TEXT
);
CREATE INDEX idx_deposit_events_deposit ON deposit_events (deposit_id, at);

CREATE TABLE audit_log (
  id INTEGER PRIMARY KEY,
  at TEXT NOT NULL,
  org_id INTEGER,
  user_id INTEGER,
  action TEXT NOT NULL,
  target TEXT,
  ip TEXT,
  data_json TEXT
);
CREATE INDEX idx_audit_org ON audit_log (org_id, at);

CREATE TABLE documents (
  id INTEGER PRIMARY KEY,
  org_id INTEGER NOT NULL REFERENCES organizations(id),
  deposit_id INTEGER NOT NULL REFERENCES deposits(id),
  uploaded_by_kind TEXT NOT NULL CHECK (uploaded_by_kind IN ('user', 'tenant')),
  uploaded_by INTEGER REFERENCES users(id),
  kind TEXT NOT NULL,
  filename TEXT NOT NULL,
  stored_name TEXT NOT NULL UNIQUE,
  mime TEXT NOT NULL,
  size_bytes INTEGER NOT NULL,
  sha256 TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX idx_documents_deposit ON documents (deposit_id);

CREATE TABLE settlements (
  id INTEGER PRIMARY KEY,
  deposit_id INTEGER NOT NULL REFERENCES deposits(id),
  org_id INTEGER NOT NULL REFERENCES organizations(id),
  status TEXT NOT NULL CHECK (status IN ('draft', 'proposed', 'agreed', 'disputed', 'superseded')),
  created_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL,
  proposed_at TEXT,
  responded_at TEXT,
  tenant_comment TEXT
);
CREATE INDEX idx_settlements_deposit ON settlements (deposit_id);

CREATE TABLE settlement_lines (
  id INTEGER PRIMARY KEY,
  settlement_id INTEGER NOT NULL REFERENCES settlements(id),
  category TEXT NOT NULL,
  description TEXT NOT NULL,
  amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
  document_id INTEGER REFERENCES documents(id)
);

CREATE TABLE disputes (
  id INTEGER PRIMARY KEY,
  deposit_id INTEGER NOT NULL REFERENCES deposits(id),
  org_id INTEGER NOT NULL REFERENCES organizations(id),
  settlement_id INTEGER REFERENCES settlements(id),
  opened_by_kind TEXT NOT NULL,
  reason TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('open', 'agreement', 'court_decision', 'withdrawn')),
  resolution_note TEXT,
  resolution_document_id INTEGER REFERENCES documents(id),
  landlord_amount_cents INTEGER,
  opened_at TEXT NOT NULL,
  resolved_at TEXT
);

CREATE TABLE kyc_checks (
  id INTEGER PRIMARY KEY,
  deposit_id INTEGER NOT NULL REFERENCES deposits(id),
  tenant_id INTEGER NOT NULL REFERENCES tenants(id),
  provider TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'failed')),
  created_at TEXT NOT NULL,
  completed_at TEXT
);

-- Financial partner layer. Rows here mirror what the partner bank reports;
-- the bank is the source of truth, these are Depiqo's shadow ledger.
CREATE TABLE bank_accounts (
  id INTEGER PRIMARY KEY,
  deposit_id INTEGER NOT NULL UNIQUE REFERENCES deposits(id),
  provider TEXT NOT NULL,
  external_id TEXT NOT NULL,
  iban TEXT NOT NULL,
  holder_name TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('open', 'blocked', 'release_requested', 'closed')),
  interest_rate_bps INTEGER NOT NULL DEFAULT 0,
  ledger_balance_cents INTEGER NOT NULL DEFAULT 0,
  ledger_interest_cents INTEGER NOT NULL DEFAULT 0,
  opened_at TEXT NOT NULL,
  closed_at TEXT
);

CREATE TABLE bank_transactions (
  id INTEGER PRIMARY KEY,
  bank_account_id INTEGER NOT NULL REFERENCES bank_accounts(id),
  kind TEXT NOT NULL CHECK (kind IN ('deposit', 'interest', 'payout_tenant', 'payout_landlord')),
  amount_cents INTEGER NOT NULL,
  external_ref TEXT NOT NULL,
  at TEXT NOT NULL,
  UNIQUE (bank_account_id, external_ref)
);

CREATE TABLE bank_events (
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

-- Sandbox only: simulated state at the "bank" side, used by the sandbox adapter.
CREATE TABLE sandbox_bank_accounts (
  id INTEGER PRIMARY KEY,
  external_id TEXT NOT NULL UNIQUE,
  iban TEXT NOT NULL UNIQUE,
  holder_name TEXT NOT NULL,
  balance_cents INTEGER NOT NULL DEFAULT 0,
  blocked INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);

CREATE TABLE outbox_emails (
  id INTEGER PRIMARY KEY,
  to_email TEXT NOT NULL,
  subject TEXT NOT NULL,
  body_text TEXT NOT NULL,
  created_at TEXT NOT NULL,
  sent_at TEXT,
  provider TEXT NOT NULL,
  error TEXT
);

CREATE TABLE invoices (
  id INTEGER PRIMARY KEY,
  org_id INTEGER NOT NULL REFERENCES organizations(id),
  period TEXT NOT NULL,
  number TEXT NOT NULL UNIQUE,
  status TEXT NOT NULL CHECK (status IN ('issued', 'paid', 'void')),
  subtotal_cents INTEGER NOT NULL,
  vat_cents INTEGER NOT NULL,
  total_cents INTEGER NOT NULL,
  lines_json TEXT NOT NULL,
  issued_at TEXT NOT NULL,
  UNIQUE (org_id, period)
);
