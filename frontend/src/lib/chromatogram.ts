/**
 * Geometry for the chromatogram: the pipeline drawn as an analytical trace.
 *
 * The x axis is retention — the pipeline's real node order. Three channels run
 * concurrently across the middle of it, because agents/orchestrator/graph.py
 * fans out from knowledge_graph_query into three nodes and joins at synthesize.
 *
 * Peak count equals the run's recorded call total. Deploy contributes exactly
 * one call (one tool), knowledge + diff contributes three when the diff tool
 * finds no candidates, and observability takes the remainder because it loops
 * over every service in the blast radius. That split is derived, and the plot's
 * legend says so.
 *
 * Two presets, because a chromatogram is a landscape instrument and a phone is
 * not. `wide` is the panel: short, full-bleed, sitting in the first viewport
 * under its own identification block. `tall` stacks the same three channels for
 * a narrow screen, with room for the type to stay legible.
 */

import type { Channel, Specimen } from '../data/run'

export interface Band {
  /** Top of the channel's band. */
  top: number
  /** The channel's baseline — the pen's rest position. */
  base: number
}

export interface Preset {
  view: { w: number; h: number }
  /** Retention marks along the x axis. */
  x: {
    intake: number
    graph: number
    fanStart: number
    fanEnd: number
    join: number
    gate: number
    end: number
  }
  bands: Band[]
  axisY: number
  /** Where the three channels converge. */
  joinY: number
  /** Confidence is read on this vertical span at the gate. */
  scale: { top: number; bottom: number }
  /** Gutter reserved for channel identification, left of the plot. */
  gutter: number
  type: { legend: number; micro: number; tick: number; verdict: number }
  /** Grid division sizes in user units. */
  grid: { minor: number; major: number }
  /** Full node names on the axis, or the short ones. */
  longAxisLabels: boolean
}

export const WIDE: Preset = {
  view: { w: 1200, h: 352 },
  x: { intake: 132, graph: 224, fanStart: 296, fanEnd: 900, join: 964, gate: 1060, end: 1160 },
  bands: [
    { top: 18, base: 96 },
    { top: 108, base: 186 },
    { top: 198, base: 276 },
  ],
  axisY: 286,
  joinY: 186,
  scale: { top: 26, bottom: 276 },
  gutter: 224,
  type: { legend: 10, micro: 9, tick: 10, verdict: 25 },
  grid: { minor: 8, major: 48 },
  longAxisLabels: true,
}

/**
 * Phone width. Same landscape proportions as WIDE, drawn at 600 units so the
 * annotations render near 1:1 inside a horizontal scroller instead of shrinking
 * to illegibility with the viewport.
 */
export const TALL: Preset = {
  view: { w: 600, h: 392 },
  x: { intake: 62, graph: 108, fanStart: 140, fanEnd: 436, join: 478, gate: 520, end: 594 },
  bands: [
    { top: 20, base: 108 },
    { top: 120, base: 208 },
    { top: 220, base: 308 },
  ],
  axisY: 322,
  joinY: 208,
  scale: { top: 28, bottom: 308 },
  gutter: 108,
  type: { legend: 11, micro: 10, tick: 11, verdict: 27 },
  grid: { minor: 8, major: 48 },
  longAxisLabels: false,
}

export interface Peak {
  /** Centre on the retention axis. */
  cx: number
  /** Half-width at the baseline. */
  hw: number
  /** Height above the baseline. */
  h: number
  /** The tool this position belongs to. */
  tool: string
  /** Which pass through the tool set this is, for looped channels. */
  pass: number
  /** True when the tool has a retention position but did not fire this run. */
  ghost: boolean
}

/**
 * How many calls each channel contributed. Deploy and knowledge + diff are
 * structurally fixed; observability absorbs whatever the recorded total has
 * left over, which is how a blast-radius loop shows up in the aggregate.
 */
export function splitCalls(specimen: Specimen, channels: Channel[]) {
  const deploy = channels[1].baseCalls // 1
  const knowledge = channels[2].baseCalls // 3 — get_commit_diff stays dark
  const observability = Math.max(0, specimen.calls - deploy - knowledge)
  return [observability, deploy, knowledge]
}

/**
 * Peak height encodes the run's mean recorded call latency, normalised across
 * the golden set so specimens stay comparable to each other.
 */
