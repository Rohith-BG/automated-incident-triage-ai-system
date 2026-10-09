/**
 * Layout engines for the knowledge-graph plot.
 *
 * `forceLayout` places services with a bounded force-directed pass — the same
 * family of arrangement a database console uses — so a snapshot of 100 nodes
 * or a thousand stays readable instead of exploding into a tall sliver (the
 * layered depth-stack reached ~35,000 units on a 500-node graph and collapsed
 * under fit-scaling). Pure functions; callers own the rendering.
 */

import type { KgSnapshot } from '../data/kg'

export interface Pt {
  x: number
  y: number
}

export interface ForceLayout {
  pos: Map<string, Pt>
  width: number
  height: number
}

const ITERATIONS = 70
const COOL = 0.94
const REPULSION_C = 0.17
const GRAVITY = 0.0012
const MARGIN = 26

/**
 * A service's printable label: the leaf of its dotted id. The full path —
 * `backend.core` — is recoverable hanging off a `contains` edge from
 * `backend`, so only `core` belongs on the ring.
 */
export function leaf(id: string): string {
  return id.split('.').pop() ?? id
}

/** Auto-size the in-ring label so names up to ~20 chars stay inside the ring. */
export function labelFont(len: number): number {
  if (len <= 8) return 11
  if (len <= 12) return 9.5
  if (len <= 16) return 7.5
  return 6.5
}

export function forceLayout(
  snapshot: KgSnapshot,
  width: number,
  height: number,
): ForceLayout {
  const ids = snapshot.nodes.map((node) => node.id)
  const n = ids.length
  const cx = width / 2
  const cy = height / 2
  const boxW = width - MARGIN * 2
  const boxH = height - MARGIN * 2

  const coords: Pt[] = new Array(n)
  if (n === 1) {
    coords[0] = { x: cx, y: cy }
  } else {
    const r = Math.min(boxW, boxH) * 0.42
    for (let i = 0; i < n; i++) {
      const a = (i / n) * Math.PI * 2
      coords[i] = { x: cx + Math.cos(a) * r, y: cy + Math.sin(a) * r }
    }
  }

  const index = new Map<string, number>()
  ids.forEach((id, i) => index.set(id, i))

  const edges: Array<[number, number]> = []
  for (const edge of snapshot.edges) {
    const a = index.get(edge.from)
    const b = index.get(edge.to)
    if (a == null || b == null || a === b) continue
    edges.push([a, b])
  }

  const k = REPULSION_C * Math.sqrt((boxW * boxH * 0.72) / Math.max(n, 1))
  let temp = Math.min(boxW, boxH) / 12
  const floor = temp * 0.05

  for (let iter = 0; iter < ITERATIONS; iter++) {
    const disp: Pt[] = coords.map(() => ({ x: 0, y: 0 }))

    for (let a = 0; a < n; a++) {
      const pa = coords[a]
      for (let b = a + 1; b < n; b++) {
        const pb = coords[b]
        let dx = pa.x - pb.x
        let dy = pa.y - pb.y
        let d2 = dx * dx + dy * dy
        if (d2 < 1) {
          dx = Math.random() - 0.5
          dy = Math.random() - 0.5
          d2 = 1
        }
        const d = Math.sqrt(d2)
        const f = (k * k) / d
        const fx = (f * dx) / d
        const fy = (f * dy) / d
        disp[a].x += fx
        disp[a].y += fy
        disp[b].x -= fx
        disp[b].y -= fy
      }
    }

    for (const [a, b] of edges) {
      const pa = coords[a]
      const pb = coords[b]
      const dx = pb.x - pa.x
      const dy = pb.y - pa.y
      const d = Math.max(Math.sqrt(dx * dx + dy * dy), 0.01)
      const f = (d * d) / k
      const fx = (f * dx) / d
      const fy = (f * dy) / d
      disp[a].x += fx
      disp[a].y += fy
      disp[b].x -= fx
      disp[b].y -= fy
    }

    for (let a = 0; a < n; a++) {
      const pa = coords[a]
      disp[a].x -= pa.x * GRAVITY * temp
      disp[a].y -= pa.y * GRAVITY * temp
      const len = Math.hypot(disp[a].x, disp[a].y) || 1
      const pull = Math.min(temp, len)
      pa.x += (disp[a].x / len) * pull
      pa.y += (disp[a].y / len) * pull
      if (pa.x < MARGIN) pa.x = MARGIN
      if (pa.x > width - MARGIN) pa.x = width - MARGIN
      if (pa.y < MARGIN) pa.y = MARGIN
      if (pa.y > height - MARGIN) pa.y = height - MARGIN
    }

    temp *= COOL
    if (temp < floor) break
  }

  const pos = new Map<string, Pt>()
  ids.forEach((id, i) => pos.set(id, coords[i]))
  return { pos, width, height }
}