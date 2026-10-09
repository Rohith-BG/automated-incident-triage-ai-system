import { useMemo, useRef, useState, useId } from 'react'
import { useMediaQuery } from '../lib/useMediaQuery'

/**
 * The shared apparatus. A schematic of one investigation across the real
 * pipeline from agents/orchestrator/graph.py: intake, the knowledge graph
 * answering the blast-radius question, three concurrent evidence channels,
 * synthesis, and the confidence gate.
 *
 * No recorded run is plotted here — the peaks are the retention slots where
 * that channel's real tools fire, so the shape of the investigation is
 * what is on the page, not a single reported outcome. The knowledge graph
 * query draws first, as its own aligned band with three reads (blast radius,
 * dependencies, history); then three concurrent channels run in the
 * parallel window, the third holding two MCP servers behind a single node —
 * incident knowledge and code diff. The scrub reads the same truth the
 * report does: when two or more independent channels hold a slot at the same
 * point in the run, the verdict is co-registered.
 */

interface Slot {
  tool: string
  x: number
  h: number
  /** The short data-face label shown under the slot (used by the KG reads). */
  short?: string
}

interface ChannelDef {
  label: string
  tools: readonly string[]
  slots: readonly Slot[]
}

/** The knowledge graph reads drawn on this schematic, in call order (graph.py: knowledge_graph_query_node). */
const KG_SLOTS: readonly Slot[] = [
  { tool: 'get_blast_radius', x: 160, h: 34, short: 'radius' },
  { tool: 'get_dependencies', x: 240, h: 22, short: 'deps' },
  { tool: 'get_historical_incidents', x: 320, h: 28, short: 'history' },
]

const CHANNELS: readonly ChannelDef[] = [
  {
    label: 'observability',
    tools: ['get_errors', 'get_traces', 'get_metrics', 'get_anomalies'],
    slots: [
      { tool: 'get_errors', x: 460, h: 35 },
      { tool: 'get_traces', x: 560, h: 27 },
      { tool: 'get_metrics', x: 660, h: 44 },
      { tool: 'get_anomalies', x: 880, h: 32 },
    ],
  },
  {
    label: 'deploy investigation',
    tools: ['get_recent_deploys'],
    slots: [{ tool: 'get_recent_deploys', x: 660, h: 44 }],
  },
  {
    label: 'incident history investigation',
    tools: ['search_incident_knowledge', 'get_past_resolutions'],
    slots: [
      { tool: 'search_incident_knowledge', x: 460, h: 44 },
      { tool: 'get_past_resolutions', x: 610, h: 30 },
    ],
  },
  {
    label: 'code change investigation',
    tools: ['get_recent_commits', 'get_commit_diff'],
    slots: [
      { tool: 'get_recent_commits', x: 750, h: 44 },
      { tool: 'get_commit_diff', x: 840, h: 44 },
    ],
  },
]

/** Co-registered retention slots: the x positions where two or more channels hold a slot. */
const CO_REGISTERED = [460, 660]

const G = {
  W: 1240,
  H: 520,
  x: { intake: 40, graph: 110, fanStart: 380, fanEnd: 980, join: 1030, gate: 1136, end: 1216 },
  bands: [
    { top: 92, base: 156 }, // knowledge_graph_query — the first query, runs before the channels
    { top: 156, base: 228 }, // observability
    { top: 228, base: 300 }, // deploy
    { top: 300, base: 372 }, // incident history investigation
    { top: 372, base: 444 }, // code change investigation
  ],
  axisY: 470,
  grid: { minor: 20, major: 80 },
  type: { legend: 11, micro: 9.5, tick: 11, verdict: 26 },
}
const HIT_W = 16

interface Props {
  /** The configured confidence gate (investigation.confidence_threshold from /config). */
  threshold: number
}

