export const isPublicMode = import.meta.env.VITE_PUBLIC_MODE === '1'
export const apiBase =
  import.meta.env.VITE_API_BASE ||
  (isPublicMode && ['localhost', '127.0.0.1'].includes(location.hostname)
    ? 'https://qinggui-assessment.c2115259095.workers.dev/api'
    : '/api')
