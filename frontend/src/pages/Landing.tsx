import Masthead from '../components/Masthead'
import HeroRun from '../components/HeroRun'
import Channels from '../components/Channels'
import Gate from '../components/Gate'
import Topology from '../components/Topology'
import Close from '../components/Close'

/**
 * The production landing page. Everything on it is either fetched from the
 * backend (signal board, providers, threshold, graph) or transcribed from the
 * repository's own architecture (pipeline, trace register, report schema).
 * No eval-run or mock figures are displayed.
 */
export default function Landing() {
  return (
    <div id="top">
      <Masthead />
      <main>
        <HeroRun />
        <Channels />
        <Gate />
        <Topology />
      </main>
      <Close />
    </div>
  )
}
