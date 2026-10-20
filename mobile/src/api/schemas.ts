/**
 * zod schemas for every API response the app uses, written by hand from docs/api/openapi.yaml (0.6.0)
 * of the Depiqo platform and checked against real responses in fixtures/ (see src/api/__tests__).
 * 0.6.1 changed behaviour (rate limits, idempotency of uploads, push_token_in_use), not response shapes.
 *
 * Rules:
 * - Money is always {cents: integer, currency: "EUR"}. Another currency fails validation, so the app
 *   never shows an amount it does not understand.
 * - Unknown is null, never a substitute amount. Nullable money stays nullable here.
 * - Status-like fields are plain strings (not enums): a new status from the backend must not break the
 *   app; the UI translates known keys and falls back to the Dutch label from the server.
 * - Unknown extra fields are stripped (zod default), so additions on the server are harmless.
 * Pure module: no React Native imports.
 */
import { z } from 'zod';

// ------------------------------------------------------------ building blocks

export const MoneySchema = z.object({
  cents: z.number().int(),
  currency: z.literal('EUR'),
});
export const NullableMoneySchema = MoneySchema.nullable();

const page = <T extends z.ZodTypeAny>(item: T) =>
  z.object({
    items: z.array(item),
    next_cursor: z.string().nullable(),
  });

const params = z.record(z.unknown());

export const ErrorBodySchema = z.object({
  error: z.object({
    code: z.string(),
    message: z.string(),
    fields: z.record(z.unknown()),
    detail: z.string().optional(),
  }),
});

// ------------------------------------------------------------ config

export const ConfigSchema = z.object({
  api_version: z.string(),
  environment: z.string(),
  banner: z.string().nullable(),
  languages: z.array(z.string()),
  default_language: z.string(),
  minimum_app_version: z.object({ ios: z.string(), android: z.string() }),
  features: z.record(z.unknown()),
  support_email: z.string().nullable(),
  links: z.object({
    privacy: z.string().nullable(),
    terms: z.string().nullable(),
    password_reset: z.string(),
    security: z.string(),
    web: z.string(),
  }),
  sandbox: z.boolean(),
});

// ------------------------------------------------------------ auth

export const TokenPairSchema = z.object({
  access_token: z.string().min(1),
  access_expires_at: z.string(),
  refresh_token: z.string().min(1),
  refresh_expires_at: z.string(),
  token_type: z.literal('Bearer'),
  expires_in: z.number().int(),
  device_id: z.number().int(),
});

const SessionUserSchema = z.object({ id: z.number().int(), name: z.string(), email: z.string() });

export const SessionSchema = TokenPairSchema.extend({
  mfa_required: z.literal(false).optional(),
  user: SessionUserSchema,
  second_factor: z.enum(['totp', 'recovery']).optional(),
  recovery_codes_left: z.number().int().nullable().optional(),
});

export const MfaChallengeSchema = z.object({
  mfa_required: z.literal(true),
  mfa_token: z.string().min(1),
  mfa_expires_at: z.string(),
  message: z.string(),
});

export const LoginResponseSchema = z.union([MfaChallengeSchema, SessionSchema]);

export const DeviceSchema = z.object({
  id: z.number().int(),
  name: z.string(),
  platform: z.string(),
  app_version: z.string().nullable(),
  created_at: z.string(),
  last_seen_at: z.string().nullable(),
  second_factor: z.boolean(),
  current: z.boolean(),
});
export const DevicesSchema = z.object({ items: z.array(DeviceSchema) });

// ------------------------------------------------------------ invitations

export const AddressSchema = z.object({
  street: z.string(),
  postcode: z.string().nullable(),
  city: z.string().nullable(),
});

export const InviteSchema = z.object({
  landlord: z.object({ name: z.string() }),
  address: AddressSchema,
  amount: MoneySchema,
  reference: z.string(),
  region: z.string(),
  term: z.string(),
  holding: z.string(),
  tenant: z.object({ name: z.string(), email: z.string() }),
  existing_account: z.boolean(),
  expires_at: z.string().nullable(),
  check: z.string(),
});

