import { Link } from 'react-router-dom'
import {
  STATUS_COLOR,
  STATUS_LABEL,
  isActiveStatus,
  type IncidentSummary,
  type IncidentStatus,
} from '../data/dashboard'

/**
 * A single row of the incident register. Drawn as a ledger line: status dot,
 * service, first alert and status in the instrument face. The whole row is
 * the opening action. The list response carries no report and no message, so
 * the middle column reads the first-alert time and alert count. Confidence
 * is read on the detail page where the report exists.
 */

function StatusDot({ status }: { status: string }) {
  const color = STATUS_COLOR[status as IncidentStatus] ?? 'var(--color-ink-3)'
  const pulse = isActiveStatus(status)
  return (
    <span
      className={`inline-block h-2 w-2 shrink-0 ${pulse ? 'animate-pulse' : ''}`}
      style={{ backgroundColor: color, borderRadius: 0 }}
      aria-hidden="true"
    />
  )
}

function formatFirstAlertAt(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

export default function RegisterRow({ incident }: { incident: IncidentSummary }) {
  return (
    <li className="border-b border-grid-minor last:border-b-0">
      <Link
        to={`/incidents/${incident.id}`}
        className="grid grid-cols-[auto_repeat(3,minmax(0,1fr))] items-center gap-x-6 px-4 py-3.5 transition-colors hover:bg-stock-2"
      >
        <StatusDot status={incident.status} />
        <span className="data-tight truncate text-ink">{incident.service_id}</span>
        <span className="hidden items-baseline gap-x-2 truncate text-[0.875rem] leading-snug text-ink-2 sm:flex">
          {formatFirstAlertAt(incident.created_at)}
          <span className="legend shrink-0 text-ink-3">
            {incident.alert_count} {incident.alert_count === 1 ? 'alert' : 'alerts'}
          </span>
        </span>
        <span className="legend text-ink-2">
          {STATUS_LABEL[incident.status as IncidentStatus] ?? incident.status}
        </span>
      </Link>
    </li>
  )
}
