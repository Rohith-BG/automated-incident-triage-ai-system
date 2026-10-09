import { useEffect, useRef, useState } from 'react'
import { fetchDashboardSummary, type DashboardSummary } from '../data/dashboard'
import { withAuthRetry } from '../lib/auth'

const BASE_INTERVAL_MS = 5_000
const MAX_RETRY_MS = 60_000

export default function DashboardMetrics() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null)
  const [offline, setOffline] = useState(false)
  const backoff = useRef(0)
  const loading = useRef(false)

  useEffect(() => {
    let cancelled = false

    const schedule = (delay: number) => window.setTimeout(run, delay)

    async function run() {
      if (loading.current) {
        schedule(1_000)
        return
      }
      loading.current = true
      try {
        const data = await withAuthRetry(() => fetchDashboardSummary())
        if (cancelled) return
        setSummary(data)
        setOffline(false)
        backoff.current = 0
        loading.current = false
        timer = schedule(BASE_INTERVAL_MS)
      } catch {
        if (cancelled) return
        setOffline(true)
        backoff.current = Math.min(backoff.current + 1, MAX_RETRY_MS / 1_000)
        loading.current = false
        timer = schedule(backoff.current * 1_000)
      }
    }

    let timer = schedule(0)

    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [])

  const incident = summary?.incident_summary
  const health = summary?.service_health

  return (
    <section aria-label="Operational overview" className="flex flex-col gap-4">
      <MetricGroup title="Incidents summary">
        <div className="grid grid-cols-2 gap-x-8 gap-y-6 sm:grid-cols-4">
          <Counter value={incident?.active ?? 0} label="active" />
          <Counter value={incident?.resolved_today ?? 0} label="resolved today" />
        </div>
        {offline ? <p className="data-tight text-tentative">Could not load operational metrics.</p> : null}
      </MetricGroup>

      <MetricGroup title="Service health">
        <div className="grid grid-cols-2 gap-x-8 gap-y-6 sm:grid-cols-4">
          <Counter value={health?.healthy ?? 0} label="healthy" />
          <Counter value={health?.degraded ?? 0} label="degraded" />
          <Counter value={health?.critical ?? 0} label="critical" />
          <Counter value={health?.total ?? 0} label="total" />
        </div>
      </MetricGroup>
    </section>
  )
}

/* ── Shared metric affordances ──────────────────────────────────────── */

function useCountUp(target: number, duration = 700): number {
  const [value, setValue] = useState(target)
  const prevValue = useRef(target)

  useEffect(() => {
    const from = prevValue.current
    prevValue.current = target

    if (from === target) {
      setValue(target)
      return
    }

    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      setValue(target)
      return
    }

    const start = performance.now()
    let raf = 0
    const tick = (now: number) => {
      const elapsed = now - start
      const t = Math.min(1, elapsed / duration)
      // Ease out cubic
      const eased = 1 - Math.pow(1 - t, 3)
      setValue(from + (target - from) * eased)
      if (t < 1) {
        raf = requestAnimationFrame(tick)
      } else {
        setValue(target)
      }
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [target, duration])

  return value
}

function Counter({ value, label }: { value: number; label: string }) {
  const v = useCountUp(value)
  return (
    <div>
      <div className="verdict-type text-[clamp(2rem,3.4vw,2.75rem)] text-ink">
        {Math.round(v).toLocaleString()}
      </div>
      <div className="legend mt-2 leading-tight text-ink-2">{label}</div>
    </div>
  )
}

function MetricGroup({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-grid-major bg-stock px-5 py-4">
      <h3 className="legend mb-4 text-ink">{title}</h3>
      <div className="space-y-4">{children}</div>
    </div>
  )
}