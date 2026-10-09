interface Source {
  label: string
  note: string
  concurrent: boolean
}

const SOURCES: Source[] = [
  {
    label: 'Knowledge Graph',
    note:
      'Before any channel opens, the knowledge graph turns the alert into a blast radius question. It identifies which services depend on the failing one, who owns each service, and how this failure has been handled in the past, so every later check knows exactly where to look.',
    concurrent: false,
  },
  {
    label: 'observability',
    note:
      'Measures the failure across every affected service. It gathers error rates, traces, metrics, and anomalies to establish what failed, when it started, and how widely it spread.',
    concurrent: true,
  },
  {
    label: 'deploy investigation',
    note:
      'Establishes the change context. It identifies what was released just before the alert struck and matches that release window against the incident timeline.',
    concurrent: true,
  },
  {
    label: 'incident history investigation',
    note:
      'Searches past incidents and their resolutions to surface the fixes that have worked for this failure mode in the past.',
    concurrent: true,
  },
  {
    label: 'code diff investigation',
    note:
      'Names the concrete change on the wire. It reviews the commits that just shipped to tie the incident to the exact change that introduced it.',
    concurrent: true,
  },
]

/**
 * The evidence sources. Each source answers one question independently and
 * runs in parallel with the others, so a mistake in any single source must
 * be contradicted by the rest before it reaches the report.
 */
export default function Channels() {
  const concurrent = SOURCES.filter((s) => s.concurrent)
  const first = SOURCES.filter((s) => !s.concurrent)

  return (
    <section id="channels" className="scroll-mt-16 border-b border-ink">
      <div className="mx-auto w-full max-w-[1400px] px-5 pt-4 pb-16 sm:px-8 lg:px-12 lg:pt-6 lg:pb-24">
        <h2 className="section-type text-[clamp(1.9rem,3.4vw,2.9rem)]">
          How Sift investigates an incident.
        </h2>
        <p className="mt-5 text-[1.0625rem] leading-[1.6] text-ink-2">
          When an alert fires, Sift does not rely on a single source. It gathers evidence from
          independent channels that cover the failure itself, what changed just before it, how
          the service has broken in the past, and which code was involved. The findings are
          combined into one report, so a mistake in any single source must be contradicted by
          the others before it reaches the final verdict.
        </p>

        <div className="mt-12 border-t border-ink pt-5">
          <h2 className="section-type text-[clamp(1.9rem,3.4vw,2.9rem)] text-ink">The evidence channels</h2>
          <div className="mt-5 flex flex-col rounded-xl border border-grid-major bg-stock-2 p-6 md:w-1/2">
            <div className="flex items-baseline gap-x-4">
              <span className="legend text-ink-3">Runs first</span>
              <h4 className="section-type text-[1.35rem] text-ink">{first[0].label}</h4>
            </div>
            <p className="prose-measure mt-4 text-[0.9375rem] leading-relaxed text-ink-2">
              {first[0].note}
            </p>
          </div>
        </div>

        <div className="mt-12 border-t border-ink pt-5">
          <h4 className="section-type text-[clamp(1.35rem,2vw,1.75rem)] text-ink capitalize">Four concurrent channels</h4>
          <div className="mt-5 grid auto-rows-fr gap-4 md:grid-cols-2">
            {concurrent.map((channel, i) => (
              <div
                key={channel.label}
                className="flex flex-col rounded-xl border border-grid-major bg-stock-2 p-6"
              >
                <div className="flex items-baseline gap-x-4">
                  <span className="legend text-ink-3">CH {i + 1}</span>
                  <h4 className="section-type text-[clamp(1.35rem,1.8vw,1.6rem)] text-ink capitalize">
                    {channel.label}
                  </h4>
                </div>
                <p className="prose-measure mt-4 text-[0.9375rem] leading-relaxed text-ink-2">
                  {channel.note}
                </p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}