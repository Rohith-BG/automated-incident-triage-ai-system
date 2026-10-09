import { useMemo, useState } from 'react'
import {
  nodeLanguage,
  nodeOwner,
  nodeThreshold,
  type KgSnapshot,
} from '../data/kg'
import { forceLayout, labelFont, leaf } from './kgLayout'

const W = 1200
const H = 720
const R = 30

interface Props {
  snapshot: KgSnapshot
  fit?: boolean
}

/**
 * Variant 1 — the overview plate. The whole approved graph is force-
 * distributed onto one bounded canvas and scaled into whatever space it is
 * given, so five services and five hundred stay legible. Ring, ruled edge,
 * leaf label inside the ring, blast radius on hover — the identity lock holds.
 */
export default function KgGraphForce({ snapshot, fit = false }: Props) {
  const [focus, setFocus] = useState<string | null>(null)

  const { pos } = useMemo(() => forceLayout(snapshot, W, H), [snapshot])

  const edges = snapshot.edges.filter(
    (e) => e.from !== e.to && pos.has(e.from) && pos.has(e.to),
  )

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
    const walk = (id: string): void => {
      for (const dep of edgesByFrom.get(id) ?? []) {
        if (seen.has(dep)) continue
        seen.add(dep)
        walk(dep)
      }
    }
    walk(focus)
    return seen
  }, [focus, edgesByFrom])

  const rendered = snapshot.nodes.filter((node) => pos.has(node.id))
  const renderedIds = rendered.length
  const renderedEdges = edges.length

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className={fit ? 'block h-full w-full' : 'block w-full'}
      style={fit ? { height: '100%', width: '100%' } : undefined}
      role="img"
      aria-label={`Service dependency graph showing ${renderedIds} services and ${renderedEdges} dependency edges. Hover or focus a service to highlight its blast radius.`}
    >
      {edges.map((edge) => {
        const a = pos.get(edge.from)!
        const b = pos.get(edge.to)!
        const dx = b.x - a.x
        const dy = b.y - a.y
        const len = Math.hypot(dx, dy) || 1
        const lit = focus ? downstream.has(edge.from) && downstream.has(edge.to) : false
        return (
          <line
            key={`${edge.from}->${edge.to}`}
            x1={a.x + (dx / len) * R}
            y1={a.y + (dy / len) * R}
            x2={b.x - (dx / len) * R}
            y2={b.y - (dy / len) * R}
            stroke={lit ? 'var(--color-signal)' : 'var(--color-grid-major)'}
            strokeWidth={lit ? 1.5 : 1}
            opacity={focus && !lit ? 0.3 : 1}
          />
        )
      })}

      {rendered.map((node) => {
        const p = pos.get(node.id)!
        const isFocus = node.id === focus
        const inRadius = downstream.has(node.id)
        const dim = focus != null && !isFocus && !inRadius
        const critical = nodeThreshold(node) === 'critical'
        const owner = nodeOwner(node)
        const language = nodeLanguage(node)
        const name = leaf(node.id)
        const sub = owner || language
          ? `${owner ?? '—'}${language ? ` · ${language}` : ''}`
          : node.kind
        return (
          <g
            key={node.id}
            tabIndex={0}
            role="button"
            aria-label={`${node.id}, ${owner ?? 'unowned'}`}
            className="cursor-pointer outline-none"
            onMouseEnter={() => setFocus(node.id)}
            onMouseLeave={() => setFocus(null)}
            onFocus={() => setFocus(node.id)}
            onBlur={() => setFocus(null)}
            opacity={dim ? 0.4 : 1}
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
              style={{ fontSize: labelFont(name.length) }}
            >
              {name}
            </text>
            <text
              x={p.x}
              y={p.y + 13}
              textAnchor="middle"
              className="data-tight"
              fill={isFocus ? '#ffffffcc' : 'var(--color-ink-3)'}
              style={{ fontSize: 8 }}
            >
              {sub.length > 16 ? `${sub.slice(0, 16)}…` : sub}
            </text>
          </g>
        )
      })}

      <text
        x="0"
        y={H - 18}
        className="legend"
        fill="var(--color-ink-3)"
        style={{ fontSize: 10 }}
      >
        {focus
          ? `${leaf(focus).toUpperCase()} → ${downstream.size} SERVICE${
              downstream.size === 1 ? '' : 'S'
            } DOWNSTREAM`
          : `${renderedIds} SERVICES · ${renderedEdges} EDGES · FILLED DOT = CRITICAL THRESHOLD`}
      </text>
    </svg>
  )
}