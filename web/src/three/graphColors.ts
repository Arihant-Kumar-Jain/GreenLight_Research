/** Shared by the 3D relationship graph and its legend, kept out of PaperGraph.tsx so the legend doesn't pull three.js. */
export const CLUSTER_COLORS = [0x0b7a47, 0x1d4ed8, 0xb45309, 0x7a3e6b, 0x0e7490, 0xbe185d, 0x4d7c0f, 0x8a5a2b, 0x64748b]
export type EdgeKind = 'cites' | 'similar' | 'idea'
