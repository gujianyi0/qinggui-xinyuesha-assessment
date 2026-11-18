export function relativeDate(value?: string): string {
  if (!value) return ''
  // The database stores naive UTC timestamps; browsers otherwise treat them as local time.
  const date = new Date(
    /Z$|[+-]\d{2}:\d{2}$/i.test(value) ? value : `${value}Z`,
  )
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'Asia/Shanghai',
  }).format(date)
}
