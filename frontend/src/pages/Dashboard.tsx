import { useEffect, useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { marketApi, aiApi } from '../services/api'
import { isWebSocketSupportedOnHost, fetchWsTicketUrl } from '../services/websocket'
import { useAuth } from '../AuthContext'
import { isIndexMatch } from '../components/LiveTicker'
import { formatNumber2Dec, formatISTTimestamp, cleanBriefMarkdown } from '../utils/formatters'
import { TrendingUp, TrendingDown, Minus, Activity, Globe, AlertCircle, RefreshCw } from 'lucide-react'

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
  const { user } = useAuth()
  const [indices, setIndices] = useState<Index[]>([])
  const [regime, setRegime] = useState<RegimeData | null>(null)
  const [vix, setVix] = useState<VIXData | null>(null)
  const [events, setEvents] = useState<Event[]>([])
  const [sectors, setSectors] = useState<any[]>([])
  const [morningBrief, setMorningBrief] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const reconnectTimerRef = useRef<number | null>(null)
  const navigate = useNavigate()

  useEffect(() => {
    if (!user) {
      navigate('/login')
      return
    }
    loadDashboard()
    const interval = setInterval(loadDashboard, 60000) // refresh every 60s
    return () => clearInterval(interval)
  }, [navigate, user?.id])

  // Load AI morning brief once
  useEffect(() => {
    if (!user) return
    async function fetchBrief() {
      try {
        const res = await aiApi.chat('Give me a 2-sentence market morning brief for Indian NSE markets today. Be concise, data-driven, and mention the key trend.', undefined)
        if (res.data?.reply) setMorningBrief(res.data.reply)
      } catch {
        setMorningBrief(null)
      }
    }
    fetchBrief()
  }, [user?.id])

  async function loadDashboard(manual = false) {
    if (!user) return
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

  // Real-time tick updates for indices via WebSocket (when supported)
  useEffect(() => {
    if (indices.length === 0 || !isWebSocketSupportedOnHost() || !user) return

    let isMounted = true
    let ws: WebSocket | null = null

    const scheduleReconnect = () => {
      if (!isMounted || !user || !isWebSocketSupportedOnHost()) return
      if (reconnectTimerRef.current !== null) return
      reconnectTimerRef.current = window.setTimeout(() => {
        reconnectTimerRef.current = null
        if (isMounted) {
          connectWebSocket()
        }
      }, 5000)
    }

    const connectWebSocket = async () => {
      if (!isMounted || !user || !isWebSocketSupportedOnHost()) return

      if (ws) {
        ws.onopen = null
        ws.onmessage = null
        ws.onerror = null
        ws.onclose = null
        try { ws.close() } catch (_) {}
        ws = null
      }

      const wsUrl = await fetchWsTicketUrl()
      if (!isMounted) return
      if (!wsUrl) {
        scheduleReconnect()
        return
      }

      try {
        ws = new WebSocket(wsUrl)

        ws.onopen = () => {
          if (!isMounted) return
          if (reconnectTimerRef.current !== null) {
            window.clearTimeout(reconnectTimerRef.current)
            reconnectTimerRef.current = null
          }
          if (ws && ws.readyState === WebSocket.OPEN) {
            indices.forEach(idx => {
              if (idx.symbol) {
                ws!.send(JSON.stringify({ type: 'subscribe', channel: 'market_data', symbol: idx.symbol }))
              }
            })
          }
        }

        ws.onerror = () => {
          // W3C WebSocket standard mandates onclose fires next; do not race reconnect here
        }

        ws.onclose = (event: CloseEvent) => {
          if (!isMounted) return
          if (event.code === 1008 || event.code === 4401 || event.code === 4003) {
            if (reconnectTimerRef.current !== null) {
              window.clearTimeout(reconnectTimerRef.current)
              reconnectTimerRef.current = null
            }
            console.warn('Dashboard WebSocket auth rejected (code ' + event.code + '). Halting reconnect loop.')
            return
          }
          scheduleReconnect()
        }

        ws.onmessage = (event) => {
          if (!isMounted) return
          try {
            const data = JSON.parse(event.data)
            const newPrice = Number(data.price)
            if (data.type === 'market_update' && Number.isFinite(newPrice) && newPrice > 0) {
              setIndices(prev => {
                let hasChanged = false
                const next = prev.map(idx => {
                  if (isIndexMatch(idx.symbol, idx.name, data.symbol)) {
                    const rawChange = Number(data.change)
                    const newChange = Number.isFinite(rawChange) ? rawChange : Number(idx.change ?? 0)
                    const rawPct = Number(data.change_pct !== undefined ? data.change_pct : data.change_percent)
                    const newPct = Number.isFinite(rawPct) ? rawPct : Number(idx.change_pct ?? 0)

                    if (Number(idx.price) !== newPrice || Number(idx.change) !== newChange || Number(idx.change_pct) !== newPct) {
                      hasChanged = true
                      return {
                        ...idx,
                        price: newPrice,
                        change: newChange,
                        change_pct: newPct,
                        timestamp: data.timestamp || new Date().toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
                        data_status: data.data_status || 'realtime',
                      }
                    }
                  }
                  return idx
                })
                if (hasChanged) {
                  setLastUpdated(new Date())
                  return next
                }
                return prev
              })
            }
          } catch (err) {
            console.error('WebSocket Dashboard error:', err)
          }
        }
      } catch (e) {
        console.warn('WebSocket Dashboard init skipped:', e)
        scheduleReconnect()
      }
    }

    connectWebSocket()

    return () => {
      isMounted = false
      if (reconnectTimerRef.current !== null) {
        window.clearTimeout(reconnectTimerRef.current)
        reconnectTimerRef.current = null
      }
      if (ws) {
        ws.onopen = null
        ws.onmessage = null
        ws.onerror = null
        ws.onclose = null
        try {
          if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
            ws.close()
          }
        } catch (_) {}
      }
    }
  }, [indices.length, user?.id])


  const RegimeIcon = regime?.regime === 'BULLISH' ? TrendingUp : regime?.regime === 'BEARISH' ? TrendingDown : Minus
  const regimeColor = regime?.regime === 'BULLISH' ? 'var(--color-bullish)' : regime?.regime === 'BEARISH' ? 'var(--color-bearish)' : 'var(--color-neutral)'
  const vixColor = vix ? (vix.vix > 25 ? 'var(--color-bearish)' : vix.vix < 15 ? 'var(--color-bullish)' : 'var(--color-neutral)') : 'var(--color-text-primary)'

  const cleanedBrief = cleanBriefMarkdown(morningBrief)
    .replace(/CMP:\s*N\/A\s*\|?/gi, '')
    .replace(/Best Buy:\s*N\/A\s*\|?/gi, '')
    .replace(/SL:\s*N\/A\s*\|?/gi, '')
    .replace(/Target:\s*N\/A\s*\|?/gi, '')
    .replace(/R:R:\s*N\/A\s*\|?/gi, '')
    .replace(/Execution Levels:\s*\|*\s*/gi, '')
    .replace(/NSE Market Brief\s*💎?\s*Large Cap/gi, 'Market Outlook')
    .replace(/\s*\|\s*(?=\·|$)/g, '')
    .replace(/\s{2,}/g, ' ')
    .trim()

  return (
    <div>
      <div className="page-header" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h1 className="page-title">Market Overview</h1>
          <p className="page-subtitle">NSE &amp; BSE indices, sector rotation, and volatility</p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          {lastUpdated && (
            <span style={{ fontSize: 11.5, color: 'var(--color-text-muted)' }}>
              {lastUpdated.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
            </span>
          )}
          <button
            onClick={() => loadDashboard(true)}
            className="btn btn-secondary"
            style={{ fontSize: 12.5, padding: '6px 12px', gap: 6 }}
          >
            <RefreshCw size={13} className={refreshing ? 'spin' : ''} style={{ animation: refreshing ? 'spin 0.8s linear infinite' : 'none' }} />
            Refresh
          </button>
        </div>
      </div>

      {/* Primary Index Cards First (Above the fold on Desktop & Mobile) */}
      <div className="grid-3" style={{ marginBottom: 18 }}>
        {loading ? (
          Array.from({ length: 6 }).map((_, i) => <SkeletonIndexCard key={i} />)
        ) : (
          indices.slice(0, 6).map((idx, i) => {
            const isUp = idx.change_pct >= 0
            const color = isUp ? 'var(--color-bullish)' : 'var(--color-bearish)'
            return (
              <div
                key={idx.symbol}
                onClick={() => idx.symbol && navigate('/chart', { state: { symbol: idx.symbol } })}
                className={`card animate-fade-in-up stagger-${Math.min(i + 1, 6)}`}
                style={{ opacity: 0, cursor: 'pointer', padding: '16px 18px' }}
              >
                <div style={{ fontSize: 12, color: 'var(--color-text-muted)', marginBottom: 4, display: 'flex', alignItems: 'center', gap: 6, fontWeight: 600 }}>
                  <span>{idx.name}</span>
                  <span className={`live-dot ${regime?.is_market_open ? '' : 'closed'}`} style={{ marginLeft: 'auto' }} />
                </div>
                <div className="mono" style={{ fontSize: 22, fontWeight: 700, color: 'var(--color-text-primary)' }}>
                  {formatNumber2Dec(idx.price ?? 0)}
                </div>
                <div className="mono" style={{ fontSize: 13, marginTop: 4, color, fontWeight: 600 }}>
                  {isUp ? '▲' : '▼'} {(idx.change_pct ?? 0) >= 0 ? '+' : ''}{(idx.change_pct ?? 0).toFixed(2)}%
                  <span style={{ opacity: 0.85, fontWeight: 500, marginLeft: 6 }}>
                    {(idx.change ?? 0) >= 0 ? '+' : ''}{(idx.change ?? 0).toFixed(2)}
                  </span>
                </div>
                <div style={{ marginTop: 6, fontSize: 11, color: 'var(--color-text-muted)' }}>
                  {idx.data_status === 'exchange_feed' || idx.data_status === 'realtime' ? 'Exchange feed' : 'Backup feed'}
                  {idx.timestamp ? ` · ${formatISTTimestamp(idx.timestamp)}` : ''}
                </div>
              </div>
            )
          })
        )}
      </div>

      {/* Concise Regime & Brief Strip */}
      {loading ? (
        <div className="skeleton-card animate-fade-in" style={{ marginBottom: 18, height: 68 }}>
          <div className="skeleton" style={{ height: '100%', borderRadius: 8 }} />
        </div>
      ) : (regime || cleanedBrief) && (
        <div className="card animate-fade-in-up" style={{ marginBottom: 18, borderLeft: `3px solid ${regimeColor}`, padding: '14px 18px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 10 }}>
            {regime && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <RegimeIcon size={22} color={regimeColor} />
                <div>
                  <div style={{ fontWeight: 700, fontSize: 15, color: regimeColor }}>
                    Market Regime: {regime.regime}
                  </div>
                  <div style={{ color: 'var(--color-text-muted)', fontSize: 12, display: 'flex', alignItems: 'center', gap: 8, marginTop: 2 }}>
                    Confidence {Math.round((regime.confidence || 0) * 100)}%
                    <span>·</span>
                    <span className={`live-dot ${regime.is_market_open ? '' : 'closed'}`} />
                    <span>{regime.is_market_open ? 'NSE Open' : 'Market Closed'}</span>
                  </div>
                </div>
              </div>
            )}
          </div>
          {cleanedBrief && (
            <div style={{ marginTop: regime ? 10 : 0, paddingTop: regime ? 10 : 0, borderTop: regime ? '1px solid var(--color-border)' : 'none', fontSize: 13, color: 'var(--color-text-secondary)', lineHeight: 1.55 }}>
              {cleanedBrief}
            </div>
          )}
        </div>
      )}

      {/* Upcoming Market Events */}
      {events.length > 0 && (
        <div style={{ marginBottom: 18, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {events.map((e, i) => (
            <div key={i} className={`card animate-fade-in-up stagger-${Math.min(i + 1, 6)}`} style={{ flex: '1 1 220px', padding: '10px 14px', borderColor: e.impact === 'HIGH' || e.impact === 'VERY_HIGH' ? 'var(--color-neutral)' : 'var(--color-border)', opacity: 0 }}>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <AlertCircle size={15} color={e.impact === 'VERY_HIGH' ? 'var(--color-bearish)' : 'var(--color-neutral)'} />
                <span style={{ fontWeight: 600, fontSize: 13 }}>{e.name}</span>
                <span style={{ marginLeft: 'auto', fontSize: 10.5, fontWeight: 700, background: 'rgba(245,158,11,0.15)', color: 'var(--color-neutral)', padding: '2px 8px', borderRadius: 10 }}>{e.impact}</span>
              </div>
              <div style={{ fontSize: 12, color: 'var(--color-text-muted)', marginTop: 4 }}>{e.description.slice(0, 100)}</div>
            </div>
          ))}
        </div>
      )}

      <div className="grid-2" style={{ gap: 18 }}>
        {/* Sector Rotation */}
        <div className="card">
          <div className="card-header">
            <span className="card-title" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <Activity size={16} /> Sector Rotation
            </span>
          </div>
          {sectors.length === 0 && <div className="empty-state">Loading sector data…</div>}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {sectors.map((s, i) => (
              <SectorHeatTile key={i} name={s.name} change_pct={s.change_pct} index={i} />
            ))}
          </div>
        </div>

        {/* Volatility & Regime Drivers (Single non-duplicated location) */}
        <div className="card">
          <div className="card-header">
            <span className="card-title" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <Globe size={16} /> Market Drivers
            </span>
            {vix && <AIScoreRing score={Math.max(0, Math.min(100, Math.round((1 - (vix.vix - 10) / 30) * 100)))} label="Calm" />}
          </div>
          {vix && (
            <div style={{ marginBottom: 14, padding: '12px', background: 'var(--color-bg-secondary)', borderRadius: 8 }}>
              <div style={{ fontSize: 11.5, color: 'var(--color-text-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.4px' }}>India VIX</div>
              <div className="mono" style={{ fontSize: 26, fontWeight: 700, color: vixColor }}>
                {(vix.vix ?? 0).toFixed(2)}
              </div>
              <div style={{ fontSize: 12, color: 'var(--color-text-secondary)', marginTop: 2 }}>{vix.interpretation}</div>
            </div>
          )}
          {regime?.signals && regime.signals.map((s, i) => (
            <div key={i} style={{ display: 'flex', gap: 10, alignItems: 'flex-start', padding: '8px 0', borderBottom: i < regime.signals!.length - 1 ? '1px solid var(--color-border)' : 'none', flexWrap: 'wrap' }}>
              <span style={{
                fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 10,
                background: s.direction === 'bullish' ? 'var(--color-bullish-dim)' : s.direction === 'bearish' ? 'var(--color-bearish-dim)' : 'rgba(100,116,139,0.2)',
                color: s.direction === 'bullish' ? 'var(--color-bullish)' : s.direction === 'bearish' ? 'var(--color-bearish)' : 'var(--color-text-secondary)',
              }}>
                {s.source}
              </span>
              <span style={{ fontSize: 12, color: 'var(--color-text-secondary)', lineHeight: 1.4, flex: '1 1 180px' }}>{s.detail.slice(0, 110)}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
