-- 0.6.0 JSON API for the tenant app: device sessions with hashed tokens, second-step challenges,
-- idempotency records, invest quotes, notifications and the push outbox.

CREATE TABLE api_devices (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id),
  device_name TEXT NOT NULL,
  platform TEXT NOT NULL CHECK (platform IN ('ios', 'android')),
  app_version TEXT NOT NULL,
  created_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  last_ip TEXT,
  mfa_at TEXT,
  revoked_at TEXT,
  revoked_reason TEXT
);
CREATE INDEX idx_api_devices_user ON api_devices(user_id);

CREATE TABLE api_access_tokens (
  id INTEGER PRIMARY KEY,
  device_id INTEGER NOT NULL REFERENCES api_devices(id),
  token_hash TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL
);
CREATE INDEX idx_api_access_device ON api_access_tokens(device_id);

-- Refresh tokens rotate on every use. A token with used_at set that is presented again is a reuse:
-- the whole device session is revoked (theft detection).
CREATE TABLE api_refresh_tokens (
  id INTEGER PRIMARY KEY,
  device_id INTEGER NOT NULL REFERENCES api_devices(id),
  token_hash TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  used_at TEXT,
  replaced_by INTEGER
);
CREATE INDEX idx_api_refresh_device ON api_refresh_tokens(device_id);

CREATE TABLE api_mfa_challenges (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id),
  token_hash TEXT NOT NULL UNIQUE,
  device_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0,
  used_at TEXT
);

-- Idempotency-Key per user: the first successful response is stored and returned again for 24 hours.
CREATE TABLE api_idempotency (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL,
  idem_key TEXT NOT NULL,
  method TEXT NOT NULL,
  path TEXT NOT NULL,
  request_hash TEXT NOT NULL,
  status_code INTEGER,
  response_json TEXT,
  created_at TEXT NOT NULL,
  UNIQUE (user_id, idem_key)
);

-- A quote shows costs and risk before an order. Valid for 10 minutes, used once.
CREATE TABLE invest_quotes (
  id INTEGER PRIMARY KEY,
  quote_key TEXT NOT NULL UNIQUE,
  user_id INTEGER NOT NULL REFERENCES users(id),
  account_id INTEGER NOT NULL REFERENCES invest_accounts(id),
  side TEXT NOT NULL CHECK (side IN ('buy', 'sell', 'switch')),
  amount_cents INTEGER,
  sell_all INTEGER NOT NULL DEFAULT 0,
  portfolio TEXT NOT NULL,
  fee_bps INTEGER NOT NULL,
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  used_at TEXT,
  order_id INTEGER
);

CREATE TABLE notifications (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id),
  type TEXT NOT NULL,
  category TEXT NOT NULL,
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  params_json TEXT,
  link_path TEXT,
  created_at TEXT NOT NULL,
  read_at TEXT
);
CREATE INDEX idx_notifications_user ON notifications(user_id, id);

CREATE TABLE push_tokens (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id),
  device_id INTEGER REFERENCES api_devices(id),
  provider TEXT NOT NULL DEFAULT 'expo',
  token TEXT NOT NULL UNIQUE,
  platform TEXT NOT NULL CHECK (platform IN ('ios', 'android')),
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  deactivated_at TEXT,
  deactivated_reason TEXT
);
CREATE INDEX idx_push_tokens_user ON push_tokens(user_id);

-- Outbox for push messages. Text is a short title and a fixed line only, never amounts or personal data.
CREATE TABLE push_messages (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL,
  push_token_id INTEGER NOT NULL REFERENCES push_tokens(id),
  notification_id INTEGER REFERENCES notifications(id),
  provider TEXT NOT NULL DEFAULT 'expo',
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  data_json TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('pending', 'sent', 'skipped', 'failed', 'delivered')),
  note TEXT,
  ticket_id TEXT,
  attempts INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  sent_at TEXT,
  receipt_checked_at TEXT
);
CREATE INDEX idx_push_messages_status ON push_messages(status);

-- Support questions from the app. Never linked to the landlord's communication log.
CREATE TABLE support_tickets (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id),
  category TEXT NOT NULL CHECK (category IN ('deposit', 'invest', 'account', 'app', 'other')),
  subject TEXT NOT NULL,
  deposit_id INTEGER REFERENCES deposits(id),
  status TEXT NOT NULL CHECK (status IN ('open', 'answered', 'closed')),
  language TEXT NOT NULL DEFAULT 'nl',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  closed_at TEXT
);
CREATE INDEX idx_support_user ON support_tickets(user_id, id);
CREATE INDEX idx_support_status ON support_tickets(status, id);

CREATE TABLE support_messages (
  id INTEGER PRIMARY KEY,
  ticket_id INTEGER NOT NULL REFERENCES support_tickets(id),
  author_kind TEXT NOT NULL CHECK (author_kind IN ('tenant', 'staff')),
  author_user_id INTEGER REFERENCES users(id),
  body TEXT NOT NULL,
  created_at TEXT NOT NULL
);

ALTER TABLE users ADD COLUMN notification_prefs TEXT;
ALTER TABLE users ADD COLUMN language TEXT;
ALTER TABLE users ADD COLUMN deleted_at TEXT
