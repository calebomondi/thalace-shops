import { Navigate, Route, Routes, useLocation } from 'react-router'

import { AppShell } from './components/app-shell'
import { AuthCallbackPage } from './features/auth/auth-callback-page'
import { SignInPage } from './features/auth/sign-in-page'
import { ShopPage } from './features/shop/shop-page'
import { ShopsPage } from './features/shops/shops-page'
import { useAuth } from './lib/auth-context'
import { HOME_PATH, safeNextPath } from './lib/next-path'

/** Every app page needs a session: send visitors to sign in, and back here after. */
function RequireSession() {
  const { session } = useAuth()
  const location = useLocation()
  if (!session) {
    const next = encodeURIComponent(location.pathname + location.search)
    return <Navigate to={`/auth/sign-in?next=${next}`} replace />
  }
  return <AppShell />
}

/** Signed-in people don't need the sign-in page: send them on. */
function SignInRoute() {
  const { session } = useAuth()
  const location = useLocation()
  if (session) {
    const next = safeNextPath(new URLSearchParams(location.search).get('next')) ?? HOME_PATH
    return <Navigate to={next} replace />
  }
  return <SignInPage />
}

function App() {
  return (
    <Routes>
      <Route path="/auth/sign-in" element={<SignInRoute />} />
      <Route path="/auth/callback" element={<AuthCallbackPage />} />
      <Route path="/auth" element={<Navigate to="/auth/sign-in" replace />} />
      <Route element={<RequireSession />}>
        <Route index element={<ShopsPage />} />
        <Route path="shops/:shopId" element={<ShopPage />} />
      </Route>
      <Route path="*" element={<Navigate to={HOME_PATH} replace />} />
    </Routes>
  )
}

export default App
