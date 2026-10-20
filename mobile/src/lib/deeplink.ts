/**
 * Deep links (pure).
 *
 * Accepted:
 *   https://app.getdepiqo.com/t/<token>          invitation (also depiqo://t/<token>)
 *   https://app.getdepiqo.com/app-link/borg/<pid>  a deposit (from notifications and push)
 *   /app-link/beleggen                             Invest
 *   /app-link/beveiliging                          devices and security
 *   /app-link/support/<id>                         a support question
 * Anything else is ignored. The parser is strict on purpose: a link must never take the app to an
 * arbitrary place or carry arbitrary data. React Native's URL class is incomplete, so this parses by hand.
 */
export type DeepLink =
  | { kind: 'invite'; token: string }
  | { kind: 'deposit'; pid: string }
  | { kind: 'invest' }
  | { kind: 'security' }
  | { kind: 'support'; id: number | null };

export const LINK_HOSTS = ['app.getdepiqo.com', 'staging.getdepiqo.com'] as const;
export const LINK_SCHEMES = ['depiqo', 'depiqo-staging', 'depiqo-dev'] as const;

const TOKEN = /^[A-Za-z0-9_-]{16,200}$/;
const PID = /^[A-Za-z0-9_-]{4,64}$/;
const ID = /^[1-9][0-9]{0,9}$/;
const URL_RE = /^([a-zA-Z][a-zA-Z0-9+.-]*):\/\/([^/?#]*)([^?#]*)(\?[^#]*)?(#.*)?$/;

/** The path part of a link, or null when the link is not ours. */
export function linkPath(input: string): string | null {
  const s = input.trim();
  if (s.startsWith('/')) return s.split(/[?#]/)[0] ?? null;
  const m = URL_RE.exec(s);
  if (!m) return null;
  const scheme = (m[1] ?? '').toLowerCase();
  const host = (m[2] ?? '').toLowerCase();
  const path = m[3] ?? '';
  if (scheme === 'https') {
    return (LINK_HOSTS as readonly string[]).includes(host) ? path || '/' : null;
  }
  if ((LINK_SCHEMES as readonly string[]).includes(scheme)) {
    // depiqo://t/abc -> host "t", path "/abc"
    return `/${host}${path}`;
  }
  return null;
}

export function parseDeepLink(input: string | null | undefined): DeepLink | null {
  if (!input || input.length > 500) return null;
  const path = linkPath(input);
  if (!path) return null;
  const parts = path.split('/').filter((p) => p.length > 0);
  if (parts.length === 2 && parts[0] === 't' && TOKEN.test(parts[1] ?? '')) {
    return { kind: 'invite', token: parts[1] as string };
  }
  if (parts[0] !== 'app-link') return null;
  const [, section, arg] = parts;
  if (section === 'borg' && parts.length === 3 && PID.test(arg ?? '')) return { kind: 'deposit', pid: arg as string };
  if (section === 'beleggen' && parts.length === 2) return { kind: 'invest' };
  if (section === 'beveiliging' && parts.length === 2) return { kind: 'security' };
  if (section === 'support' && parts.length === 2) return { kind: 'support', id: null };
  if (section === 'support' && parts.length === 3 && ID.test(arg ?? '')) return { kind: 'support', id: Number(arg) };
  return null;
}

/** The screen in the app (expo-router path) for a link. */
export function routeFor(link: DeepLink): string {
  switch (link.kind) {
    case 'invite':
      return `/t/${link.token}`;
    case 'deposit':
      return `/deposit/${encodeURIComponent(link.pid)}`;
    case 'invest':
      return '/invest';
    case 'security':
      return '/settings/devices';
    case 'support':
      return link.id === null ? '/support' : `/support/${link.id}`;
  }
}

/** Invitations work without a session; everything else needs a signed-in, unlocked app. */
export function requiresAuth(link: DeepLink): boolean {
  return link.kind !== 'invite';
}

/** True for an https link to one of our hosts (used to send unknown paths home, not to a 404). */
export function isOwnWebLink(input: string): boolean {
  const m = URL_RE.exec(input.trim());
  return !!m && (m[1] ?? '').toLowerCase() === 'https' && (LINK_HOSTS as readonly string[]).includes((m[2] ?? '').toLowerCase());
}
