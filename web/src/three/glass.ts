/**
 * Liquid glass: a noise-displaced sphere that refracts whatever was rendered behind it.
 * Screen-space refraction from a render target (the scene without the glass), RGB dispersion,
 * fresnel rim, thin-film iridescence and a sharp specular. Shared by the landing Journey and the
 * workspace verdict orb. Also: a lens pass (chromatic aberration + vignette).
 */
import * as THREE from 'three'

// Ashima / Stefan Gustavson 3D simplex noise.
const NOISE = /* glsl */ `
vec3 mod289(vec3 x){return x-floor(x*(1.0/289.0))*289.0;}
vec4 mod289(vec4 x){return x-floor(x*(1.0/289.0))*289.0;}
vec4 permute(vec4 x){return mod289(((x*34.0)+1.0)*x);}
vec4 taylorInvSqrt(vec4 r){return 1.79284291400159-0.85373472095314*r;}
float snoise(vec3 v){
  const vec2 C=vec2(1.0/6.0,1.0/3.0); const vec4 D=vec4(0.0,0.5,1.0,2.0);
  vec3 i=floor(v+dot(v,C.yyy)); vec3 x0=v-i+dot(i,C.xxx);
  vec3 g=step(x0.yzx,x0.xyz); vec3 l=1.0-g; vec3 i1=min(g.xyz,l.zxy); vec3 i2=max(g.xyz,l.zxy);
  vec3 x1=x0-i1+C.xxx; vec3 x2=x0-i2+C.yyy; vec3 x3=x0-D.yyy;
  i=mod289(i);
  vec4 p=permute(permute(permute(i.z+vec4(0.0,i1.z,i2.z,1.0))+i.y+vec4(0.0,i1.y,i2.y,1.0))+i.x+vec4(0.0,i1.x,i2.x,1.0));
  float n_=0.142857142857; vec3 ns=n_*D.wyz-D.xzx;
  vec4 j=p-49.0*floor(p*ns.z*ns.z); vec4 x_=floor(j*ns.z); vec4 y_=floor(j-7.0*x_);
  vec4 x=x_*ns.x+ns.yyyy; vec4 y=y_*ns.x+ns.yyyy; vec4 h=1.0-abs(x)-abs(y);
  vec4 b0=vec4(x.xy,y.xy); vec4 b1=vec4(x.zw,y.zw);
  vec4 s0=floor(b0)*2.0+1.0; vec4 s1=floor(b1)*2.0+1.0; vec4 sh=-step(h,vec4(0.0));
  vec4 a0=b0.xzyw+s0.xzyw*sh.xxyy; vec4 a1=b1.xzyw+s1.xzyw*sh.zzww;
  vec3 p0=vec3(a0.xy,h.x); vec3 p1=vec3(a0.zw,h.y); vec3 p2=vec3(a1.xy,h.z); vec3 p3=vec3(a1.zw,h.w);
  vec4 norm=taylorInvSqrt(vec4(dot(p0,p0),dot(p1,p1),dot(p2,p2),dot(p3,p3)));
  p0*=norm.x; p1*=norm.y; p2*=norm.z; p3*=norm.w;
  vec4 m=max(0.6-vec4(dot(x0,x0),dot(x1,x1),dot(x2,x2),dot(x3,x3)),0.0); m=m*m;
  return 42.0*dot(m*m,vec4(dot(p0,x0),dot(p1,x1),dot(p2,x2),dot(p3,x3)));
}`

const GLASS_VERT = /* glsl */ `
uniform float uTime; uniform float uWobble; uniform float uFreq;
varying vec3 vNormalV; varying vec3 vViewPos;
${NOISE}
vec3 warp(vec3 p){
  vec3 n = normalize(p);
  float d = snoise(n * uFreq + vec3(uTime * 0.22, uTime * 0.16, -uTime * 0.19)) * 0.82
          + snoise(n * uFreq * 1.9 - uTime * 0.28) * 0.18;
  return n * (1.0 + d * uWobble);
}
void main(){
  vec3 n = normalize(position);
  vec3 t = normalize(cross(n, abs(n.y) > 0.99 ? vec3(1.0, 0.0, 0.0) : vec3(0.0, 1.0, 0.0)));
  vec3 b = normalize(cross(n, t));
  float e = 0.012;
  vec3 p0 = warp(n);
  vec3 p1 = warp(normalize(n + t * e));
  vec3 p2 = warp(normalize(n + b * e));
  vec3 dn = normalize(cross(p1 - p0, p2 - p0));
  if (dot(dn, n) < 0.0) dn = -dn;
  vec4 mv = modelViewMatrix * vec4(p0, 1.0);
  vViewPos = mv.xyz;
  vNormalV = normalize(normalMatrix * dn);
  gl_Position = projectionMatrix * mv;
}`

