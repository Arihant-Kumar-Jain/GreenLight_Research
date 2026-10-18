/**
 * Landing hero: "the literature" as a slowly turning spiral galaxy of papers with citation threads, and your idea
 * as a liquid-glass orb at its core. Scout comets stream evidence from the galaxy into the orb. The orb refracts
 * the galaxy behind it (screen-space refraction from a render target), then bloom + lens finish the frame.
 */
import { useEffect, useRef } from 'react'
import * as THREE from 'three'
import { createStage, GO, INFO, pointCloud, pointsMaterial, WAIT } from './core'
import { createGlass, createRefractionTarget } from './glass'

export default function Constellation({ className }: { className?: string }) {
  const mount = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = mount.current
    if (!el) return
    const st = createStage(el, { fov: 42, bloom: [0.75, 0.6, 0.12] })
    if (!st) return
    const { scene, camera, renderer, track, dpr, reduced } = st
    const root = new THREE.Group()
    root.rotation.x = -0.42
    scene.add(root)

    // ---------------------------------------------------------------- galaxy of papers
    const N = 9000
    const g = pointCloud(N)
    const anchors: THREE.Vector3[] = []
    const c = new THREE.Color()
    for (let i = 0; i < N; i++) {
      const arm = i % 4
      const r = 1.6 + Math.pow(Math.random(), 0.65) * 9
      const ang = arm * (Math.PI / 2) + r * 0.55 + (Math.random() - 0.5) * (0.9 / (0.4 + r * 0.12))
      const y = (Math.random() - 0.5) * (0.5 + 3.2 / (r + 1)) * 0.5
      const x = Math.cos(ang) * r, z = Math.sin(ang) * r
      g.pos.set([x, y, z], i * 3)
      const mix = Math.random()
      c.copy(mix < 0.62 ? GO : mix < 0.9 ? INFO : WAIT).lerp(new THREE.Color(0xffffff), Math.random() * 0.35)
      c.multiplyScalar(r < 3 ? 1.1 : 0.85)
      g.col.set([c.r, c.g, c.b], i * 3)
      g.alpha[i] = 0.25 + Math.random() * 0.55
      g.size[i] = 0.025 + Math.random() * Math.random() * 0.12
      g.rand[i] = Math.random()
      if (i % 60 === 0) anchors.push(new THREE.Vector3(x, y, z))
    }
    track(g.geo)
    const gMat = track(pointsMaterial(dpr, 0.7))
    root.add(new THREE.Points(g.geo, gMat))

    // dust shell far out
    const D = 2500
    const d = pointCloud(D)
    for (let i = 0; i < D; i++) {
      const v = new THREE.Vector3().randomDirection().multiplyScalar(14 + Math.random() * 26)
      d.pos.set([v.x, v.y, v.z], i * 3)
      d.col.set([0.6, 0.75, 0.68], i * 3)
      d.alpha[i] = 0.08 + Math.random() * 0.25
      d.size[i] = 0.05 + Math.random() * 0.1
      d.rand[i] = Math.random()
    }
    track(d.geo)
    scene.add(new THREE.Points(d.geo, track(pointsMaterial(dpr, 1))))

    // ---------------------------------------------------------------- citation threads
    const segs: number[] = []
    for (let i = 0; i < anchors.length; i++) {
      const a = anchors[i]
      const near = anchors.map((b, j) => [a.distanceToSquared(b), j] as const).filter(([dd, j]) => j !== i && dd < 3.5).slice(0, 2)
      for (const [, j] of near) segs.push(a.x, a.y, a.z, anchors[j].x, anchors[j].y, anchors[j].z)
    }
    const lineGeo = track(new THREE.BufferGeometry())
    lineGeo.setAttribute('position', new THREE.Float32BufferAttribute(segs, 3))
    const lineMat = track(new THREE.LineBasicMaterial({ color: 0x3ee07f, transparent: true, opacity: 0.12, blending: THREE.AdditiveBlending, depthWrite: false }))
    root.add(new THREE.LineSegments(lineGeo, lineMat))

    // ---------------------------------------------------------------- scout comets: evidence flowing to the idea
    const COMETS = reduced ? 0 : 26, TRAIL = 16
    const cm = pointCloud(COMETS * TRAIL)
    track(cm.geo)
    root.add(new THREE.Points(cm.geo, track(pointsMaterial(dpr, 0))))
    const comets = Array.from({ length: COMETS }, () => ({ curve: new THREE.QuadraticBezierCurve3(), t: Math.random(), speed: 0.15, color: GO }))
    const spawn = (k: typeof comets[number]) => {
      const a = anchors[Math.floor(Math.random() * anchors.length)]
      k.curve.v0.copy(a)
      k.curve.v1.copy(a.clone().multiplyScalar(0.45).add(new THREE.Vector3(0, 1.5 + Math.random() * 2, 0)))
      k.curve.v2.set(0, 0, 0)
      k.t = 0
      k.speed = 0.12 + Math.random() * 0.14
      k.color = Math.random() < 0.7 ? GO : INFO
    }
    comets.forEach((k) => { const t = k.t; spawn(k); k.t = t })

    // ---------------------------------------------------------------- the idea: liquid glass orb
    const glass = createGlass({ tint: 0x3ee07f, wobble: 0.16, refract: 0.07, detail: 40 })
    track(glass.geometry); track(glass.material)
    glass.mesh.scale.setScalar(1.15)
    scene.add(glass.mesh)
    const rt = track(createRefractionTarget())
    const core = new THREE.Mesh(track(new THREE.SphereGeometry(0.2, 32, 32)), track(new THREE.MeshBasicMaterial({ color: 0x7dffb0 })))
    scene.add(core)
    const ring = new THREE.Mesh(track(new THREE.TorusGeometry(1.75, 0.006, 8, 200)), track(new THREE.MeshBasicMaterial({ color: 0x9dffc4, transparent: true, opacity: 0.35 })))
    ring.rotation.x = Math.PI / 2.2
    scene.add(ring)

    // ---------------------------------------------------------------- interaction + loop
    const mouse = { x: 0, y: 0, sx: 0, sy: 0 }
    const onMove = (e: PointerEvent) => { mouse.x = (e.clientX / window.innerWidth) * 2 - 1; mouse.y = (e.clientY / window.innerHeight) * 2 - 1 }
    window.addEventListener('pointermove', onMove, { passive: true })
    const size = new THREE.Vector2()
    const p = new THREE.Vector3()
    st.start((t, dt) => {
      gMat.uniforms.uTime.value = t
      root.rotation.y += dt * 0.035
      for (let ci = 0; ci < comets.length; ci++) {
        const k = comets[ci]
        k.t += dt * k.speed
        if (k.t >= 1) spawn(k)
        for (let j = 0; j < TRAIL; j++) {
          const tt = Math.max(0, k.t - j * 0.014)
          k.curve.getPoint(tt, p)
          const idx = ci * TRAIL + j
          cm.pos.set([p.x, p.y, p.z], idx * 3)
          cm.col.set([k.color.r, k.color.g, k.color.b], idx * 3)
          cm.alpha[idx] = (1 - j / TRAIL) * Math.min(1, k.t * 6) * (1 - Math.pow(k.t, 6))
          cm.size[idx] = (j === 0 ? 0.2 : 0.12) * (1 - j / (TRAIL * 1.2))
        }
      }
      if (COMETS) for (const a of ['position', 'color', 'alpha', 'size']) cm.geo.attributes[a].needsUpdate = true
      glass.material.uniforms.uTime.value = t
      glass.material.uniforms.uGlow.value = 0.25 + Math.sin(t * 1.3) * 0.1
      core.scale.setScalar(1 + Math.sin(t * 2.1) * 0.08)
      ring.rotation.z += dt * 0.2
      mouse.sx += (mouse.x - mouse.sx) * 0.03
      mouse.sy += (mouse.y - mouse.sy) * 0.03
      camera.position.set(mouse.sx * 1.6, 2.6 - mouse.sy * 1.0, 11.5)
      camera.lookAt(0, -2.6, 0) // the idea sits above the headline
    }, () => {
      // refraction: render everything except the glass into the target the glass samples
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
      window.removeEventListener('pointermove', onMove)
      st.dispose()
    }
  }, [])

  return <div ref={mount} className={className} />
}
