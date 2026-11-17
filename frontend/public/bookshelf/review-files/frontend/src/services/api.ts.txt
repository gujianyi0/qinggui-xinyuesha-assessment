import { apiBase } from '@/lib/runtime-config'

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

function errorText(detail: unknown): string {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail))
    return detail
      .map((item) => (typeof item?.msg === 'string' ? item.msg : String(item)))
      .join('；')
  return '请求未完成，请稍后重试'
}

export async function request<T>(
  path: string,
  token?: string,
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers)
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (options.body) headers.set('Content-Type', 'application/json')
  const timeout = new AbortController()
  const timer = setTimeout(
    () => timeout.abort(new DOMException('请求超时', 'TimeoutError')),
    15_000,
  )
  const signal = options.signal
    ? AbortSignal.any([options.signal, timeout.signal])
    : timeout.signal
  try {
    const response = await fetch(`${apiBase}${path}`, {
      ...options,
      headers,
      signal,
    })
    if (!response.ok) {
      if (response.status === 401 && token)
        window.dispatchEvent(new Event('qinggui-auth-expired'))
      let message = `请求失败（${response.status}）`
      try {
        message = errorText((await response.json()).detail)
      } catch {
        /* HTTP status remains actionable. */
      }
      throw new ApiError(message, response.status)
    }
    if (response.status === 204) return undefined as T
    return (await response.json()) as T
  } catch (error) {
    if (timeout.signal.aborted && !options.signal?.aborted)
      throw new Error(
        '请求超过15秒，请检查服务后重试；提交结果不明时会核对原请求。',
      )
    throw error
  } finally {
    clearTimeout(timer)
  }
}

export function listResult<T>(value: T[] | { items: T[] }): T[] {
  return Array.isArray(value) ? value : value.items
}
export function displayError(error: unknown): string {
  return error instanceof Error ? error.message : '请求未完成，请稍后重试'
}