export function peakHeight(specimen: Specimen, bandHeight: number) {
  const mean = specimen.toolLatencyMs / specimen.calls
  // The set spans roughly 548ms (inc-gold-001) to 753ms (inc-gold-002) per call.
  const lo = 500
  const hi = 800
  const t = Math.min(1, Math.max(0, (mean - lo) / (hi - lo)))
  return bandHeight * (0.44 + t * 0.5)
}

/**
 * Lay out one channel's peaks. Tools cycle in call order; a channel given more
 * calls than it has tools runs the set again, which is the loop over the blast
 * radius made visible. A tool with no call left over keeps its retention
 * position and renders as a ghost.
 */
export function layoutPeaks(
  callCount: number,
  tools: string[],
  height: number,
  preset: Preset,
): Peak[] {
  const slots = Math.max(callCount, tools.length)
  const span = preset.x.fanEnd - preset.x.fanStart
  const pitch = span / Math.max(slots, 1)
  const hw = Math.min(preset === TALL ? 20 : 26, Math.max(4, pitch * 0.36))

  const peaks: Peak[] = []
  for (let i = 0; i < slots; i++) {
    peaks.push({
      cx: preset.x.fanStart + pitch * (i + 0.5),
      hw,
      h: height,
      tool: tools[i % tools.length],
      pass: Math.floor(i / tools.length) + 1,
      ghost: i >= callCount,
    })
  }
  return peaks
}

/**
 * One continuous pen path for a channel: rest at the baseline, rise through
 * each peak, return to rest. Ghost positions are skipped here and drawn
 * separately, because the pen never lifted for them.
 */
export function channelPath(peaks: Peak[], band: Band, preset: Preset): string {
  const y0 = band.base
  const live = peaks.filter((p) => !p.ghost)
  if (!live.length) return `M ${preset.x.graph} ${y0} L ${preset.x.join} ${y0}`

  let d = `M ${preset.x.graph} ${y0}`
  for (const p of live) {
    const y1 = y0 - p.h
    d += ` L ${r(p.cx - p.hw)} ${y0}`
    d += ` C ${r(p.cx - p.hw * 0.34)} ${y0} ${r(p.cx - p.hw * 0.3)} ${r(y1)} ${r(p.cx)} ${r(y1)}`
    d += ` C ${r(p.cx + p.hw * 0.3)} ${r(y1)} ${r(p.cx + p.hw * 0.34)} ${y0} ${r(p.cx + p.hw)} ${y0}`
  }
  d += ` L ${preset.x.join} ${y0}`
  return d
}

/**
 * The three channels converge on synthesize. Each band's baseline sweeps to the
 * join, which is the fan-in the workflow actually performs.
 */
export function convergePath(band: Band, preset: Preset): string {
  const x0 = preset.x.join
  const x1 = preset.x.gate - 14
  const midX = (x0 + x1) / 2
  return `M ${x0} ${band.base} C ${r(midX)} ${band.base} ${r(midX)} ${preset.joinY} ${x1} ${preset.joinY}`
}

/**
 * Retention positions where two or more channels peak at the same instant.
 * Co-registration across independent sources is the strongest evidence the
 * system has, so it gets drawn rather than asserted.
 */
export function coRegistrations(channelPeaks: Peak[][], tolerance = 14): number[] {
  const marks: number[] = []
  const [a, b, c] = channelPeaks
  for (const pa of a) {
    if (pa.ghost) continue
    const hitB = b.some((p) => !p.ghost && Math.abs(p.cx - pa.cx) <= tolerance)
    const hitC = c.some((p) => !p.ghost && Math.abs(p.cx - pa.cx) <= tolerance)
    if (hitB || hitC) marks.push(pa.cx)
  }
  return marks.filter((m, i) => i === 0 || m - marks[i - 1] > tolerance * 2)
}

function r(n: number) {
  return Math.round(n * 10) / 10
}

/** Path length estimate, good enough to seed a stroke-dashoffset draw. */
export function approxLength(d: string): number {
  const nums = d.match(/-?\d+(\.\d+)?/g)
  if (!nums) return 2000
  let len = 0
  for (let i = 2; i < nums.length; i += 2) {
    const dx = Number(nums[i]) - Number(nums[i - 2])
    const dy = Number(nums[i + 1] ?? 0) - Number(nums[i - 1])
    len += Math.hypot(dx, dy)
  }
  return Math.max(600, Math.round(len))
}
