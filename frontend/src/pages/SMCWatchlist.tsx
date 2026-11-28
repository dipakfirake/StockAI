import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Target, Activity, ShieldAlert, Zap, TrendingUp, TrendingDown, RefreshCw, ExternalLink } from 'lucide-react'
import api from '../services/api'
import { formatINR, formatISTTimestamp } from '../utils/formatters'

// TradePlan removed, replaced by multi-timeframe POI approach

interface Confluence {
  score: number
  factors: string[]
  grade: string
}

interface FVG {
  type: string
  top: number
  bottom: number
  gap_size: number
  gap_pct: number
  time: string
  confluence: Confluence
}

interface SMCZoneData {
  fvgs: FVG[]
  last_price: number
  generated_at: string
}

const gradeColors: Record<string, string> = {
  'A+': '#10b981',
  'A': '#22c55e',
  'B': '#f59e0b',
  'C': '#ef4444',
}

export default function SMCWatchlist() {
  const navigate = useNavigate()
  const [zones, setZones] = useState<Record<string, SMCZoneData>>({})
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    fetchInstitutionalZones()
  }, [])

  async function fetchInstitutionalZones() {
    setLoading(true)
    try {
      const res = await api.get('/scanner/institutional')
      if (res.data && res.data.zones) {
        setZones(res.data.zones)
      }
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
        <div style={{ minWidth: 0 }}>
          <h1 className="page-title" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Target size={22} /> Institutional Liquidity Watchlist
          </h1>
          <p className="page-subtitle">Daily Smart Money Fair Value Gaps monitored for 15-minute reversal setups</p>
        </div>
        <button onClick={fetchInstitutionalZones} className="btn btn-primary" disabled={loading} style={{ flexShrink: 0 }}>
          <RefreshCw size={15} className={loading ? 'spin' : ''} /> {loading ? 'Scanning…' : 'Refresh'}
        </button>
      </div>

      {loading ? (
        <div className="text-center" style={{ padding: 40, color: 'var(--color-text-muted)' }}>Scanning daily candles for institutional liquidity zones…</div>
      ) : Object.keys(zones).length === 0 ? (
        <div className="card text-center" style={{ padding: 40 }}>
          <ShieldAlert size={28} style={{ color: 'var(--color-text-muted)', marginBottom: 12 }} />
          <h3>No Institutional Zones Found</h3>
          <p style={{ color: 'var(--color-text-muted)', fontSize: 13 }}>No high-probability FVG setups detected for today.</p>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(min(100%, 320px), 1fr))', gap: '16px' }}>
          {Object.entries(zones).map(([symbol, data]) => (
            <div key={symbol} className="card" style={{ borderTop: '3px solid var(--color-accent-blue)', padding: 18 }}>
              {/* Header */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 14, gap: 8 }}>
                <div>
                  <h2 style={{ margin: 0, fontSize: '1.2rem' }}>{symbol.replace('.NS', '')}</h2>
                  <span className="mono" style={{ fontSize: '0.84rem', color: 'var(--color-text-muted)' }}>LTP {formatINR(data.last_price)}</span>
                </div>
                <button
                  type="button"
                  onClick={() => navigate('/chart', { state: { symbol } })}
                  className="btn btn-secondary"
                  style={{ fontSize: 12, padding: '5px 10px' }}
                >
                  <ExternalLink size={13} /> Chart
                </button>
              </div>

              {/* FVG Zones */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {data.fvgs.map((fvg, idx) => (
                  <div key={idx} style={{
                    padding: 12,
                    backgroundColor: 'var(--color-bg-secondary)',
                    borderRadius: 8,
                    borderLeft: `3px solid ${fvg.type === 'bullish_fvg' ? 'var(--color-bullish)' : 'var(--color-bearish)'}`
                  }}>
                    {/* FVG Type + Grade */}
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6, gap: 8, flexWrap: 'wrap' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        {fvg.type === 'bullish_fvg'
                          ? <TrendingUp size={15} color="var(--color-bullish)" />
                          : <TrendingDown size={15} color="var(--color-bearish)" />}
                        <strong style={{ fontSize: '0.88rem' }}>{fvg.type === 'bullish_fvg' ? 'Bullish FVG' : 'Bearish FVG'}</strong>
                      </div>
                      <span style={{
                        padding: '2px 8px',
                        borderRadius: 10,
                        fontSize: '0.75rem',
                        fontWeight: 700,
                        backgroundColor: `${gradeColors[fvg.confluence?.grade] || '#666'}22`,
                        color: gradeColors[fvg.confluence?.grade] || '#666',
                      }}>
                        Grade {fvg.confluence?.grade} · {fvg.confluence?.score}/100
                      </span>
                    </div>

                    {/* Zone + Gap % */}
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', marginBottom: 6, flexWrap: 'wrap', gap: 6 }}>
                      <span className="mono">Zone: <strong>{formatINR(fvg.bottom)} – {formatINR(fvg.top)}</strong></span>
                      <span className="mono" style={{ color: 'var(--color-text-muted)' }}>Gap {Number(fvg.gap_pct || 0).toFixed(2)}%</span>
                    </div>

                    {/* Zone Proximity Indicator */}
                    <div style={{
                      marginTop: 6,
                      padding: '7px 10px',
                      borderRadius: 6,
                      backgroundColor: data.last_price >= fvg.bottom && data.last_price <= fvg.top
                        ? 'var(--color-bullish-dim)'
                        : 'var(--color-bg-card)',
                      border: data.last_price >= fvg.bottom && data.last_price <= fvg.top
                        ? '1px solid rgba(16,185,129,0.35)'
                        : '1px solid var(--color-border)',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 7,
                      fontSize: '0.8rem'
                    }}>
                      {data.last_price >= fvg.bottom && data.last_price <= fvg.top ? (
                        <>
                          <Zap size={14} color="var(--color-bullish)" />
                          <span style={{ color: 'var(--color-bullish)', fontWeight: 600 }}>Price in zone · Watching 15m reversal</span>
                        </>
                      ) : (
                        <>
                          <Target size={14} color="var(--color-text-muted)" />
                          <span style={{ color: 'var(--color-text-muted)' }}>
                            {fvg.type === 'bullish_fvg'
                              ? `Needs ₹${Math.abs(data.last_price - fvg.top).toFixed(2)} pullback`
                              : `Needs ₹${Math.abs(fvg.bottom - data.last_price).toFixed(2)} upside`}
                          </span>
                        </>
                      )}
                    </div>

                    {/* Confluence Factors (deduplicate redundant gap strings) */}
                    {fvg.confluence?.factors?.length > 0 && (
                      <div style={{ marginTop: 8, display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                        {fvg.confluence.factors
                          .filter((f) => !/\bgap\b/i.test(f))
                          .map((f, fi) => (
                            <span key={fi} style={{
                              padding: '2px 8px',
                              borderRadius: 6,
                              backgroundColor: 'var(--color-bg-card)',
                              border: '1px solid var(--color-border)',
                              fontSize: '0.72rem',
                              color: 'var(--color-text-muted)',
                            }}>
                              {f}
                            </span>
                          ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>

              <div style={{ fontSize: '0.72rem', color: 'var(--color-text-muted)', marginTop: 10, textAlign: 'right' }}>
                Updated {formatISTTimestamp(data.generated_at)}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
