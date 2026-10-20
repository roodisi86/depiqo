import { isOwnWebLink, linkPath, parseDeepLink, requiresAuth, routeFor } from '../deeplink';

const TOKEN = 'k6XlRILPmjGqdPzbIzYSTHH6PPcCrexqfe5GyL9R-qs';

describe('deep links', () => {
  it('parses invitation links (universal link and custom scheme)', () => {
    expect(parseDeepLink(`https://app.getdepiqo.com/t/${TOKEN}`)).toEqual({ kind: 'invite', token: TOKEN });
    expect(parseDeepLink(`depiqo://t/${TOKEN}`)).toEqual({ kind: 'invite', token: TOKEN });
    expect(parseDeepLink(`https://APP.getdepiqo.com/t/${TOKEN}?utm=x#y`)).toEqual({ kind: 'invite', token: TOKEN });
    expect(parseDeepLink(`/t/${TOKEN}`)).toEqual({ kind: 'invite', token: TOKEN });
  });

  it('parses notification links', () => {
    expect(parseDeepLink('/app-link/borg/9xeunnxp8zx2')).toEqual({ kind: 'deposit', pid: '9xeunnxp8zx2' });
    expect(parseDeepLink('https://app.getdepiqo.com/app-link/beleggen')).toEqual({ kind: 'invest' });
    expect(parseDeepLink('/app-link/beveiliging')).toEqual({ kind: 'security' });
    expect(parseDeepLink('/app-link/support/12')).toEqual({ kind: 'support', id: 12 });
    expect(parseDeepLink('/app-link/support')).toEqual({ kind: 'support', id: null });
  });

  it('ignores other hosts, schemes and malformed paths', () => {
    expect(parseDeepLink(`https://evil.example/t/${TOKEN}`)).toBeNull();
    expect(parseDeepLink(`http://app.getdepiqo.com/t/${TOKEN}`)).toBeNull();
    expect(parseDeepLink(`https://app.getdepiqo.com.evil.example/t/${TOKEN}`)).toBeNull();
    expect(parseDeepLink('otherapp://t/abc')).toBeNull();
    expect(parseDeepLink('/t/short')).toBeNull();
    expect(parseDeepLink('/t/has%20escape%20characters%20in%20it')).toBeNull();
    expect(parseDeepLink(`/t/${TOKEN}/extra`)).toBeNull();
    expect(parseDeepLink('/app-link/borg/../../admin')).toBeNull();
    expect(parseDeepLink('/app-link/support/abc')).toBeNull();
    expect(parseDeepLink('/app-link/unknown')).toBeNull();
    expect(parseDeepLink('javascript:alert(1)')).toBeNull();
    expect(parseDeepLink('')).toBeNull();
    expect(parseDeepLink(null)).toBeNull();
    expect(parseDeepLink('/t/' + 'a'.repeat(600))).toBeNull();
  });

  it('maps links to app screens', () => {
    expect(routeFor({ kind: 'invite', token: TOKEN })).toBe(`/t/${TOKEN}`);
    expect(routeFor({ kind: 'deposit', pid: 'abc123' })).toBe('/deposit/abc123');
    expect(routeFor({ kind: 'invest' })).toBe('/invest');
    expect(routeFor({ kind: 'security' })).toBe('/settings/devices');
    expect(routeFor({ kind: 'support', id: 5 })).toBe('/support/5');
    expect(routeFor({ kind: 'support', id: null })).toBe('/support');
  });

  it('lets invitations through without login and guards everything else', () => {
    expect(requiresAuth({ kind: 'invite', token: TOKEN })).toBe(false);
    expect(requiresAuth({ kind: 'deposit', pid: 'abc123' })).toBe(true);
  });

  it('recognises our own web links and paths', () => {
    expect(isOwnWebLink('https://staging.getdepiqo.com/whatever')).toBe(true);
    expect(isOwnWebLink('https://example.com/')).toBe(false);
    expect(linkPath('depiqo-dev://app-link/beleggen')).toBe('/app-link/beleggen');
  });
});
