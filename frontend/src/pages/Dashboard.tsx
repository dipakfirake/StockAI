import { useEffect, useState } from 'react'
import { marketApi, stocksApi } from '../services/api'
import { TrendingUp, TrendingDown, Minus, Activity, Globe, AlertCircle } from 'lucide-react'

interface Index {
  name: string
  symbol: string
  price: number
  change: number
  change_pct: number
}

interface RegimeData {
  regime: string
  confidence: number
  bullish_signals?: number
  bearish_signals?: number
  signals?: { source: string; direction: string; detail: string }[]
  is_market_open?: boolean
}

interface VIXData {
  vix: number
  sentiment: string
  interpretation: string
}

interface Event {
  name: string
  type: string
  impact: string
  description: string
}

export default function Dashboard() {
  const [indices, setIndices] = useState<Index[]>([])
  const [regime, setRegime] = useState<RegimeData | null>(null)
  const [vix, setVix] = useState<VIXData | null>(null)
  const [events, setEvents] = useState<Event[]>([])
  const [sectors, setSectors] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadDashboard()
    const interval = setInterval(loadDashboard, 60000) // refresh every 60s
    return () => clearInterval(interval)
  }, [])

  async function loadDashboard() {
    try {
      const [indicesRes, regimeRes, vixRes, eventsRes, sectorsRes] = await Promise.allSettled([
        marketApi.getIndices(),
        marketApi.getRegime(),
        marketApi.getVix(),
        marketApi.getEvents(),
        marketApi.getSectors(),
      ])

      if (indicesRes.status === 'fulfilled') setIndices(indicesRes.value.data.indices || [])
      if (regimeRes.status === 'fulfilled') setRegime(regimeRes.value.data)
      if (vixRes.status === 'fulfilled') setVix(vixRes.value.data as any)
      if (eventsRes.status === 'fulfilled') setEvents((eventsRes.value.data as any).events || [])
      if (sectorsRes.status === 'fulfilled') setSectors((sectorsRes.value.data as any).sectors || [])
    } catch (err) {
      console.error('Dashboard load error:', err)
    } finally {
      setLoading(false)
    }
  }

  const RegimeIcon = regime?.regime === 'BULLISH' ? TrendingUp : regime?.regime === 'BEARISH' ? TrendingDown : Minus
  const regimeColor = regime?.regime === 'BULLISH' ? 'var(--color-bullish)' : regime?.regime === 'BEARISH' ? 'var(--color-bearish)' : 'var(--color-neutral)'

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Market Dashboard</h1>
        <p className="page-subtitle">Live India market intelligence — NSE &amp; BSE</p>
      </div>

      {loading && <div className="loading">Loading market data…</div>}

      {/* Market Status Banner */}
      {regime && (
        <div className="card" style={{ marginBottom: 16, borderColor: regimeColor, display: 'flex', alignItems: 'center', gap: 16 }}>
          <RegimeIcon size={28} color={regimeColor} />
          <div>
            <div style={{ fontWeight: 700, fontSize: 18, color: regimeColor }}>
              Market is {regime.regime}
            </div>
            <div style={{ color: 'var(--color-text-secondary)', fontSize: 13 }}>
              Confidence: {Math.round((regime.confidence || 0) * 100)}% ·&nbsp;
              {regime.is_market_open ? '🟢 Market Open' : '🔴 Market Closed'}
            </div>
          </div>
          {regime.signals && regime.signals.slice(0, 2).map((s, i) => (
            <div key={i} style={{ marginLeft: 'auto', fontSize: 12, textAlign: 'right' }}>
              <span style={{ color: s.direction === 'bullish' ? 'var(--color-bullish)' : s.direction === 'bearish' ? 'var(--color-bearish)' : 'var(--color-neutral)' }}>
                {s.source}
              </span>
              <div style={{ color: 'var(--color-text-muted)' }}>{s.detail.slice(0, 60)}</div>
            </div>
          ))}
        </div>
      )}

      {/* Market Events */}
      {events.length > 0 && (
        <div style={{ marginBottom: 16, display: 'flex', gap: 8 }}>
          {events.map((e, i) => (
            <div key={i} className="card" style={{ flex: 1, padding: '10px 14px', borderColor: e.impact === 'HIGH' || e.impact === 'VERY_HIGH' ? 'var(--color-neutral)' : 'var(--color-border)' }}>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <AlertCircle size={16} color={e.impact === 'VERY_HIGH' ? 'var(--color-bearish)' : 'var(--color-neutral)'} />
                <span style={{ fontWeight: 600, fontSize: 13 }}>{e.name}</span>
                <span style={{ marginLeft: 'auto', fontSize: 11, background: 'rgba(245,158,11,0.15)', color: 'var(--color-neutral)', padding: '2px 8px', borderRadius: 12 }}>{e.impact}</span>
              </div>
              <div style={{ fontSize: 12, color: 'var(--color-text-secondary)', marginTop: 4 }}>{e.description.slice(0, 100)}</div>
            </div>
          ))}
        </div>
      )}

      {/* Index Cards */}
      <div className="grid-3" style={{ marginBottom: 20 }}>
        {indices.slice(0, 6).map((idx) => (
          <div key={idx.symbol} className="card">
            <div style={{ fontSize: 12, color: 'var(--color-text-muted)', marginBottom: 4 }}>{idx.name}</div>
            <div style={{ fontSize: 22, fontWeight: 700, fontFamily: 'var(--font-mono)' }}>
              {idx.price?.toLocaleString('en-IN', { maximumFractionDigits: 2 })}
            </div>
            <div className={idx.change_pct >= 0 ? 'positive' : 'negative'} style={{ fontSize: 14, marginTop: 4 }}>
              {idx.change_pct >= 0 ? '▲' : '▼'} {Math.abs(idx.change_pct).toFixed(2)}%
              &nbsp;({idx.change >= 0 ? '+' : ''}{idx.change?.toFixed(2)})
            </div>
          </div>
        ))}
      </div>

      <div className="grid-2" style={{ gap: 20 }}>
        {/* Sector Heatmap */}
        <div className="card">
          <div className="card-header">
            <span className="card-title"><Activity size={16} style={{ marginRight: 6 }} />Sector Rotation</span>
          </div>
          {sectors.length === 0 && <div className="empty-state">Loading sector data…</div>}
          {sectors.map((s, i) => (
            <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '7px 0', borderBottom: i < sectors.length - 1 ? '1px solid var(--color-border)' : 'none' }}>
              <span style={{ fontSize: 13, color: 'var(--color-text-secondary)' }}>{s.name}</span>
              <span className={s.change_pct >= 0 ? 'positive' : 'negative'} style={{ fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: 600 }}>
                {s.change_pct >= 0 ? '+' : ''}{s.change_pct?.toFixed(2)}%
              </span>
            </div>
          ))}
        </div>

        {/* India Intelligence Signals */}
        <div className="card">
          <div className="card-header">
            <span className="card-title"><Globe size={16} style={{ marginRight: 6 }} />India Intelligence</span>
          </div>
          {vix && (
            <div style={{ marginBottom: 16, padding: '12px', background: 'var(--color-bg-secondary)', borderRadius: 8 }}>
              <div style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>India VIX (Fear Gauge)</div>
              <div style={{ fontSize: 24, fontWeight: 700, fontFamily: 'var(--font-mono)', color: vix.vix > 25 ? 'var(--color-bearish)' : vix.vix < 15 ? 'var(--color-bullish)' : 'var(--color-neutral)' }}>
                {vix.vix}
              </div>
              <div style={{ fontSize: 12, color: 'var(--color-text-secondary)', marginTop: 2 }}>{vix.interpretation}</div>
            </div>
          )}
          {regime?.signals && regime.signals.map((s, i) => (
            <div key={i} style={{ display: 'flex', gap: 10, alignItems: 'flex-start', padding: '8px 0', borderBottom: i < regime.signals!.length - 1 ? '1px solid var(--color-border)' : 'none' }}>
              <span style={{
                fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 12,
                background: s.direction === 'bullish' ? 'var(--color-bullish-dim)' : s.direction === 'bearish' ? 'var(--color-bearish-dim)' : 'rgba(100,116,139,0.2)',
                color: s.direction === 'bullish' ? 'var(--color-bullish)' : s.direction === 'bearish' ? 'var(--color-bearish)' : 'var(--color-text-secondary)',
                whiteSpace: 'nowrap',
              }}>
                {s.source}
              </span>
              <span style={{ fontSize: 12, color: 'var(--color-text-secondary)', lineHeight: 1.4 }}>{s.detail.slice(0, 100)}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
