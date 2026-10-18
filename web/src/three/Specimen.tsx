/**
 * Specimen: one fixed particle "engraving" behind the landing page that morphs as you scroll (after GreenLight's Journey).
 * Ink dots on paper; colour only where it means something.
 *
 *   0 question     a double helix: healthcare research starts from a question
 *   1 discovery    a sphere of sources with scouts orbiting it, searching in parallel
 *   2 ask papers   a fanned stack of pages; the cited lines turn green
 *   3 credibility  a histogram of trust scores: high bars green, a retracted paper red at zero
 *   4 graph        clusters of papers joined by citations, with an empty space between them
 *   5 verdict      a traffic light; the green lamp is lit
 *
 * Sections declare their stage with data-stage="n"; the scroll position interpolates between them. All morphing
 * runs in the vertex shader (one draw call). An element with data-specimen-end fades the specimen out behind
 * the reference sections that follow.
 */
import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'

const STAGES = 6
const TAU = Math.PI * 2

let seed = 2026
const rnd = () => ((seed = (seed * 16807) % 2147483647) - 1) / 2147483646
const gauss = () => {
  let u = 0, v = 0
  while (!u) u = rnd()
  while (!v) v = rnd()
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(TAU * v)
}

// ---------------------------------------------------------------- shapes: each fills n xyz and a tag per point

function helix(n: number, tag: Float32Array) {
  const out = new Float32Array(n * 3)
  const R = 0.82, H = 4.4, TURNS = 2.3, RUNGS = 30
  const at = (t: number, strand: number): [number, number, number] => {
    const a = t * TAU * TURNS + strand * Math.PI
    return [Math.cos(a) * R, (t - 0.5) * H, Math.sin(a) * R]
  }
  for (let i = 0; i < n; i++) {
    const k = rnd()
    let p: [number, number, number]
    if (k < 0.6) {
      p = at(rnd(), rnd() < 0.5 ? 0 : 1)
      p = [p[0] + gauss() * 0.025, p[1] + gauss() * 0.01, p[2] + gauss() * 0.025]
      tag[i] = 0
    } else if (k < 0.86) {
      const r = Math.floor(rnd() * RUNGS)
      const t = (r + 0.5) / RUNGS
      const a = at(t, 0), b = at(t, 1), u = rnd()
      p = [a[0] + (b[0] - a[0]) * u, a[1] + gauss() * 0.008, a[2] + (b[2] - a[2]) * u]
      tag[i] = r % 7 === 3 ? 3 : 1
    } else {
      const a = rnd() * TAU, r = 1.15 + Math.abs(gauss()) * 0.55
      p = [Math.cos(a) * r, (rnd() - 0.5) * H * 1.05, Math.sin(a) * r]
      tag[i] = 2
    }
    out.set(p, i * 3)
  }
  return out
}

function sources(n: number, tag: Float32Array) {
  const out = new Float32Array(n * 3)
  const R = 1.75
  for (let i = 0; i < n; i++) {
    const k = rnd()
    let x: number, y: number, z: number
    tag[i] = 0
    if (k < 0.5) {
      const phi = Math.acos(1 - 2 * ((i + 0.5) / n))
      const th = Math.PI * (1 + Math.sqrt(5)) * i
      x = Math.cos(th) * Math.sin(phi) * R; y = Math.cos(phi) * R; z = Math.sin(th) * Math.sin(phi) * R
    } else if (k < 0.78) {
      const u = rnd() * TAU
      if (rnd() < 0.5) {
        const m = (Math.floor(rnd() * 12) / 12) * TAU
        x = Math.cos(m) * Math.sin(u) * R; y = Math.cos(u) * R; z = Math.sin(m) * Math.sin(u) * R
      } else {
        const lat = (Math.floor(rnd() * 9) / 8 - 0.5) * Math.PI * 0.92
        x = Math.cos(u) * Math.cos(lat) * R; y = Math.sin(lat) * R; z = Math.sin(u) * Math.cos(lat) * R
      }
    } else {
      // scouts: four orbits, each a dense comet with a fading tail
      const ring = Math.floor(rnd() * 4)
      const head = ring * 1.7
      const u = head - Math.pow(rnd(), 1.8) * 2.2
      const rr = R * (1.3 + ring * 0.08)
      const tilt = 0.35 + ring * 0.6
      x = Math.cos(u) * rr; y = Math.sin(u) * rr * Math.sin(tilt) * 0.55; z = Math.sin(u) * rr * Math.cos(tilt)
      tag[i] = 1
    }
    out.set([x, y, z], i * 3)
  }
  return out
}

