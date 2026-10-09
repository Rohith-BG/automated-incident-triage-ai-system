/**
 * KgBloom — Neo4j Bloom-inspired knowledge graph visualization.
 *
 * Canvas-based force-directed graph with:
 *  - Dark background matching the Bloom aesthetic
 *  - Colorful circular nodes sized by connection count
 *  - Smooth curved edges with directional arrows
 *  - Labels that appear/scale on zoom
 *  - Pan (drag) + zoom (scroll) with smooth inertia
 *  - Node hover glow + click detail panel
 *  - Blast-radius highlighting on hover
 */

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  type SimulationLinkDatum,
  type SimulationNodeDatum,
} from 'd3-force'
import {
  nodeLanguage,
  nodeOwner,
  type KgSnapshot,
} from '../data/kg'

/* ── Colour palette ─────────────────────────────────────────────────── */

const BG = '#0f1117'
const BG_GRID = '#191c24'
const EDGE_DEFAULT = 'rgba(100,120,160,0.22)'
const EDGE_LIT = 'rgba(120,180,255,0.55)'
const LABEL_COLOR = '#c8d0e0'
const LABEL_SUB_COLOR = '#6b7894'
const PANEL_BG = '#1a1d27'
const PANEL_BORDER = '#2a2f3d'
const SEARCH_BG = '#1a1d27'
const SEARCH_BORDER = '#2a2f3d'
const SEARCH_TEXT = '#c8d0e0'
const BADGE_BG = 'rgba(40,46,60,0.9)'

/**
 * Palette for node kinds — each kind gets a hue from this ring
 * so visually distinct clusters emerge like in Bloom.
 */
const KIND_COLORS: Record<string, string> = {
  service: '#5b8af5',
  module: '#8b6ff0',
  package: '#6fcf97',
  class: '#f0b86f',
  function: '#f06f9b',
  method: '#6fcfd4',
  endpoint: '#d4a76f',
  database: '#f06f6f',
  queue: '#c56ff0',
  cache: '#6ff0b8',
  default: '#5b8af5',
}

function kindColor(kind: string): string {
  const k = kind?.toLowerCase() ?? ''
  return KIND_COLORS[k] ?? KIND_COLORS['default']
}

function kindColorGlow(kind: string): string {
  const base = kindColor(kind)
  return base + '66'
}

/* ── Force graph node/link types ────────────────────────────────────── */

interface GNode extends SimulationNodeDatum {
  id: string
  kind: string
  label: string
  fullId: string
  owner: string | null
  language: string | null
  properties: Record<string, unknown>
  radius: number
  connections: number
}

interface GLink extends SimulationLinkDatum<GNode> {
  sourceId: string
  targetId: string
  type: string
}

/* ── View transform ─────────────────────────────────────────────────── */

interface ViewTransform {
  x: number
  y: number
  k: number
}

/* ── Main component ─────────────────────────────────────────────────── */

export interface BloomNodeClickEvent {
  id: string
  label: string
  kind: string
  owner: string | null
  properties: Record<string, unknown>
}

interface Props {
  snapshot: KgSnapshot
  onNodeClick?: (node: BloomNodeClickEvent) => void
  selectedNodeId?: string | null
  height?: number | string
  onAttachFeedback?: (nodeId: string) => void
  attachButtonLabel?: string
}

