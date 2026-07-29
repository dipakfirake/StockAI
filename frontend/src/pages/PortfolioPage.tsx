import { useEffect, useState } from 'react'
import { portfolioApi } from '../services/api'
import { PieChart, TrendingUp, TrendingDown } from 'lucide-react'

export default function PortfolioPage() {
  const [portfolio, setPortfolio] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => { loadPortfolio() }, [])

  async function loadPortfolio() {
    try {
      const res = await portfolioApi.get()
      setPortfolio(res.data)
    } finally { setLoading(false) }
  }

  if (loading) return <div className="loading">Loading portfolio…</div>

  const totalPnlColor = portfolio?.total_pnl >= 0 ? 'var(--color-bullish)' : 'var(--color-bearish)'

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Portfolio</h1>
        <p className="page-subtitle">Paper portfolio summary — realized + unrealized PnL, win rate, allocation</p>
      </div>

      {portfolio && (
        <>
          {/* Summary Cards */}
          <div className="grid-4" style={{ marginBottom: 24 }}>
            <div className="card">
              <div style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>Current Value</div>
              <div style={{ fontSize: 24, fontWeight: 700, fontFamily: 'var(--font-mono)' }}>₹{portfolio.current_value?.toLocaleString('en-IN')}</div>
              <div style={{ fontSize: 11, color: 'var(--color-text-muted)', marginTop: 2 }}>Started ₹{portfolio.initial_capital?.toLocaleString('en-IN')}</div>
            </div>
            <div className="card">
              <div style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>Total PnL</div>
              <div style={{ fontSize: 24, fontWeight: 700, fontFamily: 'var(--font-mono)', color: totalPnlColor }}>
                {portfolio.total_pnl >= 0 ? '+' : ''}₹{portfolio.total_pnl?.toFixed(2)}
              </div>
              <div style={{ fontSize: 13, color: totalPnlColor }}>{portfolio.total_pnl_pct >= 0 ? '+' : ''}{portfolio.total_pnl_pct?.toFixed(2)}%</div>
            </div>
            <div className="card">
              <div style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>Win Rate</div>
              <div style={{ fontSize: 24, fontWeight: 700 }}>{Math.round(portfolio.win_rate * 100)}%</div>
              <div style={{ fontSize: 11, color: 'var(--color-text-muted)', marginTop: 2 }}>{portfolio.closed_trades} closed trades</div>
            </div>
            <div className="card">
              <div style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>Total STT Tax Paid</div>
              <div style={{ fontSize: 24, fontWeight: 700, color: 'var(--color-text-muted)' }}>₹{portfolio.total_stt_paid?.toFixed(2) || '0.00'}</div>
            </div>
            <div className="card">
              <div style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>Open / Pending</div>
              <div style={{ fontSize: 24, fontWeight: 700 }}>{portfolio.open_trades} / {portfolio.pending_orders}</div>
              <div style={{ fontSize: 11, color: 'var(--color-text-muted)', marginTop: 2 }}>Unrealized: ₹{portfolio.unrealized_pnl?.toFixed(2)}</div>
            </div>
          </div>

          {/* Allocation Table */}
          <div className="card">
            <div className="card-header">
              <span className="card-title"><PieChart size={15} style={{ marginRight: 6 }} />Position Allocation</span>
            </div>
            {portfolio.allocation?.length === 0 && <div className="empty-state">No open positions. Place paper trades to see allocation.</div>}
            {portfolio.allocation?.length > 0 && (
              <table className="table">
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th>Direction</th>
                    <th>Product</th>
                    <th>Qty</th>
                    <th>Entry</th>
                    <th>Current</th>
                    <th>Unrealized PnL</th>
                    <th>Value</th>
                    <th>Weight</th>
                  </tr>
                </thead>
                <tbody>
                  {portfolio.allocation.map((a: any, i: number) => (
                    <tr key={i}>
                      <td className="mono" style={{ fontWeight: 600 }}>{a.symbol}</td>
                      <td><span className={`badge ${a.direction === 'BUY' ? 'badge-buy' : 'badge-sell'}`}>{a.direction}</span></td>
                      <td><span className="badge badge-secondary">{a.product_type}</span></td>
                      <td>{a.quantity}</td>
                      <td className="mono">₹{a.entry_price?.toFixed(2)}</td>
                      <td className="mono">₹{a.current_price?.toFixed(2)}</td>
                      <td className={a.unrealized_pnl >= 0 ? 'positive mono' : 'negative mono'}>
                        {a.unrealized_pnl >= 0 ? '+' : ''}₹{a.unrealized_pnl?.toFixed(2)}
                      </td>
                      <td className="mono">₹{a.value?.toLocaleString('en-IN')}</td>
                      <td>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          <div style={{ width: 60, height: 6, background: 'var(--color-bg-secondary)', borderRadius: 3, overflow: 'hidden' }}>
                            <div style={{ width: `${a.weight_pct}%`, height: '100%', background: a.unrealized_pnl >= 0 ? 'var(--color-bullish)' : 'var(--color-bearish)', borderRadius: 3 }} />
                          </div>
                          <span style={{ fontSize: 12, color: 'var(--color-text-secondary)' }}>{a.weight_pct}%</span>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}
    </div>
  )
}
