/**
 * Dashboard domain types and API calls.
 *
 * Types mirror the backend Pydantic response schemas exactly:
 *   - backend/app/schemas/incidents.py (IncidentSummaryResponse …)
 *   - backend/app/schemas/services.py (ServiceSummary …)
 * All data is fetched from the live API; nothing is hardcoded here.
 */

import { api } from '../lib/api'

/* ── Incident types (backend incidents.py schemas) ───────────────────── */

export type IncidentStatus =
  | 'investigating'
  | 'root_cause_identified'
  | 'resolved'
  | 'completed'
  | 'failed'

export interface IncidentSummary {
  id: string
  service_id: string
  status: string
  created_at: string
  updated_at: string
  alert_count: number
}

export interface IncidentList {
  items: IncidentSummary[]
  next_cursor: string | null
  has_more: boolean
  limit: number
}

export interface Alert {
  id: string
  incident_id: string
  alert_message: string
  created_at: string
}

export interface ReportResponse {
  id: string
  root_cause: string
  affected_services: string[]
  raw_logs: Record<string, unknown>
  raw_metrics: Record<string, unknown>
  observability_analysis: string
  code_diffs: Record<string, unknown>
  past_resolutions: Record<string, unknown>[]
  remediation_steps: string[]
  confidence_score: number
  uncertainty: string
  created_at: string
}

export interface IncidentDetail {
  id: string
  service_id: string
  status: string
  created_at: string
  updated_at: string
  alerts: Alert[]
  report: ReportResponse | null
  resolution: unknown | null
}

/* ── Dashboard summary types (backend dashboard.py schemas) ───────────── */

export interface IncidentSummaryMetrics {
  active: number
  resolved_today: number
}

export interface ServiceHealthMetrics {
  healthy: number
  degraded: number
  critical: number
  total: number
}

export interface DashboardSummary {
  incident_summary: IncidentSummaryMetrics
  service_health: ServiceHealthMetrics
}

/* ── Service types (backend services.py schemas) ─────────────────────── */

export interface ServiceSummary {
  id: string
  owner_team: string
  repo: string
  language: string
  alert_threshold: string
  oncall_slack: string | null
}

/* ── Configured service registry (backend service_registry.py schemas) ── */

export interface RegisteredService {
  id: string
  service_id: string
  repo: string
  architecture_type: string
  owner_team: string
  language: string | null
  alert_threshold: string
  is_active: boolean
  created_at: string
  updated_at: string
}

/* ── Configuration (backend config endpoint) ─────────────────────────── */

export interface SystemConfig {
  environment: string
  llm: {
    provider: string
    model: string
    temperature: number
    configured: boolean
  }
  backends: Record<string, string>
  investigation: {
    confidence_threshold: number
    tool_timeout_seconds: number
  }
}

/* ── Status helpers ──────────────────────────────────────────────────── */

export const ACTIVE_STATUSES: ReadonlySet<IncidentStatus> = new Set([
  'investigating',
  'root_cause_identified',
])

export const STATUS_LABEL: Record<IncidentStatus, string> = {
  investigating: 'Investigating',
  root_cause_identified: 'Root cause found',
  resolved: 'Resolved',
  completed: 'Completed',
  failed: 'Failed',
}

export const STATUS_COLOR: Record<IncidentStatus, string> = {
  investigating: 'var(--color-signal)',
  root_cause_identified: 'var(--color-signal)',
  resolved: 'var(--color-ink-3)',
  completed: 'var(--color-ink-3)',
  failed: 'var(--color-tentative)',
}

export function isActiveStatus(status: string): boolean {
  return ACTIVE_STATUSES.has(status as IncidentStatus)
}

export function confidenceOf(incident: IncidentDetail | IncidentSummary): number | null {
  const report =
    'report' in incident && incident.report ? (incident as IncidentDetail).report : null
  if (!report) return null
  return report.confidence_score
}

export function firstAlertMessage(incident: IncidentDetail | IncidentSummary): string | null {
  if ('alerts' in incident && incident.alerts.length > 0) {
    return (incident as IncidentDetail).alerts[0].alert_message
  }
  return null
}

/* ── API calls ───────────────────────────────────────────────────────── */

export async function fetchIncidents(params?: {
  limit?: number
  cursor?: string
  service_id?: string
  status?: IncidentStatus
}): Promise<IncidentList> {
  const query = new URLSearchParams()
  if (params?.limit != null) query.set('limit', String(params.limit))
  if (params?.cursor) query.set('cursor', params.cursor)
  if (params?.service_id) query.set('service_id', params.service_id)
  if (params?.status) query.set('status', params.status)
  const qs = query.toString()
  return api.get<IncidentList>(`/incidents${qs ? `?${qs}` : ''}`)
}

export async function fetchIncident(id: string): Promise<IncidentDetail> {
  return api.get<IncidentDetail>(`/incidents/${id}`)
}

export async function fetchServices(): Promise<ServiceSummary[]> {
  return api.get<ServiceSummary[]>('/services')
}

export async function fetchRegisteredServices(): Promise<RegisteredService[]> {
  return api.get<RegisteredService[]>('/service-registry')
}

export async function fetchDashboardSummary(): Promise<DashboardSummary> {
  return api.get<DashboardSummary>('/dashboard/summary')
}

export async function fetchConfig(): Promise<SystemConfig> {
  return api.get<SystemConfig>('/config')
}
