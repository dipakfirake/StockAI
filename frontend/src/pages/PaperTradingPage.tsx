import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { paperTradingApi, stocksApi } from '../services/api'
import { TrendingUp, TrendingDown, X, ShieldCheck, WalletCards, Briefcase, Clock, PlusCircle, Calendar, Eye, AlignJustify, Bot, User } from 'lucide-react'
import StockSearchBox from '../components/StockSearchBox'
import HoldingDetailModal from '../components/HoldingDetailModal'
import MarketDepthModal from '../components/MarketDepthModal'
import { formatINR, formatNumber2Dec, getPnlColor, getPnlClass, getPnlSign } from '../utils/formatters'

export default function PaperTradingPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [trades, setTrades] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [quote, setQuote] = useState<any>(null)
  const initialTab = searchParams.get('tab')?.toUpperCase()
  const [activeTab, setActiveTab] = useState<'POSITIONS' | 'ORDERS' | 'HISTORY'>(
    initialTab === 'ORDERS' || initialTab === 'HISTORY' ? (initialTab as 'ORDERS' | 'HISTORY') : 'POSITIONS'
  )
  const [isOrderModalOpen, setIsOrderModalOpen] = useState(false)
  const [selectedPosition, setSelectedPosition] = useState<any | null>(null)
  const [depthModalSymbol, setDepthModalSymbol] = useState<string | null>(null)

  useEffect(() => {
    const qTab = searchParams.get('tab')?.toUpperCase()
    if (qTab === 'ORDERS' || qTab === 'HISTORY' || qTab === 'POSITIONS') {
      setActiveTab(qTab as 'POSITIONS' | 'ORDERS' | 'HISTORY')
    }
  }, [searchParams])
  
  const [form, setForm] = useState({ 
    symbol: '', 
    direction: 'BUY', 
    quantity: '1',
    order_type: 'MARKET',
    product_type: 'INTRADAY',
    limit_price: '',
    stop_price: '',
    target_price: '',
    stop_loss: ''
  })

  useEffect(() => { loadTrades() }, [])
  
  useEffect(() => {
    const symbol = form.symbol.trim()
    if (!symbol) { setQuote(null); return }
    const timer = window.setTimeout(async () => {
      try { setQuote((await stocksApi.getQuote(symbol)).data) } catch { setQuote(null) }
    }, 350)
    return () => window.clearTimeout(timer)
  }, [form.symbol])

  async function loadTrades() {
    try {
      const res = await paperTradingApi.list()
      setTrades(res.data.trades || [])
    } finally { setLoading(false) }
  }

  async function handlePlace(e: React.FormEvent) {
    e.preventDefault()
    setSubmitting(true)
    try {
      await paperTradingApi.place({
        symbol: form.symbol.toUpperCase(),
        direction: form.direction,
        quantity: parseInt(form.quantity),
        order_type: form.order_type,
        product_type: form.product_type,
        limit_price: form.limit_price ? parseFloat(form.limit_price) : undefined,
        stop_price: form.stop_price ? parseFloat(form.stop_price) : undefined,
        target_price: form.target_price ? parseFloat(form.target_price) : undefined,
        stop_loss: form.stop_loss ? parseFloat(form.stop_loss) : undefined,
      })
      await loadTrades()
      setForm({ ...form, symbol: '', limit_price: '', stop_price: '', target_price: '', stop_loss: '' })
      setIsOrderModalOpen(false)
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Failed to place trade')
    } finally { setSubmitting(false) }
  }

  async function handleClose(tradeId: string) {
    if (!confirm('Close/Cancel this trade at current market price?')) return
    await paperTradingApi.close(tradeId)
    await loadTrades()
  }

  const pendingTrades = trades.filter(t => t.status === 'PENDING')
  const openTrades = trades.filter(t => t.status === 'OPEN')
  const closedTrades = trades.filter(t => t.status === 'CLOSED')
  const totalPnL = closedTrades.reduce((sum, t) => sum + (t.realized_pnl || 0), 0)
  
  // Kite style header calculation
  const totalInvested = openTrades.reduce((sum, t) => sum + (parseFloat(t.entry_price) * t.quantity), 0)
  const currentOpenValue = openTrades.reduce((sum, t) => sum + ((t.current_price || parseFloat(t.entry_price)) * t.quantity), 0)
  const openPnL = openTrades.reduce((sum, t) => sum + (t.unrealized_pnl || 0), 0)
  const totalDayPnL = openTrades.reduce((sum, t) => sum + (t.day_pnl || 0), 0)

  const quantity = Number(form.quantity) || 0
  const referencePrice = form.order_type === 'LIMIT' ? Number(form.limit_price) : form.order_type === 'SL' ? Number(form.stop_price) : quote?.price || 0
  const orderValue = referencePrice * quantity

  return (
    <div style={{ maxWidth: 1200, margin: '0 auto' }}>
      {/* Compact Header Summary + Place Order CTA */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 18, borderBottom: '1px solid var(--color-border)', paddingBottom: 14, flexWrap: 'wrap', gap: 14 }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(115px, 1fr))', gap: 16, flex: '1 1 520px', minWidth: 0 }}>
          <div>
            <div style={{ fontSize: 11, color: 'var(--color-text-muted)', marginBottom: 2, textTransform: 'uppercase', fontWeight: 600 }}>Realized P&amp;L</div>
            <div style={{ fontSize: 19, fontWeight: 700, color: getPnlColor(totalPnL) }} className={`${getPnlClass(totalPnL)} mono`}>
              {getPnlSign(totalPnL)}{formatINR(totalPnL)}
            </div>
          </div>
          <div>
            <div style={{ fontSize: 11, color: 'var(--color-text-muted)', marginBottom: 2, textTransform: 'uppercase', fontWeight: 600 }}>Day P&amp;L</div>
            <div style={{ fontSize: 19, fontWeight: 700, color: getPnlColor(totalDayPnL) }} className={`${getPnlClass(totalDayPnL)} mono`}>
              {getPnlSign(totalDayPnL)}{formatINR(totalDayPnL)}
            </div>
          </div>
          <div>
            <div style={{ fontSize: 11, color: 'var(--color-text-muted)', marginBottom: 2, textTransform: 'uppercase', fontWeight: 600 }}>Unrealized</div>
            <div style={{ fontSize: 19, fontWeight: 700, color: getPnlColor(openPnL) }} className={`${getPnlClass(openPnL)} mono`}>
              {getPnlSign(openPnL)}{formatINR(openPnL)}
            </div>
          </div>
          <div>
            <div style={{ fontSize: 11, color: 'var(--color-text-muted)', marginBottom: 2, textTransform: 'uppercase', fontWeight: 600 }}>Invested</div>
            <div className="mono" style={{ fontSize: 16, fontWeight: 600, color: 'var(--color-text-primary)', marginTop: 2 }}>
              {formatINR(totalInvested)}
            </div>
          </div>
          <div>
            <div style={{ fontSize: 11, color: 'var(--color-text-muted)', marginBottom: 2, textTransform: 'uppercase', fontWeight: 600 }}>Current Value</div>
            <div className="mono" style={{ fontSize: 16, fontWeight: 600, color: 'var(--color-text-primary)', marginTop: 2 }}>
              {formatINR(currentOpenValue)}
            </div>
          </div>
        </div>
        <button
          className="btn btn-primary mobile-w-100"
          onClick={() => setIsOrderModalOpen(true)}
          style={{ gap: 6, flexShrink: 0 }}
        >
          <PlusCircle size={15} /> Place Order
        </button>
      </div>

      {/* Tabs */}
      <div className="mobile-scroll-tabs" style={{ display: 'flex', gap: 24, borderBottom: '1px solid var(--color-border-light)', marginBottom: 16 }}>
        <div
          onClick={() => { setActiveTab('POSITIONS'); setSearchParams({ tab: 'positions' }) }}
          style={{ padding: '10px 0', cursor: 'pointer', fontWeight: 600, fontSize: 13.5, whiteSpace: 'nowrap', borderBottom: activeTab === 'POSITIONS' ? '2px solid var(--color-accent-blue)' : '2px solid transparent', color: activeTab === 'POSITIONS' ? 'var(--color-accent-blue)' : 'var(--color-text-secondary)' }}
        >
          <Briefcase size={15} style={{ display: 'inline', marginRight: 6, verticalAlign: '-3px' }} /> Positions ({openTrades.length})
        </div>
        <div
          onClick={() => { setActiveTab('ORDERS'); setSearchParams({ tab: 'orders' }) }}
          style={{ padding: '10px 0', cursor: 'pointer', fontWeight: 600, fontSize: 13.5, whiteSpace: 'nowrap', borderBottom: activeTab === 'ORDERS' ? '2px solid var(--color-accent-blue)' : '2px solid transparent', color: activeTab === 'ORDERS' ? 'var(--color-accent-blue)' : 'var(--color-text-secondary)' }}
        >
          <Clock size={15} style={{ display: 'inline', marginRight: 6, verticalAlign: '-3px' }} /> Orders ({pendingTrades.length})
        </div>
        <div
          onClick={() => { setActiveTab('HISTORY'); setSearchParams({ tab: 'history' }) }}
          style={{ padding: '10px 0', cursor: 'pointer', fontWeight: 600, fontSize: 13.5, whiteSpace: 'nowrap', borderBottom: activeTab === 'HISTORY' ? '2px solid var(--color-accent-blue)' : '2px solid transparent', color: activeTab === 'HISTORY' ? 'var(--color-accent-blue)' : 'var(--color-text-secondary)' }}
        >
          History ({closedTrades.length})
        </div>
      </div>

      {/* Pending Orders Notice */}
      {activeTab === 'POSITIONS' && pendingTrades.length > 0 && (
        <div
          style={{
            marginBottom: 14,
            padding: '10px 14px',
            borderRadius: 8,
            background: 'rgba(245, 158, 11, 0.1)',
            border: '1px solid rgba(245, 158, 11, 0.35)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: 10,
            fontSize: 12.5,
          }}
        >
          <span style={{ color: '#fbbf24', fontWeight: 600, display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <Clock size={14} /> {pendingTrades.length} pending order{pendingTrades.length > 1 ? 's' : ''} ({pendingTrades.map((p) => p.symbol).slice(0, 3).join(', ')}{pendingTrades.length > 3 ? '…' : ''})
          </span>
          <button
            type="button"
            className="btn btn-secondary"
            style={{ padding: '4px 12px', fontSize: 12, borderColor: 'rgba(245, 158, 11, 0.4)', color: '#fbbf24' }}
            onClick={() => { setActiveTab('ORDERS'); setSearchParams({ tab: 'orders' }) }}
          >
            View Pending
          </button>
        </div>
      )}

      {/* Desktop Tables + Mobile Cards */}
      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        {activeTab === 'POSITIONS' && (
          <>
            <div className="table-container desktop-only-table" style={{ marginBottom: 0 }}>
              <table className="table" style={{ margin: 0, minWidth: '850px' }}>
                <thead style={{ background: 'var(--color-bg-card-hover)' }}>
                  <tr>
                    <th>Product</th>
                    <th>Instrument</th>
                    <th>Held</th>
                    <th>Qty</th>
                    <th>Avg Cost</th>
                    <th>LTP</th>
                    <th>Day P&amp;L</th>
                    <th>Net P&amp;L</th>
                    <th>Value</th>
                    <th style={{ textAlign: 'center' }}>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {openTrades.length === 0 ? (
                    <tr><td colSpan={10} style={{ textAlign: 'center', padding: 36, color: 'var(--color-text-muted)' }}>No open positions yet</td></tr>
                  ) : openTrades.map(t => {
                    const daysHeld = t.days_held ?? 0
                    return (
                      <tr key={t.trade_id} onClick={() => setSelectedPosition(t)} style={{ cursor: 'pointer' }}>
                        <td><span className="badge" style={{ fontSize: 10.5, background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border)', color: 'var(--color-text-secondary)' }}>{t.product_type}</span></td>
                        <td>
                          <div className="mono" style={{ fontWeight: 600 }}>{t.symbol}</div>
                          {(t.stop_loss || t.target_1 || t.target_price || t.ratchet_stage) && (
                            <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', marginTop: 2, fontSize: 10.5 }}>
                              {t.ratchet_stage && t.ratchet_stage !== 'INITIAL' && (
                                <span style={{ padding: '1px 5px', borderRadius: 4, background: 'var(--color-bullish-dim)', color: 'var(--color-bullish)', fontWeight: 700 }}>
                                  {String(t.ratchet_stage).replace(/_/g, ' ')}
                                </span>
                              )}
                              {t.stop_loss && <span className="mono" style={{ color: 'var(--color-bearish)' }}>SL ₹{Number(t.stop_loss).toFixed(2)}</span>}
                              {(t.target_3 || t.target_2 || t.target_price) && (
                                <span className="mono" style={{ color: 'var(--color-bullish)' }}>
                                  {t.target_1 ? `T1 ₹${Number(t.target_1).toFixed(0)}` : ''}
                                  {t.target_2 ? ` · T2 ₹${Number(t.target_2).toFixed(0)}` : ''}
                                  {t.target_3 ? ` · T3 ₹${Number(t.target_3).toFixed(0)}` : (!t.target_1 && t.target_price ? `T ₹${Number(t.target_price).toFixed(2)}` : '')}
                                </span>
                              )}
                            </div>
                          )}
                        </td>
                        <td className="mono" style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>{daysHeld === 0 ? 'Today' : `${daysHeld}d`}</td>
                        <td className={t.direction === 'BUY' ? 'positive mono' : 'negative mono'}>{t.direction === 'BUY' ? t.quantity : `-${t.quantity}`}</td>
                        <td className="mono">{formatINR(t.entry_price)}</td>
                        <td className="mono">{t.current_price ? formatINR(t.current_price) : '—'}</td>
                        <td className={`${getPnlClass(t.day_pnl)} mono`} style={{ whiteSpace: 'nowrap' }}>
                          <div style={{ color: getPnlColor(t.day_pnl), fontWeight: 600 }}>{t.day_pnl !== undefined ? `${getPnlSign(t.day_pnl)}${formatINR(t.day_pnl)}` : '—'}</div>
                          <div style={{ fontSize: 11, color: getPnlColor(t.day_change_pct) }}>{t.day_change_pct !== undefined ? `${getPnlSign(t.day_change_pct)}${t.day_change_pct.toFixed(2)}%` : ''}</div>
                        </td>
                        <td className={`${getPnlClass(t.unrealized_pnl)} mono`} style={{ whiteSpace: 'nowrap' }}>
                          <div style={{ color: getPnlColor(t.unrealized_pnl), fontWeight: 600 }}>{t.unrealized_pnl !== undefined ? `${getPnlSign(t.unrealized_pnl)}${formatINR(t.unrealized_pnl)}` : '—'}</div>
                          <div style={{ fontSize: 11, color: getPnlColor(t.pnl_pct) }}>{t.pnl_pct !== undefined ? `${getPnlSign(t.pnl_pct)}${t.pnl_pct.toFixed(2)}%` : ''}</div>
                        </td>
                        <td className="mono">{t.current_price ? formatINR(t.current_price * t.quantity) : '—'}</td>
                        <td style={{ textAlign: 'center' }}>
                          <div style={{ display: 'inline-flex', gap: 5 }} onClick={(e) => e.stopPropagation()}>
                            <button className="btn btn-secondary" style={{ padding: '4px 8px', fontSize: 11 }} onClick={() => setDepthModalSymbol(t.symbol)} title="Market Depth">
                              <AlignJustify size={12} /> Depth
                            </button>
                            <button className="btn btn-secondary" style={{ padding: '4px 8px', fontSize: 11 }} onClick={() => setSelectedPosition(t)} title="Inspect">
                              <Eye size={12} /> View
                            </button>
                            <button className="btn btn-danger" style={{ padding: '4px 10px', fontSize: 11 }} onClick={() => handleClose(t.trade_id)}>
                              Exit
                            </button>
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>

            <div className="mobile-only-cards" style={{ padding: 10 }}>
              {openTrades.length === 0 ? (
                <div className="empty-state" style={{ padding: 28 }}>No open positions yet</div>
              ) : openTrades.map(t => {
                const daysHeld = t.days_held ?? 0
                return (
                  <div key={t.trade_id} style={{ padding: 12, borderRadius: 8, background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border)' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6, gap: 6 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                        <strong>{t.symbol.replace('.NS', '')}</strong>
                        <span className={`badge ${t.direction === 'BUY' ? 'badge-buy' : 'badge-sell'}`} style={{ fontSize: 10 }}>{t.quantity} qty</span>
                        <span style={{ fontSize: 10.5, color: 'var(--color-text-muted)' }}>{daysHeld === 0 ? 'Today' : `${daysHeld}d`}</span>
                      </div>
                      <strong className="mono" style={{ color: getPnlColor(t.unrealized_pnl) }}>
                        {t.unrealized_pnl !== undefined ? `${getPnlSign(t.unrealized_pnl)}${formatINR(t.unrealized_pnl)}` : '—'}
                      </strong>
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 6, fontSize: 11.5, marginBottom: 8 }}>
                      <div><div style={{ fontSize: 10, color: 'var(--color-text-muted)' }}>Avg</div><strong className="mono">{formatINR(t.entry_price)}</strong></div>
                      <div><div style={{ fontSize: 10, color: 'var(--color-text-muted)' }}>LTP</div><strong className="mono">{t.current_price ? formatINR(t.current_price) : '—'}</strong></div>
                      <div><div style={{ fontSize: 10, color: 'var(--color-text-muted)' }}>Day P&amp;L</div><strong className="mono" style={{ color: getPnlColor(t.day_pnl) }}>{t.day_pnl !== undefined ? `${getPnlSign(t.day_pnl)}${formatINR(t.day_pnl)}` : '—'}</strong></div>
                    </div>
                    <div style={{ display: 'flex', gap: 6 }}>
                      <button className="btn btn-secondary" style={{ flex: 1, fontSize: 11.5 }} onClick={() => setDepthModalSymbol(t.symbol)}>Depth</button>
                      <button className="btn btn-secondary" style={{ flex: 1, fontSize: 11.5 }} onClick={() => setSelectedPosition(t)}>View</button>
                      <button className="btn btn-danger" style={{ flex: 1, fontSize: 11.5 }} onClick={() => handleClose(t.trade_id)}>Exit</button>
                    </div>
                  </div>
                )
              })}
            </div>
          </>
        )}

        {activeTab === 'ORDERS' && (
          <>
            <div className="table-container desktop-only-table" style={{ marginBottom: 0 }}>
              <table className="table" style={{ margin: 0, minWidth: '760px' }}>
                <thead style={{ background: 'var(--color-bg-card-hover)' }}>
                  <tr>
                    <th>Time</th><th>Type</th><th>Instrument</th><th>Product</th><th>Qty</th><th>Price</th><th>Status</th><th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {pendingTrades.length === 0 ? (
                    <tr><td colSpan={8} style={{ textAlign: 'center', padding: 36, color: 'var(--color-text-muted)' }}>No pending orders</td></tr>
                  ) : pendingTrades.map(t => {
                    const rawTs = t.opened_at || t.created_at
                    const parsedDate = rawTs ? new Date(rawTs) : null
                    const formattedTime = parsedDate && !isNaN(parsedDate.getTime()) ? parsedDate.toLocaleString() : (t.buy_date_formatted || '—')
                    const orderPrice = t.limit_price ?? t.stop_price
                    return (
                      <tr key={t.trade_id}>
                        <td style={{ fontSize: 12, color: 'var(--color-text-muted)', whiteSpace: 'nowrap' }}>{formattedTime}</td>
                        <td><span className={`badge ${t.direction === 'BUY' ? 'badge-buy' : 'badge-sell'}`}>{t.direction} {t.order_type}</span></td>
                        <td className="mono" style={{ fontWeight: 600 }}>{t.symbol}</td>
                        <td>{t.product_type}</td>
                        <td className="mono">{t.quantity}</td>
                        <td className="mono" style={{ fontSize: 12 }}>
                          <div>{orderPrice ? formatINR(orderPrice) : 'Market'}</div>
                          {(t.target_price || t.stop_loss) && (
                            <div style={{ fontSize: 10, color: 'var(--color-text-muted)' }}>
                              {t.target_price ? `T ₹${Number(t.target_price).toFixed(2)}` : ''}{t.target_price && t.stop_loss ? ' · ' : ''}{t.stop_loss ? `SL ₹${Number(t.stop_loss).toFixed(2)}` : ''}
                            </div>
                          )}
                        </td>
                        <td><span className="badge badge-hold">{t.status || 'PENDING'}</span></td>
                        <td><button className="btn btn-secondary" style={{ padding: '4px 12px', fontSize: 12 }} onClick={() => handleClose(t.trade_id)}>Cancel</button></td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>

            <div className="mobile-only-cards" style={{ padding: 10 }}>
              {pendingTrades.length === 0 ? (
                <div className="empty-state" style={{ padding: 28 }}>No pending orders</div>
              ) : pendingTrades.map(t => (
                <div key={t.trade_id} style={{ padding: 12, borderRadius: 8, background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                  <div>
                    <div className="mono" style={{ fontWeight: 700 }}>{t.symbol.replace('.NS', '')} · {t.direction} {t.quantity}</div>
                    <div style={{ fontSize: 11.5, color: 'var(--color-text-muted)' }}>{t.limit_price ?? t.stop_price ? formatINR(t.limit_price ?? t.stop_price) : 'Market'}</div>
                  </div>
                  <button className="btn btn-secondary" style={{ fontSize: 12 }} onClick={() => handleClose(t.trade_id)}>Cancel</button>
                </div>
              ))}
            </div>
          </>
        )}

        {activeTab === 'HISTORY' && (
          <>
            <div className="table-container desktop-only-table" style={{ marginBottom: 0 }}>
              <table className="table" style={{ margin: 0, minWidth: '880px' }}>
                <thead style={{ background: 'var(--color-bg-card-hover)' }}>
                  <tr>
                    <th>Instrument</th><th>Side</th><th>Qty</th><th>Avg Cost</th><th>Exit</th><th>Charges</th><th>Net P&amp;L</th><th>Sold By</th><th>Closed</th>
                  </tr>
                </thead>
                <tbody>
                  {closedTrades.length === 0 ? (
                    <tr><td colSpan={9} style={{ textAlign: 'center', padding: 36, color: 'var(--color-text-muted)' }}>No trade history</td></tr>
                  ) : closedTrades.slice(0, 50).map(t => {
                    const isAuto = t.closed_by === 'AUTO_SYSTEM'
                    return (
                      <tr key={t.trade_id}>
                        <td className="mono" style={{ fontWeight: 600 }}>
                          <div>{t.symbol}</div>
                          <div style={{ fontSize: 10.5, color: 'var(--color-text-muted)', fontWeight: 400 }}>{t.product_type} · {t.holding_duration_label || `${t.days_held ?? 0}d`}</div>
                        </td>
                        <td><span className={`badge ${t.direction === 'BUY' ? 'badge-buy' : 'badge-sell'}`}>{t.direction}</span></td>
                        <td className="mono">{t.quantity}</td>
                        <td className="mono">{t.entry_price ? formatNumber2Dec(t.entry_price) : '—'}</td>
                        <td className="mono">{t.exit_price ? formatNumber2Dec(t.exit_price) : '—'}</td>
                        <td className="mono" style={{ fontSize: 12 }}>₹{formatNumber2Dec(t.total_charges ?? ((t.commission || 0) + (t.stt_tax || 0)))}</td>
                        <td className={t.realized_pnl >= 0 ? 'positive mono' : 'negative mono'} style={{ fontWeight: 600 }}>
                          <div>{t.realized_pnl !== undefined && t.realized_pnl !== null ? `${t.realized_pnl >= 0 ? '+' : ''}${formatNumber2Dec(t.realized_pnl)}` : '—'}</div>
                          {t.pnl_pct != null && <div style={{ fontSize: 10.5 }}>{t.pnl_pct >= 0 ? '+' : ''}{Number(t.pnl_pct).toFixed(2)}%</div>}
                        </td>
                        <td>
                          <span className="badge" style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 10, background: isAuto ? 'rgba(99, 102, 241, 0.16)' : 'rgba(245, 158, 11, 0.14)', color: isAuto ? '#a5b4fc' : '#fcd34d' }}>
                            {isAuto ? <Bot size={11} /> : <User size={11} />}
                            {isAuto ? 'System' : 'Manual'}
                          </span>
                          {t.exit_reason_label && <div style={{ fontSize: 10.5, color: 'var(--color-text-muted)', marginTop: 2 }}>{t.exit_reason_label}</div>}
                        </td>
                        <td style={{ fontSize: 11, color: 'var(--color-text-muted)' }}>
                          {t.sell_date_formatted || (t.closed_at ? new Date(t.closed_at).toLocaleString() : '—')}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>

            <div className="mobile-only-cards" style={{ padding: 10 }}>
              {closedTrades.length === 0 ? (
                <div className="empty-state" style={{ padding: 28 }}>No trade history</div>
              ) : closedTrades.slice(0, 50).map(t => {
                const isAuto = t.closed_by === 'AUTO_SYSTEM'
                return (
                  <div key={t.trade_id} style={{ padding: 12, borderRadius: 8, background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border)' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <strong>{t.symbol.replace('.NS', '')}</strong>
                        <span style={{ fontSize: 10.5, color: isAuto ? '#a5b4fc' : '#fcd34d' }}>{isAuto ? 'System Auto' : 'Manual'}</span>
                      </div>
                      <strong className={t.realized_pnl >= 0 ? 'positive mono' : 'negative mono'}>
                        {t.realized_pnl != null ? `${t.realized_pnl >= 0 ? '+' : ''}₹${formatNumber2Dec(t.realized_pnl)}` : '—'}
                      </strong>
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 6, fontSize: 11.5 }}>
                      <div><div style={{ fontSize: 10, color: 'var(--color-text-muted)' }}>Qty</div><strong className="mono">{t.quantity}</strong></div>
                      <div><div style={{ fontSize: 10, color: 'var(--color-text-muted)' }}>Buy</div><strong className="mono">{t.entry_price ? formatINR(t.entry_price) : '—'}</strong></div>
                      <div><div style={{ fontSize: 10, color: 'var(--color-text-muted)' }}>Exit</div><strong className="mono">{t.exit_price ? formatINR(t.exit_price) : '—'}</strong></div>
                    </div>
                  </div>
                )
              })}
            </div>
          </>
        )}
      </div>

      {/* Floating Order Modal */}
      {isOrderModalOpen && (
        <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(3px)', zIndex: 9999, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '16px' }}>
          <div className="card" style={{ width: '100%', maxWidth: 450, padding: 0, overflow: 'hidden', border: '1px solid var(--color-border)' }}>
            
            {/* Modal Header */}
            <div style={{ 
              background: form.direction === 'BUY' ? 'var(--color-buy)' : 'var(--color-sell)', 
              color: 'white', padding: '16px 20px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' 
            }}>
              <div>
                <h3 style={{ margin: 0, fontWeight: 600 }}>{form.direction} {form.symbol || 'Instrument'}</h3>
                <div style={{ fontSize: 12, opacity: 0.9, marginTop: 4 }}>
                  {form.product_type} • {form.order_type}
                </div>
              </div>
              <button onClick={() => setIsOrderModalOpen(false)} style={{ background: 'none', border: 'none', color: 'white', cursor: 'pointer' }}>
                <X size={20} />
              </button>
            </div>

            {/* Modal Body */}
            <div style={{ padding: 20 }}>
              <form onSubmit={handlePlace}>
                <div style={{ display: 'flex', gap: 16, marginBottom: 16 }}>
                  <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
                    <input type="radio" checked={form.direction === 'BUY'} onChange={() => setForm({...form, direction: 'BUY'})} /> BUY
                  </label>
                  <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
                    <input type="radio" checked={form.direction === 'SELL'} onChange={() => setForm({...form, direction: 'SELL'})} /> SELL
                  </label>
                </div>

                <div style={{ marginBottom: 16 }}>
                  <label className="form-label">Symbol</label>
                  <StockSearchBox 
                    placeholder="e.g. RELIANCE.NS" 
                    width="100%" 
                    autoNavigate={false} 
                    clearOnSelect={false}
                    value={form.symbol} 
                    onChange={(val) => setForm({ ...form, symbol: val })} 
                  />
                </div>

                {form.symbol && (
                  <div style={{ marginBottom: 16 }}>
                    <button
                      type="button"
                      className="btn btn-secondary"
                      onClick={() => setDepthModalSymbol(form.symbol)}
                      style={{ fontSize: 12, width: '100%' }}
                    >
                      <AlignJustify size={13} /> Market Depth
                    </button>
                  </div>
                )}

                <div style={{ display: 'flex', gap: 16, marginBottom: 16 }}>
                  <div style={{ flex: 1 }}>
                    <label className="form-label">Product</label>
                    <select className="input" value={form.product_type} onChange={e => setForm({ ...form, product_type: e.target.value })} style={{ width: '100%' }}>
                      <option value="INTRADAY">Intraday · MIS</option>
                      <option value="DELIVERY">Delivery · CNC</option>
                    </select>
                  </div>
                  <div style={{ flex: 1 }}>
                    <label className="form-label">Order Type</label>
                    <select className="input" value={form.order_type} onChange={e => setForm({ ...form, order_type: e.target.value })} style={{ width: '100%' }}>
                      <option value="MARKET">Market</option>
                      <option value="LIMIT">Limit</option>
                      <option value="SL">Stop Loss</option>
                    </select>
                  </div>
                </div>

                <div style={{ display: 'flex', gap: 16, marginBottom: 20 }}>
                  <div style={{ flex: 1 }}>
                    <label className="form-label">Quantity</label>
                    <input className="input" type="number" min="1" required value={form.quantity} onChange={e => setForm({ ...form, quantity: e.target.value })} style={{ width: '100%' }} />
                  </div>
                  <div style={{ flex: 1 }}>
                    <label className="form-label">Price</label>
                    <input className="input" type="number" step="0.05" disabled={form.order_type === 'MARKET'} required={form.order_type === 'LIMIT'} value={form.limit_price} onChange={e => setForm({ ...form, limit_price: e.target.value })} style={{ width: '100%' }} placeholder={form.order_type === 'MARKET' ? 'Market' : '0.00'} />
                  </div>
                </div>
                
                {form.order_type === 'SL' && (
                  <div style={{ marginBottom: 20 }}>
                    <label className="form-label">Trigger Price</label>
                    <input className="input" type="number" step="0.05" required value={form.stop_price} onChange={e => setForm({ ...form, stop_price: e.target.value })} style={{ width: '100%' }} />
                  </div>
                )}

                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 24, paddingTop: 16, borderTop: '1px solid var(--color-border-light)' }}>
                  <div style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>
                    <div>Margin Required: <span style={{ color: 'var(--color-text-primary)', fontWeight: 600 }}>{formatINR(orderValue || 0)}</span></div>
                    {quote?.price && <div>LTP: <span className="mono">{formatINR(quote.price)}</span></div>}
                  </div>
                  
                  <button type="submit" disabled={submitting} className={`btn`} style={{ 
                    background: form.direction === 'BUY' ? 'var(--color-buy)' : 'var(--color-sell)', 
                    color: 'white', padding: '10px 24px', fontWeight: 600 
                  }}>
                    {submitting ? 'Placing…' : form.direction}
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}

      {/* Holding Detail Modal */}
      <HoldingDetailModal
        isOpen={!!selectedPosition}
        onClose={() => setSelectedPosition(null)}
        holding={selectedPosition}
        onExit={handleClose}
      />

      {/* Zerodha Kite Market Depth Modal */}
      {depthModalSymbol && (
        <MarketDepthModal
          isOpen={!!depthModalSymbol}
          symbol={depthModalSymbol}
          onClose={() => setDepthModalSymbol(null)}
          onTrade={(direction, price) => {
            setForm({
              ...form,
              symbol: depthModalSymbol,
              direction,
              limit_price: price ? String(price) : form.limit_price,
              order_type: price ? 'LIMIT' : 'MARKET'
            })
            setDepthModalSymbol(null)
            setIsOrderModalOpen(true)
          }}
        />
      )}

      <style>{`
        .form-label { font-size: 11px; color: var(--color-text-muted); margin-bottom: 6px; display: block; text-transform: uppercase; font-weight: 600; letter-spacing: 0.5px; }
      `}</style>
    </div>
  )
}
