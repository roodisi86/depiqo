-- Depiqo platform, migration 003: price plans per organisation and the security model per deposit.
-- Runs statement by statement. SQLite only allows constant defaults on ADD COLUMN, so the
-- backfill is done with UPDATE statements below.

-- Plan per organisation. Enterprise numbers are only used when plan = 'enterprise';
-- NULL means "same as Professional".
ALTER TABLE organizations ADD COLUMN plan TEXT NOT NULL DEFAULT 'essential' CHECK (plan IN ('essential', 'professional', 'enterprise'));
ALTER TABLE organizations ADD COLUMN ent_base_cents INTEGER;
ALTER TABLE organizations ADD COLUMN ent_included INTEGER;
ALTER TABLE organizations ADD COLUMN ent_extra_external_cents INTEGER;
ALTER TABLE organizations ADD COLUMN ent_extra_depiqo_cents INTEGER;
ALTER TABLE organizations ADD COLUMN ent_new_dossier_cents INTEGER;

-- Security model. The deposit row is the obligation (amount_cents: what the tenant owes as
-- security). These columns describe the collateral that covers it.
ALTER TABLE deposits ADD COLUMN security_type TEXT NOT NULL DEFAULT 'bank_deposit' CHECK (security_type IN ('bank_deposit', 'external_account', 'pledged_portfolio', 'guarantee'));
ALTER TABLE deposits ADD COLUMN custodian TEXT;
ALTER TABLE deposits ADD COLUMN beneficiary TEXT;
ALTER TABLE deposits ADD COLUMN legal_lock_status TEXT NOT NULL DEFAULT 'none' CHECK (legal_lock_status IN ('none', 'requested', 'active', 'released'));
ALTER TABLE deposits ADD COLUMN asset_value_cents INTEGER;
ALTER TABLE deposits ADD COLUMN eligible_value_cents INTEGER;

-- Backfill: deposits held elsewhere sit on the landlord's or manager's own account.
UPDATE deposits SET security_type = 'external_account' WHERE holding = 'external';

-- Backfill: the beneficiary of the security is always the organisation (landlord side).
UPDATE deposits SET beneficiary = (SELECT o.name FROM organizations o WHERE o.id = deposits.org_id);

-- Backfill: Depiqo deposit accounts. The bank holds the money; the lock follows the bank status.
UPDATE deposits SET custodian = 'Sandbox-partnerbank'
  WHERE holding = 'depiqo' AND id IN (SELECT deposit_id FROM bank_accounts WHERE provider = 'sandbox');
UPDATE deposits SET legal_lock_status = 'requested'
  WHERE holding = 'depiqo' AND (status = 'payment_received' OR (status = 'legal_hold' AND hold_previous_status = 'payment_received'));
UPDATE deposits SET legal_lock_status = 'active',
  asset_value_cents = (SELECT b.ledger_balance_cents FROM bank_accounts b WHERE b.deposit_id = deposits.id),
  eligible_value_cents = (SELECT b.ledger_balance_cents FROM bank_accounts b WHERE b.deposit_id = deposits.id)
  WHERE holding = 'depiqo' AND (status IN ('secured', 'move_out', 'settlement_proposed', 'agreed', 'disputed', 'payout_pending')
    OR (status = 'legal_hold' AND hold_previous_status IN ('secured', 'move_out', 'settlement_proposed', 'agreed', 'disputed', 'payout_pending')));
UPDATE deposits SET legal_lock_status = 'released', asset_value_cents = 0, eligible_value_cents = 0
  WHERE holding = 'depiqo' AND status = 'closed';
UPDATE deposits SET asset_value_cents = (SELECT b.ledger_balance_cents FROM bank_accounts b WHERE b.deposit_id = deposits.id)
  WHERE holding = 'depiqo' AND asset_value_cents IS NULL AND id IN (SELECT deposit_id FROM bank_accounts);

-- Backfill: external deposits confirmed by finance count at their full amount until closed.
UPDATE deposits SET asset_value_cents = amount_cents, eligible_value_cents = amount_cents
  WHERE holding = 'external' AND secured_at IS NOT NULL AND status NOT IN ('closed', 'cancelled');
UPDATE deposits SET asset_value_cents = 0, eligible_value_cents = 0
  WHERE holding = 'external' AND status = 'closed'
