import { useEffect, useMemo, useRef, useState } from 'react'
import type { FormEvent } from 'react'

type LocationFix = {
  latitude: number
  longitude: number
  accuracy_m?: number | null
  timestamp?: string | null
  battery?: string | null
}

type Accessory = {
  id: string
  name: string
  kind: string
  identifier?: string | null
  battery: string
  location: LocationFix | null
}

type Me = {
  mode: 'demo' | 'live'
  email: string
  first_name: string
  last_name: string
  pending_2fa: boolean
  findmy: boolean
}

type Method = { index: number; type: string; label: string }

type LeafletMap = {
  setView: (c: [number, number], z: number) => void
  remove: () => void
  fitBounds: (b: unknown, o?: unknown) => void
}

declare global {
  interface Window {
    L?: {
      map: (el: HTMLElement) => LeafletMap & { addLayer: (x: unknown) => void }
      tileLayer: (url: string, opts: object) => { addTo: (m: unknown) => void }
      marker: (c: [number, number]) => {
        addTo: (m: unknown) => { bindPopup: (h: string) => void }
      }
      featureGroup: (layers: unknown[]) => { getBounds: () => unknown }
    }
  }
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { credentials: 'include', ...init })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    const detail = (data as { detail?: string }).detail
    throw new Error(typeof detail === 'string' ? detail : `Request failed (${res.status})`)
  }
  return data as T
}

function formatWhen(iso?: string | null) {
  if (!iso) return 'No recent report'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString()
}

function MapPanel({ accessories, selectedId }: { accessories: Accessory[]; selectedId: string | null }) {
  const ref = useRef<HTMLDivElement>(null)
  const mapRef = useRef<LeafletMap | null>(null)

  const points = useMemo(
    () => accessories.filter((a) => a.location && a.location.latitude != null),
    [accessories],
  )

  useEffect(() => {
    const el = ref.current
    const L = window.L
    if (!el || !L) return
    if (mapRef.current) {
      mapRef.current.remove()
      mapRef.current = null
    }
    const start: [number, number] = points[0]
      ? [points[0].location!.latitude, points[0].location!.longitude]
      : [42.6977, 23.3219]
    const map = L.map(el)
    map.setView(start, 13)
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; OpenStreetMap',
    }).addTo(map)
    const markers = points.map((tag) => {
      const m = L.marker([tag.location!.latitude, tag.location!.longitude])
      m.addTo(map).bindPopup(`<strong>${tag.name}</strong><br/>${tag.battery}`)
      return m
    })
    if (markers.length > 1) {
      map.fitBounds(L.featureGroup(markers).getBounds(), { padding: [28, 28] })
    }
    const selected = points.find((p) => p.id === selectedId)
    if (selected?.location) {
      map.setView([selected.location.latitude, selected.location.longitude], 15)
    }
    mapRef.current = map
    return () => {
      map.remove()
      mapRef.current = null
    }
  }, [points, selectedId])

  return <div className="map" ref={ref} />
}

