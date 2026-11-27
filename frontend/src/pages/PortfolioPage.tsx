import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { portfolioApi, paperTradingApi } from '../services/api'
import { PieChart, TrendingUp, TrendingDown, Clock, Calendar, Eye, HelpCircle, ArrowRight, Bot, User, History } from 'lucide-react'
import HoldingDetailModal from '../components/HoldingDetailModal'
import { formatINR, formatNumber2Dec, getPnlColor, getPnlClass, getPnlSign } from '../utils/formatters'

export default function PortfolioPage() {
  const navigate = useNavigate()
  const [portfolio, setPortfolio] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [selectedHolding, setSelectedHolding] = useState<any | null>(null)
  const [soldFilter, setSoldFilter] = useState<'ALL' | 'TODAY' | 'AUTO' | 'USER'>('ALL')

  useEffect(() => { loadPortfolio() }, [])

  async function loadPortfolio() {
    try {
      const res = await portfolioApi.get()
      setPortfolio(res.data)
    } finally { setLoading(false) }
  }

  async function handleCancelPendingOrder(tradeId: string) {
    if (!confirm('Cancel this pending order?')) return
    await paperTradingApi.close(tradeId)
    await loadPortfolio()
  }

  if (loading) return <div className="loading">Loading portfolio…</div>

  const totalDayPnl = portfolio?.total_day_pnl ?? 0
  const totalDayPnlBorder = totalDayPnl > 0.0001
    ? 'rgba(16, 185, 129, 0.4)'
    : totalDayPnl < -0.0001
    ? 'rgba(239, 68, 68, 0.4)'
    : 'rgba(255, 255, 255, 0.2)'

  // Sum of holdings current market value
  const holdingsMarketValue = portfolio?.total_current_value ?? portfolio?.allocation?.reduce((sum: number, a: any) => sum + (a.value || 0), 0) ?? portfolio?.current_value

  return (
    <div>
      <div className="page-header" style={{ marginBottom: 20 }}>
        <h1 className="page-title">Portfolio & Holdings</h1>
        <p className="page-subtitle">Real-time paper portfolio analytics — holding duration, day's P&L, return on buying, and allocation</p>
      </div>

      {portfolio && (
        <>
          {/* Summary Cards Grid */}
          <div style={{ 
            display: 'grid', 
            gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))', 
            gap: 16, 
            marginBottom: 24 
          }}>
            {/* 1. Holdings Current Market Value */}
            <div className="card">
              <div style={{ fontSize: 12, color: 'var(--color-text-muted)', marginBottom: 4, textTransform: 'uppercase', fontWeight: 600 }}>
                Holdings Current Value
              </div>
              <div style={{ fontSize: 24, fontWeight: 700, fontFamily: 'var(--font-mono)', color: 'var(--color-text-primary)' }}>
                {formatINR(holdingsMarketValue)}
              </div>
              <div style={{ fontSize: 11, color: 'var(--color-text-muted)', marginTop: 4 }}>
                Market value of {portfolio.allocation?.length || 0} open positions
              </div>
            </div>

            {/* 2. Total Invested (Holdings) */}
            <div className="card">
              <div style={{ fontSize: 12, color: 'var(--color-text-muted)', marginBottom: 4, textTransform: 'uppercase', fontWeight: 600 }}>
                Total Invested (Holdings)
              </div>
              <div style={{ fontSize: 24, fontWeight: 700, fontFamily: 'var(--font-mono)', color: 'var(--color-text-primary)' }}>
                {formatINR(portfolio.total_invested || 0)}
              </div>
              <div style={{ fontSize: 11, color: 'var(--color-text-muted)', marginTop: 4 }}>
                Open positions capital deployed
              </div>
            </div>

            {/* 3. Today's Day P&L (All Stocks) */}
            <div className="card" style={{ border: `1px solid ${totalDayPnlBorder}` }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
                <span style={{ fontSize: 12, color: 'var(--color-text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>
                  Today's Day P&L (All Stocks)
                </span>
                <Clock size={14} style={{ color: getPnlColor(totalDayPnl) }} />
              </div>
              <div style={{ fontSize: 24, fontWeight: 700, fontFamily: 'var(--font-mono)', color: getPnlColor(totalDayPnl) }}>
                {getPnlSign(totalDayPnl)}{formatINR(totalDayPnl)}
              </div>
              <div style={{ fontSize: 12, fontWeight: 600, color: getPnlColor(portfolio.total_day_pnl_pct), marginTop: 4 }}>
                {getPnlSign(portfolio.total_day_pnl_pct)}{(portfolio.total_day_pnl_pct ?? 0).toFixed(2)}% Today
              </div>
            </div>

            {/* 4. Total Overall P&L */}
            <div className="card">
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
                <span style={{ fontSize: 12, color: 'var(--color-text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>
                  Total P&L (All Time)
                </span>
                {portfolio.total_pnl > 0.0001 ? (
                  <TrendingUp size={14} style={{ color: '#10b981' }} />
                ) : portfolio.total_pnl < -0.0001 ? (
                  <TrendingDown size={14} style={{ color: '#ef4444' }} />
                ) : (
                  <Clock size={14} style={{ color: '#ffffff' }} />
                )}
              </div>
              <div style={{ fontSize: 24, fontWeight: 700, fontFamily: 'var(--font-mono)', color: getPnlColor(portfolio.total_pnl) }}>
                {getPnlSign(portfolio.total_pnl)}{formatINR(portfolio.total_pnl)}
              </div>
              <div style={{ fontSize: 12, fontWeight: 600, color: getPnlColor(portfolio.total_pnl_pct), marginTop: 4 }}>
                {getPnlSign(portfolio.total_pnl_pct)}{portfolio.total_pnl_pct?.toFixed(2)}% Total Return
              </div>
            </div>

            {/* 5. Account Net Equity */}
            <div className="card">
              <div style={{ fontSize: 12, color: 'var(--color-text-muted)', marginBottom: 4, textTransform: 'uppercase', fontWeight: 600 }}>
                Account Net Equity
              </div>
              <div style={{ fontSize: 24, fontWeight: 700, fontFamily: 'var(--font-mono)' }}>
                {formatINR(portfolio.current_value)}
              </div>
              <div style={{ fontSize: 11, color: 'var(--color-text-muted)', marginTop: 4 }}>
                Virtual balance (Started: {formatINR(portfolio.initial_capital)})
              </div>
            </div>

            {/* 6. Open / Pending */}
            <div
              className="card"
              onClick={() => navigate(portfolio.pending_orders > 0 ? '/paper-trading?tab=orders' : '/paper-trading')}
              style={{ cursor: 'pointer' }}
              title="Click to inspect Orders & Positions"
            >
              <div style={{ fontSize: 12, color: 'var(--color-text-muted)', marginBottom: 4, textTransform: 'uppercase', fontWeight: 600, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span>Open Positions / Orders</span>
                <ArrowRight size={13} />
              </div>
              <div style={{ fontSize: 24, fontWeight: 700 }}>
                {portfolio.open_trades} <span style={{ fontSize: 16, color: portfolio.pending_orders > 0 ? '#fbbf24' : 'var(--color-text-muted)', fontWeight: portfolio.pending_orders > 0 ? 600 : 400 }}>/ {portfolio.pending_orders} pending</span>
              </div>
              <div style={{ fontSize: 11, marginTop: 4, color: getPnlColor(portfolio.unrealized_pnl) }}>
                Unrealized: {getPnlSign(portfolio.unrealized_pnl)}{formatINR(portfolio.unrealized_pnl)}
              </div>
            </div>
          </div>

          {/* Allocation & Stock Holdings Table */}
          <div className="card">
            <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span className="card-title" style={{ display: 'flex', alignItems: 'center' }}>
                  <PieChart size={16} style={{ marginRight: 6 }} /> Stock Holdings & Position Allocation
                </span>
                <span className="badge badge-secondary">{portfolio.allocation?.length || 0} Open</span>
              </div>
              <div style={{ fontSize: 12, color: 'var(--color-text-muted)', display: 'flex', alignItems: 'center', gap: 6 }}>
                <HelpCircle size={14} /> Click any row to inspect days held & P&L breakdown
              </div>
            </div>

            {portfolio.allocation?.length === 0 && (
              <div className="empty-state" style={{ padding: 40, textAlign: 'center' }}>
                No open positions. Place paper trades to see live holding analytics and days held.
              </div>
            )}

            {portfolio.allocation?.length > 0 && (
              <div className="table-container" style={{ overflowX: 'auto' }}>
                <table className="table" style={{ minWidth: '950px', margin: 0 }}>
                  <thead>
                    <tr>
                      <th>Instrument</th>
                      <th>Holding Period</th>
                      <th>Qty</th>
                      <th>Avg. Buy Price</th>
                      <th>LTP (Current)</th>
                      <th>Today's P&L</th>
                      <th>Overall Return on Buy</th>
                      <th>Current Value</th>
                      <th>Weight</th>
                      <th style={{ textAlign: 'center' }}>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {portfolio.allocation.map((a: any, i: number) => {
                      const daysHeld = a.days_held ?? 0

                      return (
                        <tr 
                          key={a.trade_id || i}
                          onClick={() => setSelectedHolding(a)}
                          style={{ cursor: 'pointer', transition: 'background 0.15s ease' }}
                          title="Click to view detailed holding analytics"
                        >
                          {/* Instrument */}
                          <td>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                              <span className="mono" style={{ fontWeight: 600, fontSize: 14 }}>{a.symbol}</span>
                              <span className={`badge ${a.direction === 'BUY' ? 'badge-buy' : 'badge-sell'}`} style={{ fontSize: 10 }}>
                                {a.direction}
                              </span>
                              <span className="badge badge-secondary" style={{ fontSize: 10 }}>
                                {a.product_type}
                              </span>
                              {a.ratchet_stage && a.ratchet_stage !== 'INITIAL' && (
                                <span
                                  className="badge"
                                  style={{
                                    fontSize: 9,
                                    padding: '2px 5px',
                                    background: 'rgba(16, 185, 129, 0.16)',
                                    color: '#34d399',
                                    border: '1px solid rgba(16, 185, 129, 0.3)',
                                  }}
                                >
                                  {String(a.ratchet_stage).replace(/_/g, ' ')}
                                </span>
                              )}
                            </div>
                            {(a.stop_loss || a.target_1 || a.target_2 || a.target_3 || a.target_price) && (
                              <div className="mono" style={{ fontSize: 10, color: 'var(--color-text-muted)', marginTop: 3 }}>
                                {a.stop_loss ? <span style={{ color: '#f87171', marginRight: 6 }}>SL: ₹{Number(a.stop_loss).toFixed(2)}</span> : null}
                                {a.target_1 ? <span>T1 ₹{Number(a.target_1).toFixed(0)}</span> : null}
                                {a.target_2 ? <span> · T2 ₹{Number(a.target_2).toFixed(0)}</span> : null}
                                {a.target_3 ? <span> · T3 ₹{Number(a.target_3).toFixed(0)}</span> : (!a.target_1 && a.target_price ? <span>T ₹{Number(a.target_price).toFixed(2)}</span> : null)}
                              </div>
                            )}
                          </td>

                          {/* Holding Period / Days Held */}
                          <td>
                            <span 
                              className="badge" 
                              style={{ 
                                background: daysHeld === 0 ? 'rgba(59, 130, 246, 0.15)' : 'rgba(255, 255, 255, 0.06)',
                                color: daysHeld === 0 ? '#60a5fa' : 'var(--color-text-secondary)',
                                border: `1px solid ${daysHeld === 0 ? 'rgba(59, 130, 246, 0.3)' : 'var(--color-border)'}`,
                                display: 'inline-flex',
                                alignItems: 'center',
                                gap: 4,
                                padding: '3px 8px',
                              }}
                            >
                              <Calendar size={12} />
                              {daysHeld === 0 ? 'Bought Today' : `${daysHeld}d held`}
                            </span>
                          </td>

                          {/* Qty */}
                          <td style={{ fontWeight: 500 }}>{a.quantity}</td>

                          {/* Avg. Buy Price */}
                          <td className="mono">{formatINR(a.entry_price)}</td>

                          {/* Current Price */}
                          <td className="mono" style={{ fontWeight: 600 }}>{formatINR(a.current_price)}</td>

                          {/* Today's Profit & Loss for Current Stock (Strict Red / Green / White) */}
                          <td className={`${getPnlClass(a.day_pnl)} mono`} style={{ whiteSpace: 'nowrap' }}>
                            <div style={{ fontWeight: 600, color: getPnlColor(a.day_pnl) }}>
                              {getPnlSign(a.day_pnl)}{formatINR(a.day_pnl ?? 0)}
                            </div>
                            <div style={{ fontSize: 11, opacity: 0.9, color: getPnlColor(a.day_change_pct) }}>
                              {getPnlSign(a.day_change_pct)}{(a.day_change_pct ?? 0).toFixed(2)}%
                            </div>
                          </td>

                          {/* Overall Return on Buy (Net Return % matching Net Rupee P&L, Strict Red / Green / White) */}
                          <td className={`${getPnlClass(a.unrealized_pnl)} mono`} style={{ whiteSpace: 'nowrap' }}>
                            <div style={{ fontWeight: 600, color: getPnlColor(a.unrealized_pnl) }}>
                              {getPnlSign(a.unrealized_pnl)}{formatINR(a.unrealized_pnl)}
                            </div>
                            <div style={{ fontSize: 11, opacity: 0.9, color: getPnlColor(a.pnl_pct) }}>
                              {getPnlSign(a.pnl_pct)}{(a.pnl_pct ?? 0).toFixed(2)}%
                            </div>
                          </td>

                          {/* Value */}
                          <td className="mono">{formatINR(a.value)}</td>

                          {/* Weight */}
                          <td>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                              <div style={{ width: 50, height: 6, background: 'var(--color-bg-secondary)', borderRadius: 3, overflow: 'hidden' }}>
                                <div style={{ 
                                  width: `${Math.min(100, Math.max(0, a.weight_pct || 0))}%`, 
                                  height: '100%', 
                                  background: getPnlColor(a.unrealized_pnl), 
                                  borderRadius: 3 
                                }} />
                              </div>
                              <span style={{ fontSize: 12, color: 'var(--color-text-secondary)' }}>{a.weight_pct}%</span>
                            </div>
                          </td>

                          {/* Action Button */}
                          <td style={{ textAlign: 'center' }}>
                            <button
                              className="btn btn-secondary"
                              onClick={(e) => {
                                e.stopPropagation()
                                setSelectedHolding(a)
                              }}
                              style={{ 
                                padding: '4px 10px', 
                                fontSize: 12, 
                                display: 'inline-flex', 
                                alignItems: 'center', 
                                gap: 4 
                              }}
                              title="Inspect Holding Details"
                            >
                              <Eye size={13} /> Inspect
                            </button>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Pending Orders Queue Section (prevents queued BUY/LIMIT/AMO orders from looking invisible) */}
          {portfolio.pending_orders_list && portfolio.pending_orders_list.length > 0 && (
            <div className="card" style={{ marginTop: 20, borderLeft: '4px solid #f59e0b' }}>
              <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span className="card-title" style={{ display: 'flex', alignItems: 'center', color: '#fbbf24' }}>
                    <Clock size={16} style={{ marginRight: 6 }} /> Pending Orders Queue (Awaiting Execution)
                  </span>
                  <span className="badge" style={{ background: 'rgba(245, 158, 11, 0.15)', color: '#fbbf24', border: '1px solid rgba(245, 158, 11, 0.35)' }}>
                    {portfolio.pending_orders_list.length} Pending
                  </span>
                </div>
                <button
                  type="button"
                  className="btn btn-secondary"
                  style={{ padding: '4px 12px', fontSize: 12, display: 'inline-flex', alignItems: 'center', gap: 5 }}
                  onClick={() => navigate('/paper-trading?tab=orders')}
                >
                  Open in Orders &amp; Positions <ArrowRight size={13} />
                </button>
              </div>
              <div className="table-container" style={{ overflowX: 'auto' }}>
                <table className="table" style={{ minWidth: '750px', margin: 0 }}>
                  <thead>
                    <tr>
                      <th>Instrument</th>
                      <th>Type</th>
                      <th>Product</th>
                      <th>Qty</th>
                      <th>Order / Trigger Price</th>
                      <th>Target / SL</th>
                      <th>Placed At</th>
                      <th>Status</th>
                      <th style={{ textAlign: 'center' }}>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {portfolio.pending_orders_list.map((po: any) => {
                      const orderPrice = po.limit_price ?? po.stop_price
                      return (
                        <tr key={po.trade_id}>
                          <td className="mono" style={{ fontWeight: 600 }}>{po.symbol}</td>
                          <td>
                            <span className={`badge ${po.direction === 'BUY' ? 'badge-buy' : 'badge-sell'}`}>
                              {po.direction} {po.order_type}
                            </span>
                          </td>
                          <td><span className="badge badge-secondary">{po.product_type}</span></td>
                          <td>{po.quantity}</td>
                          <td className="mono">{orderPrice ? formatINR(orderPrice) : 'Market Price'}</td>
                          <td className="mono" style={{ fontSize: 12 }}>
                            {po.target_price ? `T: ₹${Number(po.target_price).toFixed(2)}` : '—'}
                            {po.stop_loss ? ` / SL: ₹${Number(po.stop_loss).toFixed(2)}` : ''}
                          </td>
                          <td style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>
                            {po.buy_date_formatted || (po.opened_at ? new Date(po.opened_at).toLocaleString() : '—')}
                          </td>
                          <td>
                            <span className="badge" style={{ background: 'rgba(245, 158, 11, 0.15)', color: '#fbbf24', border: '1px solid rgba(245, 158, 11, 0.35)' }}>
                              {po.status || 'PENDING'}
                            </span>
                          </td>
                          <td style={{ textAlign: 'center' }}>
                            <button
                              type="button"
                              className="btn btn-secondary"
                              style={{ padding: '4px 10px', fontSize: 12 }}
                              onClick={() => handleCancelPendingOrder(po.trade_id)}
                            >
                              Cancel
                            </button>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Sold Stocks History Ledger (Auto-Sold by System vs User Sold) */}
          <div className="card" style={{ marginTop: 20, borderLeft: '4px solid #38bdf8' }}>
            <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                <span className="card-title" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <History size={16} style={{ color: '#38bdf8' }} /> Sold Stocks History (Realized Exits)
                </span>
                <span className="badge" style={{ background: 'rgba(56, 189, 248, 0.14)', color: '#38bdf8', border: '1px solid rgba(56, 189, 248, 0.35)' }}>
                  {(portfolio.closed_trades_list || []).length} Exits
                </span>
                {(portfolio.sold_today_count ?? 0) > 0 && (
                  <span className="badge" style={{ background: 'rgba(16, 185, 129, 0.15)', color: '#34d399', border: '1px solid rgba(16, 185, 129, 0.35)' }}>
                    {portfolio.sold_today_count} Sold Today
                  </span>
                )}
              </div>

              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
                {([
                  { key: 'ALL', label: `All (${(portfolio.closed_trades_list || []).length})` },
                  { key: 'TODAY', label: `Today (${portfolio.sold_today_count ?? 0})` },
                  { key: 'AUTO', label: `Auto-Sold (${portfolio.auto_sold_count ?? 0})` },
                  { key: 'USER', label: `User Sold (${portfolio.user_sold_count ?? 0})` },
                ] as const).map(tab => (
                  <button
                    key={tab.key}
                    type="button"
                    className={soldFilter === tab.key ? 'btn btn-primary' : 'btn btn-secondary'}
                    style={{ padding: '4px 10px', fontSize: 12 }}
                    onClick={() => setSoldFilter(tab.key)}
                  >
                    {tab.label}
                  </button>
                ))}
                <button
                  type="button"
                  className="btn btn-secondary"
                  style={{ padding: '4px 12px', fontSize: 12, display: 'inline-flex', alignItems: 'center', gap: 5 }}
                  onClick={() => navigate('/paper-trading?tab=history')}
                >
                  Full Ledger <ArrowRight size={13} />
                </button>
              </div>
            </div>

            {(() => {
              const allSold: any[] = portfolio.closed_trades_list || []
              const filteredSold = allSold.filter(item => {
                if (soldFilter === 'TODAY') return Boolean(item.is_sold_today)
                if (soldFilter === 'AUTO') return item.closed_by === 'AUTO_SYSTEM'
                if (soldFilter === 'USER') return item.closed_by === 'USER_MANUAL'
                return true
              })
              if (filteredSold.length === 0) {
                return (
                  <div className="empty-state" style={{ padding: 32, textAlign: 'center', color: 'var(--color-text-muted)' }}>
                    {allSold.length === 0
                      ? 'No sold stocks recorded yet. Exited holdings (both System Auto-Sell and Manual Exits) will appear here.'
                      : 'No exited positions match the selected filter.'}
                  </div>
                )
              }
              return (
                <div className="table-container" style={{ overflowX: 'auto' }}>
                  <table className="table" style={{ minWidth: '1080px', margin: 0 }}>
                    <thead>
                      <tr>
                        <th>Stock & Duration</th>
                        <th>Qty.</th>
                        <th>Buy Price</th>
                        <th>Sell Price</th>
                        <th>Targets & Stop-Loss Guard</th>
                        <th>Charges</th>
                        <th>Realized Net P&amp;L</th>
                        <th>Sold By & Exit Reason</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredSold.map(c => {
                        const netPnl = Number(c.realized_pnl ?? 0)
                        const pnlPct = c.pnl_pct
                        const isAuto = c.closed_by === 'AUTO_SYSTEM'
                        const hasT123 = Boolean(c.target_1 || c.target_2 || c.target_3)
                        return (
                          <tr key={c.trade_id} style={{ background: c.is_sold_today ? 'rgba(56, 189, 248, 0.04)' : undefined }}>
                            <td>
                              <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                                <strong className="mono">{c.symbol}</strong>
                                <span className={`badge ${c.direction === 'BUY' ? 'badge-buy' : 'badge-sell'}`} style={{ fontSize: 10 }}>
                                  {c.direction}
                                </span>
                                <span className="badge badge-secondary" style={{ fontSize: 10 }}>{c.product_type}</span>
                                {c.is_sold_today && (
                                  <span className="badge" style={{ fontSize: 10, background: 'rgba(16, 185, 129, 0.16)', color: '#34d399', border: '1px solid rgba(16, 185, 129, 0.35)' }}>
                                    Today
                                  </span>
                                )}
                              </div>
                              <div style={{ fontSize: 11, color: 'var(--color-text-muted)', marginTop: 3 }}>
                                Held: {c.holding_duration_label || `${c.days_held ?? 0}d`} · Sold {c.sell_date_formatted || (c.closed_at ? new Date(c.closed_at).toLocaleString() : '—')}
                              </div>
                            </td>
                            <td className="mono">{c.quantity}</td>
                            <td className="mono">
                              <div>{c.entry_price != null ? formatINR(c.entry_price) : '—'}</div>
                              <div style={{ fontSize: 10, color: 'var(--color-text-muted)' }}>
                                {c.buy_date_formatted || ''}
                              </div>
                            </td>
                            <td className="mono" style={{ fontWeight: 600 }}>
                              {c.exit_price != null ? formatINR(c.exit_price) : '—'}
                            </td>
                            <td className="mono" style={{ fontSize: 11 }}>
                              {hasT123 ? (
                                <div>
                                  {c.target_1 ? `T1 ₹${Number(c.target_1).toFixed(0)}` : ''}
                                  {c.target_2 ? ` · T2 ₹${Number(c.target_2).toFixed(0)}` : ''}
                                  {c.target_3 ? ` · T3 ₹${Number(c.target_3).toFixed(0)}` : ''}
                                </div>
                              ) : (
                                <div>{c.target_price ? `Tgt: ₹${Number(c.target_price).toFixed(2)}` : 'Target: —'}</div>
                              )}
                              <div style={{ color: 'var(--color-text-muted)', fontSize: 10, marginTop: 2 }}>
                                {c.stop_loss ? `SL: ₹${Number(c.stop_loss).toFixed(2)}` : 'SL: —'}
                                {c.initial_stop_loss && c.stop_loss && Number(c.initial_stop_loss) !== Number(c.stop_loss)
                                  ? ` (Init ₹${Number(c.initial_stop_loss).toFixed(2)})`
                                  : ''}
                                {c.ratchet_stage && c.ratchet_stage !== 'INITIAL'
                                  ? ` · ${String(c.ratchet_stage).replace(/_/g, ' ')}`
                                  : ''}
                              </div>
                            </td>
                            <td className="mono" style={{ fontSize: 12 }}>
                              <div>{formatINR(c.total_charges ?? 0)}</div>
                              <div style={{ fontSize: 10, color: 'var(--color-text-muted)' }}>
                                Brok ₹{formatNumber2Dec(c.commission ?? 0)} · STT ₹{formatNumber2Dec(c.stt_tax ?? 0)}
                              </div>
                            </td>
                            <td className={`${getPnlClass(netPnl)} mono`} style={{ whiteSpace: 'nowrap' }}>
                              <div style={{ fontWeight: 700, color: getPnlColor(netPnl) }}>
                                {getPnlSign(netPnl)}{formatINR(netPnl)}
                              </div>
                              {pnlPct != null && (
                                <div style={{ fontSize: 11, color: getPnlColor(pnlPct) }}>
                                  {getPnlSign(pnlPct)}{Number(pnlPct).toFixed(2)}%
                                </div>
                              )}
                            </td>
                            <td>
                              <div
                                className="badge"
                                style={{
                                  display: 'inline-flex',
                                  alignItems: 'center',
                                  gap: 5,
                                  fontSize: 11,
                                  fontWeight: 700,
                                  background: isAuto ? 'rgba(99, 102, 241, 0.16)' : 'rgba(245, 158, 11, 0.14)',
                                  color: isAuto ? '#a5b4fc' : '#fcd34d',
                                  border: `1px solid ${isAuto ? 'rgba(99, 102, 241, 0.35)' : 'rgba(245, 158, 11, 0.35)'}`,
                                }}
                              >
                                {isAuto ? <Bot size={12} /> : <User size={12} />}
                                {isAuto ? 'Auto-Sold by System' : 'User Sold'}
                              </div>
                              <div style={{ fontSize: 11, color: 'var(--color-text-muted)', marginTop: 3 }}>
                                {c.exit_reason_label || 'Settled'}
                              </div>
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              )
            })()}
          </div>

          {/* Holding Detail Modal */}
          <HoldingDetailModal
            isOpen={!!selectedHolding}
            onClose={() => setSelectedHolding(null)}
            holding={selectedHolding}
            onExit={async (tradeId: string) => {
              if (!confirm('Close this holding at current market price?')) return
              await paperTradingApi.close(tradeId)
              setSelectedHolding(null)
              await loadPortfolio()
            }}
          />
        </>
      )}
    </div>
  )
}