function pages(n: number, tag: Float32Array) {
  // One readable front page with its cited lines in green; three fainter sheets stacked behind it.
  const out = new Float32Array(n * 3)
  const sheets = 4, w = 2.0, h = 2.7, LINES = 17
  for (let i = 0; i < n; i++) {
    const s = rnd() < 0.55 ? 0 : 1 + Math.floor(rnd() * (sheets - 1))
    let x: number, y: number
    if (rnd() < 0.14) {
      const e = rnd() * 2 * (w + h)
      if (e < w) { x = e - w / 2; y = h / 2 } else if (e < 2 * w) { x = e - w - w / 2; y = -h / 2 } else if (e < 2 * w + h) { x = -w / 2; y = e - 2 * w - h / 2 } else { x = w / 2; y = e - 2 * w - h - h / 2 }
      tag[i] = s === 0 ? 0 : 2
    } else {
      let line = Math.floor(rnd() * LINES)
      if (line === 0) line = rnd() < 0.5 ? 1 : 2 // title row is short and bold
      const para = line === 6 || line === 12 // paragraph breaks
      const len = line < 3 ? 0.5 : para ? 0.35 : 0.62 + ((line * 7919 + s * 31) % 10) / 28
      x = -w / 2 + 0.18 + rnd() * (w - 0.36) * len
      y = h / 2 - 0.3 - line * 0.135
      tag[i] = s > 0 ? 2 : line === 8 || line === 9 || line === 14 ? 1 : 0
    }
    out.set([x + s * 0.2, y + s * 0.2 + gauss() * 0.004, -s * 0.28 + gauss() * 0.004], i * 3)
  }
  return out
}

// Illustrative distribution (shape only, no data): a few weak papers, a broad middle, a strong tail, one retraction.
const BARS = [0.05, 0.12, 0.2, 0.3, 0.42, 0.55, 0.7, 0.82, 0.9, 0.86, 0.72, 0.6, 0.48, 0.36, 0.24, 0.14]
function histogram(n: number, tag: Float32Array) {
  const out = new Float32Array(n * 3)
  const B = BARS.length, x0 = -2.1, step = 4.2 / (B - 1), bw = 0.17, base = -1.5
  for (let i = 0; i < n; i++) {
    if (rnd() < 0.07) {
      out.set([x0 - 0.2 + rnd() * 4.6, base - 0.06, (rnd() - 0.5) * 0.3], i * 3) // axis
      tag[i] = 0
      continue
    }
    const b = Math.floor(rnd() * B)
    const hgt = BARS[b] * 3.1
    out.set([x0 + b * step + (rnd() - 0.5) * bw, base + rnd() * hgt, (rnd() - 0.5) * bw], i * 3)
    tag[i] = b === 0 ? 3 : b >= 11 ? 2 : 1
  }
  return out
}

function network(n: number, tag: Float32Array) {
  const out = new Float32Array(n * 3)
  // six clusters with open space between them: the under-explored gaps
  const centers = [[-1.4, 0.9, 0.2], [-1.6, -0.7, -0.3], [-0.2, 1.5, -0.4], [0.1, -1.4, 0.4], [0.2, 0.1, 0.9], [1.7, -0.2, -0.8]]
  const nodes: number[][] = []
  const cl: number[] = []
  for (let k = 0; k < 72; k++) {
    const c = k % centers.length
    const cc = centers[c]
    nodes.push([cc[0] + gauss() * 0.32, cc[1] + gauss() * 0.32, cc[2] + gauss() * 0.32])
    cl.push(c)
  }
  const edges: [number, number][] = []
  for (let a = 0; a < nodes.length; a++) {
    const d = nodes.map((p, b) => [b, Math.hypot(p[0] - nodes[a][0], p[1] - nodes[a][1], p[2] - nodes[a][2])] as [number, number])
      .filter(([b]) => b !== a).sort((u, v) => u[1] - v[1])
    edges.push([a, d[0][0]], [a, d[1][0]])
    if (a % 9 === 0) edges.push([a, d[6 + (a % 5)][0]]) // a few long citations across clusters
  }
  for (let i = 0; i < n; i++) {
    if (rnd() < 0.5) {
      const k = Math.floor(rnd() * nodes.length), p = nodes[k], r = 0.045 + (k % 4) * 0.012
      out.set([p[0] + gauss() * r, p[1] + gauss() * r, p[2] + gauss() * r], i * 3)
      tag[i] = cl[k] === 4 ? 2 : 0
    } else {
      const [a, b] = edges[Math.floor(rnd() * edges.length)], u = rnd()
      const p = nodes[a], q = nodes[b]
      out.set([p[0] + (q[0] - p[0]) * u, p[1] + (q[1] - p[1]) * u, p[2] + (q[2] - p[2]) * u], i * 3)
      tag[i] = 1
    }
  }
  return out
}

