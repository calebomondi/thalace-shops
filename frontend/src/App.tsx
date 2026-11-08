import { useEffect, useState } from 'react'

type Health = { status: string; project: string; environment: string }

function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetch('/api/v1/health')
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(`HTTP ${res.status}`))))
      .then(setHealth)
      .catch((err: Error) => setError(err.message))
  }, [])

  return (
    <main>
      <h1>Thalace Shops</h1>
      <p>
        Backend:{' '}
        {health ? `${health.status} (${health.environment})` : error ? `unreachable: ${error}` : 'checking…'}
      </p>
    </main>
  )
}

export default App
