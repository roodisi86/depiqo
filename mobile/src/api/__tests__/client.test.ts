/**
 * The API client: auth header, single-flight refresh, revoke -> logout, idempotency key on retry,
 * error mapping. Pure: fetch and token storage are fakes.
 */
import { ApiClient, type FetchLike, type HttpRequestInit, type HttpResponseLike, type TokenSet, type TokenStore } from '../client';
import { ApiError } from '../errors';
import { MeSchema } from '../schemas';

const FUTURE = '2999-01-01T00:00:00+00:00';
const PAST = '2000-01-01T00:00:00+00:00';

const ME = {
  id: 8,
  name: 'Daan Visser',
  email: 'daan@huurder.test',
  two_factor_enabled: false,
  recovery_codes_left: null,
  created_at: '2026-10-20T12:17:27+00:00',
  language: 'nl',
  deposit_count: 1,
  notification_preferences: { push: { deposit: true, invest: true, security: true, support: true } },
  invest: { visibility: 'available', eligible: true, offered_by_landlord: true, account_status: 'active' },
};

function res(status: number, body?: unknown, headers: Record<string, string> = {}): HttpResponseLike {
  const text = body === undefined ? '' : typeof body === 'string' ? body : JSON.stringify(body);
  return {
    status,
    headers: { get: (name: string) => headers[name] ?? null },
    text: async () => text,
  };
}

const errorBody = (code: string, fields: Record<string, unknown> = {}) => ({ error: { code, message: `msg ${code}`, fields } });

function tokens(n: number, accessExpiresAt = FUTURE): TokenSet {
  return { accessToken: `A${n}`, refreshToken: `R${n}`, accessExpiresAt, refreshExpiresAt: FUTURE, deviceId: 1 };
}

function pair(n: number) {
  return { access_token: `A${n}`, access_expires_at: FUTURE, refresh_token: `R${n}`, refresh_expires_at: FUTURE, token_type: 'Bearer', expires_in: 900, device_id: 1 };
}

function memoryStore(initial: TokenSet | null) {
  let current: TokenSet | null = initial;
  const saves: TokenSet[] = [];
  const store: TokenStore = {
    load: async () => current,
    save: async (t) => {
      current = t;
      saves.push(t);
    },
    clear: async () => {
      current = null;
    },
  };
  return { store, saves, current: () => current };
}

interface Call {
  url: string;
  init: HttpRequestInit;
}

function setup(handler: (url: string, init: HttpRequestInit) => HttpResponseLike | Promise<HttpResponseLike>, initial: TokenSet | null = tokens(1)) {
  const calls: Call[] = [];
  const fetchImpl: FetchLike = async (url, init) => {
    calls.push({ url, init });
    return handler(url, init);
  };
  const mem = memoryStore(initial);
  const client = new ApiClient({ baseUrl: 'https://api.test', tokenStore: mem.store, fetchImpl, getLanguage: () => 'fr', platform: 'ios', appVersion: '1.0.0' });
  const ended = jest.fn();
  const update = jest.fn();
  client.onSessionEnded(ended);
  client.onUpdateRequired(update);
  return { client, calls, mem, ended, update };
}

const isRefresh = (url: string) => url.endsWith('/api/v1/auth/refresh');
const delay = (ms: number) => new Promise((r) => setTimeout(r, ms));

describe('ApiClient headers', () => {
  it('sends the bearer token, language and app headers, and omits cookies', async () => {
    const { client, calls } = setup(() => res(200, ME));
    const me = await client.request('/me', { schema: MeSchema });
    expect(me.email).toBe('daan@huurder.test');
    expect(calls).toHaveLength(1);
    const { url, init } = calls[0] as Call;
    expect(url).toBe('https://api.test/api/v1/me');
    expect(init.headers.Authorization).toBe('Bearer A1');
    expect(init.headers['Accept-Language']).toBe('fr');
    expect(init.headers['X-App-Platform']).toBe('ios');
    expect(init.headers['X-App-Version']).toBe('1.0.0');
    expect(init.credentials).toBe('omit');
  });

  it('never sends a token on public endpoints', async () => {
    const { client, calls } = setup(() => res(200, { ok: true }));
    await client.request('/config', { auth: 'none' });
    expect((calls[0] as Call).init.headers.Authorization).toBeUndefined();
  });

  it('builds query strings and accepts server paths under /api/v1 only', async () => {
    const { client } = setup(() => res(200, {}));
    expect(client.url('/deposits', { limit: 20, cursor: null })).toBe('https://api.test/api/v1/deposits?limit=20');
    expect(client.url('/api/v1/deposits/abc/documents/3')).toBe('https://api.test/api/v1/deposits/abc/documents/3');
    expect(() => client.url('https://evil.example/x')).toThrow();
    expect(() => client.url('//evil.example/x')).toThrow();
    expect(() => client.url('/deposits/../../admin')).toThrow();
  });

  it('refuses to call an authenticated endpoint without a session', async () => {
    const { client, calls } = setup(() => res(200, ME), null);
    await expect(client.request('/me')).rejects.toMatchObject({ code: 'not_signed_in' });
    expect(calls).toHaveLength(0);
  });
});

