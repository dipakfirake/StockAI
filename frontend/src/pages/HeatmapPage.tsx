import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { marketApi } from '../services/api'
import { Activity } from 'lucide-react'

export default function HeatmapPage() {
  const navigate = useNavigate()
  const [heatmap, setHeatmap] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function load() {
      try {
        const res = await marketApi.getHeatmap()
        setHeatmap(res.data.heatmap || [])
      } catch (err) {
        console.error("Failed to load heatmap", err)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  // Sort by market cap to determine block sizes (roughly)
  const sorted = [...heatmap].sort((a, b) => (b.market_cap || 0) - (a.market_cap || 0))

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Market Heatmap</h1>
        <p className="page-subtitle">Nifty 50 constituents sized by market cap and colored by daily change</p>
      </div>

      {loading ? (
        <div style={{ textAlign: 'center', padding: '40px 0', color: 'var(--color-text-muted)' }}>
          <Activity size={28} className="spinner" style={{ marginBottom: 12, opacity: 0.5 }} />
          <p>Loading market data...</p>
        </div>
      ) : (
        <div className="card" style={{ padding: 12 }}>
          <div style={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: 4,
            width: '100%',
            minHeight: 360,
            alignContent: 'flex-start'
          }}>
            {sorted.map(stock => {
              const flexGrow = Math.max(1, (stock.market_cap || 1e12) / 1e11)
              const flexBasis = Math.max(14, Math.min(32, flexGrow * 2)) + '%'
              const isPositive = stock.change_pct >= 0
              const absChange = Math.abs(stock.change_pct || 0)

              const intensity = Math.min(1, absChange / 3)
              let bg = isPositive
                ? `rgba(16, 185, 129, ${0.35 + (intensity * 0.5)})`
                : `rgba(239, 68, 68, ${0.35 + (intensity * 0.5)})`

              if (absChange < 0.2) {
                bg = 'var(--color-bg-tertiary)'
              }

              return (
                <div
                  key={stock.symbol}
                  onClick={() => navigate('/chart', { state: { symbol: stock.symbol } })}
                  role="button"
                  tabIndex={0}
                  style={{
                    flexGrow,
                    flexBasis,
                    background: bg,
                    borderRadius: 4,
                    padding: '8px 6px',
                    display: 'flex',
                    flexDirection: 'column',
                    justifyContent: 'center',
                    alignItems: 'center',
                    cursor: 'pointer',
                    color: absChange < 0.2 ? 'var(--color-text-primary)' : '#fff',
                    transition: 'opacity 0.15s',
                    minWidth: 74,
                    minHeight: 58,
                    overflow: 'hidden',
                    textAlign: 'center',
                  }}
                  onMouseEnter={e => e.currentTarget.style.opacity = '0.82'}
                  onMouseLeave={e => e.currentTarget.style.opacity = '1'}
                >
                  <div style={{ fontWeight: 700, fontSize: 'clamp(11px, 1.1vw, 15px)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: '100%' }}>
                    {stock.symbol.replace('.NS', '')}
                  </div>
                  <div className="mono" style={{ fontSize: 'clamp(10px, 0.95vw, 12px)', opacity: 0.92 }}>
                    {stock.change_pct > 0 ? '+' : ''}{Number(stock.change_pct || 0).toFixed(2)}%
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
