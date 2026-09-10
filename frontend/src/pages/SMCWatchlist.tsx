import { useState, useEffect } from 'react'
import { Target, Activity, ShieldAlert, Zap, TrendingUp, TrendingDown, RefreshCw } from 'lucide-react'
import api from '../services/api'

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
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h1 className="page-title"><Target size={24} style={{ marginRight: 8, display: 'inline' }} /> Institutional Liquidity Watchlist</h1>
          <p className="page-subtitle">Multi-Timeframe SMC: Daily Points of Interest (POI) zones. The Auto-Trader monitors these for 15-minute reversals.</p>
        </div>
        <button onClick={fetchInstitutionalZones} className="btn btn-primary" disabled={loading} style={{ flexShrink: 0 }}>
          <RefreshCw size={16} className={loading ? 'spin' : ''} /> {loading ? 'Scanning...' : 'Refresh Zones'}
        </button>
      </div>

      {loading ? (
        <div className="text-center" style={{ padding: 40 }}>Scanning daily candles for institutional volume traps...</div>
      ) : Object.keys(zones).length === 0 ? (
        <div className="card text-center" style={{ padding: 40 }}>
          <ShieldAlert size={32} style={{ color: 'var(--color-text-muted)', marginBottom: 16 }} />
          <h3>No Institutional Zones Found</h3>
          <p className="text-muted">The AI did not find any high-probability FVG setups for today.</p>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(380px, 1fr))', gap: '20px' }}>
          {Object.entries(zones).map(([symbol, data]) => (
            <div key={symbol} className="card" style={{ borderTop: '4px solid #8b5cf6', padding: 20 }}>
              {/* Header */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                <div>
                  <h2 style={{ margin: 0, fontSize: '1.3rem' }}>{symbol.replace('.NS', '')}</h2>
                  <span style={{ fontSize: '0.85rem', color: 'var(--color-text-muted)' }}>LTP: ₹{data.last_price}</span>
                </div>
                <span className="badge" style={{ backgroundColor: 'rgba(139, 92, 246, 0.2)', color: '#a78bfa', padding: '4px 10px' }}>
                  <Activity size={12} style={{ marginRight: 4 }} /> SMC Target
                </span>
              </div>

              {/* FVG Zones */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                {data.fvgs.map((fvg, idx) => (
                  <div key={idx} style={{
                    padding: 14,
                    backgroundColor: 'rgba(255,255,255,0.03)',
                    borderRadius: 10,
                    borderLeft: `4px solid ${fvg.type === 'bullish_fvg' ? 'var(--color-bullish)' : 'var(--color-bearish)'}`
                  }}>
                    {/* FVG Type + Grade */}
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        {fvg.type === 'bullish_fvg'
                          ? <TrendingUp size={16} color="var(--color-bullish)" />
                          : <TrendingDown size={16} color="var(--color-bearish)" />}
                        <strong style={{ fontSize: '0.95rem' }}>{fvg.type === 'bullish_fvg' ? 'BULLISH FVG' : 'BEARISH FVG'}</strong>
                      </div>
                      <span style={{
                        padding: '2px 10px',
                        borderRadius: 12,
                        fontSize: '0.8rem',
                        fontWeight: 700,
                        backgroundColor: `${gradeColors[fvg.confluence?.grade] || '#666'}22`,
                        color: gradeColors[fvg.confluence?.grade] || '#666',
                      }}>
                        Grade {fvg.confluence?.grade} ({fvg.confluence?.score}/100)
                      </span>
                    </div>

                    {/* Zone + Gap % */}
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.9rem', marginBottom: 6 }}>
                      <span>Zone: <strong>₹{fvg.bottom} – ₹{fvg.top}</strong></span>
                      <span style={{ color: 'var(--color-text-muted)' }}>Gap: {fvg.gap_pct}%</span>
                    </div>

                    {/* Zone Proximity Indicator */}
                    <div style={{
                      marginTop: 8,
                      padding: '8px 10px',
                      borderRadius: 6,
                      backgroundColor: data.last_price >= fvg.bottom && data.last_price <= fvg.top 
                        ? 'rgba(16,185,129,0.1)' 
                        : 'rgba(255,255,255,0.05)',
                      border: data.last_price >= fvg.bottom && data.last_price <= fvg.top 
                        ? '1px solid rgba(16,185,129,0.3)'
                        : '1px solid transparent',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 8,
                      fontSize: '0.85rem'
                    }}>
                      {data.last_price >= fvg.bottom && data.last_price <= fvg.top ? (
                        <>
                          <Zap size={14} color="#10b981" className="pulse" />
                          <span style={{ color: '#10b981', fontWeight: 600 }}>PRICE IN ZONE: Monitoring 15m for Reversal</span>
                        </>
                      ) : (
                        <>
                          <Target size={14} color="var(--color-text-muted)" />
                          <span style={{ color: 'var(--color-text-muted)' }}>
                            {fvg.type === 'bullish_fvg' 
                              ? `Needs to drop ₹${(data.last_price - fvg.top).toFixed(2)} to enter zone`
                              : `Needs to rise ₹${(fvg.bottom - data.last_price).toFixed(2)} to enter zone`}
                          </span>
                        </>
                      )}
                    </div>

                    {/* Confluence Factors */}
                    {fvg.confluence?.factors?.length > 0 && (
                      <div style={{ marginTop: 8, display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                        {fvg.confluence.factors.map((f, fi) => (
                          <span key={fi} style={{
                            padding: '2px 8px',
                            borderRadius: 6,
                            backgroundColor: 'rgba(255,255,255,0.05)',
                            fontSize: '0.75rem',
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

              <div style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', marginTop: 12, textAlign: 'right' }}>
                Generated: {new Date(data.generated_at).toLocaleTimeString()}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
