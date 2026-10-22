import { useEffect, useState } from 'react'
import { paperTradingApi, stocksApi } from '../services/api'
import { TrendingUp, TrendingDown, X, ShieldCheck, WalletCards, Briefcase, Clock, PlusCircle, Calendar, Eye } from 'lucide-react'
import StockSearchBox from '../components/StockSearchBox'
import HoldingDetailModal from '../components/HoldingDetailModal'
import { formatINR, formatNumber2Dec } from '../utils/formatters'

export default function PaperTradingPage() {
  const [trades, setTrades] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [quote, setQuote] = useState<any>(null)
  const [activeTab, setActiveTab] = useState<'POSITIONS' | 'ORDERS' | 'HISTORY'>('POSITIONS')
  const [isOrderModalOpen, setIsOrderModalOpen] = useState(false)
  const [selectedPosition, setSelectedPosition] = useState<any | null>(null)
  
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
      {/* Dashboard Top Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: 24, borderBottom: '1px solid var(--color-border)', paddingBottom: 16 }}>
        <div style={{ display: 'flex', gap: 32, flexWrap: 'wrap' }}>
          <div>
            <div style={{ fontSize: 12, color: 'var(--color-text-muted)', marginBottom: 4, textTransform: 'uppercase', fontWeight: 600 }}>Total Realized P&L</div>
            <div style={{ fontSize: 24, fontWeight: 600 }} className={totalPnL >= 0 ? 'positive' : 'negative'}>
              {totalPnL >= 0 ? '+' : ''}{formatINR(totalPnL)}
            </div>
          </div>
          <div>
            <div style={{ fontSize: 12, color: 'var(--color-text-muted)', marginBottom: 4, textTransform: 'uppercase', fontWeight: 600 }}>Day's P&L (Today)</div>
            <div style={{ fontSize: 24, fontWeight: 600 }} className={totalDayPnL >= 0 ? 'positive' : 'negative'}>
              {totalDayPnL >= 0 ? '+' : ''}{formatINR(totalDayPnL)}
            </div>
          </div>
          <div>
            <div style={{ fontSize: 12, color: 'var(--color-text-muted)', marginBottom: 4, textTransform: 'uppercase', fontWeight: 600 }}>Open Unrealized P&L</div>
            <div style={{ fontSize: 24, fontWeight: 600 }} className={openPnL >= 0 ? 'positive' : 'negative'}>
              {openPnL >= 0 ? '+' : ''}{formatINR(openPnL)}
            </div>
          </div>
          <div>
            <div style={{ fontSize: 12, color: 'var(--color-text-muted)', marginBottom: 4, textTransform: 'uppercase', fontWeight: 600 }}>Invested</div>
            <div style={{ fontSize: 18, fontWeight: 600, color: 'var(--color-text-primary)', marginTop: 4 }}>
              {formatINR(totalInvested)}
            </div>
          </div>
          <div>
            <div style={{ fontSize: 12, color: 'var(--color-text-muted)', marginBottom: 4, textTransform: 'uppercase', fontWeight: 600 }}>Current Value</div>
            <div style={{ fontSize: 18, fontWeight: 600, color: 'var(--color-text-primary)', marginTop: 4 }}>
              {formatINR(currentOpenValue)}
            </div>
          </div>
        </div>
        <button 
          className="btn btn-primary" 
          onClick={() => setIsOrderModalOpen(true)}
          style={{ display: 'flex', alignItems: 'center', gap: 6 }}
        >
          <PlusCircle size={16} /> Place Order
        </button>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 30, borderBottom: '1px solid var(--color-border-light)', marginBottom: 20 }}>
        <div 
          onClick={() => setActiveTab('POSITIONS')}
          style={{ padding: '10px 0', cursor: 'pointer', fontWeight: 500, borderBottom: activeTab === 'POSITIONS' ? '2px solid var(--color-accent-blue)' : '2px solid transparent', color: activeTab === 'POSITIONS' ? 'var(--color-accent-blue)' : 'var(--color-text-secondary)' }}
        >
          <Briefcase size={16} style={{ display: 'inline', marginRight: 6, verticalAlign: '-3px' }}/> Positions ({openTrades.length})
        </div>
        <div 
          onClick={() => setActiveTab('ORDERS')}
          style={{ padding: '10px 0', cursor: 'pointer', fontWeight: 500, borderBottom: activeTab === 'ORDERS' ? '2px solid var(--color-accent-blue)' : '2px solid transparent', color: activeTab === 'ORDERS' ? 'var(--color-accent-blue)' : 'var(--color-text-secondary)' }}
        >
          <Clock size={16} style={{ display: 'inline', marginRight: 6, verticalAlign: '-3px' }}/> Orders ({pendingTrades.length})
        </div>
        <div 
          onClick={() => setActiveTab('HISTORY')}
          style={{ padding: '10px 0', cursor: 'pointer', fontWeight: 500, borderBottom: activeTab === 'HISTORY' ? '2px solid var(--color-accent-blue)' : '2px solid transparent', color: activeTab === 'HISTORY' ? 'var(--color-accent-blue)' : 'var(--color-text-secondary)' }}
        >
          History ({closedTrades.length})
        </div>
      </div>

      {/* Content based on Active Tab */}
      <div className="card table-container" style={{ padding: 0, overflowX: 'auto' }}>
        {activeTab === 'POSITIONS' && (
          <table className="table" style={{ margin: 0, minWidth: '850px' }}>
            <thead style={{ background: 'var(--color-bg-card-hover)' }}>
              <tr>
                <th>Product</th>
                <th>Instrument</th>
                <th>Holding Period</th>
                <th>Qty.</th>
                <th>Avg. Cost</th>
                <th>LTP</th>
                <th>Today's P&L</th>
                <th>Overall Return on Buy</th>
                <th>Current Value</th>
                <th style={{ textAlign: 'center' }}>Action</th>
              </tr>
            </thead>
            <tbody>
              {openTrades.length === 0 ? (
                <tr><td colSpan={10} style={{ textAlign: 'center', padding: 40, color: 'var(--color-text-muted)' }}>You don't have any open positions yet</td></tr>
              ) : openTrades.map(t => {
                const daysHeld = t.days_held ?? 0
                const isDayProfitable = (t.day_pnl ?? 0) >= 0
                const isOverallProfitable = (t.unrealized_pnl ?? 0) >= 0

                return (
                  <tr 
                    key={t.trade_id}
                    onClick={() => setSelectedPosition(t)}
                    style={{ cursor: 'pointer', transition: 'background 0.15s ease' }}
                    title="Click to view detailed holding duration & P&L"
                  >
                    <td><span className="badge badge-secondary">{t.product_type}</span></td>
                    <td className="mono" style={{ fontWeight: 600 }}>{t.symbol}</td>
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
                          padding: '2px 7px',
                          fontSize: 11
                        }}
                      >
                        <Calendar size={11} />
                        {daysHeld === 0 ? 'Today' : `${daysHeld}d held`}
                      </span>
                    </td>
                    <td className={t.direction === 'BUY' ? 'positive' : 'negative'}>{t.direction === 'BUY' ? t.quantity : `-${t.quantity}`}</td>
                    <td className="mono">{formatINR(t.entry_price)}</td>
                    <td className="mono">{t.current_price ? formatINR(t.current_price) : '—'}</td>
                    
                    {/* Today's P&L for current stock */}
                    <td className={isDayProfitable ? 'positive mono' : 'negative mono'}>
                      <div>{t.day_pnl !== undefined ? `${t.day_pnl >= 0 ? '+' : ''}${formatINR(t.day_pnl)}` : '—'}</div>
                      <div style={{ fontSize: 11, opacity: 0.85 }}>
                        {t.day_change_pct !== undefined ? `${t.day_change_pct >= 0 ? '+' : ''}${t.day_change_pct.toFixed(2)}%` : ''}
                      </div>
                    </td>

                    {/* Overall Profit/Loss % of buying */}
                    <td className={isOverallProfitable ? 'positive mono' : 'negative mono'} style={{ fontWeight: 500 }}>
                      <div>{t.unrealized_pnl !== undefined ? `${t.unrealized_pnl >= 0 ? '+' : ''}${formatINR(t.unrealized_pnl)}` : '—'}</div>
                      <div style={{ fontSize: 11, opacity: 0.85 }}>
                        {t.pnl_pct !== undefined ? `${t.pnl_pct >= 0 ? '+' : ''}${t.pnl_pct.toFixed(2)}%` : ''}
                      </div>
                    </td>

                    <td className="mono">{t.current_price ? formatINR(t.current_price * t.quantity) : '—'}</td>
                    <td style={{ textAlign: 'center' }}>
                      <div style={{ display: 'inline-flex', gap: 6 }} onClick={(e) => e.stopPropagation()}>
                        <button 
                          className="btn btn-secondary" 
                          style={{ padding: '4px 8px', fontSize: 11, display: 'inline-flex', alignItems: 'center', gap: 3 }}
                          onClick={() => setSelectedPosition(t)}
                          title="Inspect details"
                        >
                          <Eye size={12} /> View
                        </button>
                        <button 
                          className="btn btn-secondary" 
                          style={{ padding: '4px 10px', fontSize: 11, border: '1px solid var(--color-border)' }} 
                          onClick={() => handleClose(t.trade_id)}
                        >
                          Exit
                        </button>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}

        {activeTab === 'ORDERS' && (
          <table className="table" style={{ margin: 0, minWidth: '650px' }}>
            <thead style={{ background: 'var(--color-bg-card-hover)' }}>
              <tr>
                <th>Time</th><th>Type</th><th>Instrument</th><th>Product</th><th>Qty.</th><th>Status</th><th>Action</th>
              </tr>
            </thead>
            <tbody>
              {pendingTrades.length === 0 ? (
                <tr><td colSpan={7} style={{ textAlign: 'center', padding: 40, color: 'var(--color-text-muted)' }}>You don't have any pending orders</td></tr>
              ) : pendingTrades.map(t => (
                <tr key={t.trade_id}>
                  <td style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>{new Date(t.created_at).toLocaleTimeString()}</td>
                  <td>
                    <span className={`badge ${t.direction === 'BUY' ? 'badge-buy' : 'badge-sell'}`}>{t.direction} {t.order_type}</span>
                  </td>
                  <td className="mono" style={{ fontWeight: 600 }}>{t.symbol}</td>
                  <td><span className="badge badge-secondary">{t.product_type}</span></td>
                  <td>{t.quantity}</td>
                  <td><span className="badge badge-watch">OPEN</span></td>
                  <td>
                    <button className="btn btn-secondary" style={{ padding: '4px 12px', fontSize: 12 }} onClick={() => handleClose(t.trade_id)}>
                      Cancel
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {activeTab === 'HISTORY' && (
          <table className="table" style={{ margin: 0, minWidth: '650px' }}>
            <thead style={{ background: 'var(--color-bg-card-hover)' }}>
              <tr>
                <th>Instrument</th><th>Direction</th><th>Qty.</th><th>Avg. Cost</th><th>Exit Price</th><th>Realized P&L</th><th>Date</th>
              </tr>
            </thead>
            <tbody>
              {closedTrades.length === 0 ? (
                <tr><td colSpan={7} style={{ textAlign: 'center', padding: 40, color: 'var(--color-text-muted)' }}>No trade history</td></tr>
              ) : closedTrades.slice(0, 30).map(t => (
                <tr key={t.trade_id}>
                  <td className="mono" style={{ fontWeight: 600 }}>{t.symbol}</td>
                  <td><span className={`badge ${t.direction === 'BUY' ? 'badge-buy' : 'badge-sell'}`}>{t.direction}</span></td>
                  <td>{t.quantity}</td>
                  <td className="mono">{t.entry_price ? formatNumber2Dec(t.entry_price) : '—'}</td>
                  <td className="mono">{t.exit_price ? formatNumber2Dec(t.exit_price) : '—'}</td>
                  <td className={t.realized_pnl >= 0 ? 'positive mono' : 'negative mono'} style={{ fontWeight: 600 }}>
                    {t.realized_pnl !== undefined ? `${t.realized_pnl >= 0 ? '+' : ''}${formatNumber2Dec(t.realized_pnl)}` : '—'}
                  </td>
                  <td style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>{t.closed_at ? new Date(t.closed_at).toLocaleDateString() : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
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
                  <label className="form-label">Search Symbol</label>
                  <StockSearchBox 
                    placeholder="e.g. RELIANCE.NS" 
                    width="100%" 
                    autoNavigate={false} 
                    clearOnSelect={false}
                    value={form.symbol} 
                    onChange={(val) => setForm({ ...form, symbol: val })} 
                  />
                </div>

                <div style={{ display: 'flex', gap: 16, marginBottom: 16 }}>
                  <div style={{ flex: 1 }}>
                    <label className="form-label">Product</label>
                    <select className="input" value={form.product_type} onChange={e => setForm({ ...form, product_type: e.target.value })} style={{ width: '100%' }}>
                      <option value="INTRADAY">MIS (Intraday)</option>
                      <option value="DELIVERY">CNC (Delivery)</option>
                    </select>
                  </div>
                  <div style={{ flex: 1 }}>
                    <label className="form-label">Order Type</label>
                    <select className="input" value={form.order_type} onChange={e => setForm({ ...form, order_type: e.target.value })} style={{ width: '100%' }}>
                      <option value="MARKET">Market</option>
                      <option value="LIMIT">Limit</option>
                      <option value="SL">SL (Stop Loss)</option>
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

      <style>{`
        .form-label { font-size: 11px; color: var(--color-text-muted); margin-bottom: 6px; display: block; text-transform: uppercase; font-weight: 600; letter-spacing: 0.5px; }
      `}</style>
    </div>
  )
}
