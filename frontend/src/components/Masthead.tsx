import { Wordmark } from './Icons'

const SECTIONS = [
  { id: 'channels', label: 'Evidence' },
  { id: 'gate', label: 'Gate' },
  { id: 'trace', label: 'Trace' },
  { id: 'report', label: 'Report' },
  { id: 'graph', label: 'Graph' },
]

export default function Masthead() {
  return (
    <header className="sticky top-0 z-20 border-b border-ink bg-stock/95 backdrop-blur-[2px]">
      <div className="mx-auto flex w-full max-w-[1400px] items-center gap-6 px-5 py-3 sm:px-8 lg:px-12">
        <a href="#top" className="text-ink no-underline" aria-label="Sift — top of page">
          <Wordmark />
        </a>

        <nav className="ml-auto hidden items-center gap-6 md:flex" aria-label="Sections">
          {SECTIONS.map((s) => (
            <a
              key={s.id}
              href={`#${s.id}`}
              className="legend text-ink-2 no-underline transition-colors hover:text-signal"
            >
              {s.label}
            </a>
          ))}
        </nav>

        <a
          href="#source"
          className="legend inline-flex items-center gap-2 px-3 py-2 text-ink no-underline transition-colors hover:text-signal"
        >
          Source
        </a>

        <a
          href="/login"
          className="legend inline-flex items-center gap-2 bg-ink px-3 py-2 text-stock no-underline transition-colors hover:bg-ink-2"
        >
          Login
        </a>
      </div>
    </header>
  )
}