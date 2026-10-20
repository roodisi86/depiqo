/**
 * Errors from the Depiqo API, always {"error": {"code", "message", "fields", "detail?"}}, plus a few
 * client-side codes (network_error, timeout, invalid_response, not_signed_in, session_ended).
 * Pure module: no React Native imports, so it runs in plain Node tests.
 */
export type ErrorFields = Record<string, unknown>;

export const CLIENT_ERROR_CODES = ['network_error', 'timeout', 'invalid_response', 'not_signed_in', 'session_ended', 'unknown'] as const;

/** 401 codes after which the device session is gone and the user must log in again. */
export const SESSION_ENDING_CODES: ReadonlySet<string> = new Set([
  'token_missing',
  'token_invalid',
  'token_expired',
  'device_revoked',
  'refresh_token_reused',
]);

const STATUS_FALLBACK: Record<number, string> = {
  400: 'bad_request',
  401: 'unauthorized',
  403: 'forbidden',
  404: 'not_found',
  405: 'method_not_allowed',
  409: 'conflict',
  410: 'invite_expired',
  413: 'file_too_large',
  415: 'unsupported_media_type',
  422: 'validation_failed',
  426: 'app_update_required',
  429: 'rate_limited',
  // A 503 without a JSON body is an outage (proxy, deploy), not partner_unavailable: falls to server_error.
};

export interface ApiErrorInit {
  status: number;
  code: string;
  message?: string;
  fields?: ErrorFields;
  detail?: string | null;
  retryAfter?: number | null;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly fields: ErrorFields;
  readonly detail: string | null;
  readonly retryAfter: number | null;
  /** The message as the server wrote it (already in the Accept-Language). Empty for client errors. */
  readonly serverMessage: string;

  constructor(init: ApiErrorInit) {
    super(init.message || init.code);
    Object.setPrototypeOf(this, ApiError.prototype);
    this.name = 'ApiError';
    this.status = init.status;
    this.code = init.code;
    this.fields = init.fields ?? {};
    this.detail = init.detail ?? null;
    this.retryAfter = init.retryAfter ?? null;
    this.serverMessage = init.message ?? '';
  }

  /** True when the request may not have reached the server (or its answer got lost). */
  get isNetwork(): boolean {
    return this.code === 'network_error' || this.code === 'timeout';
  }

  /** The message for one input field, if the server sent one. */
  fieldMessage(name: string): string | null {
    const v = this.fields[name];
    return typeof v === 'string' ? v : null;
  }
}

export function isApiError(e: unknown): e is ApiError {
  return e instanceof ApiError;
}

export function hasCode(e: unknown, code: string): boolean {
  return isApiError(e) && e.code === code;
}

function parseRetryAfter(value: string | null | undefined): number | null {
  if (!value) return null;
  const n = Number(value);
  return Number.isFinite(n) && n >= 0 ? n : null;
}

/** Builds an ApiError from a non-2xx response body (JSON or not). Never throws. */
export function errorFromBody(status: number, bodyText: string, retryAfterHeader?: string | null): ApiError {
  let parsed: unknown = null;
  try {
    parsed = bodyText ? JSON.parse(bodyText) : null;
  } catch {
    parsed = null;
  }
  const err = parsed && typeof parsed === 'object' ? (parsed as { error?: unknown }).error : null;
  if (err && typeof err === 'object' && typeof (err as { code?: unknown }).code === 'string') {
    const e = err as { code: string; message?: unknown; fields?: unknown; detail?: unknown };
    return new ApiError({
      status,
      code: e.code,
      message: typeof e.message === 'string' ? e.message : '',
      fields: e.fields && typeof e.fields === 'object' && !Array.isArray(e.fields) ? (e.fields as ErrorFields) : {},
      detail: typeof e.detail === 'string' ? e.detail : null,
      retryAfter: parseRetryAfter(retryAfterHeader),
    });
  }
  const code = STATUS_FALLBACK[status] ?? (status >= 500 ? 'server_error' : 'unknown');
  return new ApiError({ status, code, message: '', retryAfter: parseRetryAfter(retryAfterHeader) });
}

export function clientError(code: (typeof CLIENT_ERROR_CODES)[number], status = 0): ApiError {
  return new ApiError({ status, code, message: '' });
}
