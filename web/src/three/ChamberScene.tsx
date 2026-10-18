/**
 * The Research Chamber, abstracted (ported from Greenlight): two curved tiers of particle "benches" (Proponent in green, Skeptic in red)
 * face each other across an aisle; the Speaker is an ink orb at the far end. Arguments fly from the
 * benches to the Speaker as comets. Some are struck mid-flight (no evidence) and fade to grey.
 * Drawn for the light theme: ink on a white surface, no bloom.
 */
import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'

const GOV = new THREE.Color(0x0b7a47)
const OPP = new THREE.Color(0xb42318)
const STRUCK = new THREE.Color(0xb3bfb9)
const SPEAKER = new THREE.Color(0x0e2a21)

const POINT_VERT = /* glsl */ `
  attribute vec3 color; attribute float alpha; attribute float size; attribute float rand;
  uniform float uTime; uniform float uPixelRatio; uniform float uTwinkle;
  varying vec3 vColor; varying float vAlpha;
  void main() {
    vColor = color;
    vAlpha = alpha * (1.0 - uTwinkle + uTwinkle * (0.55 + 0.45 * sin(uTime * 1.7 + rand * 6.2831)));
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    gl_PointSize = size * uPixelRatio * (260.0 / -mv.z);
    gl_Position = projectionMatrix * mv;
  }`
const POINT_FRAG = /* glsl */ `
  varying vec3 vColor; varying float vAlpha;
  void main() {
    float d = length(gl_PointCoord - 0.5);
    float a = smoothstep(0.5, 0.25, d);
    gl_FragColor = vec4(vColor, a * vAlpha);
  }`

function pointsMaterial(dpr: number, twinkle: number) {
  return new THREE.ShaderMaterial({
    vertexShader: POINT_VERT, fragmentShader: POINT_FRAG, transparent: true, depthWrite: false,
    blending: THREE.NormalBlending,
    uniforms: { uTime: { value: 0 }, uPixelRatio: { value: dpr }, uTwinkle: { value: twinkle } },
  })
}

