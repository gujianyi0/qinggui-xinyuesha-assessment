import type { Auth } from '@/types/domain'
import { request } from './api'

export function signIn({
  username,
  password,
}: {
  username: string
  password: string
}) {
  return request<Auth>('/auth/token', undefined, {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  })
}
export function signInGuest(clientSecret: string) {
  return request<Auth>('/auth/guest', undefined, {
    method: 'POST',
    body: JSON.stringify({ client_secret: clientSecret }),
  })
}