const GLASS_FRAG = /* glsl */ `
uniform sampler2D uScene; uniform vec2 uRes; uniform vec3 uTint; uniform float uTime;
uniform float uRefract; uniform float uGlow;
varying vec3 vNormalV; varying vec3 vViewPos;
void main(){
  vec3 N = normalize(vNormalV);
  vec3 V = normalize(-vViewPos);
  float ndv = max(dot(N, V), 0.0);
  float fres = pow(1.0 - ndv, 2.4);
  vec2 uv = gl_FragCoord.xy / uRes;
  vec2 off = N.xy * uRefract * (0.6 + fres);
  vec3 refr = vec3(
    texture2D(uScene, uv - off * 0.92).r,
    texture2D(uScene, uv - off * 1.00).g,
    texture2D(uScene, uv - off * 1.10).b);
  // a second, stronger-bent sample so the particles behind read as "inside" the glass
  refr += texture2D(uScene, uv - off * 1.6).rgb * 0.25;
  vec3 L1 = normalize(vec3(-0.5, 0.8, 0.6));
  vec3 L2 = normalize(vec3(0.7, -0.2, 0.5));
  float spec = pow(max(dot(reflect(-L1, N), V), 0.0), 90.0) * 1.8 + pow(max(dot(reflect(-L2, N), V), 0.0), 40.0) * 0.35;
  vec3 irid = 0.5 + 0.5 * cos(6.2831 * (fres * 1.4 + uTime * 0.05 + vec3(0.0, 0.33, 0.67)));
  vec3 col = refr * mix(vec3(1.0), uTint, 0.1) * 1.08;
  col += mix(vec3(0.85, 1.0, 0.92), uTint, 0.55) * fres * (0.38 + uGlow * 0.5);
  col += irid * fres * 0.18;
  col += spec;
  col += uTint * 0.025 * uGlow;
  gl_FragColor = vec4(col, 1.0);
}`

export function createGlass(opts: { tint?: number; wobble?: number; freq?: number; refract?: number; detail?: number } = {}) {
  const material = new THREE.ShaderMaterial({
    vertexShader: GLASS_VERT,
    fragmentShader: GLASS_FRAG,
    uniforms: {
      uScene: { value: null },
      uRes: { value: new THREE.Vector2(1, 1) },
      uTint: { value: new THREE.Color(opts.tint ?? 0x3ee07f) },
      uTime: { value: 0 },
      uWobble: { value: opts.wobble ?? 0.14 },
      uFreq: { value: opts.freq ?? 1.35 },
      uRefract: { value: opts.refract ?? 0.06 },
      uGlow: { value: 0.3 },
    },
  })
  const geometry = new THREE.IcosahedronGeometry(1, opts.detail ?? 48)
  const mesh = new THREE.Mesh(geometry, material)
  return { mesh, material, geometry }
}

/** Render target holding "the scene without the glass", sampled by the glass shader. */
export function createRefractionTarget() {
  const rt = new THREE.WebGLRenderTarget(2, 2, { type: THREE.HalfFloatType, samples: 0 })
  return rt
}

export const LensShader = {
  uniforms: { tDiffuse: { value: null }, uAmount: { value: 0.011 }, uVignette: { value: 0.85 } },
  vertexShader: /* glsl */ `varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
  fragmentShader: /* glsl */ `
    uniform sampler2D tDiffuse; uniform float uAmount; uniform float uVignette; varying vec2 vUv;
    void main(){
      vec2 c = vUv - 0.5; float d = dot(c, c);
      vec2 off = c * d * uAmount * 4.0;
      vec3 col = vec3(texture2D(tDiffuse, vUv - off).r, texture2D(tDiffuse, vUv).g, texture2D(tDiffuse, vUv + off).b);
      col *= 1.0 - d * uVignette;
      gl_FragColor = vec4(col, 1.0);
    }`,
}