export default function KgBloom({
  snapshot,
  onNodeClick,
  selectedNodeId,
  height,
  onAttachFeedback,
  attachButtonLabel,
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const wrapRef = useRef<HTMLDivElement | null>(null)
  const animRef = useRef<number>(0)

  const [view, setView] = useState<ViewTransform>({ x: 0, y: 0, k: 1 })
  const viewRef = useRef(view)
  viewRef.current = view

  const [hovered, setHovered] = useState<string | null>(null)
  const hoveredRef = useRef(hovered)
  hoveredRef.current = hovered

  const [selected, setSelected] = useState<GNode | null>(null)
  const [search, setSearch] = useState('')
  const [dims, setDims] = useState({ w: 1200, h: 720 })

  /* Drag state */
  const dragRef = useRef<{
    active: boolean
    startX: number
    startY: number
    startViewX: number
    startViewY: number
    moved: boolean
  } | null>(null)

  /* ── Build simulation data ──────────────────────────────────────── */

  const { nodes, links, nodeMap, adjacency } = useMemo(() => {
    const connectionCount = new Map<string, number>()
    for (const edge of snapshot.edges) {
      connectionCount.set(edge.from, (connectionCount.get(edge.from) ?? 0) + 1)
      connectionCount.set(edge.to, (connectionCount.get(edge.to) ?? 0) + 1)
    }

    const nm = new Map<string, GNode>()
    const gNodes: GNode[] = snapshot.nodes.map((n) => {
      const conns = connectionCount.get(n.id) ?? 0
      const r = Math.max(8, Math.min(28, 10 + Math.sqrt(conns) * 4))
      const node: GNode = {
        id: n.id,
        kind: n.kind ?? 'service',
        label: n.id.split('.').pop() ?? n.id,
        fullId: n.id,
        owner: nodeOwner(n),
        language: nodeLanguage(n),
        properties: n.properties,
        radius: r,
        connections: conns,
      }
      nm.set(n.id, node)
      return node
    })

    const idSet = new Set(gNodes.map((n) => n.id))
    const gLinks: GLink[] = snapshot.edges
      .filter(
        (e) =>
          e.from !== e.to && idSet.has(e.from) && idSet.has(e.to),
      )
      .map((e) => ({
        source: e.from,
        target: e.to,
        sourceId: e.from,
        targetId: e.to,
        type: e.type,
      }))

    /* Adjacency for blast-radius walk */
    const adj = new Map<string, Set<string>>()
    for (const e of snapshot.edges) {
      if (!idSet.has(e.from) || !idSet.has(e.to)) continue
      if (!adj.has(e.from)) adj.set(e.from, new Set())
      adj.get(e.from)!.add(e.to)
    }

    return { nodes: gNodes, links: gLinks, nodeMap: nm, adjacency: adj }
  }, [snapshot])

  /* ── Run d3-force simulation ────────────────────────────────────── */

  const simRef = useRef<ReturnType<typeof forceSimulation<GNode>> | null>(null)
  const positionsRef = useRef<GNode[]>(nodes)

  useEffect(() => {
    if (selectedNodeId) {
      const found = nodeMap.get(selectedNodeId)
      if (found) setSelected(found)
    } else if (selectedNodeId === null) {
      setSelected(null)
    }
  }, [selectedNodeId, nodeMap])

  useEffect(() => {
    const sim = forceSimulation<GNode>(nodes)
      .force(
        'link',
        forceLink<GNode, GLink>(links)
          .id((d) => d.id)
          .distance(180)
          .strength(0.35),
      )
      .force('charge', forceManyBody<GNode>().strength(-550).distanceMax(900))
      .force('center', forceCenter(0, 0).strength(0.02))
      .force(
        'collide',
        forceCollide<GNode>((d) => d.radius + 16).strength(0.8),
      )
      .alphaDecay(0.018)
      .velocityDecay(0.32)

    sim.on('tick', () => {
      positionsRef.current = nodes
    })

    simRef.current = sim

    return () => {
      sim.stop()
    }
  }, [nodes, links])

  /* ── Blast radius computation ───────────────────────────────────── */

  const blastRadius = useMemo(() => {
    if (!hovered) return new Set<string>()
    const seen = new Set<string>()
    const walk = (id: string) => {
      for (const dep of adjacency.get(id) ?? []) {
        if (seen.has(dep)) continue
        seen.add(dep)
        walk(dep)
      }
    }
    walk(hovered)
    return seen
  }, [hovered, adjacency])

  /* ── Search filter ──────────────────────────────────────────────── */

  const searchMatches = useMemo(() => {
    if (!search.trim()) return null
    const q = search.toLowerCase()
    return new Set(
      nodes
        .filter(
          (n) =>
            n.id.toLowerCase().includes(q) ||
            n.label.toLowerCase().includes(q) ||
            (n.owner ?? '').toLowerCase().includes(q) ||
            (n.kind ?? '').toLowerCase().includes(q),
        )
        .map((n) => n.id),
    )
  }, [search, nodes])

  /* ── Canvas resize ──────────────────────────────────────────────── */

  useEffect(() => {
    const el = wrapRef.current
    if (!el) return
    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect
        if (width > 0 && height > 0) {
          setDims({ w: Math.round(width), h: Math.round(height) })
        }
      }
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  /* ── Auto-fit on first data ─────────────────────────────────────── */

  const didFit = useRef(false)
  useEffect(() => {
    if (didFit.current || nodes.length === 0) return
    const timer = setTimeout(() => {
      fitAll()
      didFit.current = true
    }, 600)
    return () => clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes.length, dims.w, dims.h])

  /* ── Fit all nodes into view ────────────────────────────────────── */

  const fitAll = useCallback(() => {
    const ns = positionsRef.current
    if (ns.length === 0) return
    let minX = Infinity,
      maxX = -Infinity,
      minY = Infinity,
      maxY = -Infinity
    for (const n of ns) {
      if (n.x == null || n.y == null) continue
      minX = Math.min(minX, n.x - n.radius)
      maxX = Math.max(maxX, n.x + n.radius)
      minY = Math.min(minY, n.y - n.radius)
      maxY = Math.max(maxY, n.y + n.radius)
    }
    const pad = 60
    const gw = maxX - minX + pad * 2
    const gh = maxY - minY + pad * 2
    const k = Math.min(dims.w / gw, dims.h / gh, 2.5) * 0.9
    const cx = (minX + maxX) / 2
    const cy = (minY + maxY) / 2
    setView({ x: dims.w / 2 - cx * k, y: dims.h / 2 - cy * k, k })
  }, [dims])

  /* ── Hit test ───────────────────────────────────────────────────── */

  const hitTest = useCallback(
    (px: number, py: number): GNode | null => {
      const v = viewRef.current
      const wx = (px - v.x) / v.k
      const wy = (py - v.y) / v.k
      let closest: GNode | null = null
      let closestDist = Infinity
      for (const n of positionsRef.current) {
        if (n.x == null || n.y == null) continue
        const dx = n.x - wx
        const dy = n.y - wy
        const dist = Math.sqrt(dx * dx + dy * dy)
        if (dist <= n.radius + 4 && dist < closestDist) {
          closest = n
          closestDist = dist
        }
      }
      return closest
    },
    [],
  )

  /* ── Canvas rendering loop ──────────────────────────────────────── */

  const render = useCallback(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const dpr = window.devicePixelRatio || 1
    const w = dims.w
    const h = dims.h
    canvas.width = w * dpr
    canvas.height = h * dpr
    canvas.style.width = `${w}px`
    canvas.style.height = `${h}px`
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)

    const v = viewRef.current
    const hov = hoveredRef.current
    const br = blastRadius
    const sm = searchMatches

    /* Background */
    ctx.fillStyle = BG
    ctx.fillRect(0, 0, w, h)

    /* Subtle grid dots (Bloom-like) */
    ctx.fillStyle = BG_GRID
    const gridStep = 40
    const startGx =
      Math.floor(-v.x / v.k / gridStep) * gridStep
    const startGy =
      Math.floor(-v.y / v.k / gridStep) * gridStep
    const endGx =
      Math.ceil((w - v.x) / v.k / gridStep) * gridStep
    const endGy =
      Math.ceil((h - v.y) / v.k / gridStep) * gridStep
    if (v.k > 0.4) {
      for (let gx = startGx; gx <= endGx; gx += gridStep) {
        for (let gy = startGy; gy <= endGy; gy += gridStep) {
          const sx = gx * v.k + v.x
          const sy = gy * v.k + v.y
          ctx.fillRect(sx - 0.5, sy - 0.5, 1, 1)
        }
      }
    }

    ctx.save()
    ctx.translate(v.x, v.y)
    ctx.scale(v.k, v.k)

    const nodesArr = positionsRef.current

    /* ── Edges ─────────────────────────────────────────────────── */
    for (const link of links) {
      const src =
        typeof link.source === 'object' ? link.source : null
      const tgt =
        typeof link.target === 'object' ? link.target : null
      if (!src?.x || !src?.y || !tgt?.x || !tgt?.y) continue

      const isLit =
        hov != null &&
        (src.id === hov || tgt.id === hov ||
          (br.has(src.id) && br.has(tgt.id)))
      const isDimmed = sm != null && (!sm.has(src.id) || !sm.has(tgt.id))

      ctx.strokeStyle = isDimmed
        ? 'rgba(60,70,90,0.08)'
        : isLit
          ? EDGE_LIT
          : EDGE_DEFAULT
      ctx.lineWidth = isLit ? 1.8 / v.k : 0.8 / v.k

      /* Curved edge (Bloom style) */
      const dx = tgt.x - src.x
      const dy = tgt.y - src.y
      const dist = Math.sqrt(dx * dx + dy * dy) || 1
      const nx = -dy / dist
      const ny = dx / dist
      const curve = dist * 0.08
      const mx = (src.x + tgt.x) / 2 + nx * curve
      const my = (src.y + tgt.y) / 2 + ny * curve

      ctx.beginPath()
      ctx.moveTo(src.x, src.y)
      ctx.quadraticCurveTo(mx, my, tgt.x, tgt.y)
      ctx.stroke()

      /* Arrow head */
      if (v.k > 0.3) {
        const arrowLen = 6 / v.k
        const ax = src.x + (tgt.x - src.x) * (1 - tgt.radius / dist)
        const ay = src.y + (tgt.y - src.y) * (1 - tgt.radius / dist)
        /* Use the tangent at endpoint of the quadratic curve */
        const tdx = tgt.x - mx
        const tdy = tgt.y - my
        const tlen = Math.sqrt(tdx * tdx + tdy * tdy) || 1
        const ux = tdx / tlen
        const uy = tdy / tlen

        ctx.fillStyle = ctx.strokeStyle
        ctx.beginPath()
        ctx.moveTo(ax, ay)
        ctx.lineTo(
          ax - ux * arrowLen + uy * arrowLen * 0.4,
          ay - uy * arrowLen - ux * arrowLen * 0.4,
        )
        ctx.lineTo(
          ax - ux * arrowLen - uy * arrowLen * 0.4,
          ay - uy * arrowLen + ux * arrowLen * 0.4,
        )
        ctx.closePath()
        ctx.fill()
      }
    }

    /* ── Nodes ─────────────────────────────────────────────────── */
    for (const node of nodesArr) {
      if (node.x == null || node.y == null) continue

      const isHov = node.id === hov
      const inRadius =
        hov != null && (node.id === hov || br.has(node.id))
      const isDimmedBySearch = sm != null && !sm.has(node.id)
      const isDimmedByHover =
        hov != null && !isHov && !inRadius
      const dimmed = isDimmedBySearch || isDimmedByHover

      const baseColor = kindColor(node.kind)
      const alpha = dimmed ? 0.15 : 1

      /* Glow for hovered/blast-radius nodes */
      if (isHov && !dimmed) {
        const glow = ctx.createRadialGradient(
          node.x,
          node.y,
          node.radius,
          node.x,
          node.y,
          node.radius * 2.8,
        )
        glow.addColorStop(0, kindColorGlow(node.kind))
        glow.addColorStop(1, 'transparent')
        ctx.fillStyle = glow
        ctx.beginPath()
        ctx.arc(node.x, node.y, node.radius * 2.8, 0, Math.PI * 2)
        ctx.fill()
      } else if (inRadius && !dimmed) {
        const glow = ctx.createRadialGradient(
          node.x,
          node.y,
          node.radius,
          node.x,
          node.y,
          node.radius * 1.8,
        )
        glow.addColorStop(0, kindColorGlow(node.kind))
        glow.addColorStop(1, 'transparent')
        ctx.fillStyle = glow
        ctx.beginPath()
        ctx.arc(node.x, node.y, node.radius * 1.8, 0, Math.PI * 2)
        ctx.fill()
      }

      /* Node circle */
      ctx.globalAlpha = alpha
      ctx.beginPath()
      ctx.arc(node.x, node.y, node.radius, 0, Math.PI * 2)

      /* Gradient fill for the node (Bloom uses subtle gradients) */
      const grad = ctx.createRadialGradient(
        node.x - node.radius * 0.3,
        node.y - node.radius * 0.3,
        0,
        node.x,
        node.y,
        node.radius,
      )
      grad.addColorStop(0, lighten(baseColor, 0.25))
      grad.addColorStop(1, baseColor)
      ctx.fillStyle = grad
      ctx.fill()

      /* Thin border */
      const isSelected = (selected && selected.id === node.id) || (selectedNodeId && selectedNodeId === node.id)
      if (isHov || isSelected) {
        ctx.strokeStyle = '#ffffff'
        ctx.lineWidth = 2.5 / v.k
      } else {
        ctx.strokeStyle = darken(baseColor, 0.3)
        ctx.lineWidth = 1 / v.k
      }
      ctx.stroke()
      ctx.globalAlpha = 1

      /* Label — show when zoomed enough or when node hovered */
      const showLabel = v.k > 0.55 || isHov
      if (showLabel && !isDimmedBySearch) {
        const fontSize = Math.max(
          10,
          Math.min(14, node.radius * 0.85),
        )
        ctx.font = `600 ${fontSize / v.k * 0.7}px 'Archivo Variable', sans-serif`
        ctx.textAlign = 'center'
        ctx.textBaseline = 'middle'
        ctx.fillStyle = dimmed
          ? 'rgba(200,208,224,0.2)'
          : isHov
            ? '#ffffff'
            : LABEL_COLOR
        const displayLabel =
          node.label.length > 14
            ? node.label.slice(0, 13) + '…'
            : node.label
        ctx.fillText(displayLabel, node.x, node.y + node.radius + 12 / v.k)

        /* Sub-label on hover */
        if (isHov && v.k > 0.4) {
          const sub = node.owner ?? node.kind
          ctx.font = `400 ${(fontSize * 0.7) / v.k * 0.7}px 'Archivo Variable', sans-serif`
          ctx.fillStyle = LABEL_SUB_COLOR
          ctx.fillText(sub, node.x, node.y + node.radius + 24 / v.k)
        }
      }
    }

    ctx.restore()

    /* ── HUD overlay ──────────────────────────────────────────── */
    ctx.fillStyle = BADGE_BG
    const hudText = `${nodesArr.length} nodes · ${links.length} edges`
    ctx.font = '600 11px "Archivo Variable", sans-serif'
    const hudW = ctx.measureText(hudText).width + 20
    const hudH = 26
    const hudX = w - hudW - 12
    const hudY = h - hudH - 12
    roundRect(ctx, hudX, hudY, hudW, hudH, 6)
    ctx.fill()
    ctx.fillStyle = LABEL_SUB_COLOR
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillText(hudText, hudX + hudW / 2, hudY + hudH / 2)

    animRef.current = requestAnimationFrame(render)
  }, [dims, links, blastRadius, searchMatches, selected])

  /* Start/stop render loop */
  useEffect(() => {
    animRef.current = requestAnimationFrame(render)
    return () => cancelAnimationFrame(animRef.current)
  }, [render])

  /* ── Pointer events ─────────────────────────────────────────── */

  const onPointerDown = useCallback(
    (e: React.PointerEvent<HTMLCanvasElement>) => {
      const rect = canvasRef.current?.getBoundingClientRect()
      if (!rect) return
      dragRef.current = {
        active: true,
        startX: e.clientX,
        startY: e.clientY,
        startViewX: viewRef.current.x,
        startViewY: viewRef.current.y,
        moved: false,
      }
      e.currentTarget.setPointerCapture(e.pointerId)
    },
    [],
  )

  const onPointerMove = useCallback(
    (e: React.PointerEvent<HTMLCanvasElement>) => {
      const rect = canvasRef.current?.getBoundingClientRect()
      if (!rect) return

      const px = e.clientX - rect.left
      const py = e.clientY - rect.top

      if (dragRef.current?.active) {
        const dx = e.clientX - dragRef.current.startX
        const dy = e.clientY - dragRef.current.startY
        if (Math.abs(dx) > 3 || Math.abs(dy) > 3) {
          dragRef.current.moved = true
        }
        setView((prev) => ({
          ...prev,
          x: dragRef.current!.startViewX + dx,
          y: dragRef.current!.startViewY + dy,
        }))
        return
      }

      /* Hover hit test */
      const hit = hitTest(px, py)
      setHovered(hit?.id ?? null)
      if (canvasRef.current) {
        canvasRef.current.style.cursor = hit ? 'pointer' : 'grab'
      }
    },
    [hitTest],
  )

  const onPointerUp = useCallback(
    (e: React.PointerEvent<HTMLCanvasElement>) => {
      const wasDrag = dragRef.current?.moved
      dragRef.current = null

      if (!wasDrag) {
        const rect = canvasRef.current?.getBoundingClientRect()
        if (!rect) return
        const px = e.clientX - rect.left
        const py = e.clientY - rect.top
        const hit = hitTest(px, py)
        setSelected(hit)
        if (hit && onNodeClick) {
          onNodeClick({
            id: hit.id,
            label: hit.label,
            kind: hit.kind,
            owner: hit.owner,
            properties: hit.properties,
          })
        }
      }
    },
    [hitTest, onNodeClick],
  )

  /* Zoom on wheel */
  useEffect(() => {
    const el = canvasRef.current
    if (!el) return
    const onWheel = (e: WheelEvent) => {
      e.preventDefault()
      const rect = el.getBoundingClientRect()
      const px = e.clientX - rect.left
      const py = e.clientY - rect.top

      if (e.ctrlKey || e.metaKey) {
        /* Pinch-to-zoom (trackpad) or Ctrl+wheel (mouse) */
        const factor = e.deltaY < 0 ? 1.12 : 0.89
        setView((prev) => {
          const nextK = Math.min(8, Math.max(0.08, prev.k * factor))
          const wx = (px - prev.x) / prev.k
          const wy = (py - prev.y) / prev.k
          return { x: px - wx * nextK, y: py - wy * nextK, k: nextK }
        })
      } else if (Math.abs(e.deltaX) > Math.abs(e.deltaY) * 1.5) {
        /* Horizontal-dominant swipe → pan */
        setView((prev) => ({
          ...prev,
          x: prev.x - e.deltaX,
          y: prev.y - e.deltaY,
        }))
      } else {
        /* Vertical scroll (mouse wheel or trackpad) → zoom */
        const factor = e.deltaY < 0 ? 1.12 : 0.89
        setView((prev) => {
          const nextK = Math.min(8, Math.max(0.08, prev.k * factor))
          const wx = (px - prev.x) / prev.k
          const wy = (py - prev.y) / prev.k
          return { x: px - wx * nextK, y: py - wy * nextK, k: nextK }
        })
      }
    }
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => el.removeEventListener('wheel', onWheel)
  }, [])

  /* ── Zoom controls ──────────────────────────────────────────── */

  const zoomIn = () =>
    setView((prev) => {
      const nextK = Math.min(8, prev.k * 1.3)
      return {
        x: dims.w / 2 - ((dims.w / 2 - prev.x) / prev.k) * nextK,
        y: dims.h / 2 - ((dims.h / 2 - prev.y) / prev.k) * nextK,
        k: nextK,
      }
    })

  const zoomOut = () =>
    setView((prev) => {
      const nextK = Math.max(0.08, prev.k * 0.7)
      return {
        x: dims.w / 2 - ((dims.w / 2 - prev.x) / prev.k) * nextK,
        y: dims.h / 2 - ((dims.h / 2 - prev.y) / prev.k) * nextK,
        k: nextK,
      }
    })

  /* ── Kind legend ────────────────────────────────────────────── */

  const kinds = useMemo(() => {
    const set = new Set<string>()
    for (const n of nodes) set.add(n.kind ?? 'service')
    return Array.from(set).sort()
  }, [nodes])

  /* ── Render ─────────────────────────────────────────────────── */

  return (
    <div
      ref={wrapRef}
      className="relative w-full overflow-hidden"
      style={{
        background: BG,
        borderRadius: '0.75rem',
        height: height ?? '100%',
      }}
    >
      <canvas
        ref={canvasRef}
        className="block h-full w-full touch-none"
        style={{ cursor: 'grab' }}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={() => {
          dragRef.current = null
        }}
      />

      {/* ── Search bar (top-left, Bloom style) ──────────────── */}
      <div
        className="absolute top-3 left-3 flex items-center gap-2"
        style={{
          background: SEARCH_BG,
          border: `1px solid ${SEARCH_BORDER}`,
          borderRadius: '8px',
          padding: '6px 12px',
          minWidth: '220px',
        }}
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={LABEL_SUB_COLOR} strokeWidth="2">
          <circle cx="11" cy="11" r="8" />
          <line x1="21" y1="21" x2="16.65" y2="16.65" />
        </svg>
        <input
          type="text"
          placeholder="Search nodes…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{
            background: 'transparent',
            border: 'none',
            outline: 'none',
            color: SEARCH_TEXT,
            fontSize: '0.8125rem',
            width: '100%',
            fontFamily: 'inherit',
          }}
        />
        {search && (
          <button
            onClick={() => setSearch('')}
            style={{
              background: 'none',
              border: 'none',
              color: LABEL_SUB_COLOR,
              cursor: 'pointer',
              fontSize: '14px',
              padding: 0,
              lineHeight: 1,
            }}
          >
            ✕
          </button>
        )}
      </div>

      {/* ── Zoom controls (bottom-right) ────────────────────── */}
      <div
        className="absolute right-3 bottom-14 flex flex-col gap-1"
        style={{ zIndex: 10 }}
      >
        <ZoomBtn label="+" onClick={zoomIn} />
        <ZoomBtn label="−" onClick={zoomOut} />
        <ZoomBtn label="⊡" onClick={fitAll} title="Fit all" />
      </div>

      {/* ── Kind legend (bottom-left) ───────────────────────── */}
      <div
        className="absolute bottom-3 left-3 flex flex-wrap gap-3"
        style={{
          background: BADGE_BG,
          padding: '6px 14px',
          borderRadius: '8px',
          maxWidth: '60%',
        }}
      >
        {kinds.map((k) => (
          <div
            key={k}
            className="flex items-center gap-1.5"
            style={{ fontSize: '0.6875rem', color: LABEL_SUB_COLOR }}
          >
            <span
              style={{
                width: 8,
                height: 8,
                borderRadius: '50%',
                background: kindColor(k),
                display: 'inline-block',
                flexShrink: 0,
              }}
            />
            {k}
          </div>
        ))}
      </div>

      {/* ── Hint text ───────────────────────────────────────── */}
      <div
        className="absolute right-3 bottom-3"
        style={{
          fontSize: '0.625rem',
          color: LABEL_SUB_COLOR,
          opacity: 0.7,
        }}
      >
        scroll to zoom · drag to pan · click node for details
      </div>

      {/* ── Detail panel (right side, Bloom-style) ──────────── */}
      {selected && (
        <DetailPanel
          node={selected}
          adjacency={adjacency}
          nodeMap={nodeMap}
          onClose={() => setSelected(null)}
          onAttachFeedback={onAttachFeedback}
          attachButtonLabel={attachButtonLabel}
        />
      )}
    </div>
  )
}

