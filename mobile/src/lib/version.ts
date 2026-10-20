/** App version checks against /config minimum_app_version (pure). Same rule as the backend. */
export function versionTuple(v: string | null | undefined): [number, number, number] {
  const parts = (v ?? '').match(/\d+/g) ?? [];
  const n = parts.slice(0, 3).map((p) => Number(p));
  while (n.length < 3) n.push(0);
  return [n[0] ?? 0, n[1] ?? 0, n[2] ?? 0];
}

export function compareVersions(a: string, b: string): number {
  const x = versionTuple(a);
  const y = versionTuple(b);
  for (let i = 0; i < 3; i += 1) {
    const d = (x[i] ?? 0) - (y[i] ?? 0);
    if (d !== 0) return d < 0 ? -1 : 1;
  }
  return 0;
}

export function isBelowMinimum(appVersion: string, minimum: string | null | undefined): boolean {
  if (!minimum) return false;
  return compareVersions(appVersion, minimum) < 0;
}