function trafficLight(n: number, tag: Float32Array) {
  const out = new Float32Array(n * 3)
  const W = 1.5, H = 3.9, rad = 0.7, lamps = [1.25, 0, -1.25], lr = 0.5
  // rounded-rect perimeter, parameterised by arc length
  const straightW = W - 2 * rad, straightH = H - 2 * rad, arc = (Math.PI / 2) * rad
  const per = 2 * straightW + 2 * straightH + 4 * arc
  const edge = (s: number): [number, number] => {
    const segs: [number, (u: number) => [number, number]][] = [
      [straightW, (u) => [-straightW / 2 + u, H / 2]],
      [arc, (u) => { const a = Math.PI / 2 - u / rad; return [straightW / 2 + Math.cos(a) * rad, straightH / 2 + Math.sin(a) * rad] }],
      [straightH, (u) => [W / 2, straightH / 2 - u]],
      [arc, (u) => { const a = -u / rad; return [straightW / 2 + Math.cos(a) * rad, -straightH / 2 + Math.sin(a) * rad] }],
      [straightW, (u) => [straightW / 2 - u, -H / 2]],
      [arc, (u) => { const a = -Math.PI / 2 - u / rad; return [-straightW / 2 + Math.cos(a) * rad, -straightH / 2 + Math.sin(a) * rad] }],
      [straightH, (u) => [-W / 2, -straightH / 2 + u]],
      [arc, (u) => { const a = Math.PI - u / rad; return [-straightW / 2 + Math.cos(a) * rad, straightH / 2 + Math.sin(a) * rad] }],
    ]
    for (const [len, f] of segs) { if (s <= len) return f(s); s -= len }
    return [0, 0]
  }
  for (let i = 0; i < n; i++) {
    const k = rnd()
    if (k < 0.24) {
      const [x, y] = edge(rnd() * per)
      out.set([x, y, rnd() < 0.5 ? -0.12 : 0.12], i * 3)
      tag[i] = 0
    } else if (k < 0.74) {
      const lamp = k < 0.36 ? 0 : k < 0.48 ? 1 : 2
      const r = Math.sqrt(rnd()) * lr, a = rnd() * TAU
      out.set([Math.cos(a) * r, lamps[lamp] + Math.sin(a) * r, gauss() * 0.02], i * 3)
      tag[i] = lamp + 1
    } else {
      const a = (Math.floor(rnd() * 16) / 16) * TAU + gauss() * 0.02
      const r = lr + 0.18 + Math.pow(rnd(), 1.6) * 0.9
      out.set([Math.cos(a) * r, lamps[2] + Math.sin(a) * r, gauss() * 0.03], i * 3)
      tag[i] = 4
    }
  }
  return out
}

