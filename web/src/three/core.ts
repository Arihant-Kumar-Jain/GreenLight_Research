/**
 * Shared WebGL plumbing for the scenes: renderer (opaque, on the light surface colour), optional bloom/lens post chain,
 * DPR cap, resize, off-screen pause, reduced-motion flag and one-call disposal. Scenes only build objects and an
 * `update(t, dt)` function.
 */
import * as THREE from 'three'
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js'
import { OutputPass } from 'three/examples/jsm/postprocessing/OutputPass.js'
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js'
import { ShaderPass } from 'three/examples/jsm/postprocessing/ShaderPass.js'
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass.js'
import { LensShader } from './glass'

// Light theme (index.css): ink on paper, colour carries meaning.
export const SURFACE = 0xffffff
export const INK = new THREE.Color(0x0e2a21)
export const GO = new THREE.Color(0x0b7a47)
export const WAIT = new THREE.Color(0xa85f00)
export const STOP = new THREE.Color(0xb42318)
export const INFO = new THREE.Color(0x155e75)
export const MUTED = new THREE.Color(0x9aa8a1)

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
    float a = smoothstep(0.5, 0.0, d);
    gl_FragColor = vec4(vColor, smoothstep(0.0, 0.6, a) * vAlpha);
  }`

export function pointsMaterial(dpr: number, twinkle: number) {
  return new THREE.ShaderMaterial({
    vertexShader: POINT_VERT, fragmentShader: POINT_FRAG, transparent: true, depthWrite: false,
    blending: THREE.NormalBlending,
    uniforms: { uTime: { value: 0 }, uPixelRatio: { value: dpr }, uTwinkle: { value: twinkle } },
  })
}

/** Point cloud with per-point color/alpha/size/rand attributes. */
export function pointCloud(n: number) {
  const geo = new THREE.BufferGeometry()
  const pos = new Float32Array(n * 3), col = new Float32Array(n * 3)
  const alpha = new Float32Array(n), size = new Float32Array(n), rand = new Float32Array(n)
  geo.setAttribute('position', new THREE.BufferAttribute(pos, 3))
  geo.setAttribute('color', new THREE.BufferAttribute(col, 3))
  geo.setAttribute('alpha', new THREE.BufferAttribute(alpha, 1))
  geo.setAttribute('size', new THREE.BufferAttribute(size, 1))
  geo.setAttribute('rand', new THREE.BufferAttribute(rand, 1))
  return { geo, pos, col, alpha, size, rand }
}

export type Stage = {
  renderer: THREE.WebGLRenderer; scene: THREE.Scene; camera: THREE.PerspectiveCamera; dpr: number; reduced: boolean
  track: <T extends { dispose: () => void }>(o: T) => T
  start: (update: (t: number, dt: number) => void, beforeRender?: () => void) => void
  dispose: () => void
}

export function createStage(el: HTMLElement, opts: { fov?: number; bloom?: [number, number, number]; lens?: boolean } = {}): Stage | null {
  let renderer: THREE.WebGLRenderer
  try {
    renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' })
  } catch {
    return null
  }
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  const dpr = Math.min(window.devicePixelRatio, 1.75)
  renderer.setPixelRatio(dpr)
  renderer.setClearColor(SURFACE, 1)
  renderer.outputColorSpace = THREE.SRGBColorSpace
  Object.assign(renderer.domElement.style, { display: 'block', width: '100%', height: '100%' })
  el.appendChild(renderer.domElement)

  const scene = new THREE.Scene()
  const camera = new THREE.PerspectiveCamera(opts.fov ?? 40, 1, 0.1, 200)
  const disposables: { dispose: () => void }[] = []
  const track = <T extends { dispose: () => void }>(o: T) => (disposables.push(o), o)

  // Post effects only when asked for: on a light surface, bloom washes colours out.
  let composer: EffectComposer | null = null
  let bloom: UnrealBloomPass | null = null
  if (opts.bloom || opts.lens) {
    composer = new EffectComposer(renderer)
    composer.addPass(new RenderPass(scene, camera))
    if (opts.bloom) composer.addPass((bloom = new UnrealBloomPass(new THREE.Vector2(800, 600), ...opts.bloom)))
    if (opts.lens) composer.addPass(new ShaderPass(LensShader))
    composer.addPass(new OutputPass())
  }
  const render = () => (composer ? composer.render() : renderer.render(scene, camera))

  const resize = () => {
    const w = el.clientWidth, h = el.clientHeight
    if (!w || !h) return
    renderer.setSize(w, h, false)
    composer?.setSize(w, h)
    bloom?.setSize(w, h)
    camera.aspect = w / h
    camera.updateProjectionMatrix()
  }
  resize()
  const ro = new ResizeObserver(resize)
  ro.observe(el)
  let visible = true
  const io = new IntersectionObserver(([e]) => (visible = e.isIntersecting), { threshold: 0 })
  io.observe(el)

  let raf = 0
  const timer = new THREE.Timer()
  return {
    renderer, scene, camera, dpr, reduced, track,
    start(update, beforeRender) {
      const frame = () => {
        raf = requestAnimationFrame(frame)
        timer.update()
        if (!visible || document.hidden) return
        const dt = Math.min(timer.getDelta(), 0.05)
        update(timer.getElapsed(), reduced ? 0 : dt)
        beforeRender?.()
        render()
      }
      frame()
    },
    dispose() {
      cancelAnimationFrame(raf)
      ro.disconnect()
      io.disconnect()
      disposables.forEach((d) => d.dispose())
      composer?.dispose()
      renderer.dispose()
      renderer.domElement.remove()
    },
  }
}
