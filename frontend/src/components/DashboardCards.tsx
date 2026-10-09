import { useEffect, useState, type CSSProperties } from 'react'
import { Link } from 'react-router-dom'
import { withAuthRetry } from '../lib/auth'
import { fetchServiceRegistry } from '../data/service_registry'
import { IncidentMark, ServiceMark, GraphMark, FlowMark, LeaderArrow } from './Icons'

interface CardDef {
  /** Route this card navigates to. Absent for cards whose destination page is removed. */
  to?: string
  title: string
  description: string
  icon: React.ComponentType<{ className?: string }>
  meta: string
}

const CARDS: CardDef[] = [
  {
    to: '/incidents',
    title: 'Incidents',
    description: 'Active and past investigations, each with its root-cause report.',
    meta: 'View list',
    icon: IncidentMark,
  },
  {
    to: '/services',
    title: 'Services',
    description: 'Catalog of services with dependency and blast-radius maps.',
    meta: 'Service count',
    icon: ServiceMark,
  },
  {
    to: '/graph',
    title: 'Knowledge graph',
    description: 'Services, dependencies, and owners mapped to speed up triage.',
    meta: 'Review proposals',
    icon: GraphMark,
  },
  {
    to: '/workflow',
    title: 'Agent workflow',
    description: 'Trace the full investigation: intake to confidence gate, step by step.',
    meta: 'Pipeline',
    icon: FlowMark,
  },
]

export default function DashboardCards() {
  const [serviceCount, setServiceCount] = useState<number | null>(null)
  const [countError, setCountError] = useState(false)

  useEffect(() => {
    let cancelled = false
    withAuthRetry(() => fetchServiceRegistry())
      .then((services) => {
        if (!cancelled) setServiceCount(services.length)
      })
      .catch(() => {
        if (!cancelled) setCountError(true)
      })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <section aria-label="Operations" className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {CARDS.map((card, index) => {
        const Icon = card.icon
        const isServiceCard = card.to === '/services'
        const meta = isServiceCard
          ? countError
            ? 'unavailable'
            : serviceCount === null
              ? 'counting…'
              : `${serviceCount} services`
          : card.meta
        const enterStyle: CSSProperties = { animationDelay: `${index * 70}ms` }
        const shared =
          'group flex flex-col rounded-xl border border-grid-major bg-stock p-5 dash-card'
        const inner = (
          <>
            <div className="flex items-start justify-between">
              <Icon className="text-ink transition-colors group-hover:text-ink-2" />
              <span
                className={`legend transition-colors ${
                  isServiceCard && countError ? 'text-tentative' : 'text-ink-2 group-hover:text-signal'
                }`}
              >
                {meta}
              </span>
            </div>
            <h3 className="section-type mt-auto flex min-h-[2.8rem] items-center gap-2 pt-6 text-[1.35rem]">
              {card.title}
              {card.to ? (
                <LeaderArrow className="text-signal translate-x-[-3px] opacity-0 transition-[opacity,transform] duration-200 group-hover:translate-x-0 group-hover:opacity-100" />
              ) : null}
            </h3>
            <p className="mt-2.5 min-h-[4.25rem] text-[0.875rem] leading-relaxed text-ink-2">
              {card.description}
            </p>
          </>
        )
        return card.to ? (
          <Link
            key={card.to}
            to={card.to}
            style={enterStyle}
            className={`${shared} transition-[border-color,box-shadow,transform] duration-200 ease-out hover:-translate-y-0.5 hover:border-ink hover:shadow-[0_16px_30px_-18px_rgba(23,26,23,0.45)]`}
          >
            {inner}
          </Link>
        ) : (
          <div key={card.title} style={enterStyle} className={shared}>
            {inner}
          </div>
        )
      })}
    </section>
  )
}