/* ── Detail panel component ───────────────────────────────────────── */

function DetailPanel({
  node,
  adjacency,
  nodeMap,
  onClose,
  onAttachFeedback,
  attachButtonLabel,
}: {
  node: GNode
  adjacency: Map<string, Set<string>>
  nodeMap: Map<string, GNode>
  onClose: () => void
  onAttachFeedback?: (nodeId: string) => void
  attachButtonLabel?: string
}) {
  const deps = Array.from(adjacency.get(node.id) ?? [])
  const dependents = Array.from(nodeMap.values()).filter((n) =>
    adjacency.get(n.id)?.has(node.id),
  )

  return (
    <div
      className="absolute top-3 right-3 bottom-3 overflow-y-auto"
      style={{
        width: '320px',
        background: PANEL_BG,
        border: `1px solid ${PANEL_BORDER}`,
        borderRadius: '12px',
        padding: '20px',
        color: LABEL_COLOR,
        zIndex: 20,
        backdropFilter: 'blur(12px)',
        boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
      }}
    >
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-2">
          <span
            style={{
              width: 12,
              height: 12,
              borderRadius: '50%',
              background: kindColor(node.kind),
              display: 'inline-block',
              flexShrink: 0,
            }}
          />
          <span
            style={{
              fontSize: '0.6875rem',
              color: LABEL_SUB_COLOR,
              textTransform: 'uppercase',
              letterSpacing: '0.06em',
            }}
          >
            {node.kind}
          </span>
        </div>
        <button
          onClick={onClose}
          style={{
            background: 'none',
            border: 'none',
            color: LABEL_SUB_COLOR,
            cursor: 'pointer',
            fontSize: '16px',
            padding: '0 4px',
            lineHeight: 1,
          }}
        >
          ✕
        </button>
      </div>

      <h3
        style={{
          fontSize: '1.125rem',
          fontWeight: 700,
          marginTop: '8px',
          wordBreak: 'break-all',
          color: '#e8edf5',
        }}
      >
        {node.label}
      </h3>

      {node.fullId !== node.label && (
        <p
          style={{
            fontSize: '0.75rem',
            color: LABEL_SUB_COLOR,
            marginTop: '2px',
            wordBreak: 'break-all',
          }}
        >
          {node.fullId}
        </p>
      )}

      {onAttachFeedback && (
        <button
          type="button"
          onClick={() => onAttachFeedback(node.id)}
          style={{
            marginTop: '12px',
            width: '100%',
            backgroundColor: '#d2231f',
            color: '#ffffff',
            border: '1px solid #d2231f',
            borderRadius: '6px',
            padding: '8px 12px',
            fontSize: '0.8125rem',
            fontFamily: 'var(--font-display, inherit)',
            fontWeight: 650,
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '6px',
            boxShadow: '0 2px 10px rgba(210, 35, 31, 0.25)',
            transition: 'background-color 150ms ease, transform 150ms ease',
          }}
        >
          <span>💬</span>
          <span>{attachButtonLabel || 'Attach node to feedback'}</span>
        </button>
      )}

      <div
        style={{
          marginTop: '16px',
          display: 'grid',
          gridTemplateColumns: '1fr 1fr',
          gap: '8px',
        }}
      >
        <StatBox label="Connections" value={String(node.connections)} />
        <StatBox label="Dependencies" value={String(deps.length)} />
        <StatBox label="Dependents" value={String(dependents.length)} />
        <StatBox
          label="Blast radius"
          value={String(
            (() => {
              const seen = new Set<string>()
              const walk = (id: string) => {
                for (const d of adjacency.get(id) ?? []) {
                  if (!seen.has(d)) {
                    seen.add(d)
                    walk(d)
                  }
                }
              }
              walk(node.id)
              return seen.size
            })(),
          )}
        />
      </div>

      {/* Properties */}
      <div style={{ marginTop: '16px' }}>
        {node.owner && <PropRow label="Owner" value={node.owner} />}
        {node.language && (
          <PropRow label="Language" value={node.language} />
        )}
        {Object.entries(node.properties)
          .filter(
            ([k]) =>
              !['id', 'kind', 'owner_team', 'team', 'language'].includes(k),
          )
          .slice(0, 8)
          .map(([k, v]) => (
            <PropRow key={k} label={k} value={String(v ?? '')} />
          ))}
      </div>

      {/* Dependencies list */}
      {deps.length > 0 && (
        <div style={{ marginTop: '16px' }}>
          <p
            style={{
              fontSize: '0.6875rem',
              color: LABEL_SUB_COLOR,
              textTransform: 'uppercase',
              letterSpacing: '0.06em',
              marginBottom: '6px',
            }}
          >
            Dependencies
          </p>
          {deps.slice(0, 10).map((d) => {
            const dn = nodeMap.get(d)
            return (
              <div
                key={d}
                className="flex items-center gap-2"
                style={{
                  fontSize: '0.8125rem',
                  padding: '3px 0',
                  color: LABEL_COLOR,
                }}
              >
                <span
                  style={{
                    width: 6,
                    height: 6,
                    borderRadius: '50%',
                    background: kindColor(dn?.kind ?? 'service'),
                    display: 'inline-block',
                    flexShrink: 0,
                  }}
                />
                {d.split('.').pop()}
              </div>
            )
          })}
          {deps.length > 10 && (
            <p style={{ fontSize: '0.75rem', color: LABEL_SUB_COLOR }}>
              +{deps.length - 10} more
            </p>
          )}
        </div>
      )}

      {/* Dependents list */}
      {dependents.length > 0 && (
        <div style={{ marginTop: '16px' }}>
          <p
            style={{
              fontSize: '0.6875rem',
              color: LABEL_SUB_COLOR,
              textTransform: 'uppercase',
              letterSpacing: '0.06em',
              marginBottom: '6px',
            }}
          >
            Dependents (upstream)
          </p>
          {dependents.slice(0, 10).map((dn) => (
            <div
              key={dn.id}
              className="flex items-center gap-2"
              style={{
                fontSize: '0.8125rem',
                padding: '3px 0',
                color: LABEL_COLOR,
              }}
            >
              <span
                style={{
                  width: 6,
                  height: 6,
                  borderRadius: '50%',
                  background: kindColor(dn.kind),
                  display: 'inline-block',
                  flexShrink: 0,
                }}
              />
              {dn.label}
            </div>
          ))}
          {dependents.length > 10 && (
            <p style={{ fontSize: '0.75rem', color: LABEL_SUB_COLOR }}>
              +{dependents.length - 10} more
            </p>
          )}
        </div>
      )}
    </div>
  )
}

