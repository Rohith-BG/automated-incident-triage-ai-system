/** Instrument-register formatting. Every quantity on the page passes through here. */

export function ms(v: number): string {
  if (v >= 10_000) return `${(v / 1000).toFixed(2)} s`
  if (v >= 1000) return `${(v / 1000).toFixed(2)} s`
  return `${v.toFixed(0)} ms`
}

export function msExact(v: number): string {
  return `${v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ms`
}

/** Scores print to two decimals so a 0.90 never reads as a 0.9. */
export function score(v: number): string {
  return v.toFixed(2)
}

export function pct(v: number): string {
  return `${Math.round(v * 100)}%`
}

export function int(v: number): string {
  return v.toLocaleString('en-US')
}
