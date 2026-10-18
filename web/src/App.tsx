import { useEffect, useState } from 'react'
import Home from './Home'
import Intake from './Intake'
import Landing from './Landing'
import ProofPage from './ProofPage'
import Workspace from './Workspace'

function useHash() {
  const [hash, setHash] = useState(window.location.hash)
  useEffect(() => {
    const on = (e: HashChangeEvent) => {
      // New page (not just another tab of the same project): start at the top.
      const page = (u: string) => (new URL(u).hash.match(/^#\/(?:p\/[a-z0-9]+(?:\/intake)?|[a-z]*)/) ?? [''])[0]
      if (page(e.oldURL) !== page(e.newURL)) window.scrollTo(0, 0)
      setHash(window.location.hash)
    }
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])
  return hash
}

export function go(path: string) {
  window.location.hash = path
}

export default function App() {
  const hash = useHash()
  const intake = hash.match(/^#\/p\/([a-z0-9]+)\/intake/)
  const ws = hash.match(/^#\/p\/([a-z0-9]+)(?:\/([a-z]+))?/)
  if (hash.startsWith('#/proof')) return <ProofPage />
  if (intake) return <Intake key={intake[1]} id={intake[1]} />
  if (ws) return <Workspace key={ws[1]} id={ws[1]} tab={ws[2] ?? 'overview'} />
  if (hash.startsWith('#/app')) return <Home />
  return <Landing />
}
