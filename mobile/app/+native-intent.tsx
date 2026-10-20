/**
 * Incoming links from the system (universal links, App Links, depiqo://). Known links are mapped to an
 * app screen; other links to our own domain go to the start screen; anything else is passed on unchanged
 * (e.g. the development client's own URLs).
 */
import { isOwnWebLink, parseDeepLink, routeFor } from '../src/lib/deeplink';

export function redirectSystemPath({ path }: { path: string; initial: boolean }): string {
  try {
    const link = parseDeepLink(path);
    if (link) return routeFor(link);
    if (isOwnWebLink(path) || path.startsWith('/app-link')) return '/';
    return path;
  } catch {
    return '/';
  }
}