// ---------------------------------------------------------------- shaders
const VERT = /* glsl */ `
  uniform float uProgress; uniform float uTime; uniform float uIntro; uniform float uPixelRatio;
  uniform vec3 uMouse; uniform float uMouseOn; uniform float uSize; uniform float uMotion;
  attribute vec3 aT0; attribute vec3 aT1; attribute vec3 aT2; attribute vec3 aT3; attribute vec3 aT4; attribute vec3 aT5;
  attribute vec3 aTagA; attribute vec3 aTagB; attribute vec4 aRand;
  varying vec3 vColor; varying float vAlpha;

  vec3 shapeAt(float i) {
    if (i < 0.5) return aT0; if (i < 1.5) return aT1; if (i < 2.5) return aT2;
    if (i < 3.5) return aT3; if (i < 4.5) return aT4; return aT5;
  }
  float tagAt(float i) {
    if (i < 0.5) return aTagA.x; if (i < 1.5) return aTagA.y; if (i < 2.5) return aTagA.z;
    if (i < 3.5) return aTagB.x; if (i < 4.5) return aTagB.y; return aTagB.z;
  }

  const vec3 INK   = vec3(0.055, 0.165, 0.129);
  const vec3 GREEN = vec3(0.043, 0.478, 0.278);
  const vec3 TEAL  = vec3(0.082, 0.369, 0.459);
  const vec3 AMBER = vec3(0.659, 0.373, 0.0);
  const vec3 RED   = vec3(0.706, 0.137, 0.094);

  // colour + alpha multiplier for a point's role in a stage
  vec4 look(float i, float g) {
    if (i < 0.5) return g < 0.5 ? vec4(INK, 1.0) : g < 1.5 ? vec4(TEAL, 0.75) : g < 2.5 ? vec4(INK, 0.22) : vec4(GREEN, 1.1);
    if (i < 1.5) return g < 0.5 ? vec4(INK, 0.55) : vec4(GREEN, 1.1);
    if (i < 2.5) return g < 0.5 ? vec4(INK, 0.8) : g < 1.5 ? vec4(GREEN, 1.4) : vec4(INK, 0.22);
    if (i < 3.5) return g < 0.5 ? vec4(INK, 0.35) : g < 1.5 ? vec4(INK, 0.8) : g < 2.5 ? vec4(GREEN, 1.0) : vec4(RED, 1.2);
    if (i < 4.5) return g < 0.5 ? vec4(INK, 0.95) : g < 1.5 ? vec4(TEAL, 0.32) : vec4(GREEN, 1.05);
    return g < 0.5 ? vec4(INK, 0.8) : g < 1.5 ? vec4(RED, 0.22) : g < 2.5 ? vec4(AMBER, 0.22) : g < 3.5 ? vec4(GREEN, 1.1) : vec4(GREEN, 0.45);
  }

  void main() {
    float p = clamp(uProgress, 0.0, 5.0);
    float i0 = floor(p);
    float i1 = min(i0 + 1.0, 5.0);
    float f = p - i0;
    float delay = aRand.x * 0.4;
    float t = smoothstep(delay, delay + 0.6, f);
    t = t * t * (3.0 - 2.0 * t);
    vec3 a = shapeAt(i0);
    vec3 b = shapeAt(i1);
    vec3 pos = mix(a, b, t);

    float transit = sin(t * 3.14159) * uMotion;
    pos += transit * vec3(sin(aRand.y * 6.283 + uTime * 0.9), cos(aRand.z * 6.283 + uTime * 0.7), sin(aRand.w * 6.283 - uTime)) * 0.55;
    pos += uMotion * 0.018 * vec3(sin(uTime * 0.6 + aRand.y * 40.0), cos(uTime * 0.5 + aRand.z * 40.0), sin(uTime * 0.7 + aRand.w * 40.0));
    float intro = smoothstep(aRand.x * 0.5, aRand.x * 0.5 + 0.5, uIntro);
    pos *= mix(0.06, 1.0, intro);

    vec3 dm = pos - uMouse;
    pos += normalize(dm + 1e-5) * max(0.0, 0.7 - length(dm)) * 0.5 * uMouseOn;

    vec4 la = look(i0, tagAt(i0));
    vec4 lb = look(i1, tagAt(i1));
    vec4 l = mix(la, lb, t);
    vColor = l.rgb;
    vAlpha = (0.42 + aRand.w * 0.45) * l.a * intro;

    vec4 mv = modelViewMatrix * vec4(pos, 1.0);
    vAlpha *= clamp(1.25 - (-mv.z - 6.0) * 0.18, 0.45, 1.0); // farther dots are lighter: depth without fog
    float sz = uSize * (0.6 + aRand.w * 0.8);
    gl_PointSize = sz * uPixelRatio * (300.0 / -mv.z);
    gl_Position = projectionMatrix * mv;
  }`

const FRAG = /* glsl */ `
  varying vec3 vColor; varying float vAlpha;
  void main() {
    float d = length(gl_PointCoord - 0.5);
    float a = smoothstep(0.5, 0.32, d); // crisp ink dot, not a glow
    gl_FragColor = vec4(vColor, a * min(vAlpha, 1.0));
  }`

const PAPER = 0xf6f8f7

