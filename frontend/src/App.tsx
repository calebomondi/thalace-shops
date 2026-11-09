import { Navigate, Route, Routes } from 'react-router'

import { AppShell } from './components/app-shell'
import { SignInPage } from './features/auth/sign-in-page'
import { ShopsPage } from './features/shops/shops-page'
import { useAuth } from './lib/auth-context'

function App() {
  const { session, loading } = useAuth()

  if (loading) {
    return <p className="p-8 text-muted">Loading…</p>
  }

  return (
    <Routes>
      <Route path="/sign-in" element={session ? <Navigate to="/" replace /> : <SignInPage />} />
      <Route element={session ? <AppShell /> : <Navigate to="/sign-in" replace />}>
        <Route index element={<ShopsPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

export default App