export default function App() {
  const [me, setMe] = useState<Me | null>(null)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [methods, setMethods] = useState<Method[]>([])
  const [methodIndex, setMethodIndex] = useState(0)
  const [code, setCode] = useState('')
  const [accessories, setAccessories] = useState<Accessory[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [boot, setBoot] = useState(true)

  async function loadSession() {
    try {
      let user: Me
      try {
        user = await api<Me>('/api/me')
      } catch {
        await api('/api/auth/resume', { method: 'POST' })
        user = await api<Me>('/api/me')
      }
      setMe(user)
      if (user.pending_2fa) {
        const m = await api<{ methods: Method[] }>('/api/auth/2fa-methods')
        setMethods(m.methods)
      }
      const list = await api<{ accessories: Accessory[] }>('/api/accessories')
      setAccessories(list.accessories)
      setSelectedId(list.accessories[0]?.id ?? null)
    } catch {
      setMe(null)
    } finally {
      setBoot(false)
    }
  }

  useEffect(() => {
    void loadSession()
  }, [])

  async function onDemo() {
    setBusy(true)
    setError(null)
    try {
      await api('/api/auth/demo', { method: 'POST' })
      await loadSession()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Demo sign-in failed')
    } finally {
      setBusy(false)
    }
  }

  async function onLogin(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const res = await api<{ needs_2fa: boolean; methods: Method[] }>('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      })
      if (res.needs_2fa) {
        setMethods(res.methods)
        setMethodIndex(res.methods[0]?.index ?? 0)
      }
      await loadSession()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sign-in failed')
    } finally {
      setBusy(false)
    }
  }

  async function sendCode() {
    setBusy(true)
    setError(null)
    try {
      await api('/api/auth/2fa/request', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ index: methodIndex }),
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not send a code')
    } finally {
      setBusy(false)
    }
  }

  async function submitCode(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await api('/api/auth/2fa/submit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ index: methodIndex, code }),
      })
      setCode('')
      await loadSession()
    } catch (err) {
      setError(err instanceof Error ? err.message : '2FA failed')
    } finally {
      setBusy(false)
    }
  }

  async function refresh() {
    setBusy(true)
    setError(null)
    try {
      const res = await api<{ accessories: Accessory[] }>('/api/accessories/refresh', { method: 'POST' })
      setAccessories(res.accessories)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Refresh failed')
    } finally {
      setBusy(false)
    }
  }

  async function onUpload(file: File | undefined) {
    if (!file) return
    setBusy(true)
    setError(null)
    try {
      const body = new FormData()
      body.append('file', file)
      await api('/api/accessories', { method: 'POST', body })
      const list = await api<{ accessories: Accessory[] }>('/api/accessories')
      setAccessories(list.accessories)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Import failed')
    } finally {
      setBusy(false)
    }
  }

  async function logout() {
    await api('/api/auth/logout', { method: 'POST' })
    setMe(null)
    setAccessories([])
    setPassword('')
  }

  const selected = accessories.find((a) => a.id === selectedId) ?? null

  if (boot) {
    return (
      <div className="shell">
        <p className="muted">Opening Find Me…</p>
      </div>
    )
  }

  if (!me) {
    return (
      <div className="shell">
        <p className="brand">Find Me</p>
        <h1>Your AirTags, without an iPhone on the desk.</h1>
        <p className="muted notice" style={{ maxWidth: 640 }}>
          Sign in with the Apple ID that owns the tags. This is not Sign in with Apple (OAuth) —
          Find My has no public OAuth scope. The app uses{' '}
          <a href="https://github.com/malmeloo/FindMy.py" style={{ color: 'var(--accent)' }}>
            FindMy.py
          </a>{' '}
          against Apple’s unofficial Find My network APIs. Use it only for devices you own.
        </p>
        <div className="grid" style={{ marginTop: 24 }}>
          <form className="card stack" onSubmit={onLogin}>
            <div>
              <label htmlFor="email">Apple ID</label>
              <input
                id="email"
                type="email"
                autoComplete="username"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>
            <div>
              <label htmlFor="password">Password</label>
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>
            {error ? <p className="error notice">{error}</p> : null}
            <div className="row">
              <button type="submit" disabled={busy}>
                Sign in
              </button>
              <button type="button" className="secondary" onClick={onDemo} disabled={busy}>
                Try the demo
              </button>
            </div>
            <p className="muted notice">
              Apple will usually ask for SMS or a trusted-device code. Passkeys are not supported by
              FindMy.py.
            </p>
          </form>
          <div className="card notice muted">
            <p>
              Signing in does <strong>not</strong> list AirTags. Apple encrypts every tag report; the
              keys live in iCloud Keychain on phones and Macs that already have Find My Items. This
              app can download reports only after you give it those keys.
            </p>
            <p>
              Without a Mac, export keys with{' '}
              <a href="https://github.com/stek29/export-findmy" style={{ color: 'var(--accent)' }}>
                export-findmy
              </a>{' '}
              on Linux or Windows: Apple ID, 2FA, then the <em>screen lock passcode</em> of an iPhone
              or iPad that already shows the tags. Import the JSON it writes.
            </p>
            <p>
              With a Mac signed into the same Apple ID:{' '}
              <code>python -m findmy decrypt --out-dir devices/</code>
            </p>
          </div>
        </div>
      </div>
    )
  }

  if (me.pending_2fa) {
    return (
      <div className="shell">
        <p className="brand">Two-factor</p>
        <h1>Confirm it’s you</h1>
        <form className="card stack" style={{ maxWidth: 420, marginTop: 18 }} onSubmit={submitCode}>
          <div>
            <label htmlFor="method">Challenge</label>
            <select
              id="method"
              value={methodIndex}
              onChange={(e) => setMethodIndex(Number(e.target.value))}
              style={{ width: '100%', padding: 10, borderRadius: 12, background: '#0b1522', color: 'inherit' }}
            >
              {methods.map((m) => (
                <option key={m.index} value={m.index}>
                  {m.label}
                </option>
              ))}
            </select>
          </div>
          <div className="row">
            <button type="button" className="secondary" onClick={sendCode} disabled={busy}>
              Send code
            </button>
          </div>
          <div>
            <label htmlFor="code">Code</label>
            <input id="code" type="text" inputMode="numeric" value={code} onChange={(e) => setCode(e.target.value)} />
          </div>
          {error ? <p className="error notice">{error}</p> : null}
          <div className="row">
            <button type="submit" disabled={busy}>
              Continue
            </button>
            <button type="button" className="ghost" onClick={logout}>
              Cancel
            </button>
          </div>
        </form>
      </div>
    )
  }

  return (
    <div className="shell">
      <header className="top">
        <div>
          <p className="brand">Find Me</p>
          <h1>{me.first_name ? `${me.first_name}’s AirTags` : 'AirTags'}</h1>
          <p className="muted">
            {me.email} · {me.mode === 'demo' ? 'demo data' : 'Apple session'}{' '}
            <span className="badge">{me.mode}</span>
          </p>
        </div>
        <div className="row">
          <button type="button" className="secondary" onClick={refresh} disabled={busy}>
            Refresh locations
          </button>
          <button type="button" className="ghost" onClick={logout}>
            Sign out
          </button>
        </div>
      </header>
      {error ? <p className="error notice">{error}</p> : null}
      <div className="grid">
        <aside className="stack">
          <div className="card">
            <p className="muted" style={{ marginTop: 0 }}>
              {accessories.length} item{accessories.length === 1 ? '' : 's'}
            </p>
            {accessories.length === 0 ? (
              <div className="empty">
                Signed in, but there are no AirTag keys yet. Apple will not send tag locations to
                this session until you import JSON from export-findmy or from{' '}
                <code>python -m findmy decrypt</code> on a Mac.
              </div>
            ) : (
              <ul className="tag-list">
                {accessories.map((tag) => (
                  <li key={tag.id}>
                    <button
                      type="button"
                      className={tag.id === selectedId ? 'tag active' : 'tag'}
                      onClick={() => setSelectedId(tag.id)}
                    >
                      <strong>{tag.name}</strong>
                      <div className="muted">
                        {tag.battery} · {tag.location ? formatWhen(tag.location.timestamp) : 'No location yet'}
                      </div>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
          {me.mode === 'live' ? (
            <label className="card notice">
              Import AirTag JSON (export-findmy or FindMy.py decrypt)
              <input
                type="file"
                accept="application/json,.json"
                style={{ marginTop: 10 }}
                onChange={(e) => void onUpload(e.target.files?.[0])}
              />
            </label>
          ) : (
            <p className="card muted notice">
              Demo tags are samples around Sofia so you can try the map. They are not talking to
              Apple.
            </p>
          )}
        </aside>
        <section className="stack">
          <MapPanel accessories={accessories} selectedId={selectedId} />
          <div className="card">
            {selected ? (
              <>
                <h2 style={{ marginTop: 0 }}>{selected.name}</h2>
                <p className="muted">
                  {selected.kind}
                  {selected.identifier ? ` · ${selected.identifier}` : ''}
                </p>
                {selected.location ? (
                  <p>
                    {selected.location.latitude.toFixed(5)}, {selected.location.longitude.toFixed(5)}
                    <br />
                    Battery {selected.battery} · {formatWhen(selected.location.timestamp)}
                  </p>
                ) : (
                  <p className="muted">No Find My report yet for this tag.</p>
                )}
              </>
            ) : (
              <p className="muted">Select a tag to see its last report.</p>
            )}
          </div>
        </section>
      </div>
    </div>
  )
}
