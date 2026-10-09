import { useEffect, useState } from 'react'
import { fetchConfig, type SystemConfig } from '../data/dashboard'
import Chromatogram from './Chromatogram'

/**
 * The instrument backdrop. The claim sits above the shared apparatus (intake →
 * graph → three concurrent evidence channels → synthesize → confidence gate).
 * Nothing here is transcribed from a recording: the gate is read from /config,
 * and the plot is a schematic of the real pipeline.
 */
export default function HeroRun() {
  const [config, setConfig] = useState<SystemConfig | null>(null)

  useEffect(() => {
    let cancelled = false
    fetchConfig()
      .then((c) => {
        if (!cancelled) setConfig(c)
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [])

  const threshold = config?.investigation.confidence_threshold ?? 0.6

  return (
    <section>
      <div className="chart-grid flex flex-col">
        <div className="hero-pad mx-auto w-full max-w-[1400px] px-5 sm:px-8 lg:px-12">
          <h1 className="verdict-type hero-title text-ink" style={{ maxWidth: '18ch' }}>
            An alert is an unresolved mixture.
          </h1>
          <p className="prose-measure hero-lede text-ink-2">
            Sift is an automated incident triage platform for production services. When an
            alert fires, it assembles the blast radius through the knowledge graph, reads
            four evidence sources in parallel, and fuses their findings
            into a single root cause report with an explicit confidence score. A cause is
            named only when the collected evidence clears the gate, and the full call trail
            stays attached for audit.
          </p>

          {/* The apparatus: a schematic of the real pipeline, not a recording. */}
          <div className="mt-12 border border-grid-major bg-stock">
            <div className="flex flex-wrap items-baseline justify-between gap-3 border-b border-grid-major px-5 py-3">
              <h2 className="legend text-ink">
                The shared apparatus — four channels and a gate
              </h2>
            </div>
            <div className="p-5 lg:p-8">
              <Chromatogram threshold={threshold} />
            </div>
            <p className="px-5 pb-5 text-[0.8125rem] leading-snug text-ink-2 lg:px-8">
              The schematic shows a single investigation from intake to verdict. The knowledge
              graph query draws first, reading blast radius, dependencies, and historical
              incidents. The three evidence channels then run in parallel, covering
              observability, deployment history, and incident knowledge with code diff behind one
              node, and all of it feeds the confidence gate before a cause is named. Scrubbing
              across the plot moves the registration cursor. Wherever two or more independent
              channels hold evidence at the same point in the run, the findings are co-registered
              as the corroboration the verdict is built on.
            </p>
          </div>
        </div>
      </div>
    </section>
  )
}