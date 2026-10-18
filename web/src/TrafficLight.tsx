import { useEffect, useRef, useState } from 'react'
import type { Light } from './api'
import { cx } from './ui'

/** The verdict as a traffic light. While agents work the lamps cycle red → amber → green; once the Chamber rules,
 *  the verdict's lamp stays lit and breathes, and a change of verdict flashes the new lamp. */

const LAMPS: { light: Light; color: string; cy: number }[] = [
  { light: 'red', color: 'var(--stop)', cy: 62 },
  { light: 'amber', color: 'var(--wait)', cy: 140 },
  { light: 'green', color: 'var(--go)', cy: 218 },
]

export default function TrafficLight({ verdict, analyzing, size = 220 }: { verdict: Light | null; analyzing: boolean; size?: number }) {
  // Remember the previous verdict so a change can flash the new lamp.
  const prev = useRef<Light | null>(verdict)
  const [flash, setFlash] = useState(0)
  useEffect(() => {
    if (prev.current && verdict && prev.current !== verdict) setFlash((n) => n + 1)
    prev.current = verdict
  }, [verdict])

  const cycling = analyzing && !verdict
  const w = (size * 100) / 280
  return (
    <div className="relative" style={{ width: w, height: size }} role="img" aria-label={verdict ? `Verdict: ${verdict}` : analyzing ? 'Agents are deliberating' : 'No verdict'}>
      <svg viewBox="0 0 100 280" width={w} height={size} className="overflow-visible">
        <defs>
          <linearGradient id="tl-body" x1="0" x2="1">
            <stop offset="0" stopColor="#1d3d32" />
            <stop offset="0.5" stopColor="#132c23" />
            <stop offset="1" stopColor="#0b1f18" />
          </linearGradient>
          <filter id="tl-glow" x="-100%" y="-100%" width="300%" height="300%">
            <feGaussianBlur stdDeviation="9" />
          </filter>
          {LAMPS.map((l) => (
            <radialGradient key={l.light} id={`tl-on-${l.light}`} cx="0.42" cy="0.38" r="0.7">
              <stop offset="0" stopColor="#fff" stopOpacity="0.95" />
              <stop offset="0.22" stopColor={l.color} />
              <stop offset="1" stopColor={l.color} stopOpacity="0.55" />
            </radialGradient>
          ))}
          <radialGradient id="tl-off" cx="0.42" cy="0.38" r="0.75">
            <stop offset="0" stopColor="#2a332e" />
            <stop offset="1" stopColor="#0b100d" />
          </radialGradient>
        </defs>

        {/* pole stub and housing */}
        <rect x="44" y="266" width="12" height="14" rx="2" fill="#132c23" />
        <rect x="6" y="8" width="88" height="262" rx="22" fill="url(#tl-body)" stroke="rgba(237,243,238,.12)" />
        <rect x="11" y="13" width="78" height="252" rx="18" fill="none" stroke="rgba(255,255,255,.04)" />

        {LAMPS.map((l, i) => {
          const on = verdict === l.light
          return (
            <g key={l.light}>
              {/* glow behind the lamp */}
              <circle
                cx="50" cy={l.cy} r="30" fill={l.color} filter="url(#tl-glow)"
                className={cx('transition-opacity duration-700', on && 'tl-breathe', cycling && 'tl-cycle')}
                style={{ opacity: on ? 0.75 : 0, animationDelay: cycling ? `${i * 0.8}s` : undefined }}
              />
              {/* dark glass, always there */}
              <circle cx="50" cy={l.cy} r="27" fill="url(#tl-off)" stroke="rgba(0,0,0,.6)" strokeWidth="2" />
              <circle cx="50" cy={l.cy} r="27" fill={l.color} opacity="0.08" />
              {/* lit glass */}
              <circle
                cx="50" cy={l.cy} r="27" fill={`url(#tl-on-${l.light})`}
                className={cx('transition-opacity duration-700', cycling && 'tl-cycle')}
                style={{ opacity: on ? 1 : 0, animationDelay: cycling ? `${i * 0.8}s` : undefined }}
              />
              {/* lens highlight */}
              <ellipse cx="41" cy={l.cy - 10} rx="10" ry="5" fill="#fff" opacity="0.12" transform={`rotate(-25 41 ${l.cy - 10})`} />
              {/* visor */}
              <path d={`M16 ${l.cy - 6} A34 34 0 0 1 84 ${l.cy - 6} L84 ${l.cy - 14} A34 34 0 0 0 16 ${l.cy - 14} Z`} fill="#050806" opacity="0.9" />
              {on && flash > 0 && (
                <circle key={flash} cx="50" cy={l.cy} r="27" fill="none" stroke={l.color} strokeWidth="3" className="tl-flash" />
              )}
            </g>
          )
        })}
      </svg>
    </div>
  )
}
