import { Fragment, useEffect, useState, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { portfolioApi, paperTradingApi } from '../services/api'
import { PieChart, TrendingUp, TrendingDown, Clock, Calendar, Eye, ArrowRight, Bot, User, History, ChevronDown, ChevronRight } from 'lucide-react'
import HoldingDetailModal from '../components/HoldingDetailModal'
import { formatINR, formatNumber2Dec, getPnlColor, getPnlClass, getPnlSign } from '../utils/formatters'

export default function PortfolioPage() {
  const navigate = useNavigate()
  const [portfolio, setPortfolio] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [selectedHolding, setSelectedHolding] = useState<any | null>(null)
  const [soldFilter, setSoldFilter] = useState<'ALL' | 'TODAY' | 'AUTO' | 'USER'>('ALL')
  const [expandedGroups, setExpandedGroups] = useState<Record<string, boolean>>({})

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

  const groupedHoldings = useMemo(() => {
    const raw: any[] = portfolio?.allocation || []
    const map = new Map<string, any>()
    for (const a of raw) {
      const key = `${a.symbol}_${a.direction}_${a.product_type}`
      if (!map.has(key)) {
        map.set(key, {
          key,
          symbol: a.symbol,
          direction: a.direction,
          product_type: a.product_type,
          lots: [a],
          quantity: Number(a.quantity || 0),
          invested: Number(a.entry_price || 0) * Number(a.quantity || 0),
          current_price: Number(a.current_price || 0),
          day_pnl: Number(a.day_pnl || 0),
          unrealized_pnl: Number(a.unrealized_pnl || 0),
          value: Number(a.value || 0),
          weight_pct: Number(a.weight_pct || 0),
          day_change_pct: Number(a.day_change_pct || 0),
          max_days_held: Number(a.days_held ?? 0),
        })
      } else {
        const g = map.get(key)
        g.lots.push(a)
        g.quantity += Number(a.quantity || 0)
        g.invested += Number(a.entry_price || 0) * Number(a.quantity || 0)
        g.day_pnl += Number(a.day_pnl || 0)
        g.unrealized_pnl += Number(a.unrealized_pnl || 0)
        g.value += Number(a.value || 0)
        g.weight_pct = Number((g.weight_pct + Number(a.weight_pct || 0)).toFixed(1))
        g.max_days_held = Math.max(g.max_days_held, Number(a.days_held ?? 0))
      }
    }
    return Array.from(map.values()).map((g) => ({
      ...g,
      avg_entry: g.quantity > 0 ? g.invested / g.quantity : 0,
      pnl_pct: g.invested > 0 ? (g.unrealized_pnl / g.invested) * 100 : 0,
    }))
  }, [portfolio])

  if (loading) return <div className="loading">Loading portfolio…</div>

  const totalDayPnl = portfolio?.total_day_pnl ?? 0
  const totalDayPnlBorder = totalDayPnl > 0.0001
    ? 'rgba(16, 185, 129, 0.35)'
    : totalDayPnl < -0.0001
    ? 'rgba(239, 68, 68, 0.35)'
    : 'var(--color-border)'

  const holdingsMarketValue = portfolio?.total_current_value ?? portfolio?.allocation?.reduce((sum: number, a: any) => sum + (a.value || 0), 0) ?? portfolio?.current_value

  return (
    <div>
      <div className="page-header" style={{ marginBottom: 16 }}>
        <h1 className="page-title">Holdings &amp; Portfolio</h1>
        <p className="page-subtitle">Open capital allocation, day P&amp;L, and realized exits</p>
      </div>

      {portfolio && (
        <>
          {/* Compact 2-Column Mobile / Auto-Fit Desktop KPI Grid */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 165px), 1fr))',
            gap: 10,
            marginBottom: 18
          }}>
            <div className="card" style={{ padding: '12px 14px' }}>
              <div style={{ fontSize: 11, color: 'var(--color-text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>Holdings Value</div>
              <div className="mono" style={{ fontSize: 19, fontWeight: 700, marginTop: 4 }}>{formatINR(holdingsMarketValue)}</div>
              <div style={{ fontSize: 11, color: 'var(--color-text-muted)', marginTop: 2 }}>
                Invested {formatINR(portfolio.total_invested || 0)}
              </div>
            </div>

            <div className="card" style={{ padding: '12px 14px', border: `1px solid ${totalDayPnlBorder}` }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span style={{ fontSize: 11, color: 'var(--color-text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>Day P&amp;L</span>
                <Clock size={13} style={{ color: getPnlColor(totalDayPnl) }} />
              </div>
              <div className="mono" style={{ fontSize: 19, fontWeight: 700, color: getPnlColor(totalDayPnl), marginTop: 4 }}>
                {getPnlSign(totalDayPnl)}{formatINR(totalDayPnl)}
              </div>
              <div className="mono" style={{ fontSize: 11.5, fontWeight: 600, color: getPnlColor(portfolio.total_day_pnl_pct), marginTop: 2 }}>
                {getPnlSign(portfolio.total_day_pnl_pct)}{(portfolio.total_day_pnl_pct ?? 0).toFixed(2)}%
              </div>
            </div>

            <div className="card" style={{ padding: '12px 14px' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span style={{ fontSize: 11, color: 'var(--color-text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>Net Return</span>
                {portfolio.total_pnl > 0.0001 ? <TrendingUp size={13} color="#10b981" /> : portfolio.total_pnl < -0.0001 ? <TrendingDown size={13} color="#ef4444" /> : null}
              </div>
              <div className="mono" style={{ fontSize: 19, fontWeight: 700, color: getPnlColor(portfolio.total_pnl), marginTop: 4 }}>
                {getPnlSign(portfolio.total_pnl)}{formatINR(portfolio.total_pnl)}
              </div>
              <div className="mono" style={{ fontSize: 11.5, fontWeight: 600, color: getPnlColor(portfolio.total_pnl_pct), marginTop: 2 }}>
                {getPnlSign(portfolio.total_pnl_pct)}{portfolio.total_pnl_pct?.toFixed(2)}% all-time
              </div>
            </div>

            <div
              className="card"
              onClick={() => navigate(portfolio.pending_orders > 0 ? '/paper-trading?tab=orders' : '/paper-trading')}
              style={{ padding: '12px 14px', cursor: 'pointer' }}
            >
              <div style={{ fontSize: 11, color: 'var(--color-text-muted)', textTransform: 'uppercase', fontWeight: 600, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span>Net Equity</span>
                <ArrowRight size={12} />
              </div>
              <div className="mono" style={{ fontSize: 19, fontWeight: 700, marginTop: 4 }}>{formatINR(portfolio.current_value)}</div>
              <div style={{ fontSize: 11, marginTop: 2, color: 'var(--color-text-muted)' }}>
                {portfolio.open_trades} open · {portfolio.pending_orders} pending
              </div>
            </div>
          </div>

          {/* Allocation & Grouped Stock Holdings */}
          <div className="card">
            <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span className="card-title" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <PieChart size={16} /> Active Holdings
                </span>
                <span className="badge" style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border)', color: 'var(--color-text-secondary)' }}>
                  {portfolio.allocation?.length || 0} lots
                </span>
              </div>
            </div>

            {groupedHoldings.length === 0 ? (
              <div className="empty-state" style={{ padding: 36 }}>
                No open holdings yet. Executed paper trades appear here with live P&amp;L.
              </div>
            ) : (
              <>
                <div className="table-container desktop-only-table" style={{ marginBottom: 0 }}>
                  <table className="table" style={{ minWidth: '880px', margin: 0 }}>
                    <thead>
                      <tr>
                        <th>Instrument</th>
                        <th>Held</th>
                        <th>Qty</th>
                        <th>Avg Buy</th>
                        <th>LTP</th>
                        <th>Day P&amp;L</th>
                        <th>Net P&amp;L</th>
                        <th>Value</th>
                        <th>Wt</th>
                        <th style={{ textAlign: 'center' }}>Inspect</th>
                      </tr>
                    </thead>
                    <tbody>
                      {groupedHoldings.map((g: any) => {
                        const isMulti = g.lots.length > 1
                        const isExpanded = Boolean(expandedGroups[g.key])
                        const primaryLot = g.lots[0]

                        return (
                          <Fragment key={g.key}>
                            <tr
                              onClick={() => isMulti ? setExpandedGroups(prev => ({ ...prev, [g.key]: !prev[g.key] })) : setSelectedHolding(primaryLot)}
                              style={{ cursor: 'pointer' }}
                            >
                              <td>
                                <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                                  {isMulti && (isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />)}
                                  <span className="mono" style={{ fontWeight: 700, fontSize: 13.5 }}>{g.symbol}</span>
                                  <span className={`badge ${g.direction === 'BUY' ? 'badge-buy' : 'badge-sell'}`} style={{ fontSize: 10 }}>{g.direction}</span>
                                  {isMulti && (
                                    <span style={{ fontSize: 10, padding: '1px 6px', borderRadius: 4, background: 'rgba(59,130,246,0.14)', color: 'var(--color-accent-blue)', fontWeight: 700 }}>
                                      {g.lots.length} lots
                                    </span>
                                  )}
                                  {!isMulti && primaryLot.ratchet_stage && primaryLot.ratchet_stage !== 'INITIAL' && (
                                    <span style={{ fontSize: 9.5, padding: '1px 6px', borderRadius: 4, background: 'var(--color-bullish-dim)', color: 'var(--color-bullish)', fontWeight: 700 }}>
                                      {String(primaryLot.ratchet_stage).replace(/_/g, ' ')}
                                    </span>
                                  )}
                                </div>
                              </td>
                              <td><span className="mono" style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>{g.max_days_held === 0 ? 'Today' : `${g.max_days_held}d`}</span></td>
                              <td className="mono" style={{ fontWeight: 600 }}>{g.quantity}</td>
                              <td className="mono">{formatINR(g.avg_entry)}</td>
                              <td className="mono" style={{ fontWeight: 600 }}>{formatINR(g.current_price)}</td>
                              <td className={`${getPnlClass(g.day_pnl)} mono`} style={{ whiteSpace: 'nowrap' }}>
                                <div style={{ fontWeight: 600, color: getPnlColor(g.day_pnl) }}>{getPnlSign(g.day_pnl)}{formatINR(g.day_pnl)}</div>
                                <div style={{ fontSize: 11, color: getPnlColor(g.day_change_pct) }}>{getPnlSign(g.day_change_pct)}{g.day_change_pct.toFixed(2)}%</div>
                              </td>
                              <td className={`${getPnlClass(g.unrealized_pnl)} mono`} style={{ whiteSpace: 'nowrap' }}>
                                <div style={{ fontWeight: 600, color: getPnlColor(g.unrealized_pnl) }}>{getPnlSign(g.unrealized_pnl)}{formatINR(g.unrealized_pnl)}</div>
                                <div style={{ fontSize: 11, color: getPnlColor(g.pnl_pct) }}>{getPnlSign(g.pnl_pct)}{g.pnl_pct.toFixed(2)}%</div>
                              </td>
                              <td className="mono">{formatINR(g.value)}</td>
                              <td className="mono" style={{ fontSize: 12 }}>{g.weight_pct}%</td>
                              <td style={{ textAlign: 'center' }}>
                                <button
                                  className="btn btn-secondary"
                                  onClick={(e) => {
                                    e.stopPropagation()
                                    if (isMulti) setExpandedGroups(prev => ({ ...prev, [g.key]: !prev[g.key] }))
                                    else setSelectedHolding(primaryLot)
                                  }}
                                  style={{ padding: '4px 10px', fontSize: 11.5 }}
                                >
                                  {isMulti ? (isExpanded ? 'Hide Lots' : 'Lots') : <><Eye size={12} /> Inspect</>}
                                </button>
                              </td>
                            </tr>
                            {isMulti && isExpanded && g.lots.map((a: any, idx: number) => (
                              <tr key={a.trade_id || idx} onClick={() => setSelectedHolding(a)} style={{ background: 'var(--color-bg-secondary)', cursor: 'pointer' }}>
                                <td style={{ paddingLeft: 28, fontSize: 12 }}>
                                  <span style={{ color: 'var(--color-text-muted)' }}>Lot #{idx + 1}</span>
                                  {a.stop_loss ? <span className="mono" style={{ color: 'var(--color-bearish)', marginLeft: 8 }}>SL ₹{Number(a.stop_loss).toFixed(2)}</span> : null}
                                  {a.target_price ? <span className="mono" style={{ color: 'var(--color-bullish)', marginLeft: 8 }}>Tgt ₹{Number(a.target_price).toFixed(2)}</span> : null}
                                </td>
                                <td className="mono" style={{ fontSize: 12 }}>{(a.days_held ?? 0) === 0 ? 'Today' : `${a.days_held}d`}</td>
                                <td className="mono">{a.quantity}</td>
                                <td className="mono">{formatINR(a.entry_price)}</td>
                                <td className="mono">{formatINR(a.current_price)}</td>
                                <td className="mono" style={{ color: getPnlColor(a.day_pnl) }}>{getPnlSign(a.day_pnl)}{formatINR(a.day_pnl ?? 0)}</td>
                                <td className="mono" style={{ color: getPnlColor(a.unrealized_pnl) }}>{getPnlSign(a.unrealized_pnl)}{formatINR(a.unrealized_pnl)}</td>
                                <td className="mono">{formatINR(a.value)}</td>
                                <td className="mono">{a.weight_pct}%</td>
                                <td style={{ textAlign: 'center' }}>
                                  <button className="btn btn-ghost" style={{ padding: '3px 8px', fontSize: 11 }} onClick={(e) => { e.stopPropagation(); setSelectedHolding(a) }}>
                                    <Eye size={12} />
                                  </button>
                                </td>
                              </tr>
                            ))}
                          </Fragment>
                        )
                      })}
                    </tbody>
                  </table>
                </div>

                {/* Mobile Cards View */}
                <div className="mobile-only-cards">
                  {groupedHoldings.map((g: any) => {
                    const isMulti = g.lots.length > 1
                    const isExpanded = Boolean(expandedGroups[g.key])
                    return (
                      <div key={g.key} style={{ padding: 12, borderRadius: 8, background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border)' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8, gap: 6 }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                            <strong style={{ fontSize: 14.5 }}>{g.symbol.replace('.NS', '')}</strong>
                            <span className={`badge ${g.direction === 'BUY' ? 'badge-buy' : 'badge-sell'}`} style={{ fontSize: 10 }}>{g.quantity} qty</span>
                            {isMulti && <span style={{ fontSize: 10, color: 'var(--color-accent-blue)', fontWeight: 600 }}>{g.lots.length} lots</span>}
                          </div>
                          <div className="mono" style={{ fontWeight: 700, fontSize: 14, color: getPnlColor(g.unrealized_pnl) }}>
                            {getPnlSign(g.unrealized_pnl)}{formatINR(g.unrealized_pnl)}
                          </div>
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 6, fontSize: 12, marginBottom: 10 }}>
                          <div><div style={{ fontSize: 10, color: 'var(--color-text-muted)' }}>Avg Buy</div><strong className="mono">{formatINR(g.avg_entry)}</strong></div>
                          <div><div style={{ fontSize: 10, color: 'var(--color-text-muted)' }}>LTP</div><strong className="mono">{formatINR(g.current_price)}</strong></div>
                          <div><div style={{ fontSize: 10, color: 'var(--color-text-muted)' }}>Day P&amp;L</div><strong className="mono" style={{ color: getPnlColor(g.day_pnl) }}>{getPnlSign(g.day_pnl)}{formatINR(g.day_pnl)}</strong></div>
                        </div>
                        {isMulti ? (
                          <>
                            <button
                              type="button"
                              className="btn btn-secondary w-100"
                              style={{ fontSize: 12 }}
                              onClick={() => setExpandedGroups(prev => ({ ...prev, [g.key]: !prev[g.key] }))}
                            >
                              {isExpanded ? 'Hide Individual Lots' : `Inspect ${g.lots.length} Lots`}
                            </button>
                            {isExpanded && (
                              <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 6 }}>
                                {g.lots.map((a: any, idx: number) => (
                                  <div
                                    key={a.trade_id || idx}
                                    onClick={() => setSelectedHolding(a)}
                                    style={{ padding: '8px 10px', borderRadius: 6, background: 'var(--color-bg-card)', border: '1px solid var(--color-border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 12, cursor: 'pointer' }}
                                  >
                                    <span className="mono">Lot #{idx + 1} · {a.quantity} @ {formatINR(a.entry_price)}</span>
                                    <span className="mono" style={{ color: getPnlColor(a.unrealized_pnl), fontWeight: 600 }}>{getPnlSign(a.unrealized_pnl)}{formatINR(a.unrealized_pnl)}</span>
                                  </div>
                                ))}
                              </div>
                            )}
                          </>
                        ) : (
                          <button type="button" className="btn btn-secondary w-100" style={{ fontSize: 12 }} onClick={() => setSelectedHolding(g.lots[0])}>
                            <Eye size={13} /> Inspect Position
                          </button>
                        )}
                      </div>
                    )
                  })}
                </div>
              </>
            )}
          </div>

          {/* Pending Orders Queue Section */}
          {portfolio.pending_orders_list && portfolio.pending_orders_list.length > 0 && (
            <div className="card" style={{ marginTop: 18, borderLeft: '3px solid var(--color-neutral)' }}>
              <div className="card-header">
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span className="card-title" style={{ display: 'flex', alignItems: 'center', gap: 6, color: 'var(--color-neutral)' }}>
                    <Clock size={15} /> Pending Orders ({portfolio.pending_orders_list.length})
                  </span>
                </div>
                <button
                  type="button"
                  className="btn btn-secondary"
                  style={{ padding: '4px 10px', fontSize: 12 }}
                  onClick={() => navigate('/paper-trading?tab=orders')}
                >
                  Manage Orders <ArrowRight size={12} />
                </button>
              </div>
              <div className="table-container desktop-only-table" style={{ marginBottom: 0 }}>
                <table className="table" style={{ minWidth: '720px', margin: 0 }}>
                  <thead>
                    <tr>
                      <th>Instrument</th>
                      <th>Type</th>
                      <th>Qty</th>
                      <th>Price</th>
                      <th>Target / SL</th>
                      <th>Placed</th>
                      <th style={{ textAlign: 'center' }}>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {portfolio.pending_orders_list.map((po: any) => {
                      const orderPrice = po.limit_price ?? po.stop_price
                      return (
                        <tr key={po.trade_id}>
                          <td className="mono" style={{ fontWeight: 600 }}>{po.symbol}</td>
                          <td><span className={`badge ${po.direction === 'BUY' ? 'badge-buy' : 'badge-sell'}`}>{po.direction} {po.order_type}</span></td>
                          <td className="mono">{po.quantity}</td>
                          <td className="mono">{orderPrice ? formatINR(orderPrice) : 'Market'}</td>
                          <td className="mono" style={{ fontSize: 12 }}>
                            {po.target_price ? `T ₹${Number(po.target_price).toFixed(2)}` : '—'}
                            {po.stop_loss ? ` · SL ₹${Number(po.stop_loss).toFixed(2)}` : ''}
                          </td>
                          <td style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>
                            {po.buy_date_formatted || (po.opened_at ? new Date(po.opened_at).toLocaleString() : '—')}
                          </td>
                          <td style={{ textAlign: 'center' }}>
                            <button type="button" className="btn btn-secondary" style={{ padding: '4px 10px', fontSize: 12 }} onClick={() => handleCancelPendingOrder(po.trade_id)}>
                              Cancel
                            </button>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
              <div className="mobile-only-cards">
                {portfolio.pending_orders_list.map((po: any) => (
                  <div key={po.trade_id} style={{ padding: 12, borderRadius: 8, background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10 }}>
                    <div>
                      <div className="mono" style={{ fontWeight: 700 }}>{po.symbol.replace('.NS', '')} · {po.direction} {po.quantity}</div>
                      <div style={{ fontSize: 11.5, color: 'var(--color-text-muted)' }}>{po.limit_price ?? po.stop_price ? formatINR(po.limit_price ?? po.stop_price) : 'Market'}</div>
                    </div>
                    <button type="button" className="btn btn-secondary" style={{ padding: '5px 10px', fontSize: 12 }} onClick={() => handleCancelPendingOrder(po.trade_id)}>
                      Cancel
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Sold Stocks History Ledger */}
          <div className="card" style={{ marginTop: 18, borderLeft: '3px solid var(--color-accent-blue)' }}>
            <div className="card-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                <span className="card-title" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <History size={16} style={{ color: 'var(--color-accent-blue)' }} /> Realized Exits ({(portfolio.closed_trades_list || []).length})
                </span>
                {(portfolio.sold_today_count ?? 0) > 0 && (
                  <span className="badge badge-buy">{portfolio.sold_today_count} Today</span>
                )}
              </div>

              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
                {([
                  { key: 'ALL', label: `All (${(portfolio.closed_trades_list || []).length})` },
                  { key: 'TODAY', label: `Today (${portfolio.sold_today_count ?? 0})` },
                  { key: 'AUTO', label: `Auto (${portfolio.auto_sold_count ?? 0})` },
                  { key: 'USER', label: `Manual (${portfolio.user_sold_count ?? 0})` },
                ] as const).map(tab => (
                  <button
                    key={tab.key}
                    type="button"
                    className={soldFilter === tab.key ? 'btn btn-primary' : 'btn btn-secondary'}
                    style={{ padding: '5px 10px', fontSize: 12 }}
                    onClick={() => setSoldFilter(tab.key)}
                  >
                    {tab.label}
                  </button>
                ))}
                <button
                  type="button"
                  className="btn btn-ghost"
                  style={{ padding: '5px 10px', fontSize: 12 }}
                  onClick={() => navigate('/paper-trading?tab=history')}
                >
                  Full History <ArrowRight size={12} />
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
                  <div className="empty-state" style={{ padding: 28 }}>
                    No closed positions match this filter yet.
                  </div>
                )
              }
              return (
                <>
                  <div className="table-container desktop-only-table" style={{ marginBottom: 0 }}>
                    <table className="table" style={{ minWidth: '940px', margin: 0 }}>
                      <thead>
                        <tr>
                          <th>Stock</th>
                          <th>Qty</th>
                          <th>Buy</th>
                          <th>Sell</th>
                          <th>Targets &amp; SL</th>
                          <th>Charges</th>
                          <th>Net P&amp;L</th>
                          <th>Exit Attribution</th>
                        </tr>
                      </thead>
                      <tbody>
                        {filteredSold.map(c => {
                          const netPnl = Number(c.realized_pnl ?? 0)
                          const pnlPct = c.pnl_pct
                          const isAuto = c.closed_by === 'AUTO_SYSTEM'
                          const hasT123 = Boolean(c.target_1 || c.target_2 || c.target_3)
                          return (
                            <tr key={c.trade_id}>
                              <td>
                                <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                                  <strong className="mono">{c.symbol}</strong>
                                  <span className={`badge ${c.direction === 'BUY' ? 'badge-buy' : 'badge-sell'}`} style={{ fontSize: 10 }}>{c.direction}</span>
                                </div>
                                <div style={{ fontSize: 11, color: 'var(--color-text-muted)', marginTop: 2 }}>
                                  Held {c.holding_duration_label || `${c.days_held ?? 0}d`} · {c.sell_date_formatted || (c.closed_at ? new Date(c.closed_at).toLocaleString() : '—')}
                                </div>
                              </td>
                              <td className="mono">{c.quantity}</td>
                              <td className="mono">{c.entry_price != null ? formatINR(c.entry_price) : '—'}</td>
                              <td className="mono" style={{ fontWeight: 600 }}>{c.exit_price != null ? formatINR(c.exit_price) : '—'}</td>
                              <td className="mono" style={{ fontSize: 11 }}>
                                {hasT123 ? (
                                  <div>
                                    {c.target_1 ? `T1 ₹${Number(c.target_1).toFixed(0)}` : ''}
                                    {c.target_2 ? ` · T2 ₹${Number(c.target_2).toFixed(0)}` : ''}
                                    {c.target_3 ? ` · T3 ₹${Number(c.target_3).toFixed(0)}` : ''}
                                  </div>
                                ) : (
                                  <div>{c.target_price ? `T ₹${Number(c.target_price).toFixed(2)}` : '—'}</div>
                                )}
                                <div style={{ color: 'var(--color-text-muted)', fontSize: 10.5 }}>
                                  {c.stop_loss ? `SL ₹${Number(c.stop_loss).toFixed(2)}` : ''}
                                </div>
                              </td>
                              <td className="mono" style={{ fontSize: 12 }}>{formatINR(c.total_charges ?? 0)}</td>
                              <td className={`${getPnlClass(netPnl)} mono`} style={{ whiteSpace: 'nowrap' }}>
                                <div style={{ fontWeight: 700, color: getPnlColor(netPnl) }}>{getPnlSign(netPnl)}{formatINR(netPnl)}</div>
                                {pnlPct != null && <div style={{ fontSize: 11, color: getPnlColor(pnlPct) }}>{getPnlSign(pnlPct)}{Number(pnlPct).toFixed(2)}%</div>}
                              </td>
                              <td>
                                <span className="badge" style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 10.5, background: isAuto ? 'rgba(99, 102, 241, 0.16)' : 'rgba(245, 158, 11, 0.14)', color: isAuto ? '#a5b4fc' : '#fcd34d' }}>
                                  {isAuto ? <Bot size={11} /> : <User size={11} />}
                                  {isAuto ? 'System Auto' : 'Manual'}
                                </span>
                                <div style={{ fontSize: 11, color: 'var(--color-text-muted)', marginTop: 2 }}>{c.exit_reason_label || 'Settled'}</div>
                              </td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>

                  <div className="mobile-only-cards">
                    {filteredSold.map(c => {
                      const netPnl = Number(c.realized_pnl ?? 0)
                      const isAuto = c.closed_by === 'AUTO_SYSTEM'
                      return (
                        <div key={c.trade_id} style={{ padding: 12, borderRadius: 8, background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border)' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6, gap: 6 }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                              <strong>{c.symbol.replace('.NS', '')}</strong>
                              <span style={{ fontSize: 10.5, color: isAuto ? '#a5b4fc' : '#fcd34d', fontWeight: 600 }}>
                                {isAuto ? 'Auto-Sold' : 'Manual'}
                              </span>
                            </div>
                            <strong className="mono" style={{ color: getPnlColor(netPnl) }}>
                              {getPnlSign(netPnl)}{formatINR(netPnl)}
                            </strong>
                          </div>
                          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 6, fontSize: 11.5, marginBottom: 6 }}>
                            <div><div style={{ fontSize: 10, color: 'var(--color-text-muted)' }}>Qty</div><strong className="mono">{c.quantity}</strong></div>
                            <div><div style={{ fontSize: 10, color: 'var(--color-text-muted)' }}>Buy</div><strong className="mono">{c.entry_price != null ? formatINR(c.entry_price) : '—'}</strong></div>
                            <div><div style={{ fontSize: 10, color: 'var(--color-text-muted)' }}>Sell</div><strong className="mono">{c.exit_price != null ? formatINR(c.exit_price) : '—'}</strong></div>
                          </div>
                          <div style={{ fontSize: 11, color: 'var(--color-text-muted)' }}>
                            {c.exit_reason_label || 'Settled'} · Held {c.holding_duration_label || `${c.days_held ?? 0}d`}
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </>
              )
            })()}
          </div>

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
