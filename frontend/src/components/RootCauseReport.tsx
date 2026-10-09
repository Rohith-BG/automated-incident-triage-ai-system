import type { ReportResponse } from '../data/dashboard'
import { GATE_THRESHOLD } from '../data/run'

/**
 * The instrument's verdict: the root-cause report for one incident. Rendered
 * as a structured incident-report card with sections for each evidence type:
 * affected services, raw observability data, analysis, code diffs, past
 * resolutions (when present), and the final root-cause diagnosis with
 * remediation steps. Confidence is drawn in the data face and tinted by
 * whether it clears the detection limit.
 */

function ReportField({
  label,
  children,
}: {
  label: string
  children: React.ReactNode
}) {
  return (
    <div>
      <h3 className="legend text-ink-3">{label}</h3>
      <div className="mt-2 text-[0.9375rem] leading-relaxed text-ink">
        {children}
      </div>
    </div>
  )
}

/** Render a JSON evidence blob as a readable, collapsible <pre>. */
function JsonEvidence({ label, data }: { label: string; data: Record<string, unknown> }) {
  if (!data || Object.keys(data).length === 0) return null
  return (
    <details className="group">
      <summary className="legend text-ink-3 cursor-pointer select-none">
        {label}
        <span className="ml-2 text-[0.75rem] text-ink-4 group-open:hidden">▸ expand</span>
        <span className="ml-2 text-[0.75rem] text-ink-4 hidden group-open:inline">▾ collapse</span>
      </summary>
      <pre className="mt-2 max-h-64 overflow-auto rounded-md border border-grid-minor bg-stock-2 p-3 text-[0.8125rem] leading-relaxed text-ink-2">
        {JSON.stringify(data, null, 2)}
      </pre>
    </details>
  )
}

export default function RootCauseReport({ report }: { report: ReportResponse }) {
  const clears = report.confidence_score >= GATE_THRESHOLD
  const confidencePct = Math.round(
    Math.min(1, Math.max(0, report.confidence_score)) * 100,
  )
  const accent = clears ? 'var(--color-signal)' : 'var(--color-tentative)'
  const hasPastResolutions =
    Array.isArray(report.past_resolutions) && report.past_resolutions.length > 0

  return (
    <article className="overflow-hidden rounded-lg border border-grid-major bg-stock">
      <header className="flex flex-wrap items-center justify-between gap-4 border-b border-grid-major px-6 py-5">
        <div>
          <h2 className="section-type text-ink">Root cause report</h2>
        </div>
        <span
          className="data-tight rounded-md border px-2.5 py-1.5"
          style={{
            color: accent,
            borderColor: accent,
            backgroundColor: `color-mix(in srgb, ${accent} 12%, var(--color-stock))`,
          }}
        >
          {clears ? 'Confident' : 'Below threshold'} ·{' '}
          {report.confidence_score.toFixed(2)}
        </span>
      </header>

      <div className="grid gap-x-10 px-6 py-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,19rem)]">
        <div className="space-y-7">
          {/* 1. Affected services */}
          {report.affected_services.length > 0 ? (
            <div>
              <h3 className="legend text-ink-3">Affected services</h3>
              <ul className="mt-2.5 flex flex-wrap gap-2">
                {report.affected_services.map((s) => (
                  <li
                    key={s}
                    className="data-tight rounded-md border border-grid-major bg-stock-2 px-2 py-1 text-ink"
                  >
                    {s}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {/* 2. Raw logs & traces */}
          <JsonEvidence label="Raw logs & traces" data={report.raw_logs} />

          {/* 3. Raw metrics */}
          <JsonEvidence label="Raw metrics & anomalies" data={report.raw_metrics} />

          {/* 4. Observability analysis */}
          {report.observability_analysis ? (
            <ReportField label="Observability analysis">
              {report.observability_analysis}
            </ReportField>
          ) : null}

          {/* 5. Code diffs */}
          <JsonEvidence label="Code diffs & commits" data={report.code_diffs} />

          {/* 6. Past resolutions — only shown when they exist */}
          {hasPastResolutions ? (
            <div>
              <h3 className="legend text-ink-3">Previously resolved incidents</h3>
              <div className="mt-2 space-y-3">
                {report.past_resolutions.map((res, i) => (
                  <div
                    key={i}
                    className="rounded-md border border-grid-minor bg-stock-2 p-3 text-[0.8125rem] leading-relaxed text-ink-2"
                  >
                    <pre className="whitespace-pre-wrap">
                      {JSON.stringify(res, null, 2)}
                    </pre>
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          {/* 7. Root cause */}
          <ReportField label="Root cause">{report.root_cause}</ReportField>

          {/* 8. Remediation */}
          {report.remediation_steps.length > 0 ? (
            <div>
              <h3 className="legend text-ink-3">Remediation</h3>
              <ol className="mt-2 list-decimal space-y-2 pl-5">
                {report.remediation_steps.map((step) => (
                  <li
                    key={step}
                    className="text-[0.9375rem] leading-relaxed text-ink"
                  >
                    {step}
                  </li>
                ))}
              </ol>
            </div>
          ) : null}
        </div>

        <aside className="mt-7 space-y-7 border-t border-grid-minor pt-7 lg:mt-0 lg:border-l lg:border-t-0 lg:pl-10 lg:pt-0">
          <div>
            <div className="flex items-baseline justify-between gap-4">
              <span className="legend text-ink-3">Confidence</span>
              <span className="data text-[1.35rem]" style={{ color: accent }}>
                {report.confidence_score.toFixed(2)}
              </span>
            </div>
            <div
              className="mt-2.5 h-1.5 overflow-hidden rounded-full"
              style={{ backgroundColor: 'var(--color-stock-3)' }}
              role="meter"
              aria-valuemin={0}
              aria-valuemax={1}
              aria-valuenow={report.confidence_score}
            >
              <div
                className="h-full rounded-full"
                style={{ width: `${confidencePct}%`, backgroundColor: accent }}
              />
            </div>
            <p className="mt-2 text-[0.8125rem] leading-relaxed text-ink-3">
              Detection limit {GATE_THRESHOLD.toFixed(2)}.{' '}
              {clears ? 'Clears the gate.' : 'Below the gate.'}
            </p>
          </div>

          {report.uncertainty ? (
            <div>
              <h3 className="legend text-tentative">Uncertainty</h3>
              <p className="mt-2 text-[0.875rem] leading-relaxed text-ink-2">
                {report.uncertainty}
              </p>
            </div>
          ) : null}
        </aside>
      </div>
    </article>
  )
}