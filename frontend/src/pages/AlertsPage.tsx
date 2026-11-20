import { useEffect, useState, useMemo } from 'react'
import { alertsApi, stocksApi } from '../services/api'
import { 
  Bell, PlusCircle, Trash2, BellOff, ShieldAlert, ShieldCheck, 
  Target, TrendingUp, TrendingDown, RefreshCw, AlertTriangle, 
  ExternalLink, ArrowUpRight, ArrowDownRight, CheckCircle2, DollarSign,
  Briefcase, Sparkles, X, Layers, Filter, Zap
} from 'lucide-react'
import StockSearchBox from '../components/StockSearchBox'
import ZerodhaOrderModal from '../components/ZerodhaOrderModal'
import { toast } from '../components/Toast'

const SECTORS = [
  { value: 'ALL', label: '🌐 All Sectors (100+ Stocks)' },
  { value: 'NIFTY_50', label: '🏛️ Nifty 50 Large Cap' },
  { value: 'BANKING', label: '🏦 Banking & Financials' },
  { value: 'IT', label: '💻 IT & Technology' },
  { value: 'AUTO', label: '🚗 Automobiles & OEMs' },
  { value: 'PHARMA', label: '💊 Healthcare & Pharma' },
  { value: 'ENERGY', label: '⚡ Energy, Oil & Power' },
  { value: 'FMCG', label: '🛒 FMCG & Consumer Goods' },
  { value: 'METAL', label: '🏗️ Metal & Mining' },
  { value: 'MID_CAP', label: '📈 Mid Cap Growth' },
  { value: 'SMALL_CAP', label: '🚀 Small Cap High Alpha' },
]

const PROXIMITY_FILTERS = [
  { value: 1.0, label: '🎯 Within 1.0% (Immediate Entry Zone)' },
  { value: 2.0, label: '⚡ Within 2.0% (Prime Pullback Setup)' },
  { value: 3.0, label: '⏳ Within 3.0% (Approaching Watchlist)' },
  { value: 5.0, label: '🔭 Within 5.0% (Broad Proximity)' },
]

const CONDITION_TYPES = [
  { value: 'PRICE_ABOVE', label: 'Price Above' },
  { value: 'PRICE_BELOW', label: 'Price Below' },
  { value: 'BUY_PROXIMITY', label: 'Buy Zone Approaching (Pre-Alert)' },
  { value: 'TARGET_PROXIMITY', label: 'Target Approaching (Sell Pre-Alert)' },
  { value: 'TARGET_HIT', label: 'Target Reached (Sell Trigger)' },
  { value: 'STOP_LOSS_PROXIMITY', label: 'Stop Loss Approaching' },
  { value: 'STOP_LOSS_HIT', label: 'Stop Loss Breached' },
  { value: 'RSI_ABOVE', label: 'RSI Above' },
  { value: 'RSI_BELOW', label: 'RSI Below' },
  { value: 'MACD_CROSS_UP', label: 'MACD Cross Up' },
  { value: 'MACD_CROSS_DOWN', label: 'MACD Cross Down' },
  { value: 'PATTERN', label: 'Candlestick Pattern' },
]

const PATTERN_TYPES = [
  { value: '1', label: 'Hammer' },
  { value: '2', label: 'Bullish Engulfing' },
  { value: '3', label: 'Bearish Engulfing' },
  { value: '4', label: 'Bullish Order Block' },
]

