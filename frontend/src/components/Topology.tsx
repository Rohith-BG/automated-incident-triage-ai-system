import { useEffect, useRef, useState } from 'react'
import { PROPOSAL_STATES } from '../data/run'
import {
  fetchLandingGraph,
  fetchBlastRadius,
  type LandingGraph,
  type BlastRadius,
} from '../data/landing'
import { LeaderArrow } from './Icons'

const W = 1200
const H = 640
const PAD_T = 52
const PAD_B = 96
const NODE_W = 168
const NODE_H = 40

/** Compute a topological depth — services with no known-service deps sit at the bottom (depth 0). */
function computeDepths(graph: LandingGraph): Map<string, number> {
  const known = new Set(graph.services.map((s) => s.id))
  const depMap = new Map<string, string[]>()
  for (const d of graph.deps) {
    depMap.set(
      d.service_id,
      d.dependencies.filter((dep) => known.has(dep.id)).map((dep) => dep.id),
    )
  }
  const depth = new Map<string, number>()
  const seen = new Set<string>()

  function walk(id: string): number {
    if (depth.has(id)) return depth.get(id)!
    if (seen.has(id)) return 0
    seen.add(id)
    const deps = depMap.get(id) ?? []
    const d = deps.length === 0 ? 0 : 1 + Math.max(...deps.map(walk))
    depth.set(id, d)
    return d
  }

  for (const s of graph.services) walk(s.id)
  return depth
}

/**
 * The topology, fetched live from the backend — not hardcoded. Nodes are
 * /services, edges are /services/{id}/dependencies (only the edges whose
 * targets are known service nodes), blast radius fetched per-focus via
 * /services/{id}/blast-radius. The graph is the source of truth for
 * dependencies, blast radius and ownership — and it does not change
 * without a human approving the change.
 */
