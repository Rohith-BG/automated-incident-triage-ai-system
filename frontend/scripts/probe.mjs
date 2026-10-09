/**
 * Targeted probes: bisect the section that widens the page, and dump raw
 * computed colour strings so the contrast audit can be trusted.
 *
 *   node scripts/probe.mjs
 */
import { readFileSync, existsSync, statSync } from 'node:fs'
import { dirname, extname, join, normalize, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createServer } from 'node:http'
import puppeteer from 'puppeteer'

const here = dirname(fileURLToPath(import.meta.url))
const dist = resolve(here, '../dist')
const PORT = 4322
const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.woff2': 'font/woff2',
}
const server = createServer((req, res) => {
  const url = (req.url ?? '/').split('?')[0]
  let f = join(dist, normalize(decodeURIComponent(url)).replace(/^(\.\.[/\\])+/, ''))
  if (!existsSync(f) || statSync(f).isDirectory()) f = join(dist, 'index.html')
  res.writeHead(200, { 'Content-Type': MIME[extname(f)] ?? 'application/octet-stream' })
  res.end(readFileSync(f))
})
await new Promise((d) => server.listen(PORT, '127.0.0.1', d))

const browser = await puppeteer.launch({ headless: true, args: ['--no-sandbox', '--hide-scrollbars'] })
const page = await browser.newPage()
await page.setViewport({ width: 390, height: 844, isMobile: true, hasTouch: true })
await page.goto(`http://127.0.0.1:${PORT}`, { waitUntil: 'networkidle0' })
await page.evaluateHandle('document.fonts.ready')

// ── Bisect: hide each top-level block and watch scrollWidth ──
const bisect = await page.evaluate(() => {
  const de = document.documentElement
  const blocks = [
    ...document.querySelectorAll('header, main > section, footer'),
  ]
  const baseline = de.scrollWidth
  const out = []
  for (const b of blocks) {
    const prev = b.style.display
    b.style.display = 'none'
    const after = de.scrollWidth
    b.style.display = prev
    out.push({
      id: b.id || b.tagName.toLowerCase() + (b.className ? `.${String(b.className).split(' ')[0]}` : ''),
      after,
      culprit: after < baseline,
    })
  }
  return { baseline, clientW: de.clientWidth, out }
})

console.log(`\nbaseline scrollWidth ${bisect.baseline} · clientWidth ${bisect.clientW}`)
for (const b of bisect.out) {
  console.log(`  ${b.culprit ? '✗ CULPRIT' : '  ok     '} hiding ${b.id.padEnd(34)} → ${b.after}`)
}

// ── Inside the culprit, find the widest right edge ──
const widest = await page.evaluate(() => {
  const de = document.documentElement
  const limit = de.clientWidth
  const rows = []
  for (const el of document.querySelectorAll('#trace *')) {
    const r = el.getBoundingClientRect()
    if (r.width === 0) continue
    const right = r.right + window.scrollX
    if (right > limit + 1) {
      const cs = getComputedStyle(el)
      rows.push({
        tag: el.tagName.toLowerCase(),
        cls: (el.getAttribute('class') ?? '').slice(0, 62),
        right: Math.round(right),
        w: Math.round(r.width),
        ovx: cs.overflowX,
        section: el.closest('section,header,footer')?.id || el.closest('footer') ? 'footer' : '?',
      })
    }
  }
  rows.sort((a, b) => b.right - a.right)
  return rows.slice(0, 10)
})
console.log('\nwidest right edges (any element):')
for (const r of widest) {
  console.log(`  right ${String(r.right).padStart(5)} w ${String(r.w).padStart(4)} ovx=${r.ovx.padEnd(7)} [${r.section}] <${r.tag} class="${r.cls}">`)
}

// ── Raw colour strings the contrast audit sees ──
const colours = await page.evaluate(() => {
  const pick = (sel) => {
    const el = document.querySelector(sel)
    if (!el) return null
    const cs = getComputedStyle(el)
    return { sel, color: cs.color, background: cs.backgroundColor }
  }
  return [
    pick('header'),
    pick('header a span:last-child'),
    pick('header nav a'),
    pick('.provenance'),
    pick('.action-primary'),
  ].filter(Boolean)
})
console.log('\nraw computed colours:')
for (const c of colours) console.log(`  ${c.sel.padEnd(26)} color=${c.color}  bg=${c.background}`)

await browser.close()
server.close()
