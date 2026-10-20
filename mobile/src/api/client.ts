/**
 * A small fetch client for the Depiqo API (pure: no React Native imports; storage and fetch are injected).
 *
 * - Bearer token only, `credentials: "omit"` (the backend refuses cookie auth).
 * - Accept-Language, X-App-Platform and X-App-Version on every request.
 * - Single-flight refresh: all callers that need a new access token share ONE refresh promise. The
 *   backend revokes the whole device session when a used refresh token shows up again
 *   (refresh_token_reused), so two refreshes in parallel would log the user out.
 * - The new token pair is stored before the old one is dropped.
 * - A 401 that ends the session (token_invalid, device_revoked, refresh_token_reused...) clears the
 *   tokens and notifies listeners, which log the user out.
 * - Responses are validated with zod at this boundary.
 * - Nothing here logs tokens, bodies or personal data.
 */
import type { ZodType, ZodTypeDef } from 'zod';

import { ApiError, clientError, errorFromBody, SESSION_ENDING_CODES } from './errors';
import { TokenPairSchema } from './schemas';

export interface TokenSet {
  accessToken: string;
  accessExpiresAt: string | null;
  refreshToken: string;
  refreshExpiresAt: string | null;
  deviceId: number | null;
}

export interface TokenStore {
  load(): Promise<TokenSet | null>;
  save(tokens: TokenSet): Promise<void>;
  clear(): Promise<void>;
}

export interface HttpResponseLike {
  status: number;
  headers: { get(name: string): string | null };
  text(): Promise<string>;
}

export interface HttpRequestInit {
  method: string;
  headers: Record<string, string>;
  body?: string | FormData;
  credentials: 'omit';
  signal?: AbortSignal;
}

export type FetchLike = (url: string, init: HttpRequestInit) => Promise<HttpResponseLike>;

export interface ApiClientOptions {
  /** Host without /api/v1, e.g. https://app.getdepiqo.com */
  baseUrl: string;
  tokenStore: TokenStore;
  fetchImpl: FetchLike;
  getLanguage: () => string;
  platform: string;
  appVersion: string;
  timeoutMs?: number;
  /** Refresh this long before the access token expires (device clocks drift). */
  refreshSkewMs?: number;
  now?: () => number;
}

export type AuthMode = 'required' | 'none' | 'optional';
export type HttpMethod = 'GET' | 'POST' | 'PATCH' | 'DELETE';

export interface RequestOptions<T> {
  method?: HttpMethod;
  query?: Record<string, string | number | null | undefined>;
  body?: unknown;
  form?: FormData;
  schema?: ZodType<T, ZodTypeDef, unknown>;
  auth?: AuthMode;
  idempotencyKey?: string;
  expect?: 'json' | 'none' | 'text';
}

export const API_PREFIX = '/api/v1';

export class ApiClient {
  private tokens: TokenSet | null = null;
  private loaded = false;
  private loading: Promise<TokenSet | null> | null = null;
  private refreshing: Promise<TokenSet> | null = null;
  private generation = 0;
  private readonly sessionListeners = new Set<(code: string) => void>();
  private readonly updateListeners = new Set<(minimumVersion: string | null) => void>();

  constructor(private readonly opts: ApiClientOptions) {}

  // ------------------------------------------------------------ listeners

  /** Called once when the session ends (revoked, reused refresh token, invalid token). */
  onSessionEnded(fn: (code: string) => void): () => void {
    this.sessionListeners.add(fn);
    return () => {
      this.sessionListeners.delete(fn);
    };
  }

  /** Called on 426 app_update_required. */
  onUpdateRequired(fn: (minimumVersion: string | null) => void): () => void {
    this.updateListeners.add(fn);
    return () => {
      this.updateListeners.delete(fn);
    };
  }

  // ------------------------------------------------------------ session

  async getTokens(): Promise<TokenSet | null> {
    if (this.loaded) return this.tokens;
    if (!this.loading) {
      const gen = this.generation;
      this.loading = this.opts.tokenStore.load().then((t) => {
        if (gen === this.generation && !this.loaded) {
          this.tokens = t;
          this.loaded = true;
        }
        this.loading = null;
        return this.tokens;
      });
    }
    return this.loading;
  }

