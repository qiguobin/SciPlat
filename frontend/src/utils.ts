import dayjs from 'dayjs'

export function fmtSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  return `${(bytes / 1024 / 1024 / 1024).toFixed(1)} GB`
}

export function fmtDate(s?: string | null): string {
  return s ? dayjs(s).format('YYYY-MM-DD') : '—'
}

export function fmtDateTime(s?: string): string {
  return s ? dayjs(s).format('YYYY-MM-DD HH:mm') : '—'
}

export function splitTags(s?: string): string[] {
  return (s ?? '')
    .split(',')
    .map((t) => t.trim())
    .filter(Boolean)
}