/* ── Helpers ──────────────────────────────────────────────────────── */

function StatBox({ label, value }: { label: string; value: string }) {
  return (
    <div
      style={{
        background: 'rgba(30,35,48,0.8)',
        borderRadius: '8px',
        padding: '10px 12px',
      }}
    >
      <p
        style={{
          fontSize: '0.625rem',
          color: LABEL_SUB_COLOR,
          textTransform: 'uppercase',
          letterSpacing: '0.06em',
        }}
      >
        {label}
      </p>
      <p
        style={{
          fontSize: '1.25rem',
          fontWeight: 700,
          color: '#e8edf5',
          marginTop: '2px',
        }}
      >
        {value}
      </p>
    </div>
  )
}

function PropRow({ label, value }: { label: string; value: string }) {
  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'baseline',
        padding: '4px 0',
        borderBottom: '1px solid rgba(42,47,61,0.5)',
        fontSize: '0.8125rem',
      }}
    >
      <span style={{ color: LABEL_SUB_COLOR }}>{label}</span>
      <span
        style={{
          color: LABEL_COLOR,
          maxWidth: '55%',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
          textAlign: 'right',
        }}
      >
        {value}
      </span>
    </div>
  )
}

function ZoomBtn({
  label,
  onClick,
  title,
}: {
  label: string
  onClick: () => void
  title?: string
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title ?? label}
      style={{
        width: 32,
        height: 32,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: PANEL_BG,
        border: `1px solid ${PANEL_BORDER}`,
        borderRadius: '8px',
        color: LABEL_COLOR,
        cursor: 'pointer',
        fontSize: '16px',
        fontWeight: 700,
        transition: 'background 0.15s',
      }}
      onMouseEnter={(e) => {
        ;(e.target as HTMLElement).style.background = '#252938'
      }}
      onMouseLeave={(e) => {
        ;(e.target as HTMLElement).style.background = PANEL_BG
      }}
    >
      {label}
    </button>
  )
}

