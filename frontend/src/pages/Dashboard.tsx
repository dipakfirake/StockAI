import { useEffect, useState } from 'react'
import { marketApi, aiApi } from '../services/api'
import { TrendingUp, TrendingDown, Minus, Activity, Globe, AlertCircle, Sparkles, RefreshCw } from 'lucide-react'
import AnimatedNumber from '../components/AnimatedNumber'

interface Index {
  name: string
  symbol: string
  price: number
  change: number
  change_pct: number
  source?: string
  data_status?: string
  timestamp?: string
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

// Skeleton card shown while loading
function SkeletonIndexCard() {
  return (
    <div className="skeleton-card">
      <div className="skeleton skeleton-line" style={{ width: '50%' }} />
      <div className="skeleton skeleton-price" />
      <div className="skeleton skeleton-line" style={{ width: '70%' }} />
    </div>
  )
}

// Sector heat tile with dynamic color intensity
function SectorHeatTile({ name, change_pct, index }: { name: string; change_pct: number; index: number }) {
  const intensity = Math.min(Math.abs(change_pct) / 5, 1) // 0→1 scale (5% = max)
  const isBull = change_pct >= 0
  const bg = isBull
    ? `rgba(16,185,129,${0.08 + intensity * 0.25})`
    : `rgba(239,68,68,${0.08 + intensity * 0.25})`
  const border = isBull
    ? `rgba(16,185,129,${0.2 + intensity * 0.4})`
    : `rgba(239,68,68,${0.2 + intensity * 0.4})`
  const color = isBull ? 'var(--color-bullish)' : 'var(--color-bearish)'

  return (
    <div
      className={`heat-tile animate-fade-in-up stagger-${Math.min(index + 1, 6)}`}
      style={{ background: bg, border: `1px solid ${border}`, opacity: 0 }}
    >
      <span style={{ fontSize: 13, color: 'var(--color-text-primary)', fontWeight: 500 }}>{name}</span>
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: 700, color }}>
        {change_pct >= 0 ? '+' : ''}{change_pct?.toFixed(2)}%
      </span>
    </div>
  )
}

// AI Score circular ring
function AIScoreRing({ score, label }: { score: number; label: string }) {
  const r = 26
  const circ = 2 * Math.PI * r
  const offset = circ - (score / 100) * circ
  const color = score >= 60 ? '#10b981' : score >= 40 ? '#f59e0b' : '#ef4444'

  return (
    <div className="ai-score-ring" style={{ width: 70, height: 70 }}>
      <svg width="70" height="70" style={{ transform: 'rotate(-90deg)' }}>
        <circle cx="35" cy="35" r={r} fill="none" stroke="var(--color-border)" strokeWidth="5" />
        <circle
          cx="35" cy="35" r={r} fill="none"
          stroke={color} strokeWidth="5"
          strokeDasharray={circ}
          strokeDashoffset={offset}
          strokeLinecap="round"
        />
      </svg>
      <div style={{ position: 'absolute', textAlign: 'center' }}>
        <div style={{ fontSize: 15, fontWeight: 700, color }}>{score}</div>
        <div style={{ fontSize: 9, color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: 0.5 }}>{label}</div>
      </div>
    </div>
  )
}

