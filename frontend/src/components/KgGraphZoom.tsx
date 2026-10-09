import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
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
const MIN_SCALE = 0.3
const MAX_SCALE = 5

interface View {
  s: number
  ox: number
  oy: number
}

interface Props {
  snapshot: KgSnapshot
}

/**
 * Variant 2 — the console drill. The same force-distributed layout, but held
 * inside a window you can actually move around in, the way a database console
 * holds a graph: scroll to zoom toward the cursor, drag to pan, double-click
 * or Fit to return to the whole plate. The identity lock — ring, ruled edge,
 * leaf label inside the ring, blast radius on hover — is unchanged.
 */
export default function KgGraphZoom({ snapshot }: Props) {
  const wrap = useRef<HTMLDivElement | null>(null)
  const [view, setView] = useState<View>({ s: 1, ox: 0, oy: 0 })
  const [focus, setFocus] = useState<string | null>(null)
  const drag = useRef<{ x: number; y: number } | null>(null)

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

  const fit = useCallback((): void => {
    const rect = wrap.current?.getBoundingClientRect()
    if (!rect) return
    const scale = (Math.min(rect.width / W, rect.height / H) || 1) * 0.94
    setView({
      s: scale,
      ox: (rect.width - W * scale) / 2,
      oy: (rect.height - H * scale) / 2,
    })
  }, [])

  useEffect(() => {
    fit()
  }, [fit])

  const zoomAt = useCallback((px: number, py: number, factor: number): void => {
    setView((prev) => {
      const next = Math.min(MAX_SCALE, Math.max(MIN_SCALE, prev.s * factor))
      const wx = (px - prev.ox) / prev.s
      const wy = (py - prev.oy) / prev.s
      return { s: next, ox: px - wx * next, oy: py - wy * next }
    })
  }, [])

  useEffect(() => {
    const el = wrap.current
    if (!el) return
    const onWheel = (event: WheelEvent): void => {
      event.preventDefault()
      const rect = el.getBoundingClientRect()
      const px = event.clientX - rect.left
      const py = event.clientY - rect.top
      zoomAt(px, py, event.deltaY < 0 ? 1.16 : 0.86)
    }
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => el.removeEventListener('wheel', onWheel)
  }, [zoomAt])

  const onPointerDown = (event: React.PointerEvent<HTMLDivElement>): void => {
    drag.current = { x: event.clientX, y: event.clientY }
    event.currentTarget.setPointerCapture(event.pointerId)
  }

  const onPointerMove = (event: React.PointerEvent<HTMLDivElement>): void => {
    if (!drag.current) return
    setView((prev) => ({
      ...prev,
      ox: prev.ox + (event.clientX - drag.current!.x),
      oy: prev.oy + (event.clientY - drag.current!.y),
    }))
    drag.current = { x: event.clientX, y: event.clientY }
  }

  const stopDrag = (): void => {
    drag.current = null
  }

  return (
    <div
      ref={wrap}
      role="group"
      aria-label="Graph console viewport — drag to pan, scroll to zoom"
      className="relative h-full w-full touch-none overflow-hidden"
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={stopDrag}
      onPointerCancel={stopDrag}
      onDoubleClick={() => fit()}
    >
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="block h-full w-full cursor-grab active:cursor-grabbing"
        role="img"
        aria-label={`Service dependency graph showing ${renderedIds} services and ${renderedEdges} dependency edges. Hover or focus a service to highlight its blast radius.`}
      >
        <g transform={`translate(${view.ox} ${view.oy}) scale(${view.s})`}>
          {edges.map((edge) => {
            const a = pos.get(edge.from)!
            const b = pos.get(edge.to)!
            const dx = b.x - a.x
            const dy = b.y - a.y
            const len = Math.hypot(dx, dy) || 1
            const lit =
              focus && downstream.has(edge.from) && downstream.has(edge.to)
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
                  stroke={
                    isFocus || inRadius ? 'var(--color-signal)' : 'var(--color-ink)'
                  }
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
        </g>
      </svg>

      <div className="pointer-events-none absolute bottom-3 left-3 text-[0.6875rem] leading-tight text-ink-3">
        drag to pan · scroll to zoom · double-click to fit
      </div>
      <button
        type="button"
        onClick={() => fit()}
        className="legend absolute right-3 bottom-3 cursor-pointer border border-grid-major bg-stock px-2.5 py-1 text-ink-2 transition-colors hover:border-ink hover:text-ink"
      >
        Fit
      </button>
    </div>
  )
}