export default function Specimen({ className }: { className?: string }) {
  const mount = useRef<HTMLDivElement>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    const el = mount.current
    if (!el) return
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const small = window.innerWidth < 768
    let renderer: THREE.WebGLRenderer
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' })
    } catch {
      setFailed(true)
      return
    }
    const dpr = Math.min(window.devicePixelRatio, small ? 1.5 : 2)
    renderer.setPixelRatio(dpr)
    renderer.setClearColor(PAPER, 1)
    Object.assign(renderer.domElement.style, { display: 'block', width: '100%', height: '100%' })
    el.appendChild(renderer.domElement)

    const scene = new THREE.Scene()
    const camera = new THREE.PerspectiveCamera(40, 1, 0.1, 100)
    camera.position.set(0, 0, 8.4)

    seed = 2026
    const N = small ? 9000 : 18000
    const tags = Array.from({ length: STAGES }, () => new Float32Array(N))
    const shapes = [helix(N, tags[0]), sources(N, tags[1]), pages(N, tags[2]), histogram(N, tags[3]), network(N, tags[4]), trafficLight(N, tags[5])]
    const rand = new Float32Array(N * 4)
    for (let i = 0; i < N * 4; i++) rand[i] = rnd()
    const tagA = new Float32Array(N * 3), tagB = new Float32Array(N * 3)
    for (let i = 0; i < N; i++) {
      tagA.set([tags[0][i], tags[1][i], tags[2][i]], i * 3)
      tagB.set([tags[3][i], tags[4][i], tags[5][i]], i * 3)
    }
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.BufferAttribute(shapes[0], 3))
    shapes.forEach((s, i) => geo.setAttribute(`aT${i}`, new THREE.BufferAttribute(s, 3)))
    geo.setAttribute('aTagA', new THREE.BufferAttribute(tagA, 3))
    geo.setAttribute('aTagB', new THREE.BufferAttribute(tagB, 3))
    geo.setAttribute('aRand', new THREE.BufferAttribute(rand, 4))
    geo.boundingSphere = new THREE.Sphere(new THREE.Vector3(), 10)

    const mat = new THREE.ShaderMaterial({
      vertexShader: VERT, fragmentShader: FRAG, transparent: true, depthWrite: false, blending: THREE.NormalBlending,
      uniforms: {
        uProgress: { value: 0 }, uTime: { value: 0 }, uIntro: { value: reduced ? 1 : 0 }, uPixelRatio: { value: dpr },
        uMouse: { value: new THREE.Vector3(99, 99, 99) }, uMouseOn: { value: 0 }, uSize: { value: small ? 0.055 : 0.047 },
        uMotion: { value: reduced ? 0 : 1 },
      },
    })
    const cloud = new THREE.Points(geo, mat)
    const rig = new THREE.Group()
    rig.add(cloud)
    scene.add(rig)
    const RIGHT = 2.3
    rig.position.x = window.innerWidth >= 1024 ? RIGHT : 0
    const TILT = [0.12, 0.22, 0.0, 0.1, 0.18, 0.0]
    const CAM_Z = [8.6, 7.6, 7.2, 8.2, 7.8, 8.8]
    const lerp = (arr: number[], p: number) => {
      const i = Math.floor(p)
      return arr[i] + (arr[Math.min(i + 1, arr.length - 1)] - arr[i]) * (p - i)
    }

    let wide = window.innerWidth >= 1024
    const resize = () => {
      const w = el.clientWidth, h = el.clientHeight
      if (!w || !h) return
      wide = w >= 1024
      renderer.setSize(w, h, false)
      camera.aspect = w / h
      camera.updateProjectionMatrix()
    }
    resize()
    const ro = new ResizeObserver(resize)
    ro.observe(el)

    let stops: { stage: number; y: number }[] = []
    let endY = Infinity
    const measure = () => {
      stops = [...document.querySelectorAll<HTMLElement>('[data-stage]')]
        .map((e) => ({ stage: Number(e.dataset.stage), y: e.getBoundingClientRect().top + window.scrollY + e.offsetHeight / 2 }))
        .sort((a, b) => a.y - b.y)
      const end = document.querySelector<HTMLElement>('[data-specimen-end]')
      endY = end ? end.getBoundingClientRect().top + window.scrollY : Infinity
    }
    measure()
    const remeasure = setInterval(measure, 1200)
    window.addEventListener('resize', measure)
    const scrollTarget = () => {
      if (!stops.length) return 0
      const c = window.scrollY + window.innerHeight / 2
      if (c <= stops[0].y) return stops[0].stage
      for (let i = 0; i < stops.length - 1; i++) {
        if (c < stops[i + 1].y) return stops[i].stage + (stops[i + 1].stage - stops[i].stage) * ((c - stops[i].y) / (stops[i + 1].y - stops[i].y))
      }
      return stops[stops.length - 1].stage
    }

    const ndc = new THREE.Vector2(9, 9)
    let mouseOn = 0
    const onMove = (e: PointerEvent) => {
      ndc.set((e.clientX / window.innerWidth) * 2 - 1, -(e.clientY / window.innerHeight) * 2 + 1)
      mouseOn = e.pointerType === 'mouse' ? 1 : 0
    }
    const onLeave = () => (mouseOn = 0)
    window.addEventListener('pointermove', onMove, { passive: true })
    document.addEventListener('pointerleave', onLeave)
    const raycaster = new THREE.Raycaster()
    const plane = new THREE.Plane(new THREE.Vector3(0, 0, 1), 0)
    const hit = new THREE.Vector3()
    const inv = new THREE.Matrix4()

    const clock = new THREE.Timer()
    let progress = 0
    let fade = 1
    let raf = 0
    const frame = () => {
      raf = requestAnimationFrame(frame)
      if (document.hidden) return
      clock.update()
      const dt = Math.min(clock.getDelta(), 0.05)
      const t = clock.getElapsed()
      const goal = Math.min(STAGES - 1, Math.max(0, scrollTarget()))
      progress += (goal - progress) * (1 - Math.exp(-dt * 3.4))
      mat.uniforms.uProgress.value = progress
      mat.uniforms.uTime.value = t
      if (!reduced) mat.uniforms.uIntro.value = Math.min(1, t * 0.6)

      // Fade out behind the reference sections.
      const past = (window.scrollY + window.innerHeight * 0.75 - endY) / (window.innerHeight * 0.5)
      const goalFade = Math.max(0, Math.min(1, 1 - past))
      fade += (goalFade - fade) * 0.12
      el.style.opacity = String(fade)
      if (fade < 0.01) return

      rig.position.x += ((wide ? RIGHT : 0) - rig.position.x) * 0.06
      rig.position.y = Math.sin(t * 0.35) * 0.05 * (reduced ? 0 : 1)
      rig.rotation.x = lerp(TILT, progress) + ndc.y * 0.04 * mouseOn
      // Helix, sources and graph spin; pages, histogram and traffic light sway so they stay readable.
      const near = Math.round(progress)
      if (near === 2 || near === 3 || near === 5) {
        cloud.rotation.y = ((((cloud.rotation.y + Math.PI) % TAU) + TAU) % TAU) - Math.PI
        cloud.rotation.y += (Math.sin(t * 0.25) * (near === 5 ? 0.2 : 0.3) - cloud.rotation.y) * 0.035
      } else cloud.rotation.y += dt * 0.14 * (reduced ? 0 : 1)

      camera.position.z += (lerp(CAM_Z, progress) - camera.position.z) * 0.05
      camera.position.x += (ndc.x * 0.3 * mouseOn - camera.position.x) * 0.04
      camera.position.y += (ndc.y * 0.18 * mouseOn - camera.position.y) * 0.04
      camera.lookAt(0, 0, 0)
      rig.updateMatrixWorld()

      raycaster.setFromCamera(ndc, camera)
      if (raycaster.ray.intersectPlane(plane, hit)) {
        inv.copy(cloud.matrixWorld).invert()
        mat.uniforms.uMouse.value.copy(hit).applyMatrix4(inv)
      }
      mat.uniforms.uMouseOn.value += (mouseOn - mat.uniforms.uMouseOn.value) * 0.08
      renderer.render(scene, camera)
    }
    frame()

    return () => {
      cancelAnimationFrame(raf)
      clearInterval(remeasure)
      ro.disconnect()
      window.removeEventListener('resize', measure)
      window.removeEventListener('pointermove', onMove)
      document.removeEventListener('pointerleave', onLeave)
      geo.dispose()
      mat.dispose()
      renderer.dispose()
      renderer.domElement.remove()
    }
  }, [])

  if (failed) return <div className={className} />
  return <div ref={mount} className={className} aria-hidden />
}
