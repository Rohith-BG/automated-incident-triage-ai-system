import { useMemo, useState } from 'react'
import {
  nodeLanguage,
  nodeOwner,
  nodeThreshold,
  type KgSnapshot,
} from '../data/kg'

const W = 1200
const R = 34
const ROW_H = 118
const TOP = 46
const BOTTOM = 56

interface Pos {
  x: number
  y: number
}

/**
 * Lay the snapshot out as a dependency stack: services nothing depends on sit
 * at the top, sources at the bottom. Pure geometry from the live edges â€”
 * nothing here is authored by hand.
 */
function computeLayout(snapshot: KgSnapshot): {
  pos: Map<string, Pos>
  height: number
} {
  const ids = snapshot.nodes.map((n) => n.id)
  const idSet = new Set(ids)

  const depsOf = new Map<string, string[]>()
  for (const edge of snapshot.edges) {
    if (edge.from === edge.to) continue
    if (!idSet.has(edge.from) || !idSet.has(edge.to)) continue
    const list = depsOf.get(edge.from) ?? []
    if (!list.includes(edge.to)) list.push(edge.to)
    depsOf.set(edge.from, list)
  }

  const reachable = new Set<string>()
  for (const edge of snapshot.edges) {
    if (idSet.has(edge.from)) reachable.add(edge.from)
    if (idSet.has(edge.to)) reachable.add(edge.to)
  }
  const layoutIds = ids.filter((id) => reachable.has(id) || depsOf.has(id))
  const useAll = layoutIds.length === 0 ? ids : layoutIds

  const depth = new Map<string, number>()
  useAll.forEach((id) => depth.set(id, 0))

  let changed = true
  let iterations = 0
  while (changed && iterations < 100) {
    changed = false
    for (const id of useAll) {
      let d = 0
      for (const dep of depsOf.get(id) ?? []) {
        d = Math.max(d, (depth.get(dep) ?? 0) + 1)
      }
      if (d > (depth.get(id) ?? 0)) {
        depth.set(id, d)
        changed = true
      }
    }
    iterations += 1
  }

  let maxDepth = 0
  useAll.forEach((id) => {
    maxDepth = Math.max(maxDepth, depth.get(id) ?? 0)
  })

  const layers = new Map<number, string[]>()
  useAll.forEach((id) => {
    const d = depth.get(id) ?? 0
    const layer = layers.get(d) ?? []
    layer.push(id)
    layers.set(d, layer)
  })

  const pos = new Map<string, Pos>()
  for (const [d, layer] of layers) {
    layer.sort()
    const y = TOP + d * ROW_H + ROW_H / 2
    layer.forEach((id, index) => {
      pos.set(id, { x: (W / (layer.length + 1)) * (index + 1), y })
    })
  }

  const height = Math.max(220, TOP + maxDepth * ROW_H + BOTTOM)
  return { pos, height }
}

interface KgGraphProps {
  snapshot: KgSnapshot
  fit?: boolean
}

function labelFont(len: number): number {
  if (len <= 8) return 11
  if (len <= 12) return 9.5
  if (len <= 16) return 7.5
  return 6.5
}

/**
 * The active knowledge graph drawn as an instrument readout: each service is
 * a ring of plotter ink, each dependency a ruled line. Hovering or focusing a
 * node lights its blast radius â€” everything downstream of it. Pass `fit` to
 * scale the whole plot into its container (the enlarged console view).
 */
