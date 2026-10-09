/**
 * Batched capture for the finish review. Serves the production build, settles
 * entrance motion, then writes one full-page file per viewport into
 * ../.impeccable/review/ and validates each file before exiting.
 *
 *   npm run build && node scripts/shots.mjs
 */
import { mkdirSync, statSync, readFileSync, existsSync } from 'node:fs'
import { dirname, extname, join, normalize, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createServer } from 'node:http'
import puppeteer from 'puppeteer'

const here = dirname(fileURLToPath(import.meta.url))
const repo = resolve(here, '../..')
const dist = resolve(here, '../dist')
const outDir = resolve(repo, '.impeccable/review')
mkdirSync(outDir, { recursive: true })

if (!existsSync(join(dist, 'index.html'))) {
  console.error('\n  No dist/index.html — run `npm run build` first.\n')
  process.exit(1)
}

const VIEWPORTS = [
  { name: 'desktop', width: 1440, height: 900 },
  { name: 'mobile', width: 390, height: 844, mobile: true },
]

const PORT = 4319
const base = `http://127.0.0.1:${PORT}`

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.woff2': 'font/woff2',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.json': 'application/json',
}

/* Static server in-process: no child shell, nothing left holding the port. */
const server = createServer((req, res) => {
  const url = (req.url ?? '/').split('?')[0]
  let file = join(dist, normalize(decodeURIComponent(url)).replace(/^(\.\.[/\\])+/, ''))
  if (!existsSync(file) || statSync(file).isDirectory()) file = join(dist, 'index.html')
  res.writeHead(200, { 'Content-Type': MIME[extname(file)] ?? 'application/octet-stream' })
  res.end(readFileSync(file))
})

await new Promise((done) => server.listen(PORT, '127.0.0.1', done))

const browser = await puppeteer.launch({
  headless: true,
  args: ['--no-sandbox', '--force-color-profile=srgb', '--hide-scrollbars'],
})

const written = []

for (const vp of VIEWPORTS) {
  const page = await browser.newPage()
  await page.setViewport({
    width: vp.width,
    height: vp.height,
    deviceScaleFactor: 1,
    isMobile: Boolean(vp.mobile),
    hasTouch: Boolean(vp.mobile),
  })

  await page.goto(base, { waitUntil: 'networkidle0' })
  await page.evaluateHandle('document.fonts.ready')

  // Settle the one authored entrance so a mid-draw trace is never mistaken for
  // a missing trace.
  await page.evaluate(() => {
    for (const el of document.querySelectorAll('.plot-draw, .pen-settle')) {
      for (const anim of el.getAnimations?.() ?? []) anim.finish()
      el.classList.remove('plot-draw', 'pen-settle')
      if (el instanceof SVGElement) el.style.strokeDashoffset = '0'
    }
    window.scrollTo(0, 0)
  })
  await new Promise((r) => setTimeout(r, 700))

  const path = resolve(outDir, `${vp.name}.png`)
  await page.screenshot({ path, fullPage: true, captureBeyondViewport: true })

  const bytes = statSync(path).size
  const dims = await page.evaluate(() => ({
    w: document.documentElement.scrollWidth,
    h: document.documentElement.scrollHeight,
    innerW: window.innerWidth,
  }))

  // Horizontal overflow at any target width is a defect, so report it here
  // rather than discovering it in the review.
  const overflow = dims.w > dims.innerW + 1

  written.push({ ...vp, path, bytes, ...dims, overflow })
  await page.close()
}

await browser.close()
server.close()

console.log('')
for (const w of written) {
  const kb = (w.bytes / 1024).toFixed(0)
  console.log(
    `  ${w.name.padEnd(8)} ${String(w.width).padStart(5)}px  page ${w.w}x${w.h}  ${kb} KB` +
      (w.overflow ? `  ⚠ HORIZONTAL OVERFLOW (${w.w} > ${w.innerW})` : ''),
  )
  if (w.bytes < 20_000) console.log(`  ⚠ ${w.name}: suspiciously small, inspect before sending`)
}
console.log(`\n  → ${outDir}\n`)
