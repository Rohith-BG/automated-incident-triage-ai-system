/**
 * Icons drawn in the instrument's own grammar: one stroke weight, butt caps,
 * square joins, no rounded corners. These are plotter marks, not a UI icon set.
 */

const base = {
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.5,
  strokeLinecap: 'butt' as const,
  strokeLinejoin: 'miter' as const,
}

export function LeaderArrow({ className = '' }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" width="16" height="16" className={className} aria-hidden="true" {...base}>
      <line x1="1" y1="8" x2="13" y2="8" />
      <path d="M9 4 L13 8 L9 12" />
    </svg>
  )
}

export function Offsheet({ className = '' }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" width="16" height="16" className={className} aria-hidden="true" {...base}>
      <path d="M6 2 H2 V14 H14 V10" />
      <line x1="7" y1="9" x2="14" y2="2" />
      <path d="M9.5 2 H14 V6.5" />
    </svg>
  )
}

/** A single resolved peak: the mark for anything the instrument identified. */
export function PeakMark({ className = '' }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" width="16" height="16" className={className} aria-hidden="true" {...base}>
      <path d="M1 13 H4.5 C6 13 6 3 8 3 C10 3 10 13 11.5 13 H15" />
    </svg>
  )
}

/** The threshold mark: a dashed rule with a value sitting under it. */
export function GateMark({ className = '' }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" width="16" height="16" className={className} aria-hidden="true" {...base}>
      <line x1="1" y1="6" x2="15" y2="6" strokeDasharray="3 2.5" />
      <line x1="4" y1="10" x2="12" y2="10" />
      <line x1="8" y1="10" x2="8" y2="14" />
    </svg>
  )
}

/** Retry exhausted: a struck position. */
export function StruckMark({ className = '' }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" width="16" height="16" className={className} aria-hidden="true" {...base}>
      <line x1="2" y1="8" x2="14" y2="8" />
      <line x1="4" y1="4" x2="12" y2="12" />
      <line x1="12" y1="4" x2="4" y2="12" />
    </svg>
  )
}

/** Two hatches crossing: the sources disagree. */
export function ConflictMark({ className = '' }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" width="16" height="16" className={className} aria-hidden="true" {...base}>
      <rect x="2" y="2" width="12" height="12" />
      <line x1="2" y1="8" x2="8" y2="2" />
      <line x1="8" y1="14" x2="14" y2="8" />
      <line x1="2" y1="8" x2="8" y2="14" />
      <line x1="8" y1="2" x2="14" y2="8" />
    </svg>
  )
}

/** Incidents: an alert trace with a flagged peak. */
export function IncidentMark({ className = '' }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" width="16" height="16" className={className} aria-hidden="true" {...base}>
      <path d="M1 12 C3 12 4 4 6 4 C8 4 8 12 11 12" />
      <line x1="12.5" y1="4" x2="12.5" y2="12" />
      <line x1="11" y1="6" x2="14" y2="6" />
    </svg>
  )
}

/** Services: a dependency node with a link to another node. */
export function ServiceMark({ className = '' }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" width="16" height="16" className={className} aria-hidden="true" {...base}>
      <rect x="1" y="1" width="6" height="6" />
      <circle cx="12" cy="11" r="3" />
      <line x1="6" y1="4" x2="10" y2="9" />
    </svg>
  )
}

/** Knowledge graph: a graph of nodes and edges. */
export function GraphMark({ className = '' }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" width="16" height="16" className={className} aria-hidden="true" {...base}>
      <circle cx="3" cy="4" r="2" />
      <circle cx="13" cy="4" r="2" />
      <circle cx="8" cy="13" r="2" />
      <line x1="3" y1="4" x2="13" y2="4" />
      <line x1="13" y1="4" x2="8" y2="13" />
      <line x1="8" y1="13" x2="3" y2="4" />
    </svg>
  )
}

/** Agent workflow: pipeline steps joined in sequence. */
export function FlowMark({ className = '' }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" width="16" height="16" className={className} aria-hidden="true" {...base}>
      <rect x="1" y="3" width="4" height="4" />
      <line x1="4" y1="8" x2="12" y2="8" />
      <rect x="11" y="9" width="4" height="4" />
    </svg>
  )
}

/** Session end: an exit hatch through the instrument wall. */
export function SignOutMark({ className = '' }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" width="16" height="16" className={className} aria-hidden="true" {...base}>
      <path d="M6 2 H2 V14 H6" />
      <path d="M10 4 L14 8 L10 12" />
      <line x1="14" y1="8" x2="6" y2="8" />
    </svg>
  )
}

/** User management: two stacked figures. */
export function UsersMark({ className = '' }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" width="16" height="16" className={className} aria-hidden="true" {...base}>
      <circle cx="6" cy="4" r="2" />
      <path d="M2 13 C2 10 4 9 6 9 C8 9 10 10 10 13" />
      <circle cx="11" cy="5" r="1.5" />
      <path d="M9 13 C9 11 10 10 11 10 C12 10 14 11 14 13" />
    </svg>
  )
}

/** The wordmark: SIFT as a plotted trace resolving into a single peak. */
export function Wordmark({ className = '' }: { className?: string }) {
  return (
    <span
      className={`inline-flex items-baseline gap-2 ${className}`}
      style={{ color: '#0a0a0a' }}
    >
      <svg
        viewBox="0 0 34 16"
        width="34"
        height="16"
        aria-hidden="true"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="butt"
      >
        <path d="M1 14 H5 C6.4 14 6.6 9.5 8 9.5 C9.4 9.5 9.6 14 11 14 H13 C14.6 14 14.4 6 16 6 C17.6 6 17.4 14 19 14 H21 C23 14 22.4 1.5 25 1.5 C27.6 1.5 27 14 29 14 H33" />
      </svg>
      <span
        style={{
          fontFamily: 'var(--font-display)',
          fontStretch: '112%',
          fontWeight: 900,
          letterSpacing: '0.02em',
          fontSize: '1.05rem',
        }}
      >
        Sift
      </span>
    </span>
  )
}
