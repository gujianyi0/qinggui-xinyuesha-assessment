import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { createElement, useEffect, useState } from 'react'

interface AppQueryProviderProps {
  children: ReactNode
}
export default function AppQueryProvider({ children }: AppQueryProviderProps) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30000,
            gcTime: 5 * 60000,
            retry: (count, error) => {
              const status = 'status' in error ? error.status : undefined
              return (
                count < 1 && ![401, 403, 404, 409, 422].includes(Number(status))
              )
            },
            refetchOnWindowFocus: true,
          },
          mutations: { retry: false },
        },
      }),
  )
  useEffect(() => () => client.clear(), [client])
  return createElement(QueryClientProvider, { client }, children)
}
