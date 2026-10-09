import { readFileSync, existsSync, statSync } from 'node:fs'
import { extname, join, resolve } from 'node:path'
import { createServer } from 'node:http'
import puppeteer from 'puppeteer'

const dist = resolve(process.cwd(), 'dist')
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
await new Promise((d) => server.listen(4323, '127.0.0.1', d))

const b = await puppeteer.launch({ headless: true, args: ['--no-sandbox', '--hide-scrollbars'] })
const p = await b.newPage()
await p.setViewport({ width: 390, height: 844, isMobile: true, hasTouch: true })
await p.goto('http://127.0.0.1:4323', { waitUntil: 'networkidle0' })
await p.evaluateHandle('document.fonts.ready')

const out = await p.evaluate(() => {
  const desc = (el) =>
    el ? `<${el.tagName.toLowerCase()} class="${(el.getAttribute('class') ?? '').slice(0, 78)}">` : 'none'
  const t = document.getElementById('trace')
  let maxR = -1e9,
    minL = 1e9,
    maxEl = null,
    minEl = null
  for (const el of t.querySelectorAll('*')) {
    const q = el.getBoundingClientRect()
    if (q.width === 0 && q.height === 0) continue
    if (q.right > maxR) {
      maxR = q.right
      maxEl = el
    }
    if (q.left < minL) {
      minL = q.left
      minEl = el
    }
  }
  const scrollers = [...t.querySelectorAll('*')]
    .filter((e) => e.scrollWidth > e.clientWidth + 1)
    .slice(0, 8)
    .map((e) => ({ el: desc(e), scrollW: e.scrollWidth, clientW: e.clientWidth }))

  const tr = t.getBoundingClientRect()
  return {
    section: { left: Math.round(tr.left), right: Math.round(tr.right), width: Math.round(tr.width) },
    sectionScrollW: t.scrollWidth,
    sectionClientW: t.clientWidth,
    widestRight: Math.round(maxR),
    widestEl: desc(maxEl),
    leftmost: Math.round(minL),
    leftmostEl: desc(minEl),
    innerScrollers: scrollers,
  }
})

console.log(JSON.stringify(out, null, 2))
await b.close()
server.close()