const AcceptLinkedSchema = z.object({ deposit_pid: z.string(), status: z.string() });
export const AcceptInviteResponseSchema = z.union([SessionSchema.merge(AcceptLinkedSchema), AcceptLinkedSchema]);

// ------------------------------------------------------------ me

export const NotificationPreferencesSchema = z.object({
  push: z.object({
    deposit: z.boolean(),
    invest: z.boolean(),
    security: z.boolean(),
    support: z.boolean(),
  }),
});

export const MeSchema = z.object({
  id: z.number().int(),
  name: z.string(),
  email: z.string(),
  two_factor_enabled: z.boolean(),
  recovery_codes_left: z.number().int().nullable(),
  created_at: z.string(),
  language: z.enum(['nl', 'fr', 'en']),
  deposit_count: z.number().int(),
  notification_preferences: NotificationPreferencesSchema,
  invest: z.object({
    visibility: z.string(),
    eligible: z.boolean(),
    offered_by_landlord: z.boolean(),
    account_status: z.string().nullable(),
  }),
});

export const DeletionInfoSchema = z.object({
  possible: z.boolean(),
  blockers: z.array(
    z.object({
      code: z.string(),
      message: z.string(),
      next_step: z.string(),
      deposit_pid: z.string().optional(),
    }),
  ),
  deleted_now: z.array(z.string()),
  kept_by_law: z.array(z.string()),
  how: z.string(),
});

export const DeleteResultSchema = z.object({
  deleted: z.boolean(),
  deleted_now: z.array(z.string()),
  kept_by_law: z.array(z.string()),
});

/** Only the envelope is checked; the file itself is saved as the server sent it. */
export const DataExportSchema = z
  .object({
    format: z.string(),
    exported_at: z.string(),
  })
  .passthrough();

// ------------------------------------------------------------ notifications, activity, support

export const NotificationSchema = z.object({
  id: z.number().int(),
  type: z.string(),
  category: z.string(),
  title: z.string(),
  body: z.string(),
  params,
  language: z.string(),
  link_path: z.string().nullable(),
  created_at: z.string(),
  read_at: z.string().nullable(),
});
export const NotificationsPageSchema = page(NotificationSchema).extend({ unread_count: z.number().int() });

export const ActivityItemSchema = z.object({
  type: z.string(),
  id: z.number().int(),
  at: z.string(),
  key: z.string(),
  params,
  message: z.string().nullable(),
  event_type: z.string().optional(),
  deposit_pid: z.string().optional(),
  deposit_reference: z.string().optional(),
  actor: z.string().nullable().optional(),
  kind: z.string().optional(),
  amount: MoneySchema.optional(),
  day: z.string().optional(),
});
export const ActivityPageSchema = page(ActivityItemSchema);

export const SupportTicketSchema = z.object({
  id: z.number().int(),
  category: z.string(),
  category_label: z.string(),
  subject: z.string(),
  deposit_pid: z.string().nullable(),
  status: z.string(),
  status_label: z.string(),
  created_at: z.string(),
  updated_at: z.string(),
  messages: z.array(z.object({ author: z.string(), body: z.string(), created_at: z.string() })),
});
export const SupportPageSchema = page(SupportTicketSchema);

export const PushTokenResultSchema = z.object({ id: z.number().int(), active: z.boolean() });

// ------------------------------------------------------------ deposits

/** One of the four separate figures: obligation, received, locked, interest. */
export const AmountSchema = z.object({
  key: z.string(),
  label: z.string(),
  value: NullableMoneySchema,
  known: z.boolean(),
  explanation: z.string(),
  explanation_key: z.string(),
});

export const DepositSummarySchema = z.object({
  pid: z.string(),
  reference: z.string(),
  region: z.string(),
  term: z.string(),
  holding: z.string(),
  provider_kind: z.string().nullable(),
  evidence_level: z.string().nullable(),
  address: AddressSchema,
  landlord: z.object({ name: z.string() }),
  status: z.string(),
  status_label: z.string(),
  display_key: z.string(),
  display_label: z.string(),
  tone: z.string(),
  amounts: z.array(AmountSchema),
  updated_at: z.string(),
});
export const DepositsPageSchema = page(DepositSummarySchema);