describe('single-flight refresh', () => {
  it('refreshes exactly once for many concurrent 401 token_expired answers', async () => {
    const { client, calls, mem } = setup(async (url, init) => {
      if (isRefresh(url)) {
        await delay(20);
        return res(200, pair(2));
      }
      if (init.headers.Authorization === 'Bearer A1') return res(401, errorBody('token_expired'));
      // The retried request must find the new pair already stored.
      expect(mem.current()?.accessToken).toBe('A2');
      return res(200, ME);
    });
    const results = await Promise.all([client.request('/me'), client.request('/deposits'), client.request('/activity')]);
    expect(results).toHaveLength(3);
    expect(calls.filter((c) => isRefresh(c.url))).toHaveLength(1);
    const refreshCall = calls.find((c) => isRefresh(c.url)) as Call;
    expect(JSON.parse(refreshCall.init.body as string)).toEqual({ refresh_token: 'R1' });
    expect(refreshCall.init.headers.Authorization).toBeUndefined();
    const retried = calls.filter((c) => !isRefresh(c.url) && c.init.headers.Authorization === 'Bearer A2');
    expect(retried).toHaveLength(3);
    expect(mem.saves).toHaveLength(1);
    expect(mem.saves[0]).toMatchObject({ accessToken: 'A2', refreshToken: 'R2' });
  });

  it('refreshes before the request when the access token has already expired', async () => {
    const { client, calls } = setup((url) => (isRefresh(url) ? res(200, pair(2)) : res(200, ME)), tokens(1, PAST));
    await client.request('/me');
    expect(calls.map((c) => c.url)).toEqual(['https://api.test/api/v1/auth/refresh', 'https://api.test/api/v1/me']);
    expect((calls[1] as Call).init.headers.Authorization).toBe('Bearer A2');
  });

  it('retries with a token another request already obtained, without a second refresh', async () => {
    const { client, calls } = setup(async (url, init) => {
      if (isRefresh(url)) {
        await delay(10);
        return res(200, pair(2));
      }
      if (init.headers.Authorization === 'Bearer A1') {
        // This answer arrives after the other request has finished refreshing.
        if (url.endsWith('/deposits')) await delay(40);
        return res(401, errorBody('token_expired'));
      }
      return res(200, ME);
    });
    await Promise.all([client.request('/me'), client.request('/deposits')]);
    expect(calls.filter((c) => isRefresh(c.url))).toHaveLength(1);
    expect(calls.filter((c) => c.url.endsWith('/deposits')).map((c) => c.init.headers.Authorization)).toEqual(['Bearer A1', 'Bearer A2']);
  });

  it('keeps the session when the refresh fails because of the network', async () => {
    const { client, mem, ended } = setup((url) => {
      if (isRefresh(url)) throw new Error('offline');
      return res(401, errorBody('token_expired'));
    });
    await expect(client.request('/me')).rejects.toMatchObject({ code: 'network_error' });
    expect(mem.current()?.refreshToken).toBe('R1');
    expect(ended).not.toHaveBeenCalled();
  });
});