  async hasSession(): Promise<boolean> {
    return (await this.getTokens()) !== null;
  }

  async setSession(tokens: TokenSet): Promise<void> {
    this.generation += 1;
    this.refreshing = null;
    await this.opts.tokenStore.save(tokens);
    this.tokens = tokens;
    this.loaded = true;
  }

  /** Forget the session on this device (does not call the server; see AuthProvider.signOut). */
  async clearSession(): Promise<void> {
    this.generation += 1;
    this.tokens = null;
    this.loaded = true;
    this.refreshing = null;
    await this.opts.tokenStore.clear();
  }

  private async endSession(code: string): Promise<void> {
    const had = this.tokens !== null;
    await this.clearSession();
    if (had) {
      for (const fn of Array.from(this.sessionListeners)) fn(code);
    }
  }

  private emitUpdate(err: ApiError): void {
    const min = err.fields.minimum_version;
    for (const fn of Array.from(this.updateListeners)) fn(typeof min === 'string' ? min : null);
  }

  // ------------------------------------------------------------ urls and headers

  /** Absolute URL for an API path. Accepts "/deposits" or a server-given "/api/v1/..." path only. */
  url(path: string, query?: RequestOptions<unknown>['query']): string {
    if (!path.startsWith('/') || path.startsWith('//') || path.includes('..')) {
      throw clientError('invalid_response');
    }
    const full = path.startsWith(API_PREFIX + '/') ? path : API_PREFIX + path;
    const qs = query
      ? Object.entries(query)
          .filter(([, v]) => v !== undefined && v !== null && v !== '')
          .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
          .join('&')
      : '';
    return this.opts.baseUrl.replace(/\/+$/, '') + full + (qs ? `?${qs}` : '');
  }

  headers(token: string | null, extra?: { idempotencyKey?: string; json?: boolean }): Record<string, string> {
    const h: Record<string, string> = {
      Accept: 'application/json',
      'Accept-Language': this.opts.getLanguage(),
      'X-App-Platform': this.opts.platform,
      'X-App-Version': this.opts.appVersion,
    };
    if (token) h.Authorization = `Bearer ${token}`;
    if (extra?.idempotencyKey) h['Idempotency-Key'] = extra.idempotencyKey;
    if (extra?.json) h['Content-Type'] = 'application/json';
    return h;
  }

  // ------------------------------------------------------------ tokens

  private now(): number {
    return this.opts.now ? this.opts.now() : Date.now();
  }

  private isAccessExpired(t: TokenSet): boolean {
    if (!t.accessExpiresAt) return false;
    const exp = Date.parse(t.accessExpiresAt);
    if (!Number.isFinite(exp)) return false;
    return exp - (this.opts.refreshSkewMs ?? 30_000) <= this.now();
  }

  /** A usable access token, refreshing first (single flight) when it has expired. */
  async getFreshAccessToken(): Promise<string> {
    const t = await this.getTokens();
    if (!t) throw clientError('not_signed_in', 401);
    if (this.isAccessExpired(t)) return (await this.refresh()).accessToken;
    return t.accessToken;
  }

  /** Exchange the refresh token for a new pair. Concurrent callers share one request. */
  refresh(): Promise<TokenSet> {
    if (this.refreshing) return this.refreshing;
    const p = this.doRefresh();
    this.refreshing = p;
    const clear = () => {
      if (this.refreshing === p) this.refreshing = null;
    };
    p.then(clear, clear);
    return p;
  }

  private async doRefresh(): Promise<TokenSet> {
    const current = await this.getTokens();
    if (!current) throw clientError('not_signed_in', 401);
    const gen = this.generation;
    const res = await this.send('/auth/refresh', { method: 'POST', body: { refresh_token: current.refreshToken } }, null);
    const text = await res.text();
    if (res.status === 200) {
      let pair;
      try {
        pair = TokenPairSchema.parse(JSON.parse(text));
      } catch {
        throw clientError('invalid_response', res.status);
      }
      const next: TokenSet = {
        accessToken: pair.access_token,
        accessExpiresAt: pair.access_expires_at,
        refreshToken: pair.refresh_token,
        refreshExpiresAt: pair.refresh_expires_at,
        deviceId: pair.device_id,
      };
      if (gen !== this.generation) throw clientError('session_ended', 401); // signed out meanwhile
      await this.opts.tokenStore.save(next); // store the new pair before the old one is dropped
      if (gen !== this.generation) {
        // A sign-out happened while saving: make sure nothing stays behind.
        await this.opts.tokenStore.clear();
        throw clientError('session_ended', 401);
      }
      this.tokens = next;
      this.loaded = true;
      return next;
    }
    const err = errorFromBody(res.status, text, res.headers.get('Retry-After'));
    if (res.status === 426) this.emitUpdate(err);
    if (res.status === 401 || res.status === 403) await this.endSession(err.code);
    throw err;
  }