export default function Dashboard() {
  const [indices, setIndices] = useState<Index[]>([])
  const [regime, setRegime] = useState<RegimeData | null>(null)
  const [vix, setVix] = useState<VIXData | null>(null)
  const [events, setEvents] = useState<Event[]>([])
  const [sectors, setSectors] = useState<any[]>([])
  const [morningBrief, setMorningBrief] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)
  const [refreshing, setRefreshing] = useState(false)

  useEffect(() => {
    loadDashboard()
    const interval = setInterval(loadDashboard, 60000) // refresh every 60s
    return () => clearInterval(interval)
  }, [])

  // Load AI morning brief once
  useEffect(() => {
    async function fetchBrief() {
      try {
        const res = await aiApi.chat('Give me a 2-sentence market morning brief for Indian NSE markets today. Be concise, data-driven, and mention the key trend.', undefined)
        if (res.data?.reply) setMorningBrief(res.data.reply)
      } catch {
        setMorningBrief(null)
      }
    }
    fetchBrief()
  }, [])

  async function loadDashboard(manual = false) {
    if (manual) setRefreshing(true)
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
      setLastUpdated(new Date())
    } catch (err) {
      console.error('Dashboard load error:', err)
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }

  const RegimeIcon = regime?.regime === 'BULLISH' ? TrendingUp : regime?.regime === 'BEARISH' ? TrendingDown : Minus
  const regimeColor = regime?.regime === 'BULLISH' ? 'var(--color-bullish)' : regime?.regime === 'BEARISH' ? 'var(--color-bearish)' : 'var(--color-neutral)'
  const vixColor = vix ? (vix.vix > 25 ? 'var(--color-bearish)' : vix.vix < 15 ? 'var(--color-bullish)' : 'var(--color-neutral)') : 'var(--color-text-primary)'

  return (
    <div>
      <div className="page-header" style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between' }}>
        <div>
          <h1 className="page-title">Market Dashboard</h1>
          <p className="page-subtitle">Live India market intelligence — NSE &amp; BSE</p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
          {lastUpdated && (
            <span style={{ fontSize: 11, color: 'var(--color-text-muted)' }}>
              Updated {lastUpdated.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
            </span>
          )}
          <button
            onClick={() => loadDashboard(true)}
            className="btn btn-ghost"
            style={{ fontSize: 12, padding: '4px 10px', height: 28, display: 'flex', gap: 6, alignItems: 'center' }}
          >
            <RefreshCw size={12} className={refreshing ? 'spin' : ''} style={{ animation: refreshing ? 'spin 0.8s linear infinite' : 'none' }} />
            Refresh
          </button>
        </div>
      </div>

      {/* AI Morning Brief */}
      {morningBrief && (
        <div className="card animate-fade-in-up" style={{ marginBottom: 16, background: 'linear-gradient(135deg, rgba(59,130,246,0.08), rgba(139,92,246,0.08))', borderColor: 'rgba(59,130,246,0.3)' }}>
          <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
            <Sparkles size={18} style={{ color: '#8b5cf6', flexShrink: 0, marginTop: 2 }} />
            <div>
              <div style={{ fontSize: 11, fontWeight: 700, color: '#8b5cf6', marginBottom: 4, textTransform: 'uppercase', letterSpacing: 1 }}>AI Morning Brief</div>
              <div style={{ fontSize: 13, color: 'var(--color-text-primary)', lineHeight: 1.6 }}>{morningBrief}</div>
            </div>
          </div>
        </div>
      )}

      {/* Market Status Banner */}
      {loading ? (
        <div className="skeleton-card animate-fade-in" style={{ marginBottom: 16, height: 72 }}>
          <div className="skeleton" style={{ height: '100%', borderRadius: 8 }} />
        </div>
      ) : regime && (
        <div className="card animate-fade-in-up" style={{ marginBottom: 16, borderColor: regimeColor }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <RegimeIcon size={28} color={regimeColor} />
            <div>
              <div style={{ fontWeight: 700, fontSize: 18, color: regimeColor }}>
                Market is {regime.regime}
              </div>
              <div style={{ color: 'var(--color-text-secondary)', fontSize: 13, display: 'flex', alignItems: 'center', gap: 8, marginTop: 2 }}>
                Confidence: {Math.round((regime.confidence || 0) * 100)}%
                &nbsp;·&nbsp;
                <span className={`live-dot ${regime.is_market_open ? '' : 'closed'}`} />
                {regime.is_market_open ? 'Market Open' : 'Market Closed'}
              </div>
            </div>
            {regime.signals && regime.signals.slice(0, 2).map((s, i) => (
              <div key={i} style={{ marginLeft: i === 0 ? 'auto' : 0, fontSize: 12, textAlign: 'right' }}>
                <span style={{ color: s.direction === 'bullish' ? 'var(--color-bullish)' : s.direction === 'bearish' ? 'var(--color-bearish)' : 'var(--color-neutral)' }}>
                  {s.source}
                </span>
                <div style={{ color: 'var(--color-text-muted)' }}>{s.detail.slice(0, 60)}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Market Events */}
      {events.length > 0 && (
        <div style={{ marginBottom: 16, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {events.map((e, i) => (
            <div key={i} className={`card animate-fade-in-up stagger-${Math.min(i + 1, 6)}`} style={{ flex: '1 1 200px', padding: '10px 14px', borderColor: e.impact === 'HIGH' || e.impact === 'VERY_HIGH' ? 'var(--color-neutral)' : 'var(--color-border)', opacity: 0 }}>
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
        {loading ? (
          Array.from({ length: 6 }).map((_, i) => <SkeletonIndexCard key={i} />)
        ) : (
          indices.slice(0, 6).map((idx, i) => {
            const isUp = idx.change_pct >= 0
            const color = isUp ? 'var(--color-bullish)' : 'var(--color-bearish)'
            return (
              <div key={idx.symbol} className={`card animate-fade-in-up stagger-${Math.min(i + 1, 6)}`} style={{ opacity: 0, cursor: 'pointer', transition: 'border-color 0.2s ease, transform 0.2s ease, box-shadow 0.2s ease' }}
                onMouseEnter={e => { (e.currentTarget as HTMLDivElement).style.transform = 'translateY(-3px)'; (e.currentTarget as HTMLDivElement).style.boxShadow = '0 8px 24px rgba(0,0,0,0.2)' }}
                onMouseLeave={e => { (e.currentTarget as HTMLDivElement).style.transform = ''; (e.currentTarget as HTMLDivElement).style.boxShadow = '' }}
              >
                <div style={{ fontSize: 12, color: 'var(--color-text-muted)', marginBottom: 4, display: 'flex', alignItems: 'center', gap: 6 }}>
                  {idx.name}
                  <span className={`live-dot ${regime?.is_market_open ? '' : 'closed'}`} style={{ marginLeft: 'auto' }} />
                </div>
                <div style={{ fontSize: 22, fontWeight: 700, fontFamily: 'var(--font-mono)' }}>
                  <AnimatedNumber value={idx.price} decimals={2} duration={600} />
                </div>
                <div style={{ fontSize: 14, marginTop: 4, color, fontWeight: 600 }}>
                  {isUp ? '▲' : '▼'} <AnimatedNumber value={Math.abs(idx.change_pct)} decimals={2} suffix="%" duration={700} />
                  &nbsp;(<AnimatedNumber value={idx.change} decimals={2} prefix={idx.change >= 0 ? '+' : ''} duration={700} />)
                </div>
                <div style={{ marginTop: 7, fontSize: 10, color: 'var(--color-text-muted)' }} title={idx.source}>
                  {idx.data_status === 'exchange_feed' ? 'Exchange feed' : 'Provider fallback'}
                  {idx.timestamp ? ` · ${idx.timestamp}` : ''}
                </div>
              </div>
            )
          })
        )}
      </div>

      <div className="grid-2" style={{ gap: 20 }}>
        {/* Sector Heatmap */}
        <div className="card">
          <div className="card-header">
            <span className="card-title"><Activity size={16} style={{ marginRight: 6 }} />Sector Rotation</span>
          </div>
          {sectors.length === 0 && <div className="empty-state">Loading sector data…</div>}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {sectors.map((s, i) => (
              <SectorHeatTile key={i} name={s.name} change_pct={s.change_pct} index={i} />
            ))}
          </div>
        </div>

        {/* India Intelligence */}
        <div className="card">
          <div className="card-header">
            <span className="card-title"><Globe size={16} style={{ marginRight: 6 }} />India Intelligence</span>
            {vix && <AIScoreRing score={Math.max(0, Math.min(100, Math.round((1 - (vix.vix - 10) / 30) * 100)))} label="Calm" />}
          </div>
          {vix && (
            <div style={{ marginBottom: 16, padding: '12px', background: 'var(--color-bg-secondary)', borderRadius: 8, display: 'flex', alignItems: 'center', gap: 16 }}>
              <div>
                <div style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>India VIX (Fear Gauge)</div>
                <div style={{ fontSize: 28, fontWeight: 700, fontFamily: 'var(--font-mono)', color: vixColor }}>
                  <AnimatedNumber value={vix.vix} decimals={2} duration={900} />
                </div>
                <div style={{ fontSize: 12, color: 'var(--color-text-secondary)', marginTop: 2 }}>{vix.interpretation}</div>
              </div>
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
