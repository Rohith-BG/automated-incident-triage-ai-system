import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createServer } from 'node:http'
import { readFileSync, statSync, existsSync } from 'node:fs'
import { extname, normalize } from 'node:path'
import puppeteer from 'puppeteer'

const here = dirname(fileURLToPath(import.meta.url))
const repo = resolve(here, '../..')
const dist = resolve(here, '../dist')
const PORT = 4323
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

const info = await page.evaluate(() => {
  const panel = document.querySelector('section[aria-label^="Investigation"]')
  const rel = panel.querySelector('.relative')
  const all = [...panel.querySelectorAll('*')]
  const trunk = all.find((el) => {
    const s = getComputedStyle(el)
    return s.position === 'absolute' && s.width === '1px' && s.backgroundColor === 'rgb(180, 198, 183)'
  })
  const trunkR = trunk?.getBoundingClientRect()
  // fan hairline = the horizontal w-px... actually h-px bg-grid-major inside parallel
  const hlines = all.filter((el) => {
    const s = getComputedStyle(el)
    return s.position === 'absolute' && s.height === '1px' && s.backgroundColor === 'rgb(180, 198, 183)'
  }).map((el) => {
    const r = el.getBoundingClientRect()
    return { left: r.left, top: r.top, right: r.right, width: r.width }
  })
  // text color check for 'PASSED' verdict heading
  const passedEls = [...panel.querySelectorAll('*')].filter((el) => el.textContent?.trim() === 'PASSED · 0.82')
  const verdictColor = passedEls.length ? getComputedStyle(passedEls[0]).color : null
  return {
    trunk: trunkR ? { left: trunkR.left, right: trunkR.right, top: trunkR.top, bottom: trunkR.bottom } : null,
    hlines,
    verdictColor,
    panelHeight: panel.getBoundingClientRect().height,
  }
})
console.log(JSON.stringify(info, null, 2))
await browser.close()
server.close()