  // ------------------------------------------------------------ requests

  private async send(path: string, o: RequestOptions<unknown>, token: string | null): Promise<HttpResponseLike> {
    const json = o.form === undefined && o.body !== undefined;
    const body = o.form !== undefined ? o.form : json ? JSON.stringify(o.body) : undefined;
    const controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      controller?.abort();
    }, this.opts.timeoutMs ?? 20_000);
    try {
      return await this.opts.fetchImpl(this.url(path, o.query), {
        method: o.method ?? 'GET',
        headers: this.headers(token, { idempotencyKey: o.idempotencyKey, json }),
        body,
        credentials: 'omit',
        signal: controller?.signal,
      });
    } catch (e) {
      if (e instanceof ApiError) throw e;
      throw clientError(timedOut ? 'timeout' : 'network_error');
    } finally {
      clearTimeout(timer);
    }
  }

  /** Token to retry with after a 401 token_expired: one another caller already got, or a fresh refresh. */
  private async tokenAfterExpiry(usedToken: string): Promise<string> {
    const latest = await this.getTokens();
    if (!latest) throw clientError('session_ended', 401);
    if (latest.accessToken !== usedToken) return latest.accessToken;
    return (await this.refresh()).accessToken;
  }

  async request<T = unknown>(path: string, o: RequestOptions<T> = {}): Promise<T> {
    const mode = o.auth ?? 'required';
    let token: string | null = null;
    if (mode === 'required') token = await this.getFreshAccessToken();
    else if (mode === 'optional' && (await this.getTokens())) token = await this.getFreshAccessToken();

    let res = await this.send(path, o, token);
    if (res.status === 401 && token) {
      const err = errorFromBody(401, await res.text(), null);
      if (err.code !== 'token_expired') {
        if (SESSION_ENDING_CODES.has(err.code)) await this.endSession(err.code);
        throw err;
      }
      // Same request, same Idempotency-Key, new token.
      res = await this.send(path, o, await this.tokenAfterExpiry(token));
      if (res.status === 401) {
        const err2 = errorFromBody(401, await res.text(), null);
        if (SESSION_ENDING_CODES.has(err2.code)) await this.endSession(err2.code);
        throw err2;
      }
    }
    return this.finish(res, o);
  }

  private async finish<T>(res: HttpResponseLike, o: RequestOptions<T>): Promise<T> {
    const text = await res.text();
    if (res.status < 200 || res.status >= 300) {
      const err = errorFromBody(res.status, text, res.headers.get('Retry-After'));
      if (res.status === 426) this.emitUpdate(err);
      throw err;
    }
    const expect = o.expect ?? 'json';
    if (expect === 'none') return undefined as T;
    if (expect === 'text') return text as unknown as T;
    let data: unknown;
    try {
      data = text ? JSON.parse(text) : null;
    } catch {
      throw clientError('invalid_response', res.status);
    }
    if (!o.schema) return data as T;
    const parsed = o.schema.safeParse(data);
    if (!parsed.success) throw clientError('invalid_response', res.status);
    return parsed.data;
  }

  /**
   * Run a non-JSON request (file download) with the bearer token, refreshing once on 401.
   * `fn` gets the headers to send and returns something with a status.
   */
  async runAuthorized<R extends { status: number }>(fn: (headers: Record<string, string>) => Promise<R>): Promise<R> {
    const token = await this.getFreshAccessToken();
    let r = await fn(this.headers(token));
    if (r.status === 401) {
      r = await fn(this.headers(await this.tokenAfterExpiry(token)));
      if (r.status === 401) await this.endSession('token_invalid');
    }
    return r;
  }
}