export default function AlertsPage() {
  const [activeTab, setActiveTab] = useState<'SCREENER_RADAR' | 'HOLDINGS' | 'RADAR' | 'CUSTOM'>('SCREENER_RADAR')
  
  // Screener Best Buy Radar State (all 10 sectors + ALL)
  const [radarSector, setRadarSector] = useState<string>('ALL')
  const [radarProximityPct, setRadarProximityPct] = useState<number>(3.0)
  const [radarData, setRadarData] = useState<any>({ candidates: [], summary: { at_best_buy: 0, near_best_buy: 0, approaching: 0 }, total_candidates: 0 })
  const [loadingRadar, setLoadingRadar] = useState<boolean>(true)
  const [settingBulkAlerts, setSettingBulkAlerts] = useState<boolean>(false)
  const [settingSingleAlertSym, setSettingSingleAlertSym] = useState<string | null>(null)

  // Custom / General Alerts
  const [alerts, setAlerts] = useState<any[]>([])
  const [loadingAlerts, setLoadingAlerts] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ 
    symbol: '', 
    condition_type: 'PRICE_ABOVE', 
    condition_value: '', 
    message: '', 
    priority: 'MEDIUM' as 'HIGH' | 'MEDIUM' | 'LOW', 
    delivery_method: 'IN_APP' as 'IN_APP' | 'EMAIL' | 'BOTH' 
  })
  const [submitting, setSubmitting] = useState(false)

  // Holdings Risk Monitor
  const [holdings, setHoldings] = useState<any[]>([])
  const [holdingsSummary, setHoldingsSummary] = useState<any>({ total_held: 0, targets_approaching: 0, sl_warnings: 0 })
  const [loadingHoldings, setLoadingHoldings] = useState(true)
  const [syncingHoldings, setSyncingHoldings] = useState(false)

  // Zerodha Order Modal for Sell / Exit
  const [sellModalData, setSellModalData] = useState<any | null>(null)
  const [sellModalOpen, setSellModalOpen] = useState(false)

  // Zerodha Kite GTT Creation Modal State
  const [showGttSearchPrompt, setShowGttSearchPrompt] = useState(false)
  const [gttSymbol, setGttSymbol] = useState('')
  const [gttOrderData, setGttOrderData] = useState<any | null>(null)
  const [gttOrderModalOpen, setGttOrderModalOpen] = useState(false)
  const [fetchingGttQuote, setFetchingGttQuote] = useState(false)

  const handleOpenRadarGtt = (candidate: any) => {
    setGttOrderData({
      symbol: candidate.symbol,
      name: candidate.name || candidate.symbol,
      currentPrice: candidate.cmp,
      bestBuyPrice: candidate.best_buy_price,
      targetPrice: candidate.target_price,
      stopLoss: candidate.stop_loss,
    })
    setGttOrderModalOpen(true)
  }

  const handleSetRadarAlert = async (candidate: any) => {
    setSettingSingleAlertSym(candidate.symbol)
    try {
      await alertsApi.screenerSetup({
        symbol: candidate.symbol,
        current_price: candidate.cmp,
        best_buy_price: candidate.best_buy_price,
        target_price: candidate.target_price,
        stop_loss: candidate.stop_loss,
        proximity_pct: 1.0,
      })
      toast.success(
        `Coupled Alerts Set: ${candidate.symbol}`,
        `Buy Pre-Alert at ₹${(candidate.best_buy_price * 1.01).toFixed(2)}, Target at ₹${candidate.target_price?.toFixed(2)}, and SL!`
      )
      await loadAlerts()
    } catch (err: any) {
      toast.error('Failed to set alert', err?.response?.data?.detail || err.message)
    } finally {
      setSettingSingleAlertSym(null)
    }
  }

  const handleBulkSetRadarAlerts = async () => {
    if (!radarData?.candidates?.length) return
    setSettingBulkAlerts(true)
    try {
      const items = radarData.candidates.map((c: any) => ({
        symbol: c.symbol,
        current_price: c.cmp,
        best_buy_price: c.best_buy_price,
        target_price: c.target_price,
        stop_loss: c.stop_loss,
        proximity_pct: 1.0,
      }))
      const res = await alertsApi.bulkScreenerSetup(items)
      toast.success(
        'Bulk Radar Alerts Activated!',
        `${res.data.alerts_created_count} coupled alerts created across ${res.data.symbols_count} stocks near Best Buy.`
      )
      await loadAlerts()
    } catch (err: any) {
      toast.error('Bulk alert setup failed', err?.response?.data?.detail || err.message)
    } finally {
      setSettingBulkAlerts(false)
    }
  }

  const loadRadar = async (sec = radarSector, prox = radarProximityPct, silent = false) => {
    if (!silent) setLoadingRadar(true)
    try {
      const res = await alertsApi.getScreenerRadar(sec, prox)
      setRadarData(res.data || { candidates: [], summary: { at_best_buy: 0, near_best_buy: 0, approaching: 0 }, total_candidates: 0 })
    } catch (err: any) {
      console.error('Failed to load screener proximity radar:', err)
    } finally {
      if (!silent) setLoadingRadar(false)
    }
  }

  async function handleLaunchGttForSymbol(sym: string) {
    if (!sym) return
    setFetchingGttQuote(true)
    try {
      const res = await stocksApi.getQuote(sym.toUpperCase())
      const quote = res.data
      const price = quote?.price || 100.0
      setGttOrderData({
        symbol: sym.toUpperCase(),
        name: quote?.name || sym.toUpperCase(),
        currentPrice: price,
        bestBuyPrice: price,
        targetPrice: Number((price * 1.08).toFixed(2)),
        stopLoss: Number((price * 0.95).toFixed(2)),
      })
      setShowGttSearchPrompt(false)
      setGttOrderModalOpen(true)
    } catch (e: any) {
      toast.error('Failed to load quote', e?.message || 'Symbol not found')
    } finally {
      setFetchingGttQuote(false)
    }
  }

  useEffect(() => {
    loadRadar(radarSector, radarProximityPct)
  }, [radarSector, radarProximityPct])

  useEffect(() => {
    loadAlerts()
    loadHoldingsMonitor()

    // Poll live holdings every 10 seconds for real-time risk tracking
    const timer = setInterval(() => {
      loadHoldingsMonitor(true)
    }, 10000)
    return () => clearInterval(timer)
  }, [])

  async function loadAlerts() {
    try {
      const res = await alertsApi.list()
      setAlerts(res.data.alerts || [])
    } catch (err: any) {
      console.error('Failed to load alerts:', err)
    } finally {
      setLoadingAlerts(false)
    }
  }

  async function loadHoldingsMonitor(silent = false) {
    if (!silent) setLoadingHoldings(true)
    try {
      const res = await alertsApi.getHoldingsMonitor()
      setHoldings(res.data.holdings || [])
      setHoldingsSummary(res.data.summary || { total_held: 0, targets_approaching: 0, sl_warnings: 0 })
    } catch (err: any) {
      console.error('Failed to load holdings risk monitor:', err)
    } finally {
      if (!silent) setLoadingHoldings(false)
    }
  }

  async function handleSyncHoldings() {
    setSyncingHoldings(true)
    try {
      const res = await alertsApi.syncHoldings()
      toast.success(
        'Holdings Guard Synced',
        `${res.data.synced_count} open holdings now have coupled Target & Stop Loss alerts active.`
      )
      await loadAlerts()
      await loadHoldingsMonitor()
    } catch (err: any) {
      toast.error('Sync failed', err?.response?.data?.detail || err.message)
    } finally {
      setSyncingHoldings(false)
    }
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    setSubmitting(true)
    try {
      await alertsApi.create({
        symbol: form.symbol.toUpperCase(),
        condition_type: form.condition_type,
        condition_value: parseFloat(form.condition_value),
        message: form.message || undefined,
        priority: form.priority,
        delivery_method: form.delivery_method,
      })
      setShowForm(false)
      setForm({ symbol: '', condition_type: 'PRICE_ABOVE', condition_value: '', message: '', priority: 'MEDIUM', delivery_method: 'IN_APP' })
      toast.success('Alert Created', `${form.condition_type} for ${form.symbol.toUpperCase()}`)
      await loadAlerts()
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Failed to create alert')
    } finally { 
      setSubmitting(false) 
    }
  }

  async function handleDelete(id: string) {
    if (!confirm('Delete this alert?')) return
    await alertsApi.delete(id)
    await loadAlerts()
    toast.info('Alert Removed')
  }

  async function handleDeactivate(id: string) {
    await alertsApi.deactivate(id)
    await loadAlerts()
    toast.info('Alert Deactivated')
  }

  const handleOpenExitModal = (holding: any) => {
    setSellModalData(holding)
    setSellModalOpen(true)
  }

  // Filter Radar alerts (Proximity and Screener pre-alerts)
  const radarAlerts = useMemo(() => {
    return alerts.filter(a => 
      a.condition_type.includes('PROXIMITY') || 
      a.condition_type.includes('TARGET') || 
      a.condition_type.includes('STOP_LOSS')
    )
  }, [alerts])

  // Custom technical alerts
  const customAlerts = useMemo(() => {
    return alerts.filter(a => 
      !a.condition_type.includes('PROXIMITY') && 
      !a.condition_type.includes('TARGET') && 
      !a.condition_type.includes('STOP_LOSS')
    )
  }, [alerts])

  return (
    <div style={{ maxWidth: 1300, margin: '0 auto', paddingBottom: 60 }}>
      {/* Page Header */}
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 16 }}>
        <div>
          <h1 className="page-title" style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <Bell size={24} style={{ color: 'var(--color-accent-blue, #387ed1)' }} />
            Institutional Alerts & Risk Guard
          </h1>
          <p className="page-subtitle">
            Pre-alerts for swing screener entries, real-time target proximity sell warnings, and automated downside stop loss protection.
          </p>
        </div>

        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <button 
            className="btn btn-secondary" 
            onClick={() => setShowGttSearchPrompt(true)} 
            style={{ display: 'flex', alignItems: 'center', gap: 6, borderColor: 'rgba(56, 189, 248, 0.4)', color: '#38bdf8' }}
            title="Create a new Zerodha Kite GTT (Good-Till-Triggered) Trigger Order"
          >
            <Target size={15} /> + Create GTT Trigger
          </button>

          <button 
            className="btn btn-secondary" 
            onClick={handleSyncHoldings} 
            disabled={syncingHoldings}
            style={{ display: 'flex', alignItems: 'center', gap: 6 }}
            title="Ensure all open holdings have coupled Target & Stop Loss alerts"
          >
            <ShieldCheck size={15} style={{ color: '#10b981' }} />
            {syncingHoldings ? 'Syncing...' : 'Sync Holdings Guard'}
          </button>

          <button className="btn btn-primary" onClick={() => setShowForm(!showForm)} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <PlusCircle size={15} /> New Custom Alert
          </button>
        </div>
      </div>

      {/* Primary Tab Navigation */}
      <div style={{
        display: 'flex',
        gap: 8,
        borderBottom: '1px solid var(--color-border, #2d3343)',
        marginBottom: 20,
        paddingBottom: 2,
        overflowX: 'auto',
      }}>
        <button
          onClick={() => setActiveTab('SCREENER_RADAR')}
          style={{
            padding: '10px 18px',
            fontSize: 14,
            fontWeight: 700,
            border: 'none',
            borderBottom: activeTab === 'SCREENER_RADAR' ? '3px solid #38bdf8' : '3px solid transparent',
            background: 'transparent',
            color: activeTab === 'SCREENER_RADAR' ? 'var(--color-text-primary, #ffffff)' : 'var(--color-text-muted, #8a92a6)',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            transition: 'all 0.15s ease',
            whiteSpace: 'nowrap',
          }}
        >
          <Zap size={16} style={{ color: activeTab === 'SCREENER_RADAR' ? '#38bdf8' : 'inherit' }} />
          <span>⚡ Best Buy Proximity Radar ({radarData.total_candidates || 0})</span>
          {radarData.summary?.at_best_buy > 0 && (
            <span style={{ background: '#10b981', color: '#000', fontSize: 11, padding: '1px 6px', borderRadius: 10, fontWeight: 800 }}>
              {radarData.summary.at_best_buy} At Best Buy
            </span>
          )}
          {radarData.summary?.near_best_buy > 0 && (
            <span style={{ background: '#38bdf8', color: '#000', fontSize: 11, padding: '1px 6px', borderRadius: 10, fontWeight: 800 }}>
              {radarData.summary.near_best_buy} Pullback
            </span>
          )}
        </button>

        <button
          onClick={() => setActiveTab('HOLDINGS')}
          style={{
            padding: '10px 18px',
            fontSize: 14,
            fontWeight: 700,
            border: 'none',
            borderBottom: activeTab === 'HOLDINGS' ? '3px solid var(--color-accent-blue, #387ed1)' : '3px solid transparent',
            background: 'transparent',
            color: activeTab === 'HOLDINGS' ? 'var(--color-text-primary, #ffffff)' : 'var(--color-text-muted, #8a92a6)',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            transition: 'all 0.15s ease',
            whiteSpace: 'nowrap',
          }}
        >
          <Briefcase size={16} style={{ color: activeTab === 'HOLDINGS' ? '#387ed1' : 'inherit' }} />
          <span>Active Holdings Guard ({holdings.length})</span>
          {holdingsSummary.targets_approaching > 0 && (
            <span style={{ background: '#10b981', color: '#000', fontSize: 11, padding: '1px 6px', borderRadius: 10, fontWeight: 800 }}>
              {holdingsSummary.targets_approaching} Target Close
            </span>
          )}
          {holdingsSummary.sl_warnings > 0 && (
            <span style={{ background: '#ef4444', color: '#fff', fontSize: 11, padding: '1px 6px', borderRadius: 10, fontWeight: 800 }}>
              {holdingsSummary.sl_warnings} SL Warning
            </span>
          )}
        </button>

        <button
          onClick={() => setActiveTab('RADAR')}
          style={{
            padding: '10px 18px',
            fontSize: 14,
            fontWeight: 700,
            border: 'none',
            borderBottom: activeTab === 'RADAR' ? '3px solid var(--color-accent-blue, #387ed1)' : '3px solid transparent',
            background: 'transparent',
            color: activeTab === 'RADAR' ? 'var(--color-text-primary, #ffffff)' : 'var(--color-text-muted, #8a92a6)',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            transition: 'all 0.15s ease',
            whiteSpace: 'nowrap',
          }}
        >
          <Target size={16} style={{ color: activeTab === 'RADAR' ? '#38bdf8' : 'inherit' }} />
          <span>⚡ GTT Triggers & Proximity Radar ({radarAlerts.length})</span>
        </button>

        <button
          onClick={() => setActiveTab('CUSTOM')}
          style={{
            padding: '10px 18px',
            fontSize: 14,
            fontWeight: 700,
            border: 'none',
            borderBottom: activeTab === 'CUSTOM' ? '3px solid var(--color-accent-blue, #387ed1)' : '3px solid transparent',
            background: 'transparent',
            color: activeTab === 'CUSTOM' ? 'var(--color-text-primary, #ffffff)' : 'var(--color-text-muted, #8a92a6)',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            transition: 'all 0.15s ease',
            whiteSpace: 'nowrap',
          }}
        >
          <Bell size={16} style={{ color: activeTab === 'CUSTOM' ? '#387ed1' : 'inherit' }} />
          <span>Custom Technical Alerts ({customAlerts.length})</span>
        </button>
      </div>

      {/* Create Alert Form (Collapsible) */}
      {showForm && (
        <div className="card" style={{ marginBottom: 20, border: '1px solid var(--color-accent-blue, #387ed1)' }}>
          <div className="card-title" style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between' }}>
            <span>Create New Custom Alert</span>
            <button className="btn btn-ghost" style={{ padding: '2px 8px', fontSize: 12 }} onClick={() => setShowForm(false)}>Close</button>
          </div>
          <form onSubmit={handleCreate} style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 12 }}>
            <div>
              <label style={{ fontSize: 12, color: 'var(--color-text-muted)', marginBottom: 4, display: 'block' }}>Symbol</label>
              <StockSearchBox 
                placeholder="RELIANCE.NS" 
                width="100%" 
                autoNavigate={false} 
                clearOnSelect={false}
                value={form.symbol} 
                onChange={(val) => setForm({ ...form, symbol: val })} 
              />
            </div>
            <div>
              <label style={{ fontSize: 12, color: 'var(--color-text-muted)', marginBottom: 4, display: 'block' }}>Priority</label>
              <select className="input" value={form.priority} onChange={e => setForm({ ...form, priority: e.target.value as typeof form.priority })}>
                <option value="LOW">Low — in-app</option><option value="MEDIUM">Medium — in-app</option><option value="HIGH">High — can email</option>
              </select>
            </div>
            <div>
              <label style={{ fontSize: 12, color: 'var(--color-text-muted)', marginBottom: 4, display: 'block' }}>Delivery</label>
              <select className="input" value={form.delivery_method} onChange={e => setForm({ ...form, delivery_method: e.target.value as typeof form.delivery_method })}>
                <option value="IN_APP">In-app notification</option><option value="EMAIL">Email (HIGH only)</option><option value="BOTH">In-app + email (HIGH only)</option>
              </select>
            </div>
            <div>
              <label style={{ fontSize: 12, color: 'var(--color-text-muted)', marginBottom: 4, display: 'block' }}>Condition</label>
              <select className="input" value={form.condition_type} onChange={e => setForm({ ...form, condition_type: e.target.value })}>
                {CONDITION_TYPES.map(c => <option key={c.value} value={c.value}>{c.label}</option>)}
              </select>
            </div>
            <div>
              <label style={{ fontSize: 12, color: 'var(--color-text-muted)', marginBottom: 4, display: 'block' }}>Value</label>
              {form.condition_type === 'PATTERN' ? (
                <select className="input" required value={form.condition_value} onChange={e => setForm({ ...form, condition_value: e.target.value })}>
                  <option value="" disabled>Select pattern</option>
                  {PATTERN_TYPES.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
                </select>
              ) : (
                <input className="input" type="number" step="any" required placeholder="e.g. 2850" value={form.condition_value} onChange={e => setForm({ ...form, condition_value: e.target.value })} />
              )}
            </div>
            <div>
              <label style={{ fontSize: 12, color: 'var(--color-text-muted)', marginBottom: 4, display: 'block' }}>Custom Message (optional)</label>
              <input className="input" placeholder="Optional note…" value={form.message} onChange={e => setForm({ ...form, message: e.target.value })} />
            </div>
            <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end' }}>
              <button type="submit" className="btn btn-primary" disabled={submitting}>{submitting ? 'Creating…' : 'Create Alert'}</button>
              <button type="button" className="btn btn-ghost" onClick={() => setShowForm(false)}>Cancel</button>
            </div>
          </form>
        </div>
      )}

      {/* TAB 0: SWING SCREENER BEST BUY PROXIMITY RADAR */}
      {activeTab === 'SCREENER_RADAR' && (
        <div>
          {/* Top Control & Zero-Rate-Limit Banner */}
          <div className="card" style={{
            background: 'linear-gradient(90deg, rgba(56, 189, 248, 0.08), rgba(16, 185, 129, 0.08))',
            border: '1px solid rgba(56, 189, 248, 0.25)',
            marginBottom: 20,
            padding: '16px 20px',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 14 }}>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 16, fontWeight: 700, color: '#38bdf8' }}>
                  <Zap size={20} />
                  <span>Swing Screener Best Buy Proximity Radar</span>
                  <span style={{ fontSize: 11, background: 'rgba(56, 189, 248, 0.2)', padding: '2px 8px', borderRadius: 12, border: '1px solid #38bdf8', color: '#e0f2fe' }}>
                    Fyers Single-Flight Calibrated
                  </span>
                </div>
                <div style={{ fontSize: 12, color: 'var(--color-text-secondary)', marginTop: 4, maxWidth: 750 }}>
                  Real-time monitoring of swing setups trading closely to their ML optimal Best Buy price across all 10 market sectors.
                  Live quotes are pre-fetched in 1 single bulk request via Fyers Rate Governor to guarantee zero rate limit exceedance.
                </div>
              </div>

              <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
                <button
                  className="btn btn-secondary"
                  onClick={() => loadRadar(radarSector, radarProximityPct)}
                  disabled={loadingRadar}
                  style={{ display: 'flex', alignItems: 'center', gap: 6 }}
                >
                  <RefreshCw size={14} className={loadingRadar ? 'spin' : ''} />
                  {loadingRadar ? 'Updating...' : 'Refresh Radar'}
                </button>

                <button
                  className="btn btn-primary"
                  onClick={handleBulkSetRadarAlerts}
                  disabled={settingBulkAlerts || !radarData?.candidates?.length}
                  style={{ display: 'flex', alignItems: 'center', gap: 6, background: '#10b981', borderColor: '#10b981' }}
                  title="Activate coupled Buy Proximity, Target, and Stop Loss alerts for all stocks listed below"
                >
                  <CheckCircle2 size={15} />
                  {settingBulkAlerts ? 'Activating...' : `Set Alerts for All (${radarData?.total_candidates || 0})`}
                </button>
              </div>
            </div>

            {/* Filter Controls Row */}
            <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', alignItems: 'center', marginTop: 16, paddingTop: 14, borderTop: '1px solid rgba(255,255,255,0.08)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--color-text-muted)', display: 'flex', alignItems: 'center', gap: 4 }}>
                  <Layers size={14} /> Sector Universe:
                </span>
                <select
                  className="input"
                  style={{ padding: '6px 12px', fontSize: 13, minWidth: 230 }}
                  value={radarSector}
                  onChange={(e) => setRadarSector(e.target.value)}
                >
                  {SECTORS.map(s => (
                    <option key={s.value} value={s.value}>{s.label}</option>
                  ))}
                </select>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--color-text-muted)', display: 'flex', alignItems: 'center', gap: 4 }}>
                  <Filter size={14} /> Proximity Filter:
                </span>
                <select
                  className="input"
                  style={{ padding: '6px 12px', fontSize: 13, minWidth: 220 }}
                  value={radarProximityPct}
                  onChange={(e) => setRadarProximityPct(parseFloat(e.target.value))}
                >
                  {PROXIMITY_FILTERS.map(p => (
                    <option key={p.value} value={p.value}>{p.label}</option>
                  ))}
                </select>
              </div>

              <div style={{ fontSize: 12, color: 'var(--color-text-muted)', marginLeft: 'auto' }}>
                Showing <strong>{radarData?.total_candidates || 0}</strong> candidates within <strong>{radarProximityPct}%</strong> of Best Buy
              </div>
            </div>
          </div>

          {/* Metric Summary Cards */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 14, marginBottom: 20 }}>
            <div className="card" style={{ padding: '16px 20px', borderLeft: '4px solid #38bdf8' }}>
              <div style={{ fontSize: 11, color: '#38bdf8', textTransform: 'uppercase', fontWeight: 600 }}>
                Total Near Best Buy
              </div>
              <div style={{ fontSize: 24, fontWeight: 700, fontFamily: 'monospace', marginTop: 4 }}>
                {radarData?.total_candidates || 0}
              </div>
              <div style={{ fontSize: 11, color: 'var(--color-text-secondary)', marginTop: 2 }}>
                Within {radarProximityPct}% entry zone
              </div>
            </div>

            <div className="card" style={{ padding: '16px 20px', borderLeft: '4px solid #10b981' }}>
              <div style={{ fontSize: 11, color: '#10b981', textTransform: 'uppercase', fontWeight: 600 }}>
                At Best Buy Zone
              </div>
              <div style={{ fontSize: 24, fontWeight: 700, fontFamily: 'monospace', marginTop: 4, color: '#10b981' }}>
                {radarData?.summary?.at_best_buy || 0}
              </div>
              <div style={{ fontSize: 11, color: 'var(--color-text-secondary)', marginTop: 2 }}>
                Within ±0.5% — Immediate execution
              </div>
            </div>

            <div className="card" style={{ padding: '16px 20px', borderLeft: '4px solid #f59e0b' }}>
              <div style={{ fontSize: 11, color: '#f59e0b', textTransform: 'uppercase', fontWeight: 600 }}>
                Prime Pullback Dips
              </div>
              <div style={{ fontSize: 24, fontWeight: 700, fontFamily: 'monospace', marginTop: 4, color: '#f59e0b' }}>
                {radarData?.summary?.near_best_buy || 0}
              </div>
              <div style={{ fontSize: 11, color: 'var(--color-text-secondary)', marginTop: 2 }}>
                0.5% to 2.0% above Best Buy dip
              </div>
            </div>

            <div className="card" style={{ padding: '16px 20px', borderLeft: '4px solid #8b5cf6' }}>
              <div style={{ fontSize: 11, color: '#8b5cf6', textTransform: 'uppercase', fontWeight: 600 }}>
                Approaching Pullback
              </div>
              <div style={{ fontSize: 24, fontWeight: 700, fontFamily: 'monospace', marginTop: 4, color: '#8b5cf6' }}>
                {radarData?.summary?.approaching || 0}
              </div>
              <div style={{ fontSize: 11, color: 'var(--color-text-secondary)', marginTop: 2 }}>
                2.0% to 4.0% away — Watch closely
              </div>
            </div>
          </div>

          {/* Radar Table */}
          <div className="card">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
              <div className="card-title" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <Target size={18} style={{ color: '#38bdf8' }} />
                <span>Closely Priced Stocks to Best Buy Value ({radarData?.candidates?.length || 0})</span>
              </div>
            </div>

            {loadingRadar && (!radarData?.candidates || radarData.candidates.length === 0) && (
              <div className="loading" style={{ padding: '40px 20px', textAlign: 'center' }}>
                <RefreshCw size={24} className="spin" style={{ marginBottom: 10, opacity: 0.5 }} />
                <div>Scanning sector setups and pre-fetching bulk live prices...</div>
              </div>
            )}

            {!loadingRadar && (!radarData?.candidates || radarData.candidates.length === 0) && (
              <div className="empty-state" style={{ padding: '40px 20px', textAlign: 'center' }}>
                <Target size={36} style={{ marginBottom: 10, opacity: 0.3 }} />
                <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 4 }}>No Stocks Within {radarProximityPct}% of Best Buy in {radarSector}</div>
                <div style={{ fontSize: 13, color: 'var(--color-text-muted)' }}>
                  Try broadening the proximity filter to 5.0% or selecting "All Sectors" to discover stocks approaching high-conviction entry zones.
                </div>
              </div>
            )}

            {radarData?.candidates && radarData.candidates.length > 0 && (
              <div className="table-container">
                <table className="table" style={{ minWidth: '950px' }}>
                  <thead>
                    <tr>
                      <th>Stock & Sector</th>
                      <th>CMP</th>
                      <th>Best Buy Value</th>
                      <th>Distance to Best Buy</th>
                      <th>Proximity Status</th>
                      <th>Target & Gain</th>
                      <th>Stop Loss</th>
                      <th style={{ textAlign: 'right' }}>Action Controls</th>
                    </tr>
                  </thead>
                  <tbody>
                    {radarData.candidates.map((c: any) => {
                      const isAtBuy = c.proximity_status === 'AT_BEST_BUY'
                      const isNearBuy = c.proximity_status === 'NEAR_BEST_BUY'
                      const isBelowBuy = c.proximity_status === 'BELOW_BUY'
                      const isSetting = settingSingleAlertSym === c.symbol

                      let badgeStyle: React.CSSProperties = { background: 'rgba(56, 189, 248, 0.15)', color: '#38bdf8', border: '1px solid #38bdf8' }
                      if (isAtBuy) {
                        badgeStyle = { background: 'rgba(16, 185, 129, 0.25)', color: '#10b981', border: '1px solid #10b981' }
                      } else if (isBelowBuy) {
                        badgeStyle = { background: 'rgba(168, 85, 247, 0.2)', color: '#c084fc', border: '1px solid #a855f7' }
                      } else if (c.proximity_status === 'APPROACHING') {
                        badgeStyle = { background: 'rgba(245, 158, 11, 0.18)', color: '#fbbf24', border: '1px solid #f59e0b' }
                      }

                      return (
                        <tr key={c.symbol} style={{ background: isAtBuy ? 'rgba(16, 185, 129, 0.04)' : isNearBuy ? 'rgba(56, 189, 248, 0.03)' : 'transparent' }}>
                          <td>
                            <div style={{ fontWeight: 700, fontSize: 14 }}>{c.symbol}</div>
                            <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginTop: 3 }}>
                              <span style={{ fontSize: 10, background: 'rgba(255,255,255,0.06)', padding: '1px 5px', borderRadius: 3, color: 'var(--color-text-muted)' }}>
                                {c.sector}
                              </span>
                              <span style={{ fontSize: 10, background: 'rgba(56, 189, 248, 0.1)', color: '#38bdf8', padding: '1px 5px', borderRadius: 3 }}>
                                {c.entry_type.replace('_', ' ')}
                              </span>
                              <span style={{ fontSize: 10, color: 'var(--color-text-muted)' }}>
                                Score: {c.total_score}
                              </span>
                            </div>
                          </td>

                          <td>
                            <div className="mono" style={{ fontWeight: 700, fontSize: 14 }}>
                              ₹{c.cmp.toFixed(2)}
                            </div>
                          </td>

                          <td>
                            <div className="mono" style={{ fontWeight: 700, color: '#38bdf8', fontSize: 14 }}>
                              ₹{c.best_buy_price.toFixed(2)}
                            </div>
                          </td>

                          <td>
                            <div className="mono" style={{ fontWeight: 700, color: isAtBuy ? '#10b981' : isBelowBuy ? '#c084fc' : '#38bdf8' }}>
                              {c.distance_pct > 0 ? '+' : ''}{c.distance_pct.toFixed(2)}%
                            </div>
                            <div style={{ fontSize: 10, color: 'var(--color-text-muted)' }}>
                              ₹{(c.cmp - c.best_buy_price).toFixed(2)} diff
                            </div>
                          </td>

                          <td>
                            <span style={{
                              ...badgeStyle,
                              padding: '3px 8px',
                              borderRadius: 6,
                              fontSize: 11,
                              fontWeight: 700,
                              display: 'inline-block',
                            }}>
                              {c.proximity_label}
                            </span>
                          </td>

                          <td>
                            <div className="mono" style={{ fontWeight: 700, color: '#10b981' }}>
                              ₹{c.target_price.toFixed(2)}
                            </div>
                            <div style={{ fontSize: 11, color: '#10b981' }}>
                              +{c.expected_gain_pct}% gain
                            </div>
                          </td>

                          <td>
                            <div className="mono" style={{ fontWeight: 700, color: '#ef4444' }}>
                              ₹{c.stop_loss.toFixed(2)}
                            </div>
                            <div style={{ fontSize: 11, color: 'var(--color-text-muted)' }}>
                              {c.risk_buffer_pct}% buffer
                            </div>
                          </td>

                          <td style={{ textAlign: 'right' }}>
                            <div style={{ display: 'inline-flex', gap: 6 }}>
                              <button
                                onClick={() => handleSetRadarAlert(c)}
                                disabled={isSetting}
                                className="btn btn-secondary"
                                style={{
                                  padding: '4px 10px',
                                  fontSize: 11,
                                  fontWeight: 700,
                                  display: 'inline-flex',
                                  alignItems: 'center',
                                  gap: 4,
                                  borderColor: 'rgba(56, 189, 248, 0.4)',
                                  color: '#38bdf8',
                                }}
                                title="Activate coupled Buy Proximity, Target, and Stop Loss alerts"
                              >
                                <Bell size={12} />
                                {isSetting ? '...' : 'Set Alert'}
                              </button>

                              <button
                                onClick={() => handleOpenRadarGtt(c)}
                                className="btn btn-primary"
                                style={{
                                  padding: '4px 10px',
                                  fontSize: 11,
                                  fontWeight: 700,
                                  display: 'inline-flex',
                                  alignItems: 'center',
                                  gap: 4,
                                }}
                                title="Open Zerodha Kite GTT order modal pre-filled with Best Buy Price"
                              >
                                <Target size={12} />
                                GTT
                              </button>
                            </div>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      {/* TAB 1: ACTIVE HOLDINGS GUARD */}
      {activeTab === 'HOLDINGS' && (
        <div>
          {/* Summary Metric Cards */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 14, marginBottom: 20 }}>
            <div className="card" style={{ padding: '16px 20px', borderLeft: '4px solid #387ed1' }}>
              <div style={{ fontSize: 11, color: 'var(--color-text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>
                Total Active Holdings
              </div>
              <div style={{ fontSize: 24, fontWeight: 700, fontFamily: 'monospace', marginTop: 4 }}>
                {holdings.length}
              </div>
              <div style={{ fontSize: 11, color: 'var(--color-text-secondary)', marginTop: 2 }}>
                Monitored for target exit and stop-loss
              </div>
            </div>

            <div className="card" style={{ padding: '16px 20px', borderLeft: '4px solid #10b981' }}>
              <div style={{ fontSize: 11, color: '#10b981', textTransform: 'uppercase', fontWeight: 600 }}>
                Approaching Target (Sell Warning)
              </div>
              <div style={{ fontSize: 24, fontWeight: 700, fontFamily: 'monospace', marginTop: 4, color: '#10b981' }}>
                {holdingsSummary.targets_approaching}
              </div>
              <div style={{ fontSize: 11, color: 'var(--color-text-secondary)', marginTop: 2 }}>
                Within 1.0% of profit target — prepare exit
              </div>
            </div>

            <div className="card" style={{ padding: '16px 20px', borderLeft: '4px solid #ef4444' }}>
              <div style={{ fontSize: 11, color: '#ef4444', textTransform: 'uppercase', fontWeight: 600 }}>
                Stop Loss Warnings
              </div>
              <div style={{ fontSize: 24, fontWeight: 700, fontFamily: 'monospace', marginTop: 4, color: '#ef4444' }}>
                {holdingsSummary.sl_warnings}
              </div>
              <div style={{ fontSize: 11, color: 'var(--color-text-secondary)', marginTop: 2 }}>
                Downside risk alert active
              </div>
            </div>
          </div>

          {/* Holdings Table */}
          <div className="card">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
              <div className="card-title" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <ShieldCheck size={18} style={{ color: '#10b981' }} />
                <span>Real-Time Position Alerts & Proximity Monitor</span>
              </div>
              <button 
                onClick={() => loadHoldingsMonitor()} 
                className="btn btn-ghost" 
                style={{ padding: '4px 10px', fontSize: 12, display: 'flex', alignItems: 'center', gap: 5 }}
              >
                <RefreshCw size={13} className={loadingHoldings ? 'spin' : ''} /> Refresh
              </button>
            </div>

            {loadingHoldings && holdings.length === 0 && <div className="loading">Loading holdings risk monitor…</div>}
            
            {!loadingHoldings && holdings.length === 0 && (
              <div className="empty-state" style={{ padding: '40px 20px', textAlign: 'center' }}>
                <Briefcase size={36} style={{ marginBottom: 10, opacity: 0.3 }} />
                <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 4 }}>No Active Bought Holdings</div>
                <div style={{ fontSize: 13, color: 'var(--color-text-muted)' }}>
                  Use the Swing Screener to discover high-conviction setups and place orders via the Zerodha execution modal. Your bought stocks will automatically appear here with live Target & Stop Loss alerts!
                </div>
              </div>
            )}

            {holdings.length > 0 && (
              <div className="table-container">
                <table className="table" style={{ minWidth: '900px' }}>
                  <thead>
                    <tr>
                      <th>Stock</th>
                      <th>Qty & Buy Price</th>
                      <th>CMP</th>
                      <th>P&L</th>
                      <th>Target & Proximity</th>
                      <th>Stop Loss & Risk</th>
                      <th>Risk Status</th>
                      <th style={{ textAlign: 'right' }}>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {holdings.map(h => {
                      const isProfit = h.unrealized_pnl >= 0
                      const pnlColor = isProfit ? '#10b981' : '#ef4444'

                      let statusBadge = (
                        <span style={{ background: 'rgba(16, 185, 129, 0.1)', color: '#10b981', padding: '3px 8px', borderRadius: 6, fontSize: 11, fontWeight: 700 }}>
                          🟢 In Safe Zone
                        </span>
                      )
                      if (h.risk_status === 'TARGET_HIT') {
                        statusBadge = (
                          <span style={{ background: '#10b981', color: '#000', padding: '3px 8px', borderRadius: 6, fontSize: 11, fontWeight: 800 }}>
                            🚀 Target Hit (Sell!)
                          </span>
                        )
                      } else if (h.risk_status === 'TARGET_APPROACHING') {
                        statusBadge = (
                          <span style={{ background: 'rgba(56, 189, 248, 0.2)', color: '#38bdf8', border: '1px solid #38bdf8', padding: '3px 8px', borderRadius: 6, fontSize: 11, fontWeight: 700 }}>
                            🎯 Approaching Target ({h.distance_to_target_pct}% away)
                          </span>
                        )
                      } else if (h.risk_status === 'SL_HIT') {
                        statusBadge = (
                          <span style={{ background: '#ef4444', color: '#fff', padding: '3px 8px', borderRadius: 6, fontSize: 11, fontWeight: 800 }}>
                            🛑 Stop Loss Breached
                          </span>
                        )
                      } else if (h.risk_status === 'SL_APPROACHING') {
                        statusBadge = (
                          <span style={{ background: 'rgba(239, 68, 68, 0.18)', color: '#ef4444', border: '1px solid #ef4444', padding: '3px 8px', borderRadius: 6, fontSize: 11, fontWeight: 700 }}>
                            ⚠️ Approaching SL ({h.distance_to_sl_pct}% buffer)
                          </span>
                        )
                      }

                      return (
                        <tr key={h.trade_id} style={{ background: h.is_target_approaching ? 'rgba(56, 189, 248, 0.04)' : h.is_sl_approaching ? 'rgba(239, 68, 68, 0.04)' : 'transparent' }}>
                          <td>
                            <div style={{ fontWeight: 700, fontSize: 14 }}>{h.symbol}</div>
                            <span style={{ fontSize: 10, background: 'rgba(255,255,255,0.06)', padding: '1px 5px', borderRadius: 3, color: 'var(--color-text-muted)' }}>
                              {h.product_type}
                            </span>
                          </td>

                          <td>
                            <div className="mono" style={{ fontWeight: 600 }}>{h.quantity} shares</div>
                            <div className="mono" style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>@ ₹{h.entry_price.toFixed(2)}</div>
                          </td>

                          <td>
                            <div className="mono" style={{ fontWeight: 700, fontSize: 14 }}>
                              ₹{h.cmp.toFixed(2)}
                            </div>
                          </td>

                          <td>
                            <div className="mono" style={{ color: pnlColor, fontWeight: 700 }}>
                              {isProfit ? '+' : ''}₹{h.unrealized_pnl.toFixed(2)}
                            </div>
                            <div className="mono" style={{ color: pnlColor, fontSize: 11 }}>
                              {isProfit ? '+' : ''}{h.pnl_pct.toFixed(2)}%
                            </div>
                          </td>

                          <td>
                            <div className="mono" style={{ fontWeight: 700, color: '#10b981' }}>
                              ₹{h.target_price.toFixed(2)}
                            </div>
                            <div style={{ fontSize: 11, color: 'var(--color-text-muted)' }}>
                              {h.distance_to_target_pct > 0 ? `${h.distance_to_target_pct}% to target` : 'Target reached'}
                            </div>
                          </td>

                          <td>
                            <div className="mono" style={{ fontWeight: 700, color: '#ef4444' }}>
                              ₹{h.stop_loss.toFixed(2)}
                            </div>
                            <div style={{ fontSize: 11, color: 'var(--color-text-muted)' }}>
                              {h.distance_to_sl_pct > 0 ? `${h.distance_to_sl_pct}% risk buffer` : 'SL breached'}
                            </div>
                          </td>

                          <td>
                            {statusBadge}
                          </td>

                          <td style={{ textAlign: 'right' }}>
                            <button
                              onClick={() => handleOpenExitModal(h)}
                              style={{
                                background: '#ff5722',
                                color: '#ffffff',
                                border: 'none',
                                borderRadius: 6,
                                padding: '5px 12px',
                                fontSize: 12,
                                fontWeight: 700,
                                cursor: 'pointer',
                                display: 'inline-flex',
                                alignItems: 'center',
                                gap: 4,
                              }}
                              title="Open Zerodha Kite-style Sell window to exit position"
                            >
                              Exit / Sell
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
        </div>
      )}

      {/* TAB 2: ZERODHA GTT TRIGGERS & PROXIMITY RADAR */}
      {activeTab === 'RADAR' && (
        <div className="card">
          {/* Zerodha GTT Information & Action Banner */}
          <div style={{
            background: 'linear-gradient(90deg, rgba(56, 126, 209, 0.12), rgba(16, 185, 129, 0.12))',
            border: '1px solid rgba(56, 189, 248, 0.25)',
            borderRadius: 8,
            padding: '12px 18px',
            marginBottom: 16,
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: 12,
          }}>
            <div>
              <div style={{ fontSize: 13, fontWeight: 700, color: '#38bdf8', display: 'flex', alignItems: 'center', gap: 6 }}>
                <Target size={16} />
                <span>Zerodha Kite GTT (Good-Till-Triggered) & Proximity Radar</span>
              </div>
              <div style={{ fontSize: 11, color: 'var(--color-text-secondary)', marginTop: 2 }}>
                Automated OCO trigger orders valid until triggered. Monitors market prices and executes your buy/sell plans without keeping the terminal open.
              </div>
            </div>
            <button
              className="btn btn-primary"
              onClick={() => setShowGttSearchPrompt(true)}
              style={{ fontSize: 12, padding: '6px 14px', display: 'flex', alignItems: 'center', gap: 6 }}
            >
              <Target size={14} /> + Create GTT Trigger
            </button>
          </div>

          <div className="card-title" style={{ marginBottom: 14 }}>
            Active GTT Trigger Orders ({radarAlerts.length})
          </div>

          {loadingAlerts && <div className="loading">Loading GTT radar alerts…</div>}
          
          {!loadingAlerts && radarAlerts.length === 0 && (
            <div className="empty-state" style={{ padding: '30px 20px', textAlign: 'center' }}>
              <Target size={32} style={{ marginBottom: 8, opacity: 0.3 }} />
              <div>No GTT proximity alerts set yet.</div>
              <div style={{ fontSize: 12, color: 'var(--color-text-muted)', marginTop: 4 }}>
                Click <strong>+ Create GTT Trigger</strong> above or navigate to the <strong>Swing Screener</strong> and click the <strong>⚡ GTT</strong> button on any stock!
              </div>
            </div>
          )}

          {radarAlerts.length > 0 && (
            <div className="table-container">
              <table className="table" style={{ minWidth: '700px' }}>
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th>GTT Trigger Type</th>
                    <th>Trigger Value</th>
                    <th>Status</th>
                    <th>Trigger Rule / Message</th>
                    <th>Last Triggered</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {radarAlerts.map(a => {
                    let badge = <span style={{ color: '#38bdf8', fontWeight: 600 }}>⚡ {a.condition_type}</span>
                    if (a.condition_type === 'TARGET_PROXIMITY') {
                      badge = <span style={{ color: '#10b981', fontWeight: 700 }}>🎯 GTT TARGET (Sell Pre-Alert)</span>
                    } else if (a.condition_type === 'TARGET_HIT') {
                      badge = <span style={{ color: '#10b981', fontWeight: 800 }}>🚀 GTT TARGET (Hit)</span>
                    } else if (a.condition_type === 'STOP_LOSS_PROXIMITY') {
                      badge = <span style={{ color: '#ef4444', fontWeight: 700 }}>⚠️ GTT STOP LOSS (Warning)</span>
                    } else if (a.condition_type === 'STOP_LOSS_HIT') {
                      badge = <span style={{ color: '#ef4444', fontWeight: 800 }}>🛑 GTT STOP LOSS (Hit)</span>
                    } else if (a.condition_type === 'BUY_PROXIMITY') {
                      badge = <span style={{ color: '#387ed1', fontWeight: 700 }}>⚡ GTT BUY (Pullback Entry)</span>
                    }

                    return (
                      <tr key={a.alert_id}>
                        <td><span className="mono" style={{ fontWeight: 700 }}>{a.symbol}</span></td>
                        <td>{badge}</td>
                        <td className="mono" style={{ fontWeight: 600 }}>₹{a.condition_value}</td>
                        <td>
                          <span style={{ color: a.is_active ? 'var(--color-bullish)' : 'var(--color-text-muted)', fontSize: 13 }}>
                            {a.is_active ? '● Active' : '○ Inactive'}
                          </span>
                        </td>
                        <td style={{ fontSize: 12, color: 'var(--color-text-secondary)', maxWidth: 260 }}>
                          {a.message || '—'}
                        </td>
                        <td style={{ color: 'var(--color-text-muted)', fontSize: 12 }}>
                          {a.triggered_at ? new Date(a.triggered_at).toLocaleString('en-IN') : 'Waiting for trigger'}
                        </td>
                        <td>
                          <div style={{ display: 'flex', gap: 6 }}>
                            {a.is_active && (
                              <button className="btn btn-ghost" style={{ padding: '4px 8px', fontSize: 12 }} onClick={() => handleDeactivate(a.alert_id)}>
                                <BellOff size={13} />
                              </button>
                            )}
                            <button className="btn btn-danger" style={{ padding: '4px 8px', fontSize: 12 }} onClick={() => handleDelete(a.alert_id)}>
                              <Trash2 size={13} />
                            </button>
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* TAB 3: CUSTOM TECHNICAL ALERTS */}
      {activeTab === 'CUSTOM' && (
        <div className="card">
          <div className="card-title" style={{ marginBottom: 14 }}>
            Custom Technical & Indicator Alerts
          </div>

          {loadingAlerts && <div className="loading">Loading custom alerts…</div>}
          
          {!loadingAlerts && customAlerts.length === 0 && (
            <div className="empty-state" style={{ padding: '30px 20px', textAlign: 'center' }}>
              <Bell size={32} style={{ marginBottom: 8, opacity: 0.3 }} />
              <div>No custom technical alerts configured yet.</div>
            </div>
          )}

          {customAlerts.length > 0 && (
            <div className="table-container">
              <table className="table" style={{ minWidth: '600px' }}>
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th>Condition</th>
                    <th>Value</th>
                    <th>Status</th>
                    <th>Last Triggered</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {customAlerts.map(a => (
                    <tr key={a.alert_id}>
                      <td><span className="mono" style={{ fontWeight: 600 }}>{a.symbol}</span></td>
                      <td style={{ color: 'var(--color-text-secondary)' }}>
                        {CONDITION_TYPES.find(c => c.value === a.condition_type)?.label || a.condition_type}
                      </td>
                      <td className="mono">
                        {a.condition_type === 'PATTERN' 
                          ? (PATTERN_TYPES.find(p => String(p.value) === String(a.condition_value))?.label || a.condition_value)
                          : a.condition_value}
                      </td>
                      <td>
                        <span style={{ color: a.is_active ? 'var(--color-bullish)' : 'var(--color-text-muted)', fontSize: 13 }}>
                          {a.is_active ? '● Active' : '○ Inactive'}
                        </span>
                      </td>
                      <td style={{ color: 'var(--color-text-muted)', fontSize: 12 }}>
                        {a.triggered_at ? new Date(a.triggered_at).toLocaleString('en-IN') : 'Never'}
                      </td>
                      <td>
                        <div style={{ display: 'flex', gap: 6 }}>
                          {a.is_active && (
                            <button className="btn btn-ghost" style={{ padding: '4px 8px', fontSize: 12 }} onClick={() => handleDeactivate(a.alert_id)}>
                              <BellOff size={13} />
                            </button>
                          )}
                          <button className="btn btn-danger" style={{ padding: '4px 8px', fontSize: 12 }} onClick={() => handleDelete(a.alert_id)}>
                            <Trash2 size={13} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Zerodha Sell / Exit Modal */}
      {sellModalData && (
        <ZerodhaOrderModal
          isOpen={sellModalOpen}
          onClose={() => setSellModalOpen(false)}
          symbol={sellModalData.symbol}
          currentPrice={sellModalData.cmp}
          targetPrice={sellModalData.target_price}
          stopLoss={sellModalData.stop_loss}
          defaultDirection="SELL"
          onOrderSuccess={() => {
            loadHoldingsMonitor()
            loadAlerts()
          }}
        />
      )}

      {/* Quick GTT Stock Selector Modal */}
      {showGttSearchPrompt && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          backgroundColor: 'rgba(0, 0, 0, 0.65)',
          backdropFilter: 'blur(3px)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 10000,
          padding: 16,
        }}>
          <div style={{
            background: 'var(--color-bg-card, #1a1e29)',
            border: '1px solid var(--color-border, #2d3343)',
            borderRadius: 12,
            width: '100%',
            maxWidth: 440,
            padding: 20,
            boxShadow: '0 24px 60px rgba(0,0,0,0.5)',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
              <div style={{ fontSize: 15, fontWeight: 700, color: '#38bdf8', display: 'flex', alignItems: 'center', gap: 6 }}>
                <Target size={18} />
                <span>Create Zerodha Kite GTT Trigger</span>
              </div>
              <button onClick={() => setShowGttSearchPrompt(false)} style={{ background: 'none', border: 'none', color: '#ffffff', cursor: 'pointer' }}>
                <X size={18} />
              </button>
            </div>
            <div style={{ fontSize: 12, color: 'var(--color-text-secondary)', marginBottom: 12 }}>
              Select any Indian stock to configure Good-Till-Triggered buy/sell price triggers:
            </div>
            <div style={{ marginBottom: 16 }}>
              <StockSearchBox 
                placeholder="Search stock (e.g. TCS, RELIANCE, PCJEWELLER)..."
                width="100%" 
                autoNavigate={false} 
                clearOnSelect={false}
                value={gttSymbol} 
                onChange={(val) => {
                  setGttSymbol(val)
                  handleLaunchGttForSymbol(val)
                }} 
              />
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
              <button className="btn btn-ghost" onClick={() => setShowGttSearchPrompt(false)}>Cancel</button>
            </div>
          </div>
        </div>
      )}

      {/* Zerodha GTT Configuration Order Modal */}
      {gttOrderData && (
        <ZerodhaOrderModal
          isOpen={gttOrderModalOpen}
          onClose={() => setGttOrderModalOpen(false)}
          symbol={gttOrderData.symbol}
          name={gttOrderData.name}
          currentPrice={gttOrderData.currentPrice}
          bestBuyPrice={gttOrderData.bestBuyPrice}
          targetPrice={gttOrderData.targetPrice}
          stopLoss={gttOrderData.stopLoss}
          defaultDirection="BUY"
          isGttMode={true}
          onOrderSuccess={() => {
            loadHoldingsMonitor()
            loadAlerts()
          }}
        />
      )}
    </div>
  )
}