export default function KgGraph({ snapshot, fit = false }: KgGraphProps) {
  const [focus, setFocus] = useState<string | null>(null)

  const leaf = (id: string): string => id.split('.').pop() ?? id

  const { pos, height } = useMemo(() => computeLayout(snapshot), [snapshot])

  const edges = useMemo(() => {
    return snapshot.edges.filter(
      (e) => e.from !== e.to && pos.has(e.from) && pos.has(e.to),
    )
  }, [snapshot.edges, pos])

  const edgesByFrom = useMemo(() => {
    const map = new Map<string, string[]>()
    for (const edge of edges) {
      const list = map.get(edge.from) ?? []
      list.push(edge.to)
      map.set(edge.from, list)
    }
    return map
  }, [edges])

  const downstream = useMemo(() => {
    if (!focus || !edgesByFrom.has(focus)) return new Set<string>()
    const seen = new Set<string>()
    const walk = (id: string) => {
      for (const dep of edgesByFrom.get(id) ?? []) {
        if (seen.has(dep)) continue
        seen.add(dep)
        walk(dep)
      }
    }
    walk(focus)
    return seen
  }, [focus, edgesByFrom])

  const focusLit = (id: string) => id === focus || downstream.has(id)

  const nodeCount = snapshot.nodes.length
  const renderedIds = new Set(
    snapshot.nodes.map((n) => n.id).filter((id) => pos.has(id)),
  )
  const renderedEdges = edges.length
  const downstreamCount = downstream.size

  return (
    <svg
      viewBox={`0 0 ${W} ${height}`}
      className={fit ? 'block h-full w-full' : 'block w-full'}
      style={fit ? { height: '100%', width: '100%' } : undefined}
      role="img"
      aria-label={`Service dependency graph showing ${nodeCount} services and ${renderedEdges} dependency edges. Hover or focus a service to highlight its blast radius.`}
    >
      {/* Edges: one ruled line per dependency. */}
      {edges.map((e) => {
        const a = pos.get(e.from)!
        const b = pos.get(e.to)!
        const dx = b.x - a.x
        const dy = b.y - a.y
        const len = Math.hypot(dx, dy) || 1
        const lit = focus ? focusLit(e.from) && focusLit(e.to) : false
        return (
          <line
            key={`${e.from}->${e.to}`}
            x1={a.x + (dx / len) * R}
            y1={a.y + (dy / len) * R}
            x2={b.x - (dx / len) * R}
            y2={b.y - (dy / len) * R}
            stroke={lit ? 'var(--color-signal)' : 'var(--color-grid-major)'}
            strokeWidth={lit ? 1.5 : 1}
            opacity={focus && !lit ? 0.35 : 1}
          />
        )
      })}

      {/* Nodes: a ring of ink per service. */}
      {snapshot.nodes
        .filter((n) => pos.has(n.id))
        .map((n) => {
          const p = pos.get(n.id)!
          const isFocus = n.id === focus
          const inRadius = downstream.has(n.id)
          const dim = focus != null && !isFocus && !inRadius
          const critical = nodeThreshold(n) === 'critical'
          const owner = nodeOwner(n)
          const language = nodeLanguage(n)
          const sub = owner || language ? `${owner ?? 'â€”'}${language ? ` Â· ${language}` : ''}` : n.kind
          return (
            <g
              key={n.id}
              tabIndex={0}
              role="button"
              aria-label={`${n.id}, ${owner ?? 'unowned'}`}
              className="cursor-pointer outline-none"
              onMouseEnter={() => setFocus(n.id)}
              onMouseLeave={() => setFocus(null)}
              onFocus={() => setFocus(n.id)}
              onBlur={() => setFocus(null)}
              opacity={dim ? 0.42 : 1}
            >
              <circle
                cx={p.x}
                cy={p.y}
                r={R}
                fill={
                  isFocus
                    ? 'var(--color-signal)'
                    : inRadius
                      ? 'var(--color-stock-3)'
                      : 'var(--color-stock)'
                }
                stroke={isFocus || inRadius ? 'var(--color-signal)' : 'var(--color-ink)'}
                strokeWidth={isFocus ? 2 : 1}
              />
              {critical && !isFocus && (
                <circle
                  cx={p.x + R * 0.62}
                  cy={p.y - R * 0.62}
                  r={4.5}
                  fill="var(--color-signal)"
                />
              )}
              <text
                x={p.x}
                y={p.y - 2}
                textAnchor="middle"
                className="data-tight"
                fill={isFocus ? '#fff' : 'var(--color-ink)'}
                style={{ fontSize: labelFont(leaf(n.id).length) }}
              >
                {leaf(n.id)}
              </text>
              <text
                x={p.x}
                y={p.y + 13}
                textAnchor="middle"
                className="data-tight"
                fill={isFocus ? '#ffffffcc' : 'var(--color-ink-3)'}
                style={{ fontSize: 8 }}
              >
                {sub.length > 16 ? `${sub.slice(0, 16)}â€¦` : sub}
              </text>
            </g>
          )
        })}

      {/* Readout: the instrument states its position. */}
      <text
        x="0"
        y={height - 20}
        className="legend"
        fill="var(--color-ink-3)"
        style={{ fontSize: 10 }}
      >
        {focus
          ? `${leaf(focus).toUpperCase()} → ${downstreamCount} SERVICE${downstreamCount === 1 ? '' : 'S'} DOWNSTREAM`
          : `${renderedIds.size} SERVICES · ${renderedEdges} EDGES · FILLED DOT = CRITICAL THRESHOLD`}
      </text>
    </svg>
  )
}