describe('session end', () => {
  it('ends the session once when the refresh token was reused (device revoked by the server)', async () => {
    const { client, mem, ended } = setup(async (url) => {
      if (isRefresh(url)) {
        await delay(5);
        return res(401, errorBody('refresh_token_reused'));
      }
      return res(401, errorBody('token_expired'));
    });
    const outcomes = await Promise.allSettled([client.request('/me'), client.request('/deposits')]);
    for (const o of outcomes) {
      expect(o.status).toBe('rejected');
      if (o.status === 'rejected') expect((o.reason as ApiError).code).toBe('refresh_token_reused');
    }
    expect(ended).toHaveBeenCalledTimes(1);
    expect(ended).toHaveBeenCalledWith('refresh_token_reused');
    expect(mem.current()).toBeNull();
  });

  it('logs out on device_revoked without trying to refresh', async () => {
    const { client, calls, mem, ended } = setup(() => res(401, errorBody('device_revoked')));
    await expect(client.request('/me')).rejects.toMatchObject({ code: 'device_revoked' });
    expect(calls.filter((c) => isRefresh(c.url))).toHaveLength(0);
    expect(ended).toHaveBeenCalledWith('device_revoked');
    expect(mem.current()).toBeNull();
  });

  it('does not end the session for an ordinary error', async () => {
    const { client, ended, mem } = setup(() => res(404, errorBody('not_found')));
    await expect(client.request('/deposits/x')).rejects.toMatchObject({ code: 'not_found', status: 404 });
    expect(ended).not.toHaveBeenCalled();
    expect(mem.current()).not.toBeNull();
  });
});

describe('idempotency', () => {
  it('sends the same Idempotency-Key and body when a request is retried after a refresh', async () => {
    const { client, calls } = setup((url, init) => {
      if (isRefresh(url)) return res(200, pair(2));
      if (init.headers.Authorization === 'Bearer A1') return res(401, errorBody('token_expired'));
      return res(201, { ok: true });
    });
    await client.request('/invest/withdrawals', { method: 'POST', body: { amount_cents: 1000 }, idempotencyKey: 'key-0001-abcd' });
    const posts = calls.filter((c) => c.url.endsWith('/invest/withdrawals'));
    expect(posts).toHaveLength(2);
    expect(posts[0]?.init.headers['Idempotency-Key']).toBe('key-0001-abcd');
    expect(posts[1]?.init.headers['Idempotency-Key']).toBe('key-0001-abcd');
    expect(posts[0]?.init.body).toBe(posts[1]?.init.body);
    expect(posts[0]?.init.headers['Content-Type']).toBe('application/json');
  });
});

describe('error mapping', () => {
  it('maps validation errors with fields', async () => {
    const { client } = setup(() => res(422, errorBody('validation_failed', { email: 'Vul dit veld in.' })));
    const err = await client.request('/me', { method: 'PATCH', body: {} }).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).code).toBe('validation_failed');
    expect((err as ApiError).fieldMessage('email')).toBe('Vul dit veld in.');
    expect((err as ApiError).serverMessage).toBe('msg validation_failed');
  });

  it('reads Retry-After on 429', async () => {
    const { client } = setup(() => res(429, errorBody('too_many_attempts'), { 'Retry-After': '900' }));
    await expect(client.request('/auth/login', { method: 'POST', auth: 'none', body: {} })).rejects.toMatchObject({ code: 'too_many_attempts', retryAfter: 900 });
  });

  it('maps a non-JSON server error to server_error', async () => {
    const { client } = setup(() => res(502, '<html>Bad gateway</html>'));
    await expect(client.request('/me')).rejects.toMatchObject({ code: 'server_error', status: 502 });
  });

  it('keeps partner_unavailable as its own code', async () => {
    const { client } = setup(() => res(503, errorBody('partner_unavailable')));
    await expect(client.request('/invest')).rejects.toMatchObject({ code: 'partner_unavailable', status: 503 });
  });

  it('maps a thrown fetch to network_error', async () => {
    const { client } = setup(() => {
      throw new Error('Network request failed');
    });
    const err = (await client.request('/me').catch((e: unknown) => e)) as ApiError;
    expect(err.code).toBe('network_error');
    expect(err.isNetwork).toBe(true);
  });

  it('rejects a response that does not match the schema', async () => {
    const { client } = setup(() => res(200, { ...ME, notification_preferences: null }));
    await expect(client.request('/me', { schema: MeSchema })).rejects.toMatchObject({ code: 'invalid_response' });
  });

  it('tells listeners when the app is too old (426)', async () => {
    const { client, update } = setup(() => res(426, errorBody('app_update_required', { minimum_version: '1.2.0' })));
    await expect(client.request('/me')).rejects.toMatchObject({ code: 'app_update_required' });
    expect(update).toHaveBeenCalledWith('1.2.0');
  });

  it('returns nothing for 204 when no body is expected', async () => {
    const { client } = setup(() => res(204));
    await expect(client.request('/auth/logout', { method: 'POST', expect: 'none' })).resolves.toBeUndefined();
  });
});