export const DepositEventSchema = z.object({
  id: z.number().int(),
  at: z.string(),
  type: z.string(),
  key: z.string(),
  params,
  message: z.string().nullable(),
  actor: z.string().nullable(),
});
export const DepositEventsPageSchema = page(DepositEventSchema);

export const LocationSchema = z.object({
  kind: z.string(),
  label: z.string(),
  account_open: z.boolean().nullable(),
  sandbox: z.boolean(),
  interest_rate_bps: z.number().nullable(),
  provider_name: z.string().nullable(),
  reference_label: z.string().nullable(),
  reference: z.string().nullable(),
  assurance: z
    .object({ code: z.string(), short: z.string(), label: z.string(), tone: z.string() })
    .nullable(),
  evidence: z.object({ level: z.string(), label: z.string(), tenant: z.string() }).nullable(),
  guarantee: z
    .object({
      kind: z.string(),
      text: z.string(),
      expires_on: z.string().nullable(),
      days_left: z.number().int().nullable(),
      warning: z.string().nullable(),
      warning_key: z.string().nullable(),
    })
    .nullable(),
});

export const DepositDetailSchema = DepositSummarySchema.extend({
  rent: NullableMoneySchema,
  lease_start: z.string().nullable(),
  lease_end: z.string().nullable(),
  move_out_date: z.string().nullable(),
  progress: z.object({
    current: z.string().nullable(),
    on_hold: z.boolean(),
    steps: z.array(z.object({ code: z.string(), label: z.string(), state: z.string() })),
  }),
  location: LocationSchema,
  deadline: z
    .object({
      date: z.string().nullable(),
      statutory: z.boolean(),
      why: z.string(),
      days_left: z.number().int().nullable(),
    })
    .nullable(),
  release_rule: z.string().nullable(),
  next_action: z.object({ code: z.string(), label: z.string(), description: z.string() }).nullable(),
  payment_instructions: z
    .object({
      iban: z.string(),
      beneficiary: z.string(),
      amount: MoneySchema,
      reference: z.string(),
      warning: z.string(),
    })
    .nullable(),
  payment_problem: z.string().nullable(),
  payout: z.object({ to_tenant: MoneySchema, to_landlord: MoneySchema }).nullable(),
  release_form_available: z.boolean(),
  interest_note: z.string().nullable(),
  events: z.array(DepositEventSchema),
  events_path: z.string(),
});

export const IdentityResultSchema = z.object({
  result: z.string(),
  message: z.string(),
  deposit: DepositDetailSchema,
});

export const DocumentSchema = z.object({
  id: z.number().int(),
  kind: z.string(),
  kind_label: z.string(),
  filename: z.string(),
  mime: z.string(),
  size_bytes: z.number().int(),
  created_at: z.string(),
  uploaded_by: z.string(),
  download_path: z.string(),
});

export const DocumentsSchema = z.object({
  items: z.array(DocumentSchema),
  upload_kinds: z.array(z.object({ kind: z.string(), label: z.string() })),
  upload_allowed: z.boolean(),
  max_bytes: z.number().int(),
  accepted_types: z.array(z.string()),
});

export const SettlementSchema = z.object({
  status: z.string(),
  proposed_at: z.string().nullable(),
  responded_at: z.string().nullable(),
  deposit_amount: MoneySchema,
  lines: z.array(
    z.object({
      category: z.string(),
      category_label: z.string(),
      description: z.string(),
      amount: MoneySchema,
      document_id: z.number().int().nullable(),
      document_path: z.string().nullable(),
    }),
  ),
  deductions: MoneySchema,
  back_to_tenant: MoneySchema,
  interest: NullableMoneySchema,
  can_respond: z.boolean(),
  tenant_comment: z.string().nullable(),
  dispute: z.object({ opened_at: z.string(), reason: z.string(), status: z.string() }).nullable(),
  note: z.string(),
});
export const SettlementResponseSchema = z.object({ settlement: SettlementSchema.nullable() });
export const SettlementResultSchema = z.object({
  message: z.string(),
  settlement: SettlementSchema.nullable(),
  deposit: DepositDetailSchema,
});

