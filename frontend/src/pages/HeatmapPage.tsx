import { useEffect, useState } from 'react'
import { marketApi } from '../services/api'
import { Activity } from 'lucide-react'

export default function HeatmapPage() {
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
        <p className="page-subtitle">Nifty 50 visualizer based on Market Cap and Daily Change</p>
      </div>

      {loading ? (
        <div style={{ textAlign: 'center', padding: '40px 0', color: 'var(--color-text-muted)' }}>
          <Activity size={32} className="spinner" style={{ marginBottom: 16, opacity: 0.5 }} />
          <p>Loading market data...</p>
        </div>
      ) : (
        <div className="card" style={{ padding: 16 }}>
          <div style={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: 4,
            width: '100%',
            height: 'calc(100vh - 200px)',
            minHeight: 500,
            alignContent: 'flex-start'
          }}>
            {sorted.map(stock => {
              // Basic treemap logic using flex-grow
              const flexGrow = Math.max(1, (stock.market_cap || 1e12) / 1e11)
              const flexBasis = Math.max(10, Math.min(30, flexGrow * 2)) + '%'
              const isPositive = stock.change_pct >= 0
              const absChange = Math.abs(stock.change_pct || 0)
              
              // Color intensity based on % change
              const intensity = Math.min(1, absChange / 3) // Cap at 3%
              let bg = isPositive 
                ? `rgba(16, 185, 129, ${0.4 + (intensity * 0.6)})`
                : `rgba(239, 68, 68, ${0.4 + (intensity * 0.6)})`
                
              if (absChange < 0.2) {
                bg = 'var(--color-bg-tertiary)'
              }

              return (
                <a 
                  key={stock.symbol}
                  href={`/chart/${stock.symbol}`}
                  style={{
                    flexGrow,
                    flexBasis,
                    background: bg,
                    borderRadius: 4,
                    padding: 8,
                    display: 'flex',
                    flexDirection: 'column',
                    justifyContent: 'center',
                    alignItems: 'center',
                    textDecoration: 'none',
                    color: '#fff',
                    transition: 'transform 0.2s, opacity 0.2s',
                    minWidth: 80,
                    minHeight: 60,
                    overflow: 'hidden'
                  }}
                  onMouseEnter={e => e.currentTarget.style.opacity = '0.8'}
                  onMouseLeave={e => e.currentTarget.style.opacity = '1'}
                >
                  <div style={{ fontWeight: 700, fontSize: 'clamp(11px, 1.2vw, 16px)' }}>
                    {stock.symbol.replace('.NS', '')}
                  </div>
                  <div style={{ fontSize: 'clamp(10px, 1vw, 13px)', opacity: 0.9 }}>
                    {stock.change_pct > 0 ? '+' : ''}{stock.change_pct.toFixed(2)}%
                  </div>
                </a>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
