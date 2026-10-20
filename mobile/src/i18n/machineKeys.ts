/**
 * Stable machine keys the backend sends next to Dutch labels. The app translates each of them itself
 * (locale namespace in brackets). Tests check that every key below has a translation in nl, fr and en.
 * Source: app/states.py, app/providers.py, app/api/*.py, app/i18n.py, app/notify.py of depiqo-platform (API 0.6.0 and 0.6.1).
 */
export const MACHINE_KEYS: Record<string, readonly string[]> = {
  // [status] deposit status
  status: [
    'concept', 'invited', 'id_pending', 'awaiting_payment', 'payment_received', 'secured', 'move_out',
    'settlement_proposed', 'agreed', 'disputed', 'payout_pending', 'closed', 'cancelled', 'id_failed', 'legal_hold',
  ],
  // [display] refined display keys (others equal a status)
  display: [
    'secured_bank_confirmed', 'secured_untrusted_lock', 'secured_declared', 'secured_document', 'secured_verified',
    'secured_legal', 'awaiting_guarantee', 'released',
  ],
  evidence: ['declared', 'document', 'verified', 'legal'],
  provider: ['depiqo_account', 'verhuurder_rekening', 'bank_geblokkeerd', 'e_depo', 'verzekering_tak26', 'borggarantie', 'ocmw', 'anders', 'unknown'],
  assurance: ['bank', 'bank_requested', 'released', 'untrusted', 'declared', 'document', 'verified', 'legal'],
  amount: ['obligation', 'received', 'locked', 'interest'],
  amountNote: [
    'per_lease', 'no_account', 'no_lock_yet', 'no_interest_yet', 'bank_confirmed', 'no_payment_reported', 'sandbox_unconfirmed',
    'not_confirmed_by_active_bank', 'lock_confirmed_by_bank', 'lock_requested', 'released_at_payout', 'interest_credited',
    'guarantee_no_money', 'ocmw_no_money', 'no_receipt_reported', 'declared_only', 'bank_proof_received', 'verified_by_depiqo',
    'legal_security_proven', 'released_by_provider', 'repaid_or_cancelled', 'guarantee_proven', 'lock_certificate_proven',
    'no_legal_lock', 'outside_depiqo', 'other',
  ],
  step: ['invited', 'id_pending', 'awaiting_payment', 'secured', 'move_out', 'settlement', 'payout', 'closed'],
  stepState: ['done', 'current', 'upcoming', 'cancelled'],
  nextAction: ['verify_identity', 'pay', 'wait', 'respond_settlement', 'choose_payout_destination', 'release_form'],
  guaranteeWarning: ['expired', 'expiring'],
  event: [
    'status_changed', 'payment_received', 'interest_credited', 'document_added', 'invited',
    'invest_deposit', 'invest_payout_in', 'invest_buy', 'invest_sell', 'invest_withdrawal', 'invest_fee',
  ],
  docKind: ['contract', 'inspection', 'photo', 'quote', 'agreement', 'court', 'bankbewijs', 'blokkering', 'vrijgave', 'other'],
  settlementCategory: ['damage', 'rent_arrears', 'service_costs', 'energy', 'other'],
  settlementStatus: ['proposed', 'agreed', 'disputed'],
  payoutStatus: ['chosen', 'cancelled', 'fallback', 'paid', 'unrecorded'],
  identityResult: ['account_open', 'opening', 'bank_unavailable', 'failed'],
  supportCategory: ['deposit', 'invest', 'account', 'app', 'other'],
  supportStatus: ['open', 'answered', 'closed'],
  notifType: [
    'invite', 'payment_received', 'deposit_secured', 'settlement_proposed', 'dispute_resolved', 'payout_completed', 'release_confirmed',
    'invest_order_executed', 'invest_order_failed', 'invest_withdrawal_completed', 'invest_withdrawal_failed', 'invest_fee_change',
    'new_device_login', 'support_reply',
  ],
  notifCategory: ['deposit', 'invest', 'security', 'support'],
  accountStatus: ['draft', 'pending', 'active', 'closed'],
  orderStatus: ['pending', 'executed', 'failed'],
  orderPurpose: ['order', 'switch_sell', 'switch_buy'],
  withdrawalStatus: ['pending', 'sent', 'acknowledged', 'confirmed', 'failed'],
  txKind: ['deposit', 'payout_in', 'buy', 'sell', 'withdrawal', 'fee'],
  side: ['buy', 'sell', 'switch'],
  portfolio: ['defensief', 'neutraal', 'offensief'],
  scenario: ['gunstig', 'neutraal', 'ongunstig'],
  appropriatenessResult: ['passend', 'niet_passend'],
  reason: ['thinks_no_loss', 'cannot_bear_loss', 'short_horizon', 'goal_mismatch', 'limited_knowledge', 'other'],
  onboardingStep: ['appropriateness', 'confirm_warning', 'terms', 'open_account'],
  blocker: ['open_deposit', 'invest_pending', 'invest_balance'],
  region: ['NL', 'VL', 'BRU'],
  holding: ['depiqo', 'external'],
  evidenceTenant: ['declared', 'document', 'verified', 'legal'],
  actor: ['bank', 'user', 'tenant', 'system'],
  uploadedBy: ['tenant', 'landlord'],
  range: ['1M', '6M', '1Y', 'max'],
  platform: ['ios', 'android'],
  // [errors] every error code of the API plus the client's own
  errors: [
    'bad_request', 'unauthorized', 'forbidden', 'not_found', 'method_not_allowed', 'file_too_large', 'unsupported_media_type',
    'rate_limited', 'server_error', 'cookie_auth_not_allowed', 'app_update_required', 'staff_not_allowed', 'not_a_tenant',
    'token_missing', 'token_invalid', 'token_expired', 'device_revoked', 'refresh_token_reused', 'mfa_token_invalid',
    'invalid_json', 'validation_failed', 'unknown_field', 'invalid_limit', 'invalid_cursor', 'idempotency_key_required',
    'invalid_idempotency_key', 'idempotency_key_reused', 'idempotency_in_progress', 'too_many_attempts', 'invalid_credentials',
    'invalid_code', 'invalid_password', 'weak_password', 'invite_expired', 'use_web', 'login_required', 'invite_for_other_account',
    'invite_not_accepted', 'confirm_details_required', 'confirm_required', 'risk_acknowledged_required', 'accept_partner_required',
    'accept_depiqo_required', 'accept_required', 'deletion_blocked', 'identity_not_possible', 'deposit_closed', 'upload_rejected',
    'settlement_not_open', 'reason_required', 'not_available', 'payout_choice_closed', 'partner_unavailable', 'invest_not_offered',
    'invest_rejected', 'account_not_active', 'account_exists', 'terms_outdated', 'terms_not_accepted', 'quote_not_found',
    'quote_used', 'quote_expired', 'amount_below_minimum', 'support_rate_limited', 'push_token_in_use', 'conflict',
    'network_error', 'timeout', 'invalid_response', 'not_signed_in', 'session_ended', 'unknown',
  ],
};
