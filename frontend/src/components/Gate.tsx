import { useEffect, useState } from 'react'
import { fetchConfig } from '../data/dashboard'
import { GateMark } from './Icons'

const W = 900
const H = 360
const PAD = { l: 48, r: 90, t: 30, b: 54 }
const plotW = W - PAD.l - PAD.r
const plotH = H - PAD.t - PAD.b

const yFor = (v: number) => PAD.t + (1 - v) * plotH

const OUTCOMES = [
  {
    id: 'cleared',
    claim: 'A cause is named.',
    note: 'Above the threshold, the report names a root cause — carrying its evidence, affected services, and a confidence score that must justify the claim.',
  },
  {
    id: 'withheld',
    claim: 'A cause is withheld.',
    note: 'Below the threshold, no cause is offered. The report states what was established, what could not be established, and why — then leaves the verdict open.',
  },
  {
    id: 'uncertain',
    claim: 'Uncertainty is written down.',
    note: 'Every report carries an uncertainty field, so a conclusion never travels without the limits of its own evidence attached.',
  },
]

/**
 * The discipline, not a recorded outcome. The gate is a configured rule
 * (investigation.confidence_threshold) read from /config; nothing on this
 * section is a claimed measurement. A report that guesses confidently is
 * worse than one that admits the evidence ran out.
 */
export default function Gate() {
  const [threshold, setThreshold] = useState(0.6)

  useEffect(() => {
    let cancelled = false
    fetchConfig()
      .then((c) => {
        if (!cancelled) setThreshold(c.investigation.confidence_threshold)
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <section id="gate" className="scroll-mt-16 border-b border-ink">
      <div className="mx-auto w-full max-w-[1400px] px-5 py-16 sm:px-8 lg:px-12 lg:py-24">
        <div className="grid gap-x-14 gap-y-9 lg:grid-cols-[minmax(0,30rem)_minmax(0,1fr)] lg:items-center">
          <div>
            <h2 className="section-type text-[clamp(1.9rem,3.4vw,2.9rem)] text-ink">
              It is allowed to not know.
            </h2>
            <p className="prose-measure mt-5 text-[1.0625rem] leading-[1.6] text-ink-2">
              Every report carries a confidence score, and the score is weighed against the
              collected evidence before a cause is named. The investigation reports what it
              established and states clearly what it could not establish, so no verdict is
              offered without the evidence to back it.
            </p>
            <p className="mt-5 flex items-start gap-2.5 text-[0.9375rem] leading-relaxed text-ink-2">
              <GateMark className="mt-0.5 shrink-0 text-ink-3" />
              <span>
                The gate for this deployment is set at a <span className="data text-ink">{threshold.toFixed(2)}</span>{' '}
                confidence threshold. Any verdict that cannot clear it is withheld and reported as
                unresolved rather than named.
              </span>
            </p>
          </div>

          <div>
            <div className="mb-3 flex flex-wrap items-baseline justify-between gap-3">
              <h3 className="legend text-ink">The gate</h3>
            </div>

            <svg
              viewBox={`0 0 ${W} ${H}`}
              className="block w-full"
              role="img"
              aria-label={`The confidence gate, configured at ${threshold.toFixed(2)}. Above the rule a cause is named; below it the cause is withheld and the uncertainty is reported.`}
            >
              {[0, 0.2, 0.4, 0.6, 0.8, 1].map((v) => (
                <g key={v}>
                  <line
                    x1={PAD.l}
                    y1={yFor(v)}
                    x2={W - PAD.r}
                    y2={yFor(v)}
                    stroke="var(--color-grid-major)"
                    strokeWidth="1"
                    opacity={v === 0 ? 1 : 0.55}
                  />
                  <text
                    x={PAD.l - 10}
                    y={yFor(v) + 3.5}
                    textAnchor="end"
                    className="data-tight"
                    fill="var(--color-ink-3)"
                    style={{ fontSize: 14 }}
                  >
                    {v.toFixed(1)}
                  </text>
                </g>
              ))}

              <defs>
                <pattern
                  id="gate-hatch"
                  width="7"
                  height="7"
                  patternTransform="rotate(45)"
                  patternUnits="userSpaceOnUse"
                >
                  <line
                    x1="0"
                    y1="0"
                    x2="0"
                    y2="7"
                    stroke="var(--color-tentative)"
                    strokeWidth="1"
                    opacity="0.45"
                  />
                </pattern>
              </defs>

              {/* The region where the verdict is withheld. */}
              <rect
                x={PAD.l}
                y={yFor(threshold)}
                width={plotW}
                height={yFor(0) - yFor(threshold)}
                fill="url(#gate-hatch)"
              />

              <text
                x={(PAD.l + W - PAD.r) / 2}
                y={yFor(threshold) + 34}
                textAnchor="middle"
                className="data-tight"
                fill="var(--color-tentative)"
                style={{ fontSize: 15 }}
              >
                cause withheld · uncertainty reported
              </text>

              {/* The rule. */}
              <line
                x1={PAD.l}
                y1={yFor(threshold)}
                x2={W - PAD.r + 80}
                y2={yFor(threshold)}
                stroke="var(--color-ink)"
                strokeWidth="1.5"
                strokeDasharray="7 5"
              />
              <text
                x={W - PAD.r + 80}
                y={yFor(threshold) - 9}
                textAnchor="end"
                className="legend"
                fill="var(--color-ink)"
                style={{ fontSize: 15 }}
              >
                GATE {threshold.toFixed(2)}
              </text>

              <text
                x={(PAD.l + W - PAD.r) / 2}
                y={Math.max(PAD.t + 16, yFor(threshold) - 16)}
                textAnchor="middle"
                className="legend"
                fill="var(--color-ink-2)"
                style={{ fontSize: 15 }}
              >
                above: cause named with its evidence
              </text>
            </svg>
          </div>
        </div>

        <div className="mt-14 border-t border-ink pt-8">
          <div className="grid gap-x-10 gap-y-8 md:grid-cols-3">
            {OUTCOMES.map((o) => (
              <div key={o.id} className="border-t border-grid-major pt-4">
                <h3 className="legend text-ink">{o.claim}</h3>
                <p className="prose-measure mt-2 text-[0.9375rem] leading-relaxed text-ink-2">
                  {o.note}
                </p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}