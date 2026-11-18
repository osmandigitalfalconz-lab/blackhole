// BlackHole API helpers — same endpoints, request shapes and query params
// as the vanilla frontend (static/app.js).

export function fmtDuration(sec) {
  if (!sec && sec !== 0) return ''
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  const h = Math.floor(m / 60)
  const mm = h ? String(m % 60).padStart(2, '0') : String(m)
  return h ? `${h}:${mm}:${String(s).padStart(2, '0')}` : `${mm}:${String(s).padStart(2, '0')}`
}

export async function fetchInfo(url) {
  const res = await fetch('/api/info', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url }),
  })
  const data = await res.json()
  if (!res.ok) throw new Error(data.error || 'Could not fetch this link.')
  return data
}

export function downloadUrl(url, opt, title) {
  const q = new URLSearchParams({
    url,
    format: opt.id,
    kind: opt.kind,
    title: title || 'video',
  })
  return `/api/download?${q.toString()}`
}
