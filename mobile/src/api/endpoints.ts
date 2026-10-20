/**
 * Every endpoint the app uses, and nothing else. Paths and payloads follow docs/api/openapi.yaml (0.6.0, also valid for 0.6.1)
 * of the Depiqo platform. No endpoint here moves deposit money: the backend has none, and the app must
 * not invent any. Money-related writes take an Idempotency-Key from the caller (one per user action).
 * Pure module.
 */
import type { ApiClient } from './client';
import * as S from './schemas';

export interface DeviceInput {
  name: string;
  platform: 'ios' | 'android';
  app_version: string;
}

export interface UploadFile {
  uri: string;
  name: string;
  type: string;
}

const enc = encodeURIComponent;

export function createApi(client: ApiClient) {
  return {
    // ------------------------------------------------------------ config and auth
    config: () => client.request('/config', { auth: 'none', schema: S.ConfigSchema }),

    login: (email: string, password: string, device: DeviceInput) =>
      client.request('/auth/login', { method: 'POST', auth: 'none', body: { email, password, device }, schema: S.LoginResponseSchema }),

    loginSecondStep: (mfaToken: string, code: string) =>
      client.request('/auth/mfa', { method: 'POST', auth: 'none', body: { mfa_token: mfaToken, code }, schema: S.SessionSchema }),

    logout: () => client.request('/auth/logout', { method: 'POST', expect: 'none' }),

    devices: () => client.request('/auth/devices', { schema: S.DevicesSchema }),

    revokeDevice: (id: number) => client.request(`/auth/devices/${id}`, { method: 'DELETE', expect: 'none' }),

    registerPushToken: (token: string, platform: 'ios' | 'android') =>
      client.request('/devices/push-token', { method: 'POST', body: { token, platform }, schema: S.PushTokenResultSchema }),

    // ------------------------------------------------------------ invitations

    invite: (token: string) => client.request(`/invites/${enc(token)}`, { auth: 'none', schema: S.InviteSchema }),

    /** New account: password + device. Existing tenant account: signed in, no password. */
    acceptInvite: (token: string, input: { password?: string; device?: DeviceInput }) =>
      client.request(`/invites/${enc(token)}/accept`, {
        method: 'POST',
        auth: 'optional',
        body: { confirm_details: true, ...input },
        schema: S.AcceptInviteResponseSchema,
      }),

    // ------------------------------------------------------------ me

    me: () => client.request('/me', { schema: S.MeSchema }),

    updateMe: (patch: { name?: string; language?: 'nl' | 'fr' | 'en'; notification_preferences?: { push: Partial<S.NotificationPreferences['push']> } }) =>
      client.request('/me', { method: 'PATCH', body: patch, schema: S.MeSchema }),

    /** The raw JSON text, to be saved as a file as the server sent it. */
    exportData: () => client.request<string>('/me/export', { method: 'POST', expect: 'text' }),

    deletionInfo: () => client.request('/me/delete-request', { schema: S.DeletionInfoSchema }),

    deleteAccount: (password: string) =>
      client.request('/me/delete-request', { method: 'POST', body: { password, confirm: true }, schema: S.DeleteResultSchema }),

    // ------------------------------------------------------------ notifications, activity, support

    notifications: (cursor?: string | null, limit = 20) =>
      client.request('/notifications', { query: { limit, cursor }, schema: S.NotificationsPageSchema }),

    markNotificationRead: (id: number) =>
      client.request(`/notifications/${id}/read`, { method: 'POST', schema: S.NotificationSchema }),

    activity: (cursor?: string | null, limit = 20) =>
      client.request('/activity', { query: { limit, cursor }, schema: S.ActivityPageSchema }),

    supportTickets: (cursor?: string | null, limit = 20) =>
      client.request('/support', { query: { limit, cursor }, schema: S.SupportPageSchema }),

    createSupportTicket: (
      input: { category: string; message: string; subject?: string; deposit_pid?: string },
      idempotencyKey: string,
    ) => client.request('/support', { method: 'POST', body: input, idempotencyKey, schema: S.SupportTicketSchema }),

    // ------------------------------------------------------------ deposits

    deposits: (cursor?: string | null, limit = 20) =>
      client.request('/deposits', { query: { limit, cursor }, schema: S.DepositsPageSchema }),

    deposit: (pid: string) => client.request(`/deposits/${enc(pid)}`, { schema: S.DepositDetailSchema }),

    depositEvents: (pid: string, cursor?: string | null, limit = 20) =>
      client.request(`/deposits/${enc(pid)}/events`, { query: { limit, cursor }, schema: S.DepositEventsPageSchema }),

    verifyIdentity: (pid: string, input: { full_name: string; birth_date: string }, idempotencyKey: string) =>
      client.request(`/deposits/${enc(pid)}/identity`, { method: 'POST', body: input, idempotencyKey, schema: S.IdentityResultSchema }),

    documents: (pid: string) => client.request(`/deposits/${enc(pid)}/documents`, { schema: S.DocumentsSchema }),

    uploadDocument: (pid: string, kind: string, file: UploadFile, idempotencyKey: string) => {
      const form = new FormData();
      form.append('kind', kind);
      // React Native's FormData takes {uri, name, type} for a file.
      form.append('file', file as unknown as Blob);
      return client.request(`/deposits/${enc(pid)}/documents`, { method: 'POST', form, idempotencyKey, schema: S.DocumentSchema });
    },

    settlement: (pid: string) => client.request(`/deposits/${enc(pid)}/settlement`, { schema: S.SettlementResponseSchema }),

    agreeSettlement: (pid: string, idempotencyKey: string) =>
      client.request(`/deposits/${enc(pid)}/settlement/agree`, {
        method: 'POST',
        body: { confirm: true },
        idempotencyKey,
        schema: S.SettlementResultSchema,
      }),

    disputeSettlement: (pid: string, reason: string, idempotencyKey: string) =>
      client.request(`/deposits/${enc(pid)}/settlement/dispute`, {
        method: 'POST',
        body: { reason },
        idempotencyKey,
        schema: S.SettlementResultSchema,
      }),

    releaseFormPath: (pid: string) => `/api/v1/deposits/${enc(pid)}/release-form`,

    payoutChoice: (pid: string) => client.request(`/deposits/${enc(pid)}/payout-choice`, { schema: S.PayoutChoiceSchema }),

    choosePayoutToInvest: (pid: string, idempotencyKey: string) =>
      client.request(`/deposits/${enc(pid)}/payout-choice`, {
        method: 'POST',
        body: { confirm: true },
        idempotencyKey,
        schema: S.PayoutChoiceSchema,
      }),

    cancelPayoutToInvest: (pid: string, idempotencyKey: string) =>
      client.request(`/deposits/${enc(pid)}/payout-choice`, { method: 'DELETE', idempotencyKey, schema: S.PayoutChoiceSchema }),

    // ------------------------------------------------------------ invest

    investOverview: () => client.request('/invest', { schema: S.InvestOverviewSchema }),

    portfolios: (amountCents?: number) =>
      client.request('/invest/portfolios', { query: { amount_cents: amountCents }, schema: S.PortfoliosSchema }),

    appropriateness: () => client.request('/invest/appropriateness', { schema: S.AppropriatenessQuestionsSchema }),

    answerAppropriateness: (answers: Record<string, string>) =>
      client.request('/invest/appropriateness', { method: 'POST', body: { answers }, schema: S.AppropriatenessSchema }),

    confirmAppropriatenessWarning: () =>
      client.request('/invest/appropriateness/confirm', { method: 'POST', body: { confirm: true }, schema: S.AppropriatenessSchema }),

    terms: () => client.request('/invest/terms', { schema: S.TermsSchema }),

    acceptTerms: (partnerVersion: string, depiqoVersion: string) =>
      client.request('/invest/terms', {
        method: 'POST',
        body: { partner_version: partnerVersion, depiqo_version: depiqoVersion, accept_partner: true, accept_depiqo: true },
        schema: S.TermsAcceptedSchema,
      }),

    openInvestAccount: (portfolio: string, idempotencyKey: string) =>
      client.request('/invest/account', { method: 'POST', body: { portfolio }, idempotencyKey, schema: S.OpenAccountResultSchema }),

    investDepositInstructions: () => client.request('/invest/deposit-instructions', { schema: S.DepositInstructionsSchema }),

    /** Sandbox only (the server answers 404 elsewhere). Simulates a transfer; moves no real money. */
    sandboxDeposit: (amountCents: number, idempotencyKey: string) =>
      client.request('/invest/sandbox/deposit', {
        method: 'POST',
        body: { amount_cents: amountCents },
        idempotencyKey,
        schema: S.SandboxDepositResultSchema,
      }),

    /** A quote moves no money; it shows costs and risk before an order. */
    quote: (input: { side: 'buy' | 'sell' | 'switch'; amount_cents?: number; sell_all?: boolean; portfolio?: string }) =>
      client.request('/invest/orders/quote', { method: 'POST', body: input, schema: S.QuoteSchema }),

    placeOrder: (quoteId: string, idempotencyKey: string) =>
      client.request('/invest/orders', {
        method: 'POST',
        body: { quote_id: quoteId, risk_acknowledged: true },
        idempotencyKey,
        schema: S.PlaceOrderResultSchema,
      }),

    orders: (cursor?: string | null, limit = 20) =>
      client.request('/invest/orders', { query: { limit, cursor }, schema: S.OrdersPageSchema }),

    investTransactions: (cursor?: string | null, limit = 20) =>
      client.request('/invest/transactions', { query: { limit, cursor }, schema: S.InvestTransactionsPageSchema }),

    withdrawals: (cursor?: string | null, limit = 20) =>
      client.request('/invest/withdrawals', { query: { limit, cursor }, schema: S.WithdrawalsPageSchema }),

    registerIban: (iban: string, code: string | undefined, idempotencyKey: string) =>
      client.request('/invest/iban', {
        method: 'POST',
        body: code ? { iban, code } : { iban },
        idempotencyKey,
        schema: S.RegisterIbanResultSchema,
      }),

    withdraw: (amountCents: number, idempotencyKey: string) =>
      client.request('/invest/withdrawals', {
        method: 'POST',
        body: { amount_cents: amountCents },
        idempotencyKey,
        schema: S.WithdrawResultSchema,
      }),

    statements: () => client.request('/invest/statements', { schema: S.StatementsSchema }),

    feeChange: () => client.request('/invest/fee-change', { schema: S.FeeChangeSchema }),

    acceptFeeChange: (idempotencyKey: string) =>
      client.request('/invest/fee-change', { method: 'POST', body: { accept: true }, idempotencyKey, schema: S.FeeChangeAcceptedSchema }),
  };
}

export type Api = ReturnType<typeof createApi>;
