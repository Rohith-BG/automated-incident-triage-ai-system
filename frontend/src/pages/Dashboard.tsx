import type { CSSProperties } from 'react'
import DashboardCards from '../components/DashboardCards'
import DashboardIncidents from '../components/DashboardIncidents'
import DashboardMetrics from '../components/DashboardMetrics'
import BoardMasthead from '../components/BoardMasthead'

function stagger(delayMs: number): CSSProperties {
  return { animationDelay: `${delayMs}ms` }
}

export default function Dashboard() {
  return (
    <div className="min-h-dvh">
      <BoardMasthead />

      <main className="mx-auto w-full max-w-[1400px] px-5 py-10 sm:px-8 lg:px-12">
        <div className="mb-8">
          <h1 className="verdict-type text-[clamp(2rem,4.5vw,3.25rem)]">
            Operations
          </h1>
          <p className="prose-measure mt-3 text-[1.0625rem] leading-[1.6] text-ink-2">
            The services under triage, the investigations running on them, and
            how the agent pipeline is resolving each signal.
          </p>
        </div>

        <div className="space-y-10">
          <div className="dash-enter" style={stagger(0)}>
            <DashboardCards />
          </div>

          <div className="dash-enter" style={stagger(90)}>
            <DashboardMetrics />
          </div>

          <div className="dash-enter" style={stagger(180)}>
            <DashboardIncidents />
          </div>
        </div>
      </main>
    </div>
  )
}
