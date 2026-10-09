import BoardMasthead from '../components/BoardMasthead'

interface SurfacePlaceholderProps {
  eyebrow: string
  title: string
  description: string
}

export default function SurfacePlaceholder({
  eyebrow,
  title,
  description,
}: SurfacePlaceholderProps) {
  return (
    <div className="chart-grid min-h-dvh">
      <BoardMasthead />

      <main className="mx-auto flex w-full max-w-[1400px] flex-col px-5 py-16 sm:px-8 lg:px-12">
        <div className="max-w-2xl border border-grid-major bg-stock-2 p-8">
          <h1 className="legend text-ink">{eyebrow}</h1>
          <h2 className="verdict-type mt-3 text-[clamp(2rem,4.5vw,3rem)] text-ink">{title}</h2>
          <p className="prose-measure mt-4 text-[1.0625rem] leading-[1.6] text-ink-2">
            {description}
          </p>
        </div>
      </main>
    </div>
  )
}
