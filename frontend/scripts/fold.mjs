/**
 * Captures exactly what lands in the first viewport, no full-page scroll. The
 * hero carries the run's ambition, so this is the frame that has to work.
 *
 *   node scripts/fold.mjs
 */
import { readFileSync, existsSync, statSync, mkdirSync } from 'node:fs'
import { dirname, extname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createServer } from 'node:http'
import puppeteer from 'puppeteer'

const here = dirname(fileURLToPath(import.meta.url))
const dist = resolve(here, '../dist')
const outDir = resolve(here, '../../.impeccable/review')
mkdirSync(outDir, { recursive: true })

const MIME = {
  '.html': 'text/html;charset=utf-8',
  '.js': 'text/javascript',
  '.css': 'text/css',
  '.woff2': 'font/woff2',
}
const server = createServer((q, s) => {
  const u = (q.url ?? '/').split('?')[0]
  let f = join(dist, u === '/' ? 'index.html' : u.slice(1))
  if (!existsSync(f) || statSync(f).isDirectory()) f = join(dist, 'index.html')
  s.writeHead(200, { 'Content-Type': MIME[extname(f)] ?? 'application/octet-stream' })
  s.end(readFileSync(f))
})
await new Promise((d) => server.listen(4324, '127.0.0.1', d))

const browser = await puppeteer.launch({
  headless: true,
  args: ['--no-sandbox', '--hide-scrollbars', '--force-color-profile=srgb'],
})

for (const vp of [
  { name: 'fold-desktop', width: 1440, height: 900 },
  { name: 'fold-laptop', width: 1280, height: 720 },
  { name: 'fold-mobile', width: 390, height: 844, mobile: true },
]) {
  const page = await browser.newPage()
  await page.setViewport({
    width: vp.width,
    height: vp.height,
    isMobile: Boolean(vp.mobile),
    hasTouch: Boolean(vp.mobile),
  })
  await page.goto('http://127.0.0.1:4324', { waitUntil: 'networkidle0' })
  await page.evaluateHandle('document.fonts.ready')
  await page.evaluate(() => {
    for (const el of document.querySelectorAll('.plot-draw, .pen-settle')) {
      for (const a of el.getAnimations?.() ?? []) a.finish()
      el.classList.remove('plot-draw', 'pen-settle')
      if (el instanceof SVGElement) el.style.strokeDashoffset = '0'
    }
    window.scrollTo(0, 0)
  })
  await new Promise((r) => setTimeout(r, 500))

  // How much of the instrument is actually above the fold?
  const reach = await page.evaluate((h) => {
    const svg = document.querySelector('figure svg')
    if (!svg) return null
    const r = svg.getBoundingClientRect()
    return {
      svgTop: Math.round(r.top),
      svgBottom: Math.round(r.bottom),
      visible: Math.round(Math.max(0, Math.min(h, r.bottom) - Math.max(0, r.top))),
      total: Math.round(r.height),
    }
  }, vp.height)

  await page.screenshot({ path: resolve(outDir, `${vp.name}.png`) })
  console.log(
    `  ${vp.name.padEnd(14)} ${vp.width}x${vp.height}  plot top ${reach?.svgTop} bottom ${reach?.svgBottom}  visible ${reach?.visible}/${reach?.total}px (${reach ? Math.round((reach.visible / reach.total) * 100) : 0}%)`,
  )
  await page.close()
}

await browser.close()
server.close()