export const PayoutChoiceSchema = z.object({
  available: z.boolean(),
  destination: z.string(),
  choice: z
    .object({
      status: z.string(),
      chosen_at: z.string().nullable(),
      paid: NullableMoneySchema,
      paid_at: z.string().nullable(),
    })
    .nullable(),
  partner: z.string().nullable(),
  risk_text: z.string(),
  confirmation_text: z.string(),
  explanation: z.string(),
});

// ------------------------------------------------------------ invest

export const CostsSchema = z.object({
  amount: MoneySchema,
  service_fee_bps: z.number(),
  ongoing_charges_bps: z.number(),
  transaction_cost_bps: z.number(),
  service_1y: MoneySchema,
  fund_1y: MoneySchema,
  transactions: MoneySchema,
  total_1y: MoneySchema,
  service_3y: MoneySchema,
  fund_3y: MoneySchema,
  total_3y: MoneySchema,
  percent_per_year: z.number(),
  note: z.string(),
});

/** Buy and switch quotes carry full Costs; a sell quote only transaction costs and a note. */
export const QuoteCostsSchema = CostsSchema.partial();

export const ScenariosSchema = z.object({
  note: z.string(),
  items: z.array(
    z.object({
      key: z.string(),
      label: z.string(),
      yearly_return: z.number(),
      value_after_1y: MoneySchema,
      value_after_3y: MoneySchema,
      result_1y: MoneySchema,
      result_3y: MoneySchema,
    }),
  ),
});

export const PortfolioSchema = z.object({
  code: z.string(),
  label: z.string(),
  risk: z.number().int(),
  risk_scale: z.number().int(),
  summary: z.string(),
  funds: z.array(
    z.object({
      fund: z.string(),
      name: z.string(),
      asset: z.string(),
      weight_bps: z.number(),
      ongoing_charges_bps: z.number(),
    }),
  ),
});

export const PortfoliosSchema = z.object({
  amount: MoneySchema,
  fee_rate_bps: z.number(),
  current: z.string().nullable(),
  risk_text: z.string(),
  advice_note: z.string(),
  items: z.array(PortfolioSchema.extend({ costs: CostsSchema, scenarios: ScenariosSchema })),
});

export const AppropriatenessSchema = z.object({
  result: z.string(),
  reasons: z.array(z.string()),
  reason_keys: z.array(z.string()),
  created_at: z.string(),
  warning_confirmed_at: z.string().nullable(),
  may_continue: z.boolean(),
  requires_confirmation: z.boolean(),
  confirmation_text: z.string().nullable(),
  risk_text: z.string().optional(),
});

export const AppropriatenessQuestionsSchema = z.object({
  version: z.string(),
  can_answer: z.boolean(),
  latest: AppropriatenessSchema.nullable(),
  questions: z.array(
    z.object({
      key: z.string(),
      text: z.string(),
      options: z.array(z.object({ value: z.string(), label: z.string() })),
    }),
  ),
});

export const TermsSchema = z.object({
  partner: z.object({ name: z.string(), version: z.string(), text: z.string() }),
  depiqo: z.object({ version: z.string(), text: z.string() }),
  accepted: z
    .object({
      partner_version: z.string().nullable(),
      partner_at: z.string().nullable(),
      depiqo_version: z.string().nullable(),
      depiqo_at: z.string().nullable(),
    })
    .nullable(),
  risk_text: z.string(),
});

export const TermsAcceptedSchema = z.object({
  accepted: z.boolean(),
  partner_version: z.string(),
  depiqo_version: z.string(),
});

export const InvestAccountSchema = z.object({
  reference: z.string(),
  status: z.string(),
  status_label: z.string(),
  portfolio: z.string().nullable(),
  portfolio_label: z.string().nullable(),
  pending_switch: z.string().nullable(),
  switch_note: z.string().nullable(),
  fee_rate_bps: z.number().nullable(),
  pending_fee_bps: z.number().nullable(),
  own_iban: z
    .object({
      masked: z.string(),
      registered_at: z.string().nullable(),
      usable_from: z.string().nullable(),
      usable_now: z.boolean(),
    })
    .nullable(),
  opened_at: z.string().nullable(),
  activated_at: z.string().nullable(),
});

