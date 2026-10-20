/** Geometry for the simple line chart (pure). Values are cents from the API series. */
export type Point = readonly [string, number];

export interface Bounds {
  min: number;
  max: number;
}

export function boundsOf(...series: (readonly Point[] | null | undefined)[]): Bounds | null {
  let min = Infinity;
  let max = -Infinity;
  for (const s of series) {
    for (const p of s ?? []) {
      if (p[1] < min) min = p[1];
      if (p[1] > max) max = p[1];
    }
  }
  if (!Number.isFinite(min) || !Number.isFinite(max)) return null;
  if (min === max) {
    // A flat line sits in the middle instead of on an edge.
    const pad = Math.max(Math.abs(min) * 0.05, 100);
    return { min: min - pad, max: max + pad };
  }
  return { min, max };
}

/** SVG path "M x y L x y ..." for points spread evenly over the width. */
export function linePath(points: readonly Point[], width: number, height: number, bounds: Bounds, padding = 4): string {
  if (points.length === 0 || width <= 0 || height <= 0) return '';
  const span = bounds.max - bounds.min || 1;
  const innerH = Math.max(height - padding * 2, 1);
  const step = points.length > 1 ? width / (points.length - 1) : 0;
  return points
    .map((p, i) => {
      const x = points.length > 1 ? i * step : width / 2;
      const y = padding + innerH - ((p[1] - bounds.min) / span) * innerH;
      return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(' ');
}
