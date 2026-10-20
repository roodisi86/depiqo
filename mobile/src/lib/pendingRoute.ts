/**
 * Where to go after login or unlock (a deep link or a notification that arrived while signed out).
 * Kept in memory only; it never holds tokens.
 */
let pending: string | null = null;

const IGNORED = new Set(['/', '/login', '/mfa', '/lock']);

export function setPendingRoute(path: string | null | undefined): void {
  if (!path || IGNORED.has(path) || !path.startsWith('/')) return;
  pending = path;
}

export function peekPendingRoute(): string | null {
  return pending;
}

export function clearPendingRoute(): void {
  pending = null;
}
