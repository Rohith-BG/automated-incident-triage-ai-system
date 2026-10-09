import { mkdirSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createServer } from 'node:http'
import { readFileSync, statSync, existsSync } from 'node:fs'
import { extname, normalize } from 'node:path'
import puppeteer from 'puppeteer'

const here = dirname(fileURLToPath(import.meta.url))
const repo = resolve(here, '../..')
const dist = resolve(here, '../dist')
const PORT = 4322
const base = `http://127.0.0.1:${PORT}`
const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.woff2': 'font/woff2',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
}
const server = createServer((req, res) => {
  const url = (req.url ?? '/').split('?')[0]
  let file = join(dist, normalize(decodeURIComponent(url)).replace(/^(\.\.[/\\])+/, ''))
  if (!existsSync(file) || statSync(file).isDirectory()) file = join(dist, 'index.html')
  res.writeHead(200, { 'Content-Type': MIME[extname(file)] ?? 'application/octet-stream' })
  res.end(readFileSync(file))
})
await new Promise((d) => server.listen(PORT, '127.0.0.1', d))

const browser = await puppeteer.launch({ headless: true, args: ['--no-sandbox'] })
const page = await browser.newPage()
await page.setViewport({ width: 1440, height: 900 })
await page.goto(`${base}/workflow?qa`, { waitUntil: 'load', timeout: 60000 })
await page.evaluateHandle('document.fonts.ready')
await page.evaluate(() => {
  for (const el of document.querySelectorAll('.pen-settle')) {
    for (const an of el.getAnimations?.() ?? []) an.finish()
  }
})

// Inspect the FIRST pipeline panel's rail geometry.
const layout = await page.evaluate(() => {
  const panel = document.querySelector('section[aria-label^="Investigation"]')
  if (!panel) return { error: 'no panel' }
  const rel = panel.querySelector('.relative')
  const trunk = rel.querySelector('.absolute.w-px.bg-grid-major')
  const markers = [...panel.querySelectorAll('.pen-settle')].map((m) => {
    const r = m.getBoundingClientRect()
    return {
      cx: +(r.left + r.width / 2).toFixed(1),
      cy: +(r.top + r.height / 2).toFixed(1),
      run: m.className.includes('animate-pulse') ? 'running' : 'other',
    }
  })
  const trunkR = trunk?.getBoundingClientRect()
  return {
    trunkX: trunkR ? +(trunkR.left + trunkR.width / 2).toFixed(1) : null,
    markers,
    delta: markers.map((m) => m.cx).map((cx) => (trunkR ? +(cx - (trunkR.left + trunkR.width / 2)).toFixed(1) : null)),
  }
})
console.log(JSON.stringify(layout, null, 2))

// Check vertical ordering: each marker cy should be increasing (rail top to bottom)
const cys = layout.markers.map((m) => m.cy)
console.log('marker cy sequence:', cys)
console.log('monotonic (rail top->bottom):', cys.every((v, i) => i === 0 || v >= cys[i - 1]))

await browser.close()
server.close()