export default function Chromatogram({ threshold }: Props) {
  const uid = useId().replace(/:/g, '')
  const svgRef = useRef<SVGSVGElement>(null)
  const [cursor, setCursor] = useState<number | null>(null)
  const narrow = useMediaQuery('(max-width: 767px)')

  const allSlots = useMemo(
    () => [...KG_SLOTS, ...CHANNELS.flatMap((c) => c.slots)],
    [],
  )

  const under = useMemo(() => {
    if (cursor == null) return []
    return allSlots.filter((s) => Math.abs(s.x - cursor) <= HIT_W)
  }, [allSlots, cursor])

  const registered = new Set(under.map((s) => s.x)).size >= 2
  const accent = registered ? 'var(--color-signal)' : 'var(--color-tentative)'

  const yFor = (v: number) => G.axisY - v * (G.axisY - G.bands[0].top)
  const gateY = yFor(threshold)

  // The cursor is constrained to the examined window: between the graph query
  // and the gate, where evidence is collected.
  function move(clientX: number) {
    const svg = svgRef.current
    if (!svg) return
    const rect = svg.getBoundingClientRect()
    const x = ((clientX - rect.left) / rect.width) * G.W
    setCursor(Math.min(G.x.gate, Math.max(G.x.graph, x)))
  }

  function step(dir: -1 | 1) {
    const ordered = [...new Set(allSlots.map((s) => s.x))].sort((a, b) => a - b)
    if (cursor == null) {
      setCursor(ordered[dir === 1 ? 0 : ordered.length - 1])
      return
    }
    const next =
      dir === 1
        ? ordered.find((x) => x > cursor + 1)
        : [...ordered].reverse().find((x) => x < cursor - 1)
    setCursor(next ?? cursor)
  }

  const axisTicks = narrow
    ? [
        { x: G.x.graph, label: 'intake' },
        { x: (G.x.fanStart + G.x.fanEnd) / 2, label: '4 concurrent' },
        { x: G.x.gate, label: 'gate' },
      ]
    : [
        { x: G.x.graph, label: 'intake' },
        { x: (G.x.fanStart + G.x.fanEnd) / 2, label: '4 nodes concurrent' },
        { x: G.x.join, label: 'synthesize' },
        { x: G.x.gate, label: 'confidence_gate' },
      ]

  const readout = cursor == null
    ? 'cause withheld below gate'
    : registered
      ? `${new Set(under.map((s) => s.x)).size} CHANNELS CO-REGISTERED`
      : 'evidence reports alone'

  return (
    <figure className="m-0">
      <div
        className={narrow ? '-mx-5 overflow-x-auto overscroll-x-contain px-5 pb-1' : ''}
      >
        <div className={narrow ? 'min-w-[640px]' : ''}>
          <svg
            ref={svgRef}
            viewBox={`0 0 ${G.W} ${G.H}`}
            className="block w-full touch-pan-y select-none"
            role="img"
            aria-label={`Schematic of one investigation: the sample injected at intake, the knowledge graph query drawn first as its own aligned band with three reads (blast radius, dependencies, historical incidents), then four concurrent evidence channels (observability, deploy investigation, incident history investigation, and code change investigation), fused at synthesize, and reported only above a ${threshold.toFixed(2)} confidence gate. Scrub across the plot to co-register independent evidence.`}
            tabIndex={0}
            onPointerMove={(e) => move(e.clientX)}
            onPointerLeave={() => setCursor(null)}
            onKeyDown={(e) => {
              if (e.key === 'ArrowRight') { e.preventDefault(); step(1) }
              else if (e.key === 'ArrowLeft') { e.preventDefault(); step(-1) }
              else if (e.key === 'Escape') { setCursor(null) }
            }}
          >
            <defs>
              <pattern id={`hatch-${uid}`} width="7" height="7" patternTransform="rotate(45)" patternUnits="userSpaceOnUse">
                <line x1="0" y1="0" x2="0" y2="7" stroke="var(--color-tentative)" strokeWidth="1" opacity="0.5" />
              </pattern>
            </defs>
            <g aria-hidden="true">
              {Array.from({ length: Math.ceil(G.W / G.grid.minor) + 1 }, (_, i) => i * G.grid.minor).map((x) => (
                <line key={`vm-${x}`} x1={x} y1="8" x2={x} y2={G.axisY}
                  stroke={x % G.grid.major === 0 ? 'var(--color-grid-major)' : 'var(--color-grid-minor)'}
                  strokeWidth="1" opacity={x % G.grid.major === 0 ? 0.8 : 0.4} />
              ))}
              {Array.from({ length: Math.ceil((G.axisY - 8) / G.grid.minor) + 1 }, (_, i) => 8 + i * G.grid.minor)
                .filter((y) => y <= G.axisY).map((y) => (
                <line key={`hm-${y}`} x1="0" y1={y} x2={G.W} y2={y}
                  stroke={(y - 8) % G.grid.major === 0 ? 'var(--color-grid-major)' : 'var(--color-grid-minor)'}
                  strokeWidth="1" opacity={(y - 8) % G.grid.major === 0 ? 0.8 : 0.4} />
              ))}
            </g>
            <line x1={G.x.graph} y1={G.bands[0].top - 12} x2={G.x.graph} y2={G.axisY} stroke="var(--color-ink-2)" strokeWidth="1" strokeDasharray="3 3" />
            <g>
              <line x1={G.x.graph} y1={G.bands[0].base} x2={G.x.fanStart} y2={G.bands[0].base} stroke="var(--color-ink-3)" strokeWidth="1" />
              {KG_SLOTS.map((s) => {
                const lit = under.includes(s)
                return (
                  <g key={s.tool}>
                    <line x1={s.x} y1={G.bands[0].base} x2={s.x} y2={G.bands[0].base - s.h} stroke={lit ? accent : 'var(--color-ink-2)'} strokeWidth={lit ? 2 : 1} />
                    <path d={`M ${s.x - 5} ${G.bands[0].base - s.h - 7} L ${s.x} ${G.bands[0].base - s.h} L ${s.x + 5} ${G.bands[0].base - s.h - 7} Z`} fill="none" stroke={lit ? accent : 'var(--color-ink)'} strokeWidth="1.25" />
                    <text x={s.x} y={G.bands[0].base - s.h - 12} textAnchor="middle" className="data-tight" fill={lit ? accent : 'var(--color-ink-3)'} style={{ fontSize: G.type.micro }}>{s.short}</text>
                  </g>
                )
              })}
              {narrow ? (
                <text x={G.x.graph - 10} y={G.bands[0].base - 4} textAnchor="end" className="legend" fill="var(--color-ink)" style={{ fontSize: G.type.legend }}>KG</text>
              ) : (
                <>
                  <text x={G.x.graph - 10} y={G.bands[0].base - 12} textAnchor="end" className="legend" fill="var(--color-ink)" style={{ fontSize: G.type.legend }}>KG QUERY</text>
                  <text x={G.x.graph - 10} y={G.bands[0].base} textAnchor="end" className="data-tight" fill="var(--color-ink-3)" style={{ fontSize: G.type.micro }}>RUNS FIRST</text>
                </>
              )}
            </g>
            {CHANNELS.map((channel, i) => {
              const band = G.bands[i + 1]
              const underHere = under.filter((s) => CHANNELS[i].slots.includes(s))
              return (
                <g key={channel.label}>
                  <line x1={G.x.fanStart} y1={band.base} x2={G.x.join - 40} y2={band.base} stroke="var(--color-ink-3)" strokeWidth="1" />
                  {channel.slots.map((s) => {
                    const lit = underHere.includes(s)
                    return (
                      <g key={s.tool}>
                        <line x1={s.x} y1={band.base} x2={s.x} y2={band.base - s.h} stroke={lit ? accent : 'var(--color-ink-2)'} strokeWidth={lit ? 2 : 1} />
                        <path d={`M ${s.x - 5} ${band.base - s.h - 7} L ${s.x} ${band.base - s.h} L ${s.x + 5} ${band.base - s.h - 7} Z`} fill="none" stroke={lit ? accent : 'var(--color-ink)'} strokeWidth="1.25" />
                        <text x={s.tool === 'get_metrics' ? s.x - 9 : s.x} y={band.base - s.h - 12} textAnchor={s.tool === 'get_metrics' ? 'end' : 'middle'} className="data-tight" fill={lit ? accent : 'var(--color-ink-3)'} style={{ fontSize: G.type.micro }}>
                          {narrow && channel.slots.length > 1 ? `${i + 1}.${channel.slots.indexOf(s) + 1}` : s.tool}
                        </text>
                      </g>
                    )
                  })}
                  {narrow ? (
                    <text x={G.x.graph - 10} y={band.base - 4} textAnchor="end" className="legend" fill="var(--color-ink)" style={{ fontSize: G.type.legend }}>CH {i + 1}</text>
                  ) : (() => {
                    const words = channel.label.toUpperCase().split(' ')
                    const firstLine =
                      words.length > 1 ? words.slice(0, -1).join(' ') : words[0]
                    const lastWord = words.length > 1 ? words[words.length - 1] : null
                    return (
                      <>
                        <text x={G.x.graph - 10} y={band.base - 12} textAnchor="end" className="legend" fill="var(--color-ink)" style={{ fontSize: G.type.legend }}>{firstLine}</text>
                        {lastWord != null ? (
                          <text x={G.x.graph - 10} y={band.base} textAnchor="end" className="data-tight" fill="var(--color-ink-3)" style={{ fontSize: G.type.micro }}>{lastWord}</text>
                        ) : null}
                      </>
                    )
                  })()}
                </g>
              )
            })}
            {CO_REGISTERED.map((x) => (
              <g key={`coreg-${x}`}>
                <line x1={x} y1={G.bands[1].top} x2={x} y2={G.bands[4].base} stroke="var(--color-signal)" strokeWidth="1" strokeDasharray="1 4" opacity="0.45" />
              </g>
            ))}
            {(() => {
              const mid = (G.bands[2].base + G.bands[3].base) / 2
              return (
                <g>
                  {G.bands.slice(1).map((band, i) => (
                    <path key={`conv-${i}`} d={`M ${G.x.join - 40} ${band.base} C ${G.x.join - 10} ${band.base} ${G.x.join - 10} ${mid} ${G.x.join} ${mid}`} fill="none" stroke="var(--color-ink)" strokeWidth="1.25" opacity="0.75" />
                  ))}
                  <path d={`M ${G.x.join} ${mid} L ${G.x.gate} ${mid}`} fill="none" stroke="var(--color-ink-2)" strokeWidth="1.5" />
                  <circle cx={G.x.join} cy={mid} r="3" fill="var(--color-ink)" />
                </g>
              )
            })()}
            <line x1={G.x.join} y1={G.bands[0].top - 12} x2={G.x.join} y2={G.axisY} stroke="var(--color-ink-2)" strokeWidth="1" strokeDasharray="3 3" />
            <g>
              <line x1={G.x.gate} y1={G.bands[0].top - 12} x2={G.x.gate} y2={G.axisY} stroke="var(--color-ink)" strokeWidth="1.5" />
              <rect x={G.x.gate + 1} y={gateY} width={G.x.end - G.x.gate - 1} height={G.axisY - gateY} fill={`url(#hatch-${uid})`} opacity="0.7" />
              <circle cx={G.x.gate} cy={gateY} r="3" fill="var(--color-ink)" />
              <line x1={G.x.gate + 1} y1={gateY} x2={G.x.end} y2={gateY} stroke="var(--color-ink-2)" strokeWidth="1.25" strokeDasharray="6 5" opacity="0.9" />
              <text x={G.x.end} y={gateY - 7} textAnchor="end" className="data-tight" fill="var(--color-ink-2)" style={{ fontSize: G.type.micro }}>gate {threshold.toFixed(2)}</text>
              <text x={G.x.gate + 1} y={G.bands[0].top - 2} textAnchor="end" className="verdict-type" style={{ fontSize: readout === 'cause withheld below gate' ? 13 : 15, fill: registered ? 'var(--color-signal)' : 'var(--color-tentative)' }}>{readout}</text>
              <text x={G.x.end} y={gateY + 14} textAnchor="end" className="data-tight" fill="var(--color-tentative)" style={{ fontSize: G.type.micro }}>below: verdict withheld</text>
            </g>
            {cursor != null && (
              <g aria-hidden="true">
                <line x1={cursor} y1={G.bands[0].top - 10} x2={cursor} y2={G.axisY} stroke={registered ? accent : 'var(--color-ink-2)'} strokeWidth={registered ? 2 : 1} />
                {registered && <rect x={cursor - 1} y={G.bands[1].top} width="2" height={G.bands[4].base - G.bands[1].top} fill={accent} opacity="0.25" />}
              </g>
            )}
            <g>
              <line x1="0" y1={G.axisY} x2={G.W} y2={G.axisY} stroke="var(--color-ink)" strokeWidth="1.5" />
              {axisTicks.map((t) => (
<g key={t.label}>
                        <line x1={t.x} y1={G.axisY} x2={t.x} y2={G.axisY + 6} stroke="var(--color-ink)" strokeWidth="1.5" />
                        <text x={t.x} y={G.axisY + 19} textAnchor="middle" className="data-tight" fill="var(--color-ink-2)" style={{ fontSize: 11 }}>{t.label}</text>
                      </g>
              ))}
            </g>
          </svg>
        </div>
      </div>

      {narrow && (
        <figcaption className="legend mt-2 text-ink-3">Scroll the plot sideways →</figcaption>
      )}
    </figure>
  )
}