export const OpenAccountResultSchema = z.object({ account: InvestAccountSchema, message: z.string() });

export const DepositInstructionsSchema = z.object({
  iban: z.string(),
  beneficiary: z.string(),
  reference: z.string(),
  sandbox: z.boolean(),
  note: z.string(),
});

export const InvestSummarySchema = z.object({
  day: z.string(),
  value: MoneySchema,
  invested_value: MoneySchema,
  cash: MoneySchema,
  available: MoneySchema,
  reserved: MoneySchema,
  net_deposits: MoneySchema,
  result: MoneySchema,
  result_pct: z.number().nullable(),
  fees_paid: MoneySchema,
  accrued_fee: MoneySchema,
  sellable: MoneySchema,
  fee_rate_bps: z.number(),
  positions: z.array(
    z.object({
      fund: z.string(),
      name: z.string(),
      asset: z.string(),
      units_1e4: z.number(),
      units: z.string(),
      price_1e4: z.number(),
      value: MoneySchema,
    }),
  ),
});

export const SandboxDepositResultSchema = z.object({ result: z.string(), summary: InvestSummarySchema });

const PointsSchema = z.array(z.tuple([z.string(), z.number()]));
export const ChartSeriesSchema = z.object({
  '1M': PointsSchema,
  '6M': PointsSchema,
  '1Y': PointsSchema,
  max: PointsSchema,
});

export const WithdrawalSchema = z.object({
  id: z.number().int(),
  amount: MoneySchema,
  iban_masked: z.string(),
  status: z.string(),
  status_label: z.string(),
  day: z.string().nullable(),
  created_at: z.string(),
});
export const WithdrawalsPageSchema = page(WithdrawalSchema);

export const InvestOverviewSchema = z.object({
  partner: z.object({ name: z.string(), sandbox: z.boolean() }),
  role_text: z.string(),
  separation_text: z.string(),
  risk_text: z.string(),
  offered_by_landlord: z.boolean(),
  minimum_order: MoneySchema,
  account: InvestAccountSchema.nullable(),
  onboarding: z
    .object({
      next_step: z.string(),
      offered_by_landlord: z.boolean(),
      terms_accepted: z.boolean(),
      appropriateness: AppropriatenessSchema.nullable(),
    })
    .nullable(),
  summary: InvestSummarySchema.nullable(),
  chart: ChartSeriesSchema.nullable(),
  chart_net_deposits: ChartSeriesSchema.nullable(),
  costs: CostsSchema.nullable(),
  withdrawals: z.array(WithdrawalSchema),
});

export const QuoteSchema = z.object({
  quote_id: z.string(),
  side: z.string(),
  amount: MoneySchema,
  sell_all: z.boolean(),
  portfolio: PortfolioSchema,
  costs: QuoteCostsSchema,
  scenarios: ScenariosSchema.nullable(),
  risk_text: z.string(),
  separation_text: z.string(),
  role_text: z.string(),
  execution_note: z.string(),
  available: MoneySchema,
  sellable: MoneySchema,
  current_value: MoneySchema,
  requires_risk_acknowledgement: z.literal(true),
  created_at: z.string(),
  expires_at: z.string(),
});

export const OrderSchema = z.object({
  id: z.number().int(),
  side: z.string(),
  portfolio: z.string(),
  portfolio_label: z.string(),
  amount: NullableMoneySchema,
  sell_all: z.boolean(),
  purpose: z.string(),
  status: z.string(),
  status_label: z.string(),
  executed_amount: NullableMoneySchema,
  executed_day: z.string().nullable(),
  created_at: z.string(),
  error: z.string().nullable(),
});
export const OrdersPageSchema = page(OrderSchema);

export const PlaceOrderResultSchema = z.object({
  order: OrderSchema.nullable(),
  message: z.string(),
  account: InvestAccountSchema,
});

export const RegisterIbanResultSchema = z.object({
  account: InvestAccountSchema,
  usable_from: z.string(),
  usable_now: z.boolean(),
  cooling_off_days: z.number().int(),
  message: z.string(),
});

export const WithdrawResultSchema = z.object({ withdrawal: WithdrawalSchema, message: z.string() });