export default function ChamberScene({ className }: { className?: string }) {
  const mount = useRef<HTMLDivElement>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    const el = mount.current
    if (!el) return
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    let renderer: THREE.WebGLRenderer
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' })
    } catch {
      setFailed(true)
      return
    }
    const dpr = Math.min(window.devicePixelRatio, 1.75)
    renderer.setPixelRatio(dpr)
    renderer.setClearColor(0xffffff, 1)
    renderer.outputColorSpace = THREE.SRGBColorSpace
    Object.assign(renderer.domElement.style, { display: 'block', width: '100%', height: '100%' })
    el.appendChild(renderer.domElement)

    const scene = new THREE.Scene()
    const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 100)
    const disposables: { dispose: () => void }[] = []
    const track = <T extends { dispose: () => void }>(o: T) => (disposables.push(o), o)

    // ---------------------------------------------------------------- benches
    const benchPts: number[] = []
    const benchCol: number[] = []
    const benchAlpha: number[] = []
    const benchSize: number[] = []
    const benchRand: number[] = []
    const seats: { pos: THREE.Vector3; side: 0 | 1 }[] = []
    for (const side of [0, 1] as const) {
      const sx = side === 0 ? -1 : 1
      const color = side === 0 ? GOV : OPP
      for (let tier = 0; tier < 4; tier++) {
        const radius = 3.2 + tier * 0.75
        const height = 0.15 + tier * 0.38
        const count = 260 + tier * 80
        for (let i = 0; i < count; i++) {
          const u = i / count
          const ang = -0.95 + u * 1.9 // arc in front of each side
          const x = sx * (0.9 + Math.cos(ang) * radius - radius * 0.62)
          const z = Math.sin(ang) * radius * 1.05 + 1.2
          const y = height + (Math.random() - 0.5) * 0.06
          benchPts.push(x + (Math.random() - 0.5) * 0.05, y, z + (Math.random() - 0.5) * 0.05)
          const c = color.clone().lerp(new THREE.Color(0xffffff), Math.random() * 0.15)
          benchCol.push(c.r, c.g, c.b)
          benchAlpha.push(0.35 + Math.random() * 0.45)
          benchSize.push(0.05 + Math.random() * 0.05)
          benchRand.push(Math.random())
          if (i % 9 === 0) seats.push({ pos: new THREE.Vector3(x, y, z), side })
        }
      }
    }
    // Aisle floor: a faint grid of points leading to the Speaker.
    for (let gx = -14; gx <= 14; gx++) {
      for (let gz = -30; gz <= 18; gz++) {
        if (Math.random() > 0.55) continue
        benchPts.push(gx * 0.42, -0.02, gz * 0.42 - 2)
        const c = new THREE.Color(0xb3bfb9)
        benchCol.push(c.r, c.g, c.b)
        benchAlpha.push(0.25 + Math.random() * 0.2)
        benchSize.push(0.035)
        benchRand.push(Math.random())
      }
    }
    const benchGeo = track(new THREE.BufferGeometry())
    benchGeo.setAttribute('position', new THREE.Float32BufferAttribute(benchPts, 3))
    benchGeo.setAttribute('color', new THREE.Float32BufferAttribute(benchCol, 3))
    benchGeo.setAttribute('alpha', new THREE.Float32BufferAttribute(benchAlpha, 1))
    benchGeo.setAttribute('size', new THREE.Float32BufferAttribute(benchSize, 1))
    benchGeo.setAttribute('rand', new THREE.Float32BufferAttribute(benchRand, 1))
    const benchMat = track(pointsMaterial(dpr, 0.6))
    scene.add(new THREE.Points(benchGeo, benchMat))

    // ---------------------------------------------------------------- the Speaker
    const speakerPos = new THREE.Vector3(0, 1.35, -6.5)
    const orbMat = track(new THREE.MeshStandardMaterial({ color: SPEAKER.clone(), emissive: SPEAKER.clone(), emissiveIntensity: 0.4, roughness: 0.35 }))
    const orb = new THREE.Mesh(track(new THREE.IcosahedronGeometry(0.42, 5)), orbMat)
    orb.position.copy(speakerPos)
    scene.add(orb)
    const haloMat = track(new THREE.MeshBasicMaterial({ color: 0x0b7a47, transparent: true, opacity: 0.4 }))
    const halo = new THREE.Mesh(track(new THREE.TorusGeometry(0.85, 0.012, 8, 120)), haloMat)
    halo.position.copy(speakerPos)
    scene.add(halo)
    const halo2 = new THREE.Mesh(track(new THREE.TorusGeometry(1.25, 0.008, 8, 120)), haloMat)
    halo2.position.copy(speakerPos)
    halo2.rotation.x = Math.PI / 2.4
    scene.add(halo2)
    // Beam of light from above onto the Speaker (echoes the hero shot).
    const beamMat = track(new THREE.ShaderMaterial({
      transparent: true, depthWrite: false, side: THREE.DoubleSide,
      uniforms: { uColor: { value: new THREE.Color(0x0b7a47) } },
      vertexShader: `varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }`,
      fragmentShader: `uniform vec3 uColor; varying vec2 vUv; void main(){ float e = sin(vUv.x*3.14159);
        gl_FragColor = vec4(uColor, e * pow(1.0 - vUv.y, 0.8) * 0.07); }`,
    }))
    const beam = new THREE.Mesh(track(new THREE.CylinderGeometry(0.5, 1.6, 7, 48, 1, true)), beamMat)
    beam.position.set(speakerPos.x, speakerPos.y + 2.4, speakerPos.z)
    scene.add(beam)
    scene.add(new THREE.AmbientLight(0xffffff, 1.2))
    const sun = new THREE.DirectionalLight(0xffffff, 1.4)
    sun.position.set(2, 6, 4)
    scene.add(sun)

    // ---------------------------------------------------------------- arguments (comets)
    const COMETS = reduced ? 0 : 22
    const TRAIL = 18
    const cPos = new Float32Array(COMETS * TRAIL * 3)
    const cCol = new Float32Array(COMETS * TRAIL * 3)
    const cAlpha = new Float32Array(COMETS * TRAIL)
    const cSize = new Float32Array(COMETS * TRAIL)
    const cRand = new Float32Array(COMETS * TRAIL)
    const cGeo = track(new THREE.BufferGeometry())
    cGeo.setAttribute('position', new THREE.BufferAttribute(cPos, 3))
    cGeo.setAttribute('color', new THREE.BufferAttribute(cCol, 3))
    cGeo.setAttribute('alpha', new THREE.BufferAttribute(cAlpha, 1))
    cGeo.setAttribute('size', new THREE.BufferAttribute(cSize, 1))
    cGeo.setAttribute('rand', new THREE.BufferAttribute(cRand, 1))
    const cMat = track(pointsMaterial(dpr, 0))
    scene.add(new THREE.Points(cGeo, cMat))

    type Comet = { curve: THREE.QuadraticBezierCurve3; t: number; speed: number; side: 0 | 1; struckAt: number; alive: boolean }
    const comets: Comet[] = Array.from({ length: COMETS }, () => ({
      curve: new THREE.QuadraticBezierCurve3(), t: 0, speed: 0.3, side: 0, struckAt: 2, alive: false,
    }))
    let flash = 0
    let flashColor = SPEAKER.clone()
    const spawn = (c: Comet) => {
      const seat = seats[Math.floor(Math.random() * seats.length)]
      const start = seat.pos.clone()
      const mid = start.clone().lerp(speakerPos, 0.5).add(new THREE.Vector3((Math.random() - 0.5) * 2, 1.6 + Math.random() * 1.8, 0))
      c.curve.v0.copy(start)
      c.curve.v1.copy(mid)
      c.curve.v2.copy(speakerPos)
      c.t = 0
      c.speed = 0.22 + Math.random() * 0.18
      c.side = seat.side
      c.struckAt = Math.random() < 0.22 ? 0.35 + Math.random() * 0.35 : 2 // ~1 in 5 arguments has no evidence
      c.alive = true
    }
    comets.forEach((c, i) => {
      spawn(c)
      c.t = i / COMETS // stagger
    })

    // ---------------------------------------------------------------- sizing
    const resize = () => {
      const w = el.clientWidth
      const h = el.clientHeight
      if (!w || !h) return
      renderer.setSize(w, h, false)
      camera.aspect = w / h
      camera.updateProjectionMatrix()
    }
    resize()
    const ro = new ResizeObserver(resize)
    ro.observe(el)
    const mouse = { x: 0, y: 0, sx: 0, sy: 0 }
    const onMove = (e: PointerEvent) => {
      mouse.x = (e.clientX / window.innerWidth) * 2 - 1
      mouse.y = (e.clientY / window.innerHeight) * 2 - 1
    }
    window.addEventListener('pointermove', onMove, { passive: true })
    let visible = false
    const io = new IntersectionObserver(([e]) => (visible = e.isIntersecting), { threshold: 0 })
    io.observe(el)

    // ---------------------------------------------------------------- loop
    const clock = new THREE.Timer()
    const p = new THREE.Vector3()
    const col = new THREE.Color()
    let raf = 0
    const frame = () => {
      raf = requestAnimationFrame(frame)
      if (!visible) {
        clock.update()
        return
      }
      clock.update()
      const dt = Math.min(clock.getDelta(), 0.05)
      const t = clock.getElapsed()
      benchMat.uniforms.uTime.value = t

      comets.forEach((c, ci) => {
        c.t += dt * c.speed
        const struck = c.t > c.struckAt
        if (c.t >= 1 || (struck && c.t > c.struckAt + 0.35)) {
          if (!struck && c.t >= 1) {
            flash = 1
            flashColor = (c.side === 0 ? GOV : OPP).clone()
          }
          spawn(c)
        }
        const base = c.side === 0 ? GOV : OPP
        for (let k = 0; k < TRAIL; k++) {
          const tt = Math.max(0, c.t - k * 0.012)
          c.curve.getPoint(Math.min(tt, 1), p)
          const idx = ci * TRAIL + k
          cPos.set([p.x, p.y, p.z], idx * 3)
          const fade = struck ? Math.max(0, 1 - (c.t - c.struckAt) / 0.35) : 1
          col.copy(struck ? STRUCK : base)
          cCol.set([col.r, col.g, col.b], idx * 3)
          cAlpha[idx] = (1 - k / TRAIL) * fade * (tt > 0 ? 1 : 0)
          cSize[idx] = (k === 0 ? 0.22 : 0.13) * (1 - k / (TRAIL * 1.3))
        }
      })
      if (COMETS) {
        cGeo.attributes.position.needsUpdate = true
        cGeo.attributes.color.needsUpdate = true
        cGeo.attributes.alpha.needsUpdate = true
        cGeo.attributes.size.needsUpdate = true
      }

      flash *= Math.pow(0.04, dt)
      orbMat.emissive.copy(SPEAKER).lerp(flashColor, flash * 0.8)
      orbMat.emissiveIntensity = 0.4 + flash * 0.6
      orb.rotation.y += dt * 0.3
      halo.rotation.z += dt * 0.4
      halo2.rotation.z -= dt * 0.25
      const hs = 1 + flash * 0.25
      halo.scale.set(hs, hs, hs)

      mouse.sx += (mouse.x - mouse.sx) * 0.03
      mouse.sy += (mouse.y - mouse.sy) * 0.03
      camera.position.set(Math.sin(t * 0.06) * 1.2 + mouse.sx * 1.2, 3.4 - mouse.sy * 0.5, 8.5)
      camera.lookAt(0, 0.9, -3.2)
      renderer.render(scene, camera)
    }
    frame()

    return () => {
      cancelAnimationFrame(raf)
      ro.disconnect()
      io.disconnect()
      window.removeEventListener('pointermove', onMove)
      disposables.forEach((d) => d.dispose())
      renderer.dispose()
      renderer.domElement.remove()
    }
  }, [])

  if (failed) return <div className={className} />
  return <div ref={mount} className={className} />
}
