import { lazy, Suspense, useCallback, useState } from 'react'
import { Spinner } from '@/components/ui'
import Login from '@/features/auth'
import AppQueryProvider from '@/lib/query/provider'
import type { Auth } from '@/types/domain'

const Workspace = lazy(() => import('@/features/workspace'))
const AUTH_KEY = 'qinggui-v2-local-auth'
function readAuth(): Auth | null {
  try {
    const value = JSON.parse(sessionStorage.getItem(AUTH_KEY) || 'null')
    return value?.access_token && value?.user?.id ? value : null
  } catch {
    return null
  }
}
export default function App() {
  const [auth, setAuth] = useState<Auth | null>(readAuth)
  const handleLogin = (value: Auth) => {
    sessionStorage.setItem(AUTH_KEY, JSON.stringify(value))
    setAuth(value)
  }
  const handleLogout = useCallback(() => {
    sessionStorage.removeItem(AUTH_KEY)
    setAuth(null)
  }, [])
  return (
    <AppQueryProvider key={auth?.user.id ?? 'signed-out'}>
      {auth ? (
        <Suspense
          fallback={
            <div className="panel-loading">
              <Spinner label="正在打开工作区" />
            </div>
          }
        >
          <Workspace auth={auth} onLogout={handleLogout} />
        </Suspense>
      ) : (
        <Login onLogin={handleLogin} />
      )}
    </AppQueryProvider>
  )
}
