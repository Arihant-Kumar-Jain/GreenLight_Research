/**
 * 3D force-directed relationship graph. Nodes = papers (+ the idea at the centre); edges = citations (with light
 * particles flowing from citing to cited paper), embedding similarity, and the idea's closest-work links. Layout is a
 * small 3D force simulation (repulsion, springs per edge type, pull towards the node's cluster). Selecting a node or
 * cluster dims everything that isn't connected to it. Drag to orbit, scroll to zoom, click to select.
 */
import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import type { GraphData } from '../api'
import { createStage, GO, INFO, MUTED, pointCloud, pointsMaterial, STOP, WAIT } from './core'
import { CLUSTER_COLORS, type EdgeKind } from './graphColors'

const EDGE = { cites: new THREE.Color(0x0b7a47), similar: new THREE.Color(0x155e75), idea: new THREE.Color(0xa85f00) }
const PAPER = new THREE.Color(0xffffff)
const IDEA_LEN: Record<string, number> = { 'same idea': 1.6, 'very close': 2.4, related: 3.4, background: 4.4 }


function credColor(score: number | null) {
  if (score == null) return MUTED
  return score >= 72 ? GO : score >= 55 ? INFO : score >= 38 ? WAIT : STOP
}

export default function PaperGraph({ data, colorBy, show, selected, cluster, onSelect, className }: {
  data: GraphData; colorBy: 'cluster' | 'credibility'; show: Record<EdgeKind, boolean>
  selected: string | null; cluster: number | null; onSelect: (id: string | null) => void; className?: string
}) {
  const mount = useRef<HTMLDivElement>(null)
  const live = useRef({ colorBy, show, selected, cluster, onSelect })
  live.current = { colorBy, show, selected, cluster, onSelect }
  const [hover, setHover] = useState<{ id: string; x: number; y: number } | null>(null)

  useEffect(() => {
    const el = mount.current
    if (!el) return
    const st = createStage(el, { fov: 45 })
    if (!st) return
    const { scene, camera, renderer, track, dpr } = st
    scene.add(new THREE.AmbientLight(0xffffff, 1.5))
    const keyLight = new THREE.DirectionalLight(0xffffff, 1.2)
    keyLight.position.set(3, 5, 6)
    scene.add(keyLight)

    // ---------------------------------------------------------------- simulation state
    type N = { id: string; p: THREE.Vector3; v: THREE.Vector3; cluster: number; r: number; mesh: THREE.Mesh; mat: THREE.MeshStandardMaterial }
    const ids = ['IDEA', ...data.nodes.map((n) => n.id)]
    const info = new Map(data.nodes.map((n) => [n.id, n]))
    const geo = track(new THREE.IcosahedronGeometry(1, 3))
    const nodes = new Map<string, N>()
    ids.forEach((id, i) => {
      const n = info.get(id)
      const mat = track(new THREE.MeshStandardMaterial({ color: 0x9aa8a1, emissive: new THREE.Color(0xffffff), emissiveIntensity: 0.2, roughness: 0.5 }))
      const mesh = new THREE.Mesh(geo, mat)
      const r = id === 'IDEA' ? 0.42 : 0.1 + Math.min(0.22, Math.log10(1 + (n?.citations ?? 0)) * 0.06) + (n?.relation ? 0.05 : 0)
      mesh.scale.setScalar(r)
      mesh.userData.id = id
      scene.add(mesh)
      const p = id === 'IDEA' ? new THREE.Vector3() : new THREE.Vector3().randomDirection().multiplyScalar(3 + (i % 7))
      nodes.set(id, { id, p, v: new THREE.Vector3(), cluster: n?.cluster ?? -1, r, mesh, mat })
    })
    const ideaHalo = new THREE.Mesh(track(new THREE.TorusGeometry(0.75, 0.01, 8, 128)), track(new THREE.MeshBasicMaterial({ color: 0xa85f00, transparent: true, opacity: 0.7 })))
    scene.add(ideaHalo)

    const edges = data.edges.filter((e) => nodes.has(e.source) && nodes.has(e.target))
    const rest = (e: typeof edges[number]) => e.type === 'cites' ? 2.2 : e.type === 'similar' ? 2.9 - (e.weight ?? 0.6) : IDEA_LEN[e.relation ?? ''] ?? 3.4
    const stiff = (e: typeof edges[number]) => e.type === 'cites' ? 0.06 : e.type === 'similar' ? 0.03 : 0.05

    const step = (alpha: number) => {
      const arr = [...nodes.values()]
      const centroids = new Map<number, THREE.Vector3>()
      const counts = new Map<number, number>()
      for (const n of arr) if (n.cluster >= 0) {
        centroids.set(n.cluster, (centroids.get(n.cluster) ?? new THREE.Vector3()).add(n.p))
        counts.set(n.cluster, (counts.get(n.cluster) ?? 0) + 1)
      }
      centroids.forEach((c, k) => c.divideScalar(counts.get(k)!))
      const d = new THREE.Vector3()
      for (let i = 0; i < arr.length; i++) for (let j = i + 1; j < arr.length; j++) {
        d.subVectors(arr[i].p, arr[j].p)
        const dist2 = Math.max(d.lengthSq(), 0.04)
        d.multiplyScalar((1.6 * alpha) / dist2)
        arr[i].v.add(d); arr[j].v.sub(d)
      }
      for (const e of edges) {
        const a = nodes.get(e.source)!, b = nodes.get(e.target)!
        d.subVectors(b.p, a.p)
        const len = d.length() || 0.01
        d.multiplyScalar(((len - rest(e)) / len) * stiff(e) * alpha * 4)
        a.v.add(d); b.v.sub(d)
      }
      for (const n of arr) {
        if (n.id === 'IDEA') { n.p.set(0, 0, 0); n.v.set(0, 0, 0); continue }
        n.v.addScaledVector(n.p, -0.004 * alpha)
        const c = centroids.get(n.cluster)
        if (c) n.v.addScaledVector(d.subVectors(c, n.p), 0.012 * alpha)
        n.v.multiplyScalar(0.82)
        n.p.add(n.v)
      }
    }
    for (let i = 0; i < 360; i++) step(1 - i / 400)

    // ---------------------------------------------------------------- edges + flow particles
    const lineGeo = track(new THREE.BufferGeometry())
    const lp = new Float32Array(edges.length * 6), lc = new Float32Array(edges.length * 6)
    lineGeo.setAttribute('position', new THREE.BufferAttribute(lp, 3))
    lineGeo.setAttribute('color', new THREE.BufferAttribute(lc, 3))
    const lineMat = track(new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, opacity: 0.9, depthWrite: false }))
    scene.add(new THREE.LineSegments(lineGeo, lineMat))
    const cites = edges.filter((e) => e.type === 'cites')
    const PER = 3
    const flow = pointCloud(cites.length * PER)
    track(flow.geo)
    const flowMat = track(pointsMaterial(dpr, 0))
    scene.add(new THREE.Points(flow.geo, flowMat))

    // starfield
    const S = 1200, sf = pointCloud(S)
    for (let i = 0; i < S; i++) {
      const v = new THREE.Vector3().randomDirection().multiplyScalar(25 + Math.random() * 30)
      sf.pos.set([v.x, v.y, v.z], i * 3); sf.col.set([0.6, 0.75, 0.7], i * 3)
      sf.alpha[i] = 0.1 + Math.random() * 0.25; sf.size[i] = 0.08; sf.rand[i] = Math.random()
    }
    track(sf.geo)
    scene.add(new THREE.Points(sf.geo, track(pointsMaterial(dpr, 1))))

    // ---------------------------------------------------------------- controls
    const cam = { theta: 0.5, phi: 1.1, dist: 17, tTheta: 0.5, tPhi: 1.1, tDist: 17 }
    let dragging = false, moved = 0, lastX = 0, lastY = 0, idle = 0
    const ray = new THREE.Raycaster()
    const ndc = new THREE.Vector2(9, 9)
    let hovered: string | null = null
    const canvas = renderer.domElement
    canvas.style.cursor = 'grab'
    const down = (e: PointerEvent) => { dragging = true; moved = 0; lastX = e.clientX; lastY = e.clientY; try { canvas.setPointerCapture(e.pointerId) } catch { /* synthetic pointer */ } }
    // click/tap does its own hit test: touch screens never hover, and the loop pauses off-screen
    const pick = (e: PointerEvent) => {
      const rect = canvas.getBoundingClientRect()
      const p = new THREE.Vector2(((e.clientX - rect.left) / rect.width) * 2 - 1, -((e.clientY - rect.top) / rect.height) * 2 + 1)
      ray.setFromCamera(p, camera)
      return (ray.intersectObjects([...nodes.values()].map((n) => n.mesh), false)[0]?.object.userData.id as string | undefined) ?? null
    }
    const up = (e: PointerEvent) => {
      dragging = false
      try { canvas.releasePointerCapture(e.pointerId) } catch { /* not captured */ }
      if (moved < 5) {
        const id = pick(e)
        live.current.onSelect(id && id !== 'IDEA' ? id : null)
      }
    }
    const move = (e: PointerEvent) => {
      const rect = canvas.getBoundingClientRect()
      ndc.set(((e.clientX - rect.left) / rect.width) * 2 - 1, -((e.clientY - rect.top) / rect.height) * 2 + 1)
      if (dragging) {
        const dx = e.clientX - lastX, dy = e.clientY - lastY
        moved += Math.abs(dx) + Math.abs(dy)
        cam.tTheta -= dx * 0.006
        cam.tPhi = Math.min(2.9, Math.max(0.25, cam.tPhi - dy * 0.005))
        lastX = e.clientX; lastY = e.clientY; idle = 0
      }
      if (hovered) setHover({ id: hovered, x: e.clientX - rect.left, y: e.clientY - rect.top })
    }
    const leave = () => { ndc.set(9, 9); setHover(null) }
    const wheel = (e: WheelEvent) => { e.preventDefault(); cam.tDist = Math.min(40, Math.max(5, cam.tDist * (1 + e.deltaY * 0.001))); idle = 0 }
    canvas.addEventListener('pointerdown', down)
    canvas.addEventListener('pointerup', up)
    canvas.addEventListener('pointermove', move)
    canvas.addEventListener('pointerleave', leave)
    canvas.addEventListener('wheel', wheel, { passive: false })

    const neighbours = (id: string) => new Set(edges.flatMap((e) => (e.source === id ? [e.target] : e.target === id ? [e.source] : [])))
    const tmp = new THREE.Color()
    const P = new THREE.Vector3()
    st.start((t, dt) => {
      step(0.05) // keep the layout gently alive
      const { colorBy: cb, show: sh, selected: sel, cluster: cl } = live.current
      const near = sel ? neighbours(sel) : null
      const focus = (id: string) => (sel ? id === sel || near!.has(id) : cl != null ? nodes.get(id)!.cluster === cl : true)

      for (const n of nodes.values()) {
        n.mesh.position.copy(n.p)
        const meta = info.get(n.id)
        const base = n.id === 'IDEA' ? WAIT : cb === 'cluster' ? (n.cluster >= 0 ? tmp.set(CLUSTER_COLORS[n.cluster % 9]) : MUTED) : credColor(meta?.credibility ?? null)
        const f = focus(n.id) || n.id === 'IDEA'
        // Light surface: out-of-focus nodes fade toward the paper instead of going dark.
        n.mat.color.copy(base).lerp(PAPER, f ? 0 : 0.82)
        n.mat.emissive.copy(n.mat.color)
        n.mat.emissiveIntensity = n.id === hovered || n.id === sel ? 0.55 : 0.25
        const target = n.r * (n.id === hovered || n.id === sel ? 1.6 : 1)
        n.mesh.scale.setScalar(n.mesh.scale.x + (target - n.mesh.scale.x) * 0.2)
      }
      ideaHalo.rotation.x = t * 0.3; ideaHalo.rotation.y = t * 0.2

      edges.forEach((e, k) => {
        const a = nodes.get(e.source)!.p, b = nodes.get(e.target)!.p
        lp.set([a.x, a.y, a.z, b.x, b.y, b.z], k * 6)
        const on = sh[e.type as EdgeKind] && (focus(e.source) && focus(e.target) || (sel != null && (e.source === sel || e.target === sel)))
        const strength = !sh[e.type as EdgeKind] ? 0 : on ? (e.type === 'similar' ? 0.35 : 0.8) : 0.04
        tmp.copy(EDGE[e.type as EdgeKind]).lerp(PAPER, 1 - strength)
        lc.set([tmp.r, tmp.g, tmp.b, tmp.r, tmp.g, tmp.b], k * 6)
      })
      lineGeo.attributes.position.needsUpdate = true
      lineGeo.attributes.color.needsUpdate = true

      cites.forEach((e, k) => {
        const a = nodes.get(e.source)!.p, b = nodes.get(e.target)!.p
        const on = sh.cites && (focus(e.source) && focus(e.target) || (sel != null && (e.source === sel || e.target === sel)))
        for (let j = 0; j < PER; j++) {
          const u = ((t * 0.35 + j / PER + k * 0.137) % 1)
          P.lerpVectors(a, b, u)
          const i = k * PER + j
          flow.pos.set([P.x, P.y, P.z], i * 3)
          flow.col.set([0.043, 0.478, 0.278], i * 3)
          flow.alpha[i] = on ? Math.sin(u * Math.PI) : 0
          flow.size[i] = 0.16
        }
      })
      for (const a of ['position', 'color', 'alpha', 'size']) flow.geo.attributes[a].needsUpdate = true

      idle += dt
      if (!dragging && idle > 3) cam.tTheta += dt * 0.05
      cam.theta += (cam.tTheta - cam.theta) * 0.08
      cam.phi += (cam.tPhi - cam.phi) * 0.08
      cam.dist += (cam.tDist - cam.dist) * 0.08
      camera.position.setFromSphericalCoords(cam.dist, cam.phi, cam.theta)
      camera.lookAt(0, 0, 0)

      ray.setFromCamera(ndc, camera)
      const hit = ray.intersectObjects([...nodes.values()].map((n) => n.mesh), false)[0]
      const id = (hit?.object.userData.id as string | undefined) ?? null
      if (id !== hovered) {
        hovered = id
        canvas.style.cursor = id ? 'pointer' : 'grab'
        if (!id) setHover(null)
      }
    })

    return () => {
      canvas.removeEventListener('pointerdown', down)
      canvas.removeEventListener('pointerup', up)
      canvas.removeEventListener('pointermove', move)
      canvas.removeEventListener('pointerleave', leave)
      canvas.removeEventListener('wheel', wheel)
      st.dispose()
    }
  }, [data])

  const hn = hover ? data.nodes.find((n) => n.id === hover.id) : null
  return (
    <div className={className} style={{ position: 'relative' }}>
      <div ref={mount} className="absolute inset-0" />
      {hover && (
        <div className="pointer-events-none absolute z-10 w-72 rounded-xl border border-line bg-surface/95 p-3 text-sm shadow-2xl backdrop-blur"
          style={{ left: Math.min(hover.x + 16, (mount.current?.clientWidth ?? 600) - 300), top: hover.y + 16 }}>
          {hover.id === 'IDEA' ? <div className="font-medium">Your idea: {data.idea.title}</div> : hn && (
            <>
              <div className="flex gap-2 text-xs"><span className="font-mono text-info">{hn.id}</span>{hn.relation && <span className="text-wait">{hn.relation}</span>}
                <span className="ml-auto">{hn.credibility != null ? `${hn.credibility}/100` : 'unscored'}</span></div>
              <div className="mt-1 font-medium leading-snug">{hn.title}</div>
              <div className="mt-1 text-xs text-muted">{hn.year ?? 'n.d.'}{hn.citations != null ? ` · ${hn.citations} cites` : ''} · click to inspect links</div>
            </>
          )}
        </div>
      )}
    </div>
  )
}
