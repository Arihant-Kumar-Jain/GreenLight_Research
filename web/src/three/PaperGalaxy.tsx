/**
 * The project's literature as an explorable 3D galaxy. Your idea is the liquid-glass core (tinted by the verdict);
 * every paper is a glowing body: orbit = how close it is to the idea (same idea → background → unranked),
 * colour = credibility, size = citations, a red ring = retracted. Threads link the idea to its closest work.
 * Drag to orbit, scroll to zoom, hover for details, click to open the paper.
 */
import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import type { Light, Paper, Relation } from '../api'
import { createStage, GO, INFO, MUTED, pointCloud, pointsMaterial, STOP, WAIT } from './core'
import { createGlass, createRefractionTarget } from './glass'

const ORBIT: Record<string, number> = { 'same idea': 2.1, 'very close': 3.2, related: 4.5, background: 5.8 }
const UNRANKED = 7.4

function credColor(p: Paper) {
  const c = p.credibility
  if (!c) return MUTED
  if (c.retracted) return STOP
  return c.score >= 72 ? GO : c.score >= 55 ? INFO : c.score >= 38 ? WAIT : STOP
}

type Hover = { id: string; x: number; y: number } | null

export default function PaperGalaxy({ papers, closest, light, onOpen, className }: {
  papers: Paper[]; closest: Relation[]; light: Light | null; onOpen: (id: string) => void; className?: string
}) {
  const mount = useRef<HTMLDivElement>(null)
  const [hover, setHover] = useState<Hover>(null)
  const openRef = useRef(onOpen)
  openRef.current = onOpen
  const key = papers.map((p) => `${p.id}:${p.credibility?.score ?? ''}`).join(',') + '|' + closest.map((c) => c.id + c.relation).join(',') + light

  useEffect(() => {
    const el = mount.current
    if (!el) return
    const st = createStage(el, { fov: 45 })
    if (!st) return
    const { scene, camera, renderer, track, dpr } = st
    const world = new THREE.Group()
    scene.add(world)
    scene.add(new THREE.AmbientLight(0xffffff, 1.4))
    const key1 = new THREE.PointLight(0xffffff, 40, 40)
    key1.position.set(3, 6, 5)
    scene.add(key1)

    const rel = new Map(closest.map((c) => [c.id, c.relation]))
    const tint = light === 'red' ? 0xb42318 : light === 'amber' ? 0xa85f00 : 0x0b7a47

    // ---------------------------------------------------------------- orbit guides
    for (const r of [...Object.values(ORBIT), UNRANKED]) {
      const ring = new THREE.Mesh(track(new THREE.TorusGeometry(r, 0.005, 6, 256)),
        track(new THREE.MeshBasicMaterial({ color: 0x0e2a21, transparent: true, opacity: r === UNRANKED ? 0.07 : 0.16 })))
      ring.rotation.x = Math.PI / 2
      world.add(ring)
    }

    // ---------------------------------------------------------------- papers
    const bodies: { mesh: THREE.Mesh; id: string; base: number; phase: number; r: number; ang: number; y: number; speed: number }[] = []
    const sphere = track(new THREE.IcosahedronGeometry(1, 3))
    const golden = Math.PI * (3 - Math.sqrt(5))
    const tiers = new Map<number, number>()
    const threads: number[] = []
    papers.forEach((p, i) => {
      const r0 = ORBIT[rel.get(p.id) ?? ''] ?? UNRANKED
      const n = tiers.get(r0) ?? 0
      tiers.set(r0, n + 1)
      const ang = n * golden * 2.1 + r0
      const r = r0 + (Math.sin(i * 12.9898) * 0.5) * (r0 === UNRANKED ? 1.4 : 0.35)
      const y = Math.sin(i * 78.233) * (r0 === UNRANKED ? 0.9 : 0.35)
      const col = credColor(p)
      const base = 0.07 + Math.min(0.2, Math.log10(1 + (p.citations ?? 0)) * 0.045) + (rel.has(p.id) ? 0.05 : 0)
      const mat = track(new THREE.MeshStandardMaterial({ color: col, emissive: col, emissiveIntensity: rel.has(p.id) ? 0.45 : 0.2, roughness: 0.5, metalness: 0 }))
      const mesh = new THREE.Mesh(sphere, mat)
      mesh.scale.setScalar(base)
      mesh.userData.id = p.id
      world.add(mesh)
      if (p.retracted) {
        const halo = new THREE.Mesh(track(new THREE.TorusGeometry(1.8, 0.12, 8, 48)), track(new THREE.MeshBasicMaterial({ color: 0xb42318 })))
        mesh.add(halo)
      }
      bodies.push({ mesh, id: p.id, base, phase: Math.random() * 6.28, r, ang, y, speed: 0.04 / Math.sqrt(r) })
      if (rel.has(p.id)) threads.push(bodies.length - 1)
    })
    const threadGeo = track(new THREE.BufferGeometry())
    const threadPos = new Float32Array(threads.length * 6)
    threadGeo.setAttribute('position', new THREE.BufferAttribute(threadPos, 3))
    const threadMat = track(new THREE.LineBasicMaterial({ color: tint, transparent: true, opacity: 0.4, depthWrite: false }))
    world.add(new THREE.LineSegments(threadGeo, threadMat))

    // ---------------------------------------------------------------- the idea core
    const glass = createGlass({ tint, wobble: 0.15, refract: 0.07, detail: 36 })
    track(glass.geometry); track(glass.material)
    glass.mesh.scale.setScalar(0.95)
    scene.add(glass.mesh)
    const core = new THREE.Mesh(track(new THREE.SphereGeometry(0.22, 24, 24)), track(new THREE.MeshBasicMaterial({ color: tint })))
    scene.add(core)
    const rt = track(createRefractionTarget())

    // starfield
    const S = 1800
    const s = pointCloud(S)
    for (let i = 0; i < S; i++) {
      const v = new THREE.Vector3().randomDirection().multiplyScalar(20 + Math.random() * 30)
      s.pos.set([v.x, v.y, v.z], i * 3); s.col.set([0.055, 0.165, 0.129], i * 3)
      s.alpha[i] = 0.06 + Math.random() * 0.16; s.size[i] = 0.06 + Math.random() * 0.1; s.rand[i] = Math.random()
    }
    track(s.geo)
    const sMat = track(pointsMaterial(dpr, 1))
    scene.add(new THREE.Points(s.geo, sMat))

    // ---------------------------------------------------------------- controls (drag orbit, wheel zoom, hover, click)
    const cam = { theta: 0.6, phi: 1.05, dist: 15, tTheta: 0.6, tPhi: 1.05, tDist: 15 }
    let dragging = false, moved = 0, lastX = 0, lastY = 0, idle = 0
    const ray = new THREE.Raycaster()
    const ndc = new THREE.Vector2(9, 9)
    let hovered: string | null = null
    const canvas = renderer.domElement
    const down = (e: PointerEvent) => { dragging = true; moved = 0; lastX = e.clientX; lastY = e.clientY; try { canvas.setPointerCapture(e.pointerId) } catch { /* synthetic pointer */ } }
    // click/tap does its own hit test: touch screens never hover, and the loop pauses off-screen
    const pick = (e: PointerEvent) => {
      const rect = canvas.getBoundingClientRect()
      const p = new THREE.Vector2(((e.clientX - rect.left) / rect.width) * 2 - 1, -((e.clientY - rect.top) / rect.height) * 2 + 1)
      ray.setFromCamera(p, camera)
      return (ray.intersectObjects(bodies.map((b) => b.mesh), false)[0]?.object.userData.id as string | undefined) ?? null
    }
    const up = (e: PointerEvent) => {
      dragging = false
      try { canvas.releasePointerCapture(e.pointerId) } catch { /* not captured */ }
      if (moved < 5) {
        const id = pick(e)
        if (id) openRef.current(id)
      }
    }
    const move = (e: PointerEvent) => {
      const rect = canvas.getBoundingClientRect()
      ndc.set(((e.clientX - rect.left) / rect.width) * 2 - 1, -((e.clientY - rect.top) / rect.height) * 2 + 1)
      if (dragging) {
        const dx = e.clientX - lastX, dy = e.clientY - lastY
        moved += Math.abs(dx) + Math.abs(dy)
        cam.tTheta -= dx * 0.006
        cam.tPhi = Math.min(1.5, Math.max(0.25, cam.tPhi - dy * 0.005))
        lastX = e.clientX; lastY = e.clientY
        idle = 0
      }
      if (hovered) setHover({ id: hovered, x: e.clientX - rect.left, y: e.clientY - rect.top })
    }
    const leave = () => { ndc.set(9, 9); setHover(null) }
    const wheel = (e: WheelEvent) => { e.preventDefault(); cam.tDist = Math.min(30, Math.max(5, cam.tDist * (1 + e.deltaY * 0.001))); idle = 0 }
    canvas.addEventListener('pointerdown', down)
    canvas.addEventListener('pointerup', up)
    canvas.addEventListener('pointermove', move)
    canvas.addEventListener('pointerleave', leave)
    canvas.addEventListener('wheel', wheel, { passive: false })
    canvas.style.cursor = 'grab'

    const size = new THREE.Vector2()
    st.start((t, dt) => {
      sMat.uniforms.uTime.value = t
      idle += dt
      if (!dragging && idle > 2.5) cam.tTheta += dt * 0.06
      cam.theta += (cam.tTheta - cam.theta) * 0.08
      cam.phi += (cam.tPhi - cam.phi) * 0.08
      cam.dist += (cam.tDist - cam.dist) * 0.08
      camera.position.setFromSphericalCoords(cam.dist, cam.phi, cam.theta)
      camera.lookAt(0, 0, 0)

      for (const b of bodies) {
        b.ang += dt * b.speed
        b.mesh.position.set(Math.cos(b.ang) * b.r, b.y + Math.sin(t * 0.6 + b.phase) * 0.05, Math.sin(b.ang) * b.r)
        const target = b.id === hovered ? b.base * 1.9 : b.base * (1 + Math.sin(t * 1.4 + b.phase) * 0.06)
        b.mesh.scale.setScalar(b.mesh.scale.x + (target - b.mesh.scale.x) * 0.2)
        b.mesh.rotation.y += dt * 0.5
      }
      threads.forEach((bi, k) => {
        const p = bodies[bi].mesh.position
        threadPos.set([0, 0, 0, p.x, p.y, p.z], k * 6)
      })
      threadGeo.attributes.position.needsUpdate = true
      threadMat.opacity = 0.25 + Math.sin(t * 1.5) * 0.1

      ray.setFromCamera(ndc, camera)
      const hit = ray.intersectObjects(bodies.map((b) => b.mesh), false)[0]
      const id = (hit?.object.userData.id as string | undefined) ?? null
      if (id !== hovered) {
        hovered = id
        canvas.style.cursor = id ? 'pointer' : 'grab'
        if (!id) setHover(null)
      }
      glass.material.uniforms.uTime.value = t
      core.scale.setScalar(1 + Math.sin(t * 2) * 0.1)
    }, () => {
      renderer.getDrawingBufferSize(size)
      if (rt.width !== size.x || rt.height !== size.y) rt.setSize(size.x, size.y)
      glass.mesh.visible = false
      renderer.setRenderTarget(rt)
      renderer.render(scene, camera)
      renderer.setRenderTarget(null)
      glass.mesh.visible = true
      glass.material.uniforms.uScene.value = rt.texture
      glass.material.uniforms.uRes.value.copy(size)
    })

    return () => {
      canvas.removeEventListener('pointerdown', down)
      canvas.removeEventListener('pointerup', up)
      canvas.removeEventListener('pointermove', move)
      canvas.removeEventListener('pointerleave', leave)
      canvas.removeEventListener('wheel', wheel)
      st.dispose()
    }
  }, [key]) // rebuild only when the papers, relations or verdict change

  const hp = hover ? papers.find((p) => p.id === hover.id) : null
  const hr = hover ? closest.find((c) => c.id === hover.id) : null
  return (
    <div className={className} style={{ position: 'relative' }}>
      <div ref={mount} className="absolute inset-0" />
      {hp && hover && (
        <div className="pointer-events-none absolute z-10 w-72 rounded-xl border border-line bg-surface/95 p-3 text-sm shadow-2xl backdrop-blur"
          style={{ left: Math.min(hover.x + 16, (mount.current?.clientWidth ?? 600) - 300), top: hover.y + 16 }}>
          <div className="flex items-center gap-2 text-xs">
            <span className="font-mono text-info">{hp.id}</span>
            {hr && <span className="text-wait">{hr.relation}</span>}
            <span className="ml-auto font-semibold">{hp.credibility ? `${hp.credibility.score}/100` : 'unscored'}</span>
          </div>
          <div className="mt-1 font-medium leading-snug">{hp.title}</div>
          <div className="mt-1 text-xs text-muted">{hp.year ?? 'n.d.'}{hp.venue ? ` · ${hp.venue}` : ''}{hp.citations != null ? ` · ${hp.citations.toLocaleString()} cites` : ''}</div>
          {hr && <div className="mt-1 text-xs text-muted">{hr.why}</div>}
        </div>
      )}
    </div>
  )
}