export default function Topology() {
  const [graph, setGraph] = useState<LandingGraph | null>(null)
  const [error, setError] = useState(false)
  const [focus, setFocus] = useState<string | null>(null)
  const [blast, setBlast] = useState<BlastRadius | null>(null)
  const blastRef = useRef<string | null>(null)

  useEffect(() => {
    let cancelled = false
    fetchLandingGraph()
      .then((g) => {
        if (!cancelled) setGraph(g)
      })
      .catch(() => {
        if (!cancelled) setError(true)
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (!focus) {
      setBlast(null)
      blastRef.current = null
      return
    }
    blastRef.current = focus
    let cancelled = false
    fetchBlastRadius(focus)
      .then((b) => {
        if (!cancelled && blastRef.current === focus) setBlast(b)
      })
      .catch(() => {
        if (!cancelled && blastRef.current === focus) setBlast(null)
      })
    return () => {
      cancelled = true
    }
  }, [focus])

  const depths = graph ? computeDepths(graph) : new Map<string, number>()
  const maxDepth = graph ? Math.max(1, ...depths.values()) : 1

  const nodeIds = graph?.services.map((s) => s.id) ?? []
  const nodeMap = new Map(
    graph?.services.map((s) => [s.id, s] as const) ?? [],
  )
  const pos = new Map<string, { x: number; y: number }>()
  const layers = new Map<number, string[]>()

  if (graph) {
    const NODE_GAP = 32
    const PER_ROW = Math.max(1, Math.floor(W / (NODE_W + NODE_GAP)))
    for (const id of nodeIds) {
      const d = depths.get(id) ?? 0
      if (!layers.has(d)) layers.set(d, [])
      layers.get(d)!.push(id)
    }
    for (const [d, members] of layers) {
      const baseY = PAD_T + (maxDepth - d) * ((H - PAD_T - PAD_B) / Math.max(1, maxDepth))
      members.forEach((id, i) => {
        const row = Math.floor(i / PER_ROW)
        const col = i % PER_ROW
        const inRow = Math.min(PER_ROW, members.length - row * PER_ROW)
        pos.set(id, {
          x: (W / (inRow + 1)) * (col + 1),
          y: baseY + row * (NODE_H + 24),
        })
      })
    }
  }

  const edges = graph
    ? graph.deps.flatMap((d) =>
        d.dependencies
          .filter((dep) => nodeIds.includes(d.service_id) && nodeIds.includes(dep.id))
          .map((dep) => ({ from: d.service_id, to: dep.id, key: `${d.service_id}->${dep.id}` })),
      )
    : []

  const downstream = (() => {
    if (!focus || !graph) return new Set<string>()
    return new Set(
      (blast?.affected_services.map((s) => s.id) ?? []).filter((id) => id !== focus),
    )
  })()

  const edgeLit = (from: string, to: string) =>
    focus != null &&
    (from === focus ||
      to === focus ||
      (blast?.direct_dependents.includes(from) && downstream.has(to)))

  if (error) {
    return (
      <section id="graph" className="scroll-mt-16 border-b border-ink">
        <div className="mx-auto w-full max-w-[1400px] px-5 py-16 sm:px-8 lg:px-12 lg:py-24">
          <h2 className="section-type text-[clamp(1.9rem,3.4vw,2.9rem)]">
            Blast radius is a graph query, not a guess.
          </h2>
          <p className="mt-5 text-[0.9375rem] leading-relaxed text-tentative">
            Unread — the topology could not be fetched from the backend.
          </p>
        </div>
      </section>
    )
  }

  return (
    <section id="graph" className="scroll-mt-16 border-b border-ink">
      <div className="mx-auto w-full max-w-[1400px] px-5 py-16 sm:px-8 lg:px-12 lg:py-24">
        <div className="grid gap-x-14 gap-y-8 lg:grid-cols-[minmax(0,26rem)_minmax(0,1fr)]">
          <div>
            <h2 className="section-type text-[clamp(1.9rem,3.4vw,2.9rem)] text-ink">
              Blast radius is a graph query, not a guess.
            </h2>
            <p className="prose-measure mt-5 text-[1.0625rem] leading-[1.6] text-ink-2">
              Before any evidence channel opens, the investigation determines the blast radius:
              the set of services that are affected when the failing service goes down. That
              determination comes from the service dependency graph, which records how every
              service connects to every other. The query returns which services depend on the
              failing one and the history of how this part of the system has broken in the past.
              The result defines the investigation scope, so the observability channel
              interrogates every affected service instead of relying on a guessed boundary. The
              graph query is made on the Neo4j knowledge graph at investigation time, so the
              answer always reflects the current service topology.
            </p>
            <p className="mt-5 flex items-start gap-2.5 text-[0.9375rem] leading-relaxed text-ink-2">
              <LeaderArrow className="mt-1 shrink-0 text-ink-3" />
              <span>
                Hover or focus a service to read its blast radius off the graph in real time. The
                topology is stored in the knowledge graph and queried at investigation time.
              </span>
            </p>
          </div>

          <div className="flex flex-col overflow-x-auto">
            <div className="flex min-w-[600px]">
              <svg
                viewBox={`0 0 ${W} ${H}`}
                className="block h-full min-h-[460px] w-full"
                role="img"
                aria-label="Live service dependency graph, fetched from the backend at render time."
              >
                {edges.map((e) => {
                  const a = pos.get(e.from)
                  const b = pos.get(e.to)
                  if (!a || !b) return null
                  const lit = edgeLit(e.from, e.to)
                  return (
                    <path
                      key={e.key}
                      d={`M ${a.x} ${a.y + NODE_H / 2} C ${a.x} ${a.y + 42} ${b.x} ${b.y - 42} ${b.x} ${b.y - NODE_H / 2}`}
                      fill="none"
                      stroke={lit ? 'var(--color-signal)' : 'var(--color-grid-major)'}
                      strokeWidth={lit ? 2 : 1}
                      opacity={focus && !lit ? 0.4 : 1}
                    />
                  )
                })}

                {nodeIds.map((id) => {
                  const p = pos.get(id)
                  const svc = nodeMap.get(id)
                  if (!p || !svc) return null
                  const isFocus = id === focus
                  const inRadius = downstream.has(id)
                  const dim = focus != null && !isFocus && !inRadius
                  const critical = svc.alert_threshold === 'critical'
                  return (
                    <g
                      key={id}
                      tabIndex={0}
                      role="button"
                      aria-label={`${id}, owned by ${svc.owner_team}, alert threshold ${svc.alert_threshold}`}
                      className="cursor-pointer outline-none"
                      onMouseEnter={() => setFocus(id)}
                      onMouseLeave={() => setFocus(null)}
                      onFocus={() => setFocus(id)}
                      onBlur={() => setFocus(null)}
                      opacity={dim ? 0.42 : 1}
                    >
                      <rect
                        x={p.x - NODE_W / 2}
                        y={p.y - NODE_H / 2}
                        width={NODE_W}
                        height={NODE_H}
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
                        <path
                          d={`M ${p.x + NODE_W / 2 - 9} ${p.y - NODE_H / 2} L ${p.x + NODE_W / 2} ${p.y - NODE_H / 2} L ${p.x + NODE_W / 2} ${p.y - NODE_H / 2 + 9} Z`}
                          fill="var(--color-signal)"
                        />
                      )}
                      <text
                        x={p.x}
                        y={p.y - 1}
                        textAnchor="middle"
                        className="data-tight"
                        fill={isFocus ? '#fff' : 'var(--color-ink)'}
                        style={{ fontSize: 12.5 }}
                      >
                        {id}
                      </text>
                      <text
                        x={p.x}
                        y={p.y + 13}
                        textAnchor="middle"
                        className="data-tight"
                        fill={isFocus ? '#ffffffcc' : 'var(--color-ink-3)'}
                        style={{ fontSize: 10 }}
                      >
                        {svc.owner_team} · {svc.language}
                      </text>
                    </g>
                  )
                })}

                <text
                  x="0"
                  y={H - 22}
                  className="legend"
                  fill="var(--color-ink-3)"
                  style={{ fontSize: 12 }}
                >
                  {focus
                    ? `${focus.toUpperCase()} → BLAST RADIUS ${blast?.impact_count ?? '?'} SERVICE(S) · ${blast?.direct_dependents.length ?? '?'} DIRECT DEPENDENT(S)`
                    : `${nodeIds.length} SERVICES · ${edges.length} EDGES · NOTCHED CORNER = CRITICAL THRESHOLD`}
                </text>
              </svg>
            </div>
          </div>
        </div>

        <div className="mt-14 border-t border-ink pt-8">
          <div className="grid gap-x-14 gap-y-8 lg:grid-cols-[minmax(0,26rem)_minmax(0,1fr)]">
            <div>
              <h3 className="section-type text-[1.5rem]">
                A discovered graph is a proposal, not a fact.
              </h3>
              <p className="prose-measure mt-3.5 text-[0.9375rem] leading-relaxed text-ink-2">
                Sift can build this topology itself by reading a GitHub organisation. What it finds
                does not go live immediately. Each discovered service and edge arrives as a change
                proposal an admin has to act on, and until they do it stays out of the active graph —
                hatched here, as anything unresolved is hatched everywhere on this page.
              </p>
          </div>

          <ol className="m-0 list-none space-y-0 p-0">
              {PROPOSAL_STATES.map((st) => {
                const pending = st.id === 'pending'
                return (
                  <li
                    key={st.id}
                    className={`grid grid-cols-[minmax(0,7.5rem)_minmax(0,1fr)] items-baseline gap-x-5 border-b border-grid-minor py-3 first:border-t first:border-t-ink ${
                      pending ? 'hatch-tentative' : ''
                    }`}
                  >
                    <span
                      className="data-tight"
                      style={{ color: pending ? 'var(--color-tentative)' : 'var(--color-ink)' }}
                    >
                      {st.id}
                    </span>
                    <span className="text-[0.9375rem] leading-snug text-ink-2">{st.note}</span>
                  </li>
                )
              })}
            </ol>
          </div>
        </div>
      </div>
    </section>
  )
}