export const InvestTransactionSchema = z.object({
  id: z.number().int(),
  kind: z.string(),
  amount: MoneySchema,
  description: z.string().nullable(),
  day: z.string(),
  at: z.string().nullable(),
});
export const InvestTransactionsPageSchema = page(InvestTransactionSchema);

export const StatementsSchema = z.object({
  items: z.array(z.object({ period: z.string(), label: z.string(), download_path: z.string() })),
});

export const FeeChangeSchema = z.object({
  current_bps: z.number().nullable(),
  pending_bps: z.number().nullable(),
  proposed_at: z.string().nullable(),
  accept_text: z.string().nullable(),
  note: z.string(),
});
export const FeeChangeAcceptedSchema = z.object({ account: InvestAccountSchema, message: z.string() });

// ------------------------------------------------------------ types

export type Money = z.infer<typeof MoneySchema>;
export type Config = z.infer<typeof ConfigSchema>;
export type TokenPair = z.infer<typeof TokenPairSchema>;
export type Session = z.infer<typeof SessionSchema>;
export type MfaChallenge = z.infer<typeof MfaChallengeSchema>;
export type LoginResponse = z.infer<typeof LoginResponseSchema>;
export type Device = z.infer<typeof DeviceSchema>;
export type Invite = z.infer<typeof InviteSchema>;
export type AcceptInviteResponse = z.infer<typeof AcceptInviteResponseSchema>;
export type Me = z.infer<typeof MeSchema>;
export type NotificationPreferences = z.infer<typeof NotificationPreferencesSchema>;
export type DeletionInfo = z.infer<typeof DeletionInfoSchema>;
export type DeleteResult = z.infer<typeof DeleteResultSchema>;
export type AppNotification = z.infer<typeof NotificationSchema>;
export type NotificationsPage = z.infer<typeof NotificationsPageSchema>;
export type ActivityItem = z.infer<typeof ActivityItemSchema>;
export type SupportTicket = z.infer<typeof SupportTicketSchema>;
export type Amount = z.infer<typeof AmountSchema>;
export type DepositSummary = z.infer<typeof DepositSummarySchema>;
export type DepositDetail = z.infer<typeof DepositDetailSchema>;
export type DepositEvent = z.infer<typeof DepositEventSchema>;
export type Location = z.infer<typeof LocationSchema>;
export type DepositDocument = z.infer<typeof DocumentSchema>;
export type Documents = z.infer<typeof DocumentsSchema>;
export type Settlement = z.infer<typeof SettlementSchema>;
export type SettlementResult = z.infer<typeof SettlementResultSchema>;
export type PayoutChoice = z.infer<typeof PayoutChoiceSchema>;
export type IdentityResult = z.infer<typeof IdentityResultSchema>;
export type Costs = z.infer<typeof CostsSchema>;
export type QuoteCosts = z.infer<typeof QuoteCostsSchema>;
export type Scenarios = z.infer<typeof ScenariosSchema>;
export type Portfolio = z.infer<typeof PortfolioSchema>;
export type Portfolios = z.infer<typeof PortfoliosSchema>;
export type Appropriateness = z.infer<typeof AppropriatenessSchema>;
export type AppropriatenessQuestions = z.infer<typeof AppropriatenessQuestionsSchema>;
export type Terms = z.infer<typeof TermsSchema>;
export type InvestAccount = z.infer<typeof InvestAccountSchema>;
export type InvestSummary = z.infer<typeof InvestSummarySchema>;
export type ChartSeries = z.infer<typeof ChartSeriesSchema>;
export type InvestOverview = z.infer<typeof InvestOverviewSchema>;
export type DepositInstructions = z.infer<typeof DepositInstructionsSchema>;
export type Quote = z.infer<typeof QuoteSchema>;
export type Order = z.infer<typeof OrderSchema>;
export type Withdrawal = z.infer<typeof WithdrawalSchema>;
export type InvestTransaction = z.infer<typeof InvestTransactionSchema>;
export type Statements = z.infer<typeof StatementsSchema>;
export type FeeChange = z.infer<typeof FeeChangeSchema>;

export type Page<T> = { items: T[]; next_cursor: string | null };
