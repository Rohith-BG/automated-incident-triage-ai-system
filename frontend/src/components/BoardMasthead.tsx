import { Link } from 'react-router-dom'
import { Wordmark } from './Icons'
import ProfileMenu from './ProfileMenu'

export default function BoardMasthead({ surface = 'stock' }: { surface?: 'stock' | 'white' }) {
  return (
    <header
      className={`sticky top-0 z-20 border-b border-ink ${
        surface === 'white' ? 'bg-white' : 'bg-stock'
      }`}
    >
      <div className="mx-auto flex w-full max-w-[1400px] items-center gap-6 px-5 py-3 sm:px-8 lg:px-12">
        <Link to="/" className="text-ink no-underline" aria-label="Sift — home">
          <Wordmark />
        </Link>

        <div className="ml-auto">
          <ProfileMenu surface={surface} />
        </div>
      </div>
    </header>
  )
}