function roundRect(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  r: number,
) {
  ctx.beginPath()
  ctx.moveTo(x + r, y)
  ctx.lineTo(x + w - r, y)
  ctx.quadraticCurveTo(x + w, y, x + w, y + r)
  ctx.lineTo(x + w, y + h - r)
  ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h)
  ctx.lineTo(x + r, y + h)
  ctx.quadraticCurveTo(x, y + h, x, y + h - r)
  ctx.lineTo(x, y + r)
  ctx.quadraticCurveTo(x, y, x + r, y)
  ctx.closePath()
}

function lighten(hex: string, amount: number): string {
  const r = parseInt(hex.slice(1, 3), 16)
  const g = parseInt(hex.slice(3, 5), 16)
  const b = parseInt(hex.slice(5, 7), 16)
  return `rgb(${Math.min(255, r + (255 - r) * amount)},${Math.min(255, g + (255 - g) * amount)},${Math.min(255, b + (255 - b) * amount)})`
}

function darken(hex: string, amount: number): string {
  const r = parseInt(hex.slice(1, 3), 16)
  const g = parseInt(hex.slice(3, 5), 16)
  const b = parseInt(hex.slice(5, 7), 16)
  return `rgb(${Math.max(0, r * (1 - amount))},${Math.max(0, g * (1 - amount))},${Math.max(0, b * (1 - amount))})`
}
