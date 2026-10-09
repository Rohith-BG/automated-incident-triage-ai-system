/**
 * Diagnostics for the inspection round: names every element wider than the
 * viewport at each target width, and writes legible section crops so the render
 * can be judged at readable scale instead of as one unreadable full-page thumb.
 *
 *   node scripts/inspect.mjs
 */
import { mkdirSync, readFileSync, existsSync, statSync } from 'node:fs'
import { dirname, extname, join, normalize, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createServer } from 'node:http'
import puppeteer from 'puppeteer'

const here = dirname(fileURLToPath(import.meta.url))
const repo = resolve(here, '../..')
const dist = resolve(here, '../dist')
const outDir = resolve(repo, '.impeccable/review/crops')
mkdirSync(outDir, { recursive: true })

const PORT = 4321
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

const browser = await puppeteer.launch({
  headless: true,
  args: ['--no-sandbox', '--force-color-profile=srgb', '--hide-scrollbars'],
})

const SECTIONS = ['hero', 'channels', 'trace', 'gate', 'graph', 'bench', 'close']

for (const vp of [
  { name: 'desktop', width: 1440, height: 900 },
  { name: 'mobile', width: 390, height: 844, mobile: true },
]) {
  const page = await browser.newPage()
  await page.setViewport({
    width: vp.width,
    height: vp.height,
    deviceScaleFactor: vp.mobile ? 2 : 1,
    isMobile: Boolean(vp.mobile),
    hasTouch: Boolean(vp.mobile),
  })
  await page.goto(base, { waitUntil: 'networkidle0' })
  await page.evaluateHandle('document.fonts.ready')
  await page.evaluate(() => {
    for (const el of document.querySelectorAll('.plot-draw, .pen-settle')) {
      for (const a of el.getAnimations?.() ?? []) a.finish()
      el.classList.remove('plot-draw', 'pen-settle')
      if (el instanceof SVGElement) el.style.strokeDashoffset = '0'
    }
  })
  await new Promise((r) => setTimeout(r, 500))

  // ── Who causes real layout overflow ──
  const offenders = await page.evaluate(() => {
    const de = document.documentElement
    const limit = de.clientWidth
    // An element inside a horizontal scroll container is scrollable overflow,
    // not layout overflow: the page does not widen because of it.
    const inScroller = (el) => {
      let n = el.parentElement
      while (n && n !== de) {
        const ov = getComputedStyle(n).overflowX
        if (ov === 'auto' || ov === 'scroll' || ov === 'hidden') return true
        n = n.parentElement
      }
      return false
    }
    const out = []
    for (const el of document.querySelectorAll('*')) {
      const r = el.getBoundingClientRect()
      if (r.width === 0 || inScroller(el)) continue
      const right = r.right + window.scrollX
      if (right > limit + 1 || r.left + window.scrollX < -1) {
        out.push({
          tag: el.tagName.toLowerCase(),
          cls: (el.getAttribute('class') ?? '').slice(0, 70),
          left: Math.round(r.left + window.scrollX),
          right: Math.round(right),
          w: Math.round(r.width),
        })
      }
    }
    return {
      innerW: window.innerWidth,
      clientW: de.clientWidth,
      scrollW: de.scrollWidth,
      visualW: Math.round(window.visualViewport?.width ?? 0),
      canScrollX: de.scrollWidth > de.clientWidth + 1,
      offenders: out.slice(0, 12),
    }
  })

  console.log(`\n── ${vp.name} @ ${vp.width} ──`)
  console.log(
    `   innerWidth ${offenders.innerW}  clientWidth ${offenders.clientW}  scrollWidth ${offenders.scrollW}  visualViewport ${offenders.visualW}`,
  )
  console.log(
    `   horizontal page scroll: ${offenders.canScrollX ? '✗ YES — the body scrolls sideways' : 'no'}`,
  )
  if (offenders.offenders.length === 0) {
    console.log('   no element causes layout overflow')
  } else {
    for (const o of offenders.offenders) {
      console.log(`   ✗ <${o.tag} class="${o.cls}"> left ${o.left} right ${o.right} w ${o.w}`)
    }
  }

  // ── Contrast audit on real rendered text ──
  const contrast = await page.evaluate(() => {
    const lum = (c) => {
      const [r, g, b] = c.map((v) => {
        const s = v / 255
        return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4
      })
      return 0.2126 * r + 0.7152 * g + 0.0722 * b
    }

    /**
     * Computed colours arrive in three shapes once color-mix is involved:
     * `rgb(0-255 …)`, `color(srgb 0-1 …)`, and `oklab(L a b)`. All three have to
     * land on the same 0-255 sRGB scale or every mixed background reads as
     * near-black and the audit invents failures that are not there.
     */
    const srgbFromLinear = (c) =>
      (c <= 0.0031308 ? 12.92 * c : 1.055 * c ** (1 / 2.4) - 0.055) * 255

    const oklabToRgb = (L, a, bb) => {
      const l_ = L + 0.3963377774 * a + 0.2158037573 * bb
      const m_ = L - 0.1055613458 * a - 0.0638541728 * bb
      const s_ = L - 0.0894841775 * a - 1.291485548 * bb
      const l = l_ ** 3
      const m = m_ ** 3
      const s = s_ ** 3
      return [
        4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
        -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
        -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
      ].map((v) => Math.min(255, Math.max(0, srgbFromLinear(v))))
    }

    const parse = (s) => {
      if (!s || /^(transparent|none)$/i.test(s.trim())) return null
      const str = s.trim()
      const nums = (str.match(/-?\d*\.?\d+(e-?\d+)?/g) ?? []).map(Number)
      if (nums.length < 3) return null
      const alphaMatch = str.match(/\/\s*([\d.]+)\s*\)/) ?? str.match(/,\s*([\d.]+)\s*\)$/)
      const alpha = alphaMatch ? Number(alphaMatch[1]) : 1
      if (/^oklab\(/i.test(str)) return { rgb: oklabToRgb(nums[0], nums[1], nums[2]), alpha }
      if (/^color\(/i.test(str))
        return { rgb: nums.slice(0, 3).map((v) => Math.min(255, Math.max(0, v * 255))), alpha }
      return { rgb: nums.slice(0, 3), alpha }
    }

    /** Composite semi-transparent layers down to a solid colour. */
    const bgOf = (el) => {
      const stack = []
      let n = el
      while (n) {
        const p = parse(getComputedStyle(n).backgroundColor)
        if (p && p.alpha > 0.004) {
          stack.push(p)
          if (p.alpha >= 0.999) break
        }
        n = n.parentElement
      }
      if (!stack.length) return [255, 255, 255]
      let out = stack[stack.length - 1].rgb
      for (let i = stack.length - 2; i >= 0; i--) {
        const { rgb, alpha } = stack[i]
        out = out.map((c, k) => rgb[k] * alpha + c * (1 - alpha))
      }
      return out
    }

    const fails = []
    const seen = new Set()
    for (const el of document.querySelectorAll(
      'p,span,dt,dd,td,th,li,a,h1,h2,h3,h4,figcaption',
    )) {
      const txt = (el.textContent ?? '').trim()
      if (!txt || el.children.length > 0) continue
      const cs = getComputedStyle(el)
      if (cs.visibility === 'hidden' || cs.display === 'none' || Number(cs.opacity) < 0.1) continue
      const f = parse(cs.color)
      if (!f) continue
      const bg = bgOf(el)
      const fg = f.alpha < 1 ? f.rgb.map((c, i) => c * f.alpha + bg[i] * (1 - f.alpha)) : f.rgb
      const l1 = lum(fg)
      const l2 = lum(bg)
      const ratio = (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05)
      const px = parseFloat(cs.fontSize)
      const weight = Number(cs.fontWeight) || 400
      const large = px >= 24 || (px >= 18.66 && weight >= 700)
      const need = large ? 3 : 4.5
      const key = `${cs.color}|${bg.map(Math.round).join(',')}|${Math.round(px)}`
      if (seen.has(key)) continue
      seen.add(key)
      if (ratio < need) {
        fails.push({
          ratio: Math.round(ratio * 100) / 100,
          need,
          px: Math.round(px * 10) / 10,
          color: cs.color,
          on: `rgb(${bg.map(Math.round).join(',')})`,
          text: txt.slice(0, 46),
        })
      }
    }
    return fails.sort((a, b) => a.ratio - b.ratio).slice(0, 16)
  })

  if (contrast.length) {
    console.log(`   contrast below threshold (${contrast.length} distinct):`)
    for (const c of contrast) {
      console.log(`   ✗ ${c.ratio}:1 (need ${c.need}) ${c.px}px ${c.color} on ${c.on} — "${c.text}"`)
    }
  } else {
    console.log('   all rendered text meets its contrast threshold')
  }

  // ── Section crops at legible scale ──
  for (const id of SECTIONS) {
    const sel = id === 'hero' ? 'main > section:first-child' : id === 'close' ? 'footer' : `#${id}`
    const el = await page.$(sel)
    if (!el) continue
    const box = await el.boundingBox()
    if (!box) continue
    // Cap very tall sections so the crop stays readable.
    const h = Math.min(box.height, vp.mobile ? 3000 : 2200)
    await page.screenshot({
      path: resolve(outDir, `${vp.name}-${id}.png`),
      clip: { x: 0, y: box.y, width: vp.width, height: h },
      captureBeyondViewport: true,
    })
  }
  await page.close()
}

await browser.close()
server.close()
console.log(`\n  crops → ${outDir}\n`)
