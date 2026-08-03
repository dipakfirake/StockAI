import { useEffect, useState } from 'react'
import { paperTradingApi, stocksApi } from '../services/api'
import { TrendingUp, TrendingDown, X, ShieldCheck, WalletCards } from 'lucide-react'

export default function PaperTradingPage() {
  const [trades, setTrades] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [quote, setQuote] = useState<any>(null)
  
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
  const totalSTT = closedTrades.reduce((sum, t) => sum + (t.stt_tax || 0), 0)
  const quantity = Number(form.quantity) || 0
  const referencePrice = form.order_type === 'LIMIT' ? Number(form.limit_price) : form.order_type === 'SL' ? Number(form.stop_price) : quote?.price || 0
  const orderValue = referencePrice * quantity
  const maxRisk = form.stop_loss ? Math.abs(referencePrice - Number(form.stop_loss)) * quantity : 0

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Advanced Paper Trading</h1>
        <p className="page-subtitle">Simulate real markets with slippage, ₹20 commission, STT taxes (0.1% delivery), and auto-execution limits/stops.</p>
      </div>

      {/* Summary */}
      <div className="grid-4" style={{ marginBottom: 20 }}>
        <div className="card"><div style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>Open / Pending</div><div style={{ fontSize: 24, fontWeight: 700 }}>{openTrades.length} / {pendingTrades.length}</div></div>
        <div className="card"><div style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>Realized PnL</div><div style={{ fontSize: 24, fontWeight: 700 }} className={totalPnL >= 0 ? 'positive' : 'negative'}>₹{totalPnL.toFixed(2)}</div></div>
        <div className="card"><div style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>STT Tax Paid</div><div style={{ fontSize: 24, fontWeight: 700, color: 'var(--color-text-muted)' }}>₹{totalSTT.toFixed(2)}</div></div>
        <div className="card">
          <div style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>Win Rate</div>
          <div style={{ fontSize: 24, fontWeight: 700 }}>
            {closedTrades.length ? Math.round(closedTrades.filter(t => t.realized_pnl > 0).length / closedTrades.length * 100) : 0}%
          </div>
        </div>
      </div>

      {/* Place Order Form */}
      <div className="card" style={{ marginBottom: 20 }}>
        <div className="card-title" style={{ marginBottom: 16 }}><WalletCards size={16} style={{ marginRight: 6 }} />Order Ticket <span className="badge badge-watch" style={{ marginLeft: 8 }}>Paper only</span></div>
        <form onSubmit={handlePlace} style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <div>
            <label className="form-label">Symbol</label>
            <input className="input" placeholder="e.g. RELIANCE.NS" required value={form.symbol} onChange={e => setForm({ ...form, symbol: e.target.value })} style={{ width: 140 }} />
          </div>
          <div>
            <label className="form-label">Product Type</label>
            <select className="input" value={form.product_type} onChange={e => setForm({ ...form, product_type: e.target.value })} style={{ width: 120 }}>
              <option value="INTRADAY">INTRADAY</option>
              <option value="DELIVERY">DELIVERY</option>
            </select>
          </div>
          <div>
            <label className="form-label">Direction</label>
            <select className="input" value={form.direction} onChange={e => setForm({ ...form, direction: e.target.value })} style={{ width: 120 }}>
              <option value="BUY">BUY</option>
              <option value="SELL">SELL (Short)</option>
            </select>
          </div>
          <div>
            <label className="form-label">Order Type</label>
            <select className="input" value={form.order_type} onChange={e => setForm({ ...form, order_type: e.target.value })} style={{ width: 120 }}>
              <option value="MARKET">MARKET</option>
              <option value="LIMIT">LIMIT</option>
              <option value="SL">SL (Stop Loss)</option>
            </select>
          </div>
          <div>
            <label className="form-label">Quantity</label>
            <input className="input" type="number" min="1" required value={form.quantity} onChange={e => setForm({ ...form, quantity: e.target.value })} style={{ width: 80 }} />
          </div>

          {form.order_type === 'LIMIT' && (
            <div>
              <label className="form-label">Limit Price</label>
              <input className="input" type="number" step="0.05" required value={form.limit_price} onChange={e => setForm({ ...form, limit_price: e.target.value })} style={{ width: 100 }} />
            </div>
          )}

          {form.order_type === 'SL' && (
            <div>
              <label className="form-label">Stop Price (Trigger)</label>
              <input className="input" type="number" step="0.05" required value={form.stop_price} onChange={e => setForm({ ...form, stop_price: e.target.value })} style={{ width: 100 }} />
            </div>
          )}

          <div>
            <label className="form-label">Target (Optional)</label>
            <input className="input" type="number" step="0.05" value={form.target_price} onChange={e => setForm({ ...form, target_price: e.target.value })} style={{ width: 100 }} />
          </div>
          
          <div>
            <label className="form-label">Stop Loss (Optional)</label>
            <input className="input" type="number" step="0.05" value={form.stop_loss} onChange={e => setForm({ ...form, stop_loss: e.target.value })} style={{ width: 100 }} />
          </div>

          <button type="submit" disabled={submitting} className={`btn ${form.direction === 'BUY' ? 'btn-success' : 'btn-danger'}`} style={{ height: 38 }}>
            {form.direction === 'BUY' ? <TrendingUp size={15} /> : <TrendingDown size={15} />}
            {submitting ? 'Placing…' : `PLACE ORDER`}
          </button>
        </form>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 10, marginTop: 16 }}>
          {[
            ['Live reference', quote ? `₹${quote.price.toLocaleString('en-IN')}` : 'Enter a symbol'],
            ['Estimated order value', orderValue ? `₹${orderValue.toLocaleString('en-IN', { maximumFractionDigits: 2 })}` : '—'],
            ['Maximum loss to stop', maxRisk ? `₹${maxRisk.toLocaleString('en-IN', { maximumFractionDigits: 2 })}` : 'Set a stop loss'],
            ['Price update', quote?.timestamp ? new Date(quote.timestamp).toLocaleTimeString('en-IN') : '—'],
          ].map(([label, value]) => <div key={label} style={{ background: 'var(--color-bg-secondary)', borderRadius: 8, padding: '9px 11px' }}><div style={{ fontSize: 11, color: 'var(--color-text-muted)' }}>{label}</div><div className="mono" style={{ marginTop: 2, fontWeight: 600 }}>{value}</div></div>)}
        </div>
        {form.direction === 'SELL' && form.product_type === 'DELIVERY' && <div style={{ display: 'flex', gap: 6, marginTop: 12, color: 'var(--color-neutral)', fontSize: 12 }}><ShieldCheck size={15} />Delivery short selling is not supported. Select Intraday.</div>}
        <style>{`
          .form-label { font-size: 11px; color: var(--color-text-muted); margin-bottom: 4px; display: block; text-transform: uppercase; font-weight: 600; letter-spacing: 0.5px; }
        `}</style>
      </div>

      {/* Pending Orders */}
      {pendingTrades.length > 0 && (
        <div className="card" style={{ marginBottom: 20 }}>
          <div className="card-header"><span className="card-title" style={{ color: '#f59e0b' }}>Pending Orders (Limit / SL)</span></div>
          <table className="table">
            <thead><tr><th>Symbol</th><th>Direction</th><th>Product</th><th>Type</th><th>Qty</th><th>Price Level</th><th>Target/SL</th><th>Action</th></tr></thead>
            <tbody>
              {pendingTrades.map(t => (
                <tr key={t.trade_id}>
                  <td className="mono" style={{ fontWeight: 600 }}>{t.symbol}</td>
                  <td><span className={`badge ${t.direction === 'BUY' ? 'badge-buy' : 'badge-sell'}`}>{t.direction}</span></td>
                  <td><span className="badge badge-secondary">{t.product_type}</span></td>
                  <td><span className="badge badge-secondary">{t.order_type}</span></td>
                  <td>{t.quantity}</td>
                  <td className="mono">
                    {t.order_type === 'LIMIT' ? `LMT: ₹${t.limit_price?.toFixed(2)}` : `SL: ₹${t.stop_price?.toFixed(2)}`}
                  </td>
                  <td className="mono" style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>
                    {t.target_price && `Tgt: ₹${t.target_price?.toFixed(2)} `}
                    {t.stop_loss && `SL: ₹${t.stop_loss?.toFixed(2)}`}
                  </td>
                  <td><button className="btn btn-secondary" style={{ padding: '4px 12px', fontSize: 12 }} onClick={() => handleClose(t.trade_id)}><X size={13} /> Cancel</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Open Trades */}
      <div className="card" style={{ marginBottom: 20 }}>
        <div className="card-header"><span className="card-title">Open Positions</span></div>
        {openTrades.length === 0 && <div className="empty-state">No open positions</div>}
        {openTrades.length > 0 && (
          <table className="table">
            <thead><tr><th>Symbol</th><th>Direction</th><th>Product</th><th>Qty</th><th>Entry</th><th>Target/SL</th><th>Current</th><th>Unrealized PnL</th><th>Action</th></tr></thead>
            <tbody>
              {openTrades.map(t => (
                <tr key={t.trade_id}>
                  <td className="mono" style={{ fontWeight: 600 }}>{t.symbol}</td>
                  <td><span className={`badge ${t.direction === 'BUY' ? 'badge-buy' : 'badge-sell'}`}>{t.direction}</span></td>
                  <td><span className="badge badge-secondary">{t.product_type}</span></td>
                  <td>{t.quantity}</td>
                  <td className="mono">₹{parseFloat(t.entry_price).toFixed(2)}</td>
                  <td className="mono" style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>
                    {t.target_price && `Tgt: ₹${t.target_price?.toFixed(2)} `}
                    {t.stop_loss && `SL: ₹${t.stop_loss?.toFixed(2)}`}
                  </td>
                  <td className="mono">{t.current_price ? `₹${t.current_price.toFixed(2)}` : '—'}</td>
                  <td className={t.unrealized_pnl >= 0 ? 'positive mono' : 'negative mono'}>
                    {t.unrealized_pnl !== undefined ? `${t.unrealized_pnl >= 0 ? '+' : ''}₹${t.unrealized_pnl.toFixed(2)}` : '—'}
                  </td>
                  <td><button className="btn btn-danger" style={{ padding: '4px 12px', fontSize: 12 }} onClick={() => handleClose(t.trade_id)}><X size={13} /> Exit</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Closed Trades */}
      {closedTrades.length > 0 && (
        <div className="card">
          <div className="card-header"><span className="card-title">Trade History (Closed / Cancelled)</span></div>
          <table className="table">
            <thead><tr><th>Symbol</th><th>Direction</th><th>Product</th><th>Qty</th><th>Entry</th><th>Exit</th><th>STT</th><th>Net PnL</th><th>Closed At</th></tr></thead>
            <tbody>
              {closedTrades.slice(0, 30).map(t => (
                <tr key={t.trade_id}>
                  <td className="mono" style={{ fontWeight: 600 }}>{t.symbol}</td>
                  <td><span className={`badge ${t.direction === 'BUY' ? 'badge-buy' : 'badge-sell'}`}>{t.direction}</span></td>
                  <td><span className="badge badge-secondary">{t.product_type}</span></td>
                  <td>{t.quantity}</td>
                  <td className="mono">{t.entry_price ? `₹${parseFloat(t.entry_price).toFixed(2)}` : '—'}</td>
                  <td className="mono">{t.exit_price ? `₹${parseFloat(t.exit_price).toFixed(2)}` : '—'}</td>
                  <td className="mono" style={{ color: 'var(--color-text-muted)' }}>₹{t.stt_tax?.toFixed(2) || '0.00'}</td>
                  <td className={t.realized_pnl >= 0 ? 'positive mono' : 'negative mono'} style={{ fontWeight: 600 }}>
                    {t.realized_pnl !== undefined ? `${t.realized_pnl >= 0 ? '+' : ''}₹${t.realized_pnl.toFixed(2)}` : '—'}
                  </td>
                  <td style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>{t.closed_at ? new Date(t.closed_at).toLocaleDateString('en-IN') : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
