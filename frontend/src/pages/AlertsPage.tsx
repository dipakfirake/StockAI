import { useEffect, useState, useMemo } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { sanitizeBrowserUrl } from '../utils/urlSecurity'
import { alertsApi, stocksApi, paperTradingApi, notificationsApi } from '../services/api'
import { 
  Bell, PlusCircle, Trash2, BellOff, ShieldAlert, ShieldCheck, 
  Target, TrendingUp, TrendingDown, RefreshCw, AlertTriangle, 
  ExternalLink, ArrowUpRight, ArrowDownRight, CheckCircle2, DollarSign,
  Briefcase, Sparkles, X, Layers, Filter, Zap, Volume2, VolumeX, BellRing, Bot, Megaphone, CheckCheck
} from 'lucide-react'
import StockSearchBox from '../components/StockSearchBox'
import ZerodhaOrderModal from '../components/ZerodhaOrderModal'
import { toast } from '../components/Toast'
import {
  isNotifSoundEnabled,
  setNotifSoundEnabled,
  isNotifPushEnabled,
  setNotifPushEnabled,
  requestDesktopPushPermission,
  playNotificationChime,
  triggerDesktopPushNotification,
} from '../utils/notificationSound'

const SECTORS = [
  { value: 'ALL', label: 'All Sectors' },
  { value: 'NIFTY_50', label: 'Nifty 50' },
  { value: 'BANKING', label: 'Banking & Financials' },
  { value: 'IT', label: 'IT & Technology' },
  { value: 'AUTO', label: 'Automobiles' },
  { value: 'PHARMA', label: 'Pharma & Healthcare' },
  { value: 'ENERGY', label: 'Energy & Power' },
  { value: 'FMCG', label: 'FMCG & Consumer' },
  { value: 'METAL', label: 'Metals & Mining' },
  { value: 'MID_CAP', label: 'Mid Cap' },
  { value: 'SMALL_CAP', label: 'Small Cap' },
]

const PROXIMITY_FILTERS = [
  { value: 1.0, label: 'Within 1.0%' },
  { value: 2.0, label: 'Within 2.0%' },
  { value: 3.0, label: 'Within 3.0%' },
  { value: 5.0, label: 'Within 5.0%' },
]

const STAGE_FILTERS = [
  { value: 'ALL', label: 'All Setups' },
  { value: 'PRE_BUY', label: 'Pre-Buy Watch' },
  { value: 'SELL_PRE_ALERT', label: 'Near Target' },
  { value: 'AT_BEST_BUY', label: 'At Best Buy Zone' },
]

const CONDITION_TYPES = [
  { value: 'PRICE_ABOVE', label: 'Price Above' },
  { value: 'PRICE_BELOW', label: 'Price Below' },
  { value: 'BUY_PROXIMITY', label: 'Near Buy Price' },
  { value: 'TARGET_PROXIMITY', label: 'Near Target' },
  { value: 'TARGET_HIT', label: 'Target Reached' },
  { value: 'STOP_LOSS_PROXIMITY', label: 'Near Stop Loss' },
  { value: 'STOP_LOSS_HIT', label: 'Stop Loss Hit' },
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
  const navigate = useNavigate()
  const location = useLocation()
  const resolveAlertTab = (): 'SCREENER_RADAR' | 'HOLDINGS' | 'RADAR' | 'CUSTOM' | 'INBOX' | null => {
    const stateTab = String((location.state as any)?.tab || '').toUpperCase()
    const queryTab = (() => {
      try {
        return new URLSearchParams(window.location.search).get('tab')?.toUpperCase()
      } catch {
        return undefined
      }
    })()
    const candidate = stateTab || queryTab
    if (candidate === 'INBOX' || candidate === 'NOTIFICATIONS') return 'INBOX'
    if (candidate === 'HOLDINGS' || candidate === 'RADAR' || candidate === 'CUSTOM' || candidate === 'SCREENER_RADAR') {
      return candidate as 'HOLDINGS' | 'RADAR' | 'CUSTOM' | 'SCREENER_RADAR'
    }
    return null
  }
  const [activeTab, setActiveTab] = useState<'SCREENER_RADAR' | 'HOLDINGS' | 'RADAR' | 'CUSTOM' | 'INBOX'>(
    resolveAlertTab() || 'SCREENER_RADAR'
  )

  // Persisted User Notifications Inbox State (Auto-Sells, Order Fills, System Notices)
  const [inboxNotifications, setInboxNotifications] = useState<any[]>([])
  const [inboxUnseenCount, setInboxUnseenCount] = useState<number>(0)
  const [inboxUnreadCount, setInboxUnreadCount] = useState<number>(0)
  const [inboxCategory, setInboxCategory] = useState<string>('ALL')
  const [inboxUnreadOnly, setInboxUnreadOnly] = useState<boolean>(false)
  const [loadingInbox, setLoadingInbox] = useState<boolean>(false)
  const [soundEnabled, setSoundEnabled] = useState<boolean>(() => isNotifSoundEnabled())
  const [pushEnabled, setPushEnabled] = useState<boolean>(() => isNotifPushEnabled())
  
  // Screener Best Buy Radar State (all 10 sectors + ALL)
  const [radarSector, setRadarSector] = useState<string>('ALL')
  const [radarProximityPct, setRadarProximityPct] = useState<number>(3.0)
  const [radarStage, setRadarStage] = useState<string>('ALL')
  const [radarData, setRadarData] = useState<any>({ candidates: [], summary: { at_best_buy: 0, near_best_buy: 0, approaching: 0, sell_pre_alerts: 0, pre_buy_prime: 0 }, total_candidates: 0 })
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

  // Direct Exit state for closing held BUY positions cleanly (without creating conflicting SHORTs)
  const [exitingTradeId, setExitingTradeId] = useState<string | null>(null)

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
      target1: candidate.target_1 ?? undefined,
      target2: candidate.target_2 ?? undefined,
      target3: candidate.target_3 ?? undefined,
      stopLoss: candidate.stop_loss,
    })
    setGttOrderModalOpen(true)
  }

  const handleSetRadarAlert = async (candidate: any) => {
    setSettingSingleAlertSym(candidate.symbol)
    const activeProx = Math.max(0.5, Math.min(5.0, radarProximityPct))
    try {
      await alertsApi.screenerSetup({
        symbol: candidate.symbol,
        current_price: candidate.cmp,
        best_buy_price: candidate.best_buy_price,
        target_price: candidate.target_price,
        stop_loss: candidate.stop_loss,
        proximity_pct: activeProx,
      })
      toast.success(
        `Coupled Alerts Set: ${candidate.symbol}`,
        `⚡ Pre-Buy Alert (+${activeProx}%) at ₹${(candidate.best_buy_price * (1 + activeProx / 100)).toFixed(2)}, 🎯 Sell Pre-Alert at ₹${(candidate.target_price * (1 - activeProx / 100)).toFixed(2)}, and SL protection!`
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
    const activeProx = Math.max(0.5, Math.min(5.0, radarProximityPct))
    try {
      const items = radarData.candidates.map((c: any) => ({
        symbol: c.symbol,
        current_price: c.cmp,
        best_buy_price: c.best_buy_price,
        target_price: c.target_price,
        stop_loss: c.stop_loss,
        proximity_pct: activeProx,
      }))
      const res = await alertsApi.bulkScreenerSetup(items)
      toast.success(
        'Bulk Radar Alerts Activated!',
        `${res.data.alerts_created_count} coupled alerts created across ${res.data.symbols_count} stocks (Pre-Buy, Sell Pre-Alert & SL).`
      )
      await loadAlerts()
    } catch (err: any) {
      toast.error('Bulk alert setup failed', err?.response?.data?.detail || err.message)
    } finally {
      setSettingBulkAlerts(false)
    }
  }

  const loadRadar = async (sec = radarSector, prox = radarProximityPct, stg = radarStage, silent = false, forceRefresh = false) => {
    if (!silent) setLoadingRadar(true)
    try {
      const res = await alertsApi.getScreenerRadar(sec, prox, 60.0, stg, forceRefresh)
      setRadarData(res.data || { candidates: [], summary: { at_best_buy: 0, near_best_buy: 0, approaching: 0, sell_pre_alerts: 0, pre_buy_prime: 0 }, total_candidates: 0 })
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
    loadRadar(radarSector, radarProximityPct, radarStage, false, false)
  }, [radarSector, radarProximityPct, radarStage])

  useEffect(() => {
    if (activeTab !== 'SCREENER_RADAR') return
    const radarTimer = setInterval(() => {
      loadRadar(radarSector, radarProximityPct, radarStage, true, false)
    }, 30000)
    return () => clearInterval(radarTimer)
  }, [activeTab, radarSector, radarProximityPct, radarStage])

  useEffect(() => {
    const nextTab = resolveAlertTab()
    if (nextTab) {
      setActiveTab(nextTab)
    }
    if (typeof window !== 'undefined' && window.location.search) {
      sanitizeBrowserUrl('/alerts')
    }
  }, [location.state])

  async function loadInboxNotifications(markSeenIfOpen: boolean = false) {
    setLoadingInbox(true)
    try {
      const res = await notificationsApi.list({
        category: inboxCategory === 'ALL' ? undefined : inboxCategory,
        unread_only: inboxUnreadOnly,
        limit: 100,
      })
      const list: any[] = res.data?.notifications || []
      let unseen = Number(res.data?.unseen_count ?? 0)
      const unread = Number(res.data?.unread_count ?? 0)
      if (markSeenIfOpen && unseen > 0) {
        await notificationsApi.markSeen()
        unseen = 0
        window.dispatchEvent(new CustomEvent('stockai:notifications-updated'))
      }
      setInboxNotifications(
        markSeenIfOpen ? list.map((it) => ({ ...it, is_seen: true })) : list
      )
      setInboxUnseenCount(unseen)
      setInboxUnreadCount(unread)
    } catch (err) {
      console.error('Failed to load notifications inbox:', err)
    } finally {
      setLoadingInbox(false)
    }
  }

  useEffect(() => {
    loadAlerts()
    loadHoldingsMonitor()
    loadInboxNotifications(activeTab === 'INBOX')

    // Poll live holdings every 10 seconds for real-time risk tracking
    const timer = setInterval(() => {
      loadHoldingsMonitor(true)
    }, 10000)
    const onNotifEvt = () => loadInboxNotifications(activeTab === 'INBOX')
    const onPrefEvt = () => {
      setSoundEnabled(isNotifSoundEnabled())
      setPushEnabled(isNotifPushEnabled())
    }
    window.addEventListener('stockai:notifications-updated', onNotifEvt)
    window.addEventListener('stockai:notif-prefs-changed', onPrefEvt)
    return () => {
      clearInterval(timer)
      window.removeEventListener('stockai:notifications-updated', onNotifEvt)
      window.removeEventListener('stockai:notif-prefs-changed', onPrefEvt)
    }
  }, [])

  useEffect(() => {
    loadInboxNotifications(activeTab === 'INBOX')
  }, [activeTab, inboxCategory, inboxUnreadOnly])

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

  const handleDirectExitHolding = async (holding: any) => {
    if (!holding?.trade_id) return
    const qty = holding.quantity || 0
    const entry = Number(holding.entry_price || 0).toFixed(2)
    const cmp = Number(holding.cmp || 0).toFixed(2)
    if (!confirm(`Close/Sell ${qty} shares of ${holding.symbol} (${holding.product_type}) bought @ ₹${entry} at current market price ₹${cmp}?`)) {
      return
    }
    setExitingTradeId(holding.trade_id)
    try {
      const res = await paperTradingApi.close(holding.trade_id)
      const pnlVal = Number(res.data?.realized_pnl ?? 0)
      const exitP = Number(res.data?.exit_price ?? holding.cmp ?? 0)
      toast.success(
        `Closed ${holding.symbol} @ ₹${exitP.toFixed(2)}`,
        `Realized Net P&L: ${pnlVal >= 0 ? '+' : ''}₹${pnlVal.toFixed(2)}. Orphan exit alerts cleared automatically.`
      )
      await Promise.all([loadHoldingsMonitor(), loadAlerts()])
    } catch (err: any) {
      toast.error('Failed to exit holding', err?.response?.data?.detail || err.message)
    } finally {
      setExitingTradeId(null)
    }
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
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 14 }}>
        <div style={{ minWidth: 0 }}>
          <h1 className="page-title" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Bell size={22} style={{ color: 'var(--color-accent-blue)' }} />
            Alerts &amp; Risk Guard
          </h1>
          <p className="page-subtitle">
            Entry proximity radar, target/stop-loss monitoring, GTT triggers, and auto-sell notifications.
          </p>
        </div>

        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button
            className="btn btn-secondary"
            onClick={() => setShowGttSearchPrompt(true)}
            style={{ gap: 6, color: 'var(--color-accent-blue)' }}
          >
            <Target size={14} /> New GTT
          </button>

          <button
            className="btn btn-secondary"
            onClick={handleSyncHoldings}
            disabled={syncingHoldings}
            style={{ gap: 6 }}
          >
            <ShieldCheck size={14} style={{ color: '#10b981' }} />
            {syncingHoldings ? 'Syncing…' : 'Sync Guard'}
          </button>

          <button className="btn btn-primary" onClick={() => setShowForm(!showForm)} style={{ gap: 6 }}>
            <PlusCircle size={14} /> New Alert
          </button>
        </div>
      </div>

      {/* Primary Tab Navigation */}
      <div className="mobile-scroll-tabs" style={{
        display: 'flex',
        gap: 6,
        borderBottom: '1px solid var(--color-border)',
        marginBottom: 18,
        paddingBottom: 2,
      }}>
        <button
          onClick={() => setActiveTab('SCREENER_RADAR')}
          style={{
            padding: '10px 14px',
            fontSize: 13.5,
            fontWeight: 600,
            border: 'none',
            borderBottom: activeTab === 'SCREENER_RADAR' ? '2px solid var(--color-accent-blue)' : '2px solid transparent',
            background: 'transparent',
            color: activeTab === 'SCREENER_RADAR' ? 'var(--color-text-primary)' : 'var(--color-text-muted)',
            cursor: 'pointer',
            display: 'inline-flex',
            alignItems: 'center',
            gap: 7,
            whiteSpace: 'nowrap',
            flexShrink: 0,
          }}
        >
          <Zap size={15} style={{ color: activeTab === 'SCREENER_RADAR' ? 'var(--color-accent-blue)' : 'inherit' }} />
          <span>Proximity Radar ({radarData.total_candidates || 0})</span>
          {radarData.summary?.at_best_buy > 0 && (
            <span style={{ background: 'var(--color-bullish-dim)', color: 'var(--color-bullish)', fontSize: 10.5, padding: '1px 6px', borderRadius: 10, fontWeight: 700 }}>
              {radarData.summary.at_best_buy} Optimal
            </span>
          )}
        </button>

        <button
          onClick={() => setActiveTab('HOLDINGS')}
          style={{
            padding: '10px 14px',
            fontSize: 13.5,
            fontWeight: 600,
            border: 'none',
            borderBottom: activeTab === 'HOLDINGS' ? '2px solid var(--color-accent-blue)' : '2px solid transparent',
            background: 'transparent',
            color: activeTab === 'HOLDINGS' ? 'var(--color-text-primary)' : 'var(--color-text-muted)',
            cursor: 'pointer',
            display: 'inline-flex',
            alignItems: 'center',
            gap: 7,
            whiteSpace: 'nowrap',
            flexShrink: 0,
          }}
        >
          <Briefcase size={15} />
          <span>Holdings Guard ({holdings.length})</span>
          {holdingsSummary.sl_warnings > 0 && (
            <span style={{ background: '#ef4444', color: '#fff', fontSize: 10.5, padding: '1px 6px', borderRadius: 10, fontWeight: 700 }}>
              {holdingsSummary.sl_warnings} SL
            </span>
          )}
        </button>

        <button
          onClick={() => setActiveTab('RADAR')}
          style={{
            padding: '10px 14px',
            fontSize: 13.5,
            fontWeight: 600,
            border: 'none',
            borderBottom: activeTab === 'RADAR' ? '2px solid var(--color-accent-blue)' : '2px solid transparent',
            background: 'transparent',
            color: activeTab === 'RADAR' ? 'var(--color-text-primary)' : 'var(--color-text-muted)',
            cursor: 'pointer',
            display: 'inline-flex',
            alignItems: 'center',
            gap: 7,
            whiteSpace: 'nowrap',
            flexShrink: 0,
          }}
        >
          <Target size={15} />
          <span>GTT Triggers ({radarAlerts.length})</span>
        </button>

        <button
          onClick={() => setActiveTab('CUSTOM')}
          style={{
            padding: '10px 14px',
            fontSize: 13.5,
            fontWeight: 600,
            border: 'none',
            borderBottom: activeTab === 'CUSTOM' ? '2px solid var(--color-accent-blue)' : '2px solid transparent',
            background: 'transparent',
            color: activeTab === 'CUSTOM' ? 'var(--color-text-primary)' : 'var(--color-text-muted)',
            cursor: 'pointer',
            display: 'inline-flex',
            alignItems: 'center',
            gap: 7,
            whiteSpace: 'nowrap',
            flexShrink: 0,
          }}
        >
          <Bell size={15} />
          <span>Custom ({customAlerts.length})</span>
        </button>

        <button
          onClick={() => setActiveTab('INBOX')}
          style={{
            padding: '10px 14px',
            fontSize: 13.5,
            fontWeight: 600,
            border: 'none',
            borderBottom: activeTab === 'INBOX' ? '2px solid #ef4444' : '2px solid transparent',
            background: activeTab === 'INBOX' ? 'rgba(239, 68, 68, 0.08)' : 'transparent',
            color: activeTab === 'INBOX' ? 'var(--color-text-primary)' : 'var(--color-text-muted)',
            cursor: 'pointer',
            display: 'inline-flex',
            alignItems: 'center',
            gap: 7,
            whiteSpace: 'nowrap',
            flexShrink: 0,
          }}
        >
          <Bell size={15} style={{ color: inboxUnseenCount > 0 ? '#ef4444' : activeTab === 'INBOX' ? 'var(--color-accent-blue)' : 'inherit' }} />
          <span>Notifications &amp; Auto-Sells</span>
          {inboxUnseenCount > 0 ? (
            <span style={{ background: '#ef4444', color: '#ffffff', fontSize: 10.5, padding: '1px 6px', borderRadius: 999, fontWeight: 700 }}>
              {inboxUnseenCount}
            </span>
          ) : inboxUnreadCount > 0 ? (
            <span style={{ background: 'rgba(59, 130, 246, 0.16)', color: 'var(--color-accent-blue)', fontSize: 10.5, padding: '1px 6px', borderRadius: 10, fontWeight: 700 }}>
              {inboxUnreadCount}
            </span>
          ) : null}
        </button>
      </div>

      {/* Create Alert Form (Collapsible) */}
      {showForm && (
        <div className="card" style={{ marginBottom: 18, border: '1px solid var(--color-accent-blue)' }}>
          <div className="card-title" style={{ marginBottom: 14, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span>New Custom Alert</span>
            <button className="btn btn-ghost" style={{ padding: '4px 10px', fontSize: 12 }} onClick={() => setShowForm(false)}>Close</button>
          </div>
          <form onSubmit={handleCreate} style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(min(100%, 200px), 1fr))', gap: 12 }}>
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
                <option value="LOW">Low — In-App</option><option value="MEDIUM">Medium — In-App</option><option value="HIGH">High — Email Eligible</option>
              </select>
            </div>
            <div>
              <label style={{ fontSize: 12, color: 'var(--color-text-muted)', marginBottom: 4, display: 'block' }}>Delivery</label>
              <select className="input" value={form.delivery_method} onChange={e => setForm({ ...form, delivery_method: e.target.value as typeof form.delivery_method })}>
                <option value="IN_APP">In-App</option><option value="EMAIL">Email</option><option value="BOTH">In-App + Email</option>
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
              <label style={{ fontSize: 12, color: 'var(--color-text-muted)', marginBottom: 4, display: 'block' }}>Note</label>
              <input className="input" placeholder="Optional note…" value={form.message} onChange={e => setForm({ ...form, message: e.target.value })} />
            </div>
            <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end' }}>
              <button type="submit" className="btn btn-primary" disabled={submitting}>{submitting ? 'Creating…' : 'Create Alert'}</button>
              <button type="button" className="btn btn-ghost" onClick={() => setShowForm(false)}>Cancel</button>
            </div>
          </form>
        </div>
      )}

      {/* TAB 0: PROXIMITY RADAR */}
      {activeTab === 'SCREENER_RADAR' && (
        <div>
          {/* Compact Filter & Refresh Bar */}
          <div className="card" style={{ marginBottom: 16, padding: '14px 16px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10 }}>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 15, fontWeight: 700, color: 'var(--color-text-primary)' }}>
                  <Zap size={17} color="var(--color-accent-blue)" />
                  <span>Entry &amp; Target Proximity Radar</span>
                </div>
                <div style={{ fontSize: 12, color: 'var(--color-text-muted)', marginTop: 2 }}>
                  Stocks trading near optimal screener entry or exit levels with live quote overlay.
                </div>
              </div>

              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                <button
                  className="btn btn-secondary"
                  onClick={() => loadRadar(radarSector, radarProximityPct, radarStage, false, true)}
                  disabled={loadingRadar}
                  style={{ gap: 6, fontSize: 12.5 }}
                >
                  <RefreshCw size={13} className={loadingRadar ? 'spin' : ''} />
                  {loadingRadar ? 'Updating…' : 'Refresh'}
                </button>

                <button
                  className="btn btn-success"
                  onClick={handleBulkSetRadarAlerts}
                  disabled={settingBulkAlerts || !radarData?.candidates?.length}
                  style={{ gap: 6, fontSize: 12.5 }}
                >
                  <CheckCircle2 size={14} />
                  {settingBulkAlerts ? 'Activating…' : `Alert All (${radarData?.total_candidates || 0})`}
                </button>
              </div>
            </div>

            {/* Filter Controls Row */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 180px), 1fr))', gap: 10, alignItems: 'end', marginTop: 12, paddingTop: 12, borderTop: '1px solid var(--color-border)' }}>
              <div>
                <label style={{ fontSize: 11, fontWeight: 600, color: 'var(--color-text-muted)', display: 'block', marginBottom: 4 }}>
                  Sector
                </label>
                <select className="input" style={{ padding: '7px 10px', fontSize: 13 }} value={radarSector} onChange={(e) => setRadarSector(e.target.value)}>
                  {SECTORS.map(s => (
                    <option key={s.value} value={s.value}>{s.label}</option>
                  ))}
                </select>
              </div>

              <div>
                <label style={{ fontSize: 11, fontWeight: 600, color: 'var(--color-text-muted)', display: 'block', marginBottom: 4 }}>
                  Stage
                </label>
                <select className="input" style={{ padding: '7px 10px', fontSize: 13 }} value={radarStage} onChange={(e) => setRadarStage(e.target.value)}>
                  {STAGE_FILTERS.map(st => (
                    <option key={st.value} value={st.value}>{st.label}</option>
                  ))}
                </select>
              </div>

              <div>
                <label style={{ fontSize: 11, fontWeight: 600, color: 'var(--color-text-muted)', display: 'block', marginBottom: 4 }}>
                  Distance
                </label>
                <select className="input" style={{ padding: '7px 10px', fontSize: 13 }} value={radarProximityPct} onChange={(e) => setRadarProximityPct(parseFloat(e.target.value))}>
                  {PROXIMITY_FILTERS.map(p => (
                    <option key={p.value} value={p.value}>{p.label}</option>
                  ))}
                </select>
              </div>

              <div style={{ fontSize: 11.5, color: 'var(--color-text-muted)', textAlign: 'left' }}>
                <div>
                  <strong>{radarData?.total_candidates || 0}</strong> setups ·{' '}
                  {radarData?.summary?.at_best_buy || 0} Optimal ·{' '}
                  {radarData?.summary?.pre_buy_prime || radarData?.summary?.near_best_buy || 0} Pre-Buy
                </div>
                {radarData?.generated_at && (
                  <div style={{ fontSize: 11, marginTop: 2, color: 'var(--color-accent-blue)' }}>
                    Live {radarData.quotes_live_count ?? radarData.total_candidates}/{radarData.total_candidates} · {new Date(radarData.generated_at).toLocaleTimeString('en-IN', { hour12: true })} IST
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Radar Table & Mobile Cards */}
          <div className="card">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
              <div className="card-title" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <Target size={16} style={{ color: 'var(--color-accent-blue)' }} />
                <span>Actionable Proximity Setups ({radarData?.candidates?.length || 0})</span>
              </div>
            </div>

            {loadingRadar && (!radarData?.candidates || radarData.candidates.length === 0) && (
              <div className="loading" style={{ padding: '36px 16px' }}>
                Scanning setups &amp; live quotes…
              </div>
            )}

            {!loadingRadar && (!radarData?.candidates || radarData.candidates.length === 0) && (
              <div className="empty-state" style={{ padding: '36px 16px' }}>
                No setups found for {radarSector} within ±{radarProximityPct}%.
              </div>
            )}

            {radarData?.candidates && radarData.candidates.length > 0 && (
              <>
                <div className="table-container desktop-only-table" style={{ marginBottom: 0 }}>
                  <table className="table" style={{ minWidth: '900px' }}>
                    <thead>
                      <tr>
                        <th>Stock</th>
                        <th>LTP</th>
                        <th>Best Buy</th>
                        <th>Distance</th>
                        <th>Status</th>
                        <th>Target</th>
                        <th>Stop Loss</th>
                        <th style={{ textAlign: 'right' }}>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {radarData.candidates.map((c: any) => {
                        const isAtBuy = c.proximity_status === 'AT_BEST_BUY'
                        const isBelowBuy = c.proximity_status === 'BELOW_BUY'
                        const isSetting = settingSingleAlertSym === c.symbol
                        return (
                          <tr key={c.symbol}>
                            <td>
                              <div style={{ fontWeight: 700, fontSize: 13.5 }}>{c.symbol}</div>
                              <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginTop: 2, fontSize: 11, color: 'var(--color-text-muted)' }}>
                                <span>{c.sector}</span>
                                <span>· Score {c.total_score}</span>
                                {c.technical_verification?.verified && <span style={{ color: 'var(--color-bullish)', fontWeight: 600 }}>· Verified</span>}
                              </div>
                            </td>
                            <td className="mono" style={{ fontWeight: 700 }}>₹{c.cmp.toFixed(2)}</td>
                            <td>
                              <div className="mono" style={{ fontWeight: 700, color: 'var(--color-accent-blue)' }}>₹{c.best_buy_price.toFixed(2)}</div>
                              {c.is_pre_buy && c.pre_buy_diff > 0 && (
                                <div style={{ fontSize: 10.5, color: 'var(--color-text-muted)' }}>₹{c.pre_buy_diff.toFixed(2)} away</div>
                              )}
                            </td>
                            <td>
                              <div className="mono" style={{ fontWeight: 700, color: isAtBuy ? 'var(--color-bullish)' : isBelowBuy ? '#a78bfa' : 'var(--color-accent-blue)' }}>
                                {c.distance_pct > 0 ? '+' : ''}{c.distance_pct.toFixed(2)}%
                              </div>
                            </td>
                            <td>
                              <span className={`badge ${isAtBuy ? 'badge-buy' : 'badge-watch'}`} style={{ fontSize: 10.5 }}>
                                {c.proximity_label}
                              </span>
                            </td>
                            <td>
                              <div className="mono" style={{ fontWeight: 700, color: 'var(--color-bullish)' }}>₹{c.target_price.toFixed(2)}</div>
                              <div style={{ fontSize: 11, color: 'var(--color-bullish)' }}>+{c.expected_gain_pct}%</div>
                            </td>
                            <td>
                              <div className="mono" style={{ fontWeight: 700, color: 'var(--color-bearish)' }}>₹{c.stop_loss.toFixed(2)}</div>
                              <div style={{ fontSize: 11, color: 'var(--color-text-muted)' }}>{c.risk_buffer_pct}% risk</div>
                            </td>
                            <td style={{ textAlign: 'right' }}>
                              <div style={{ display: 'inline-flex', gap: 6 }}>
                                <button
                                  onClick={() => handleSetRadarAlert(c)}
                                  disabled={isSetting}
                                  className="btn btn-secondary"
                                  style={{ padding: '5px 10px', fontSize: 11.5 }}
                                >
                                  <Bell size={12} /> {isSetting ? '…' : 'Alert'}
                                </button>
                                <button
                                  onClick={() => handleOpenRadarGtt(c)}
                                  className="btn btn-primary"
                                  style={{ padding: '5px 10px', fontSize: 11.5 }}
                                >
                                  <Target size={12} /> GTT
                                </button>
                              </div>
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>

                <div className="mobile-only-cards">
                  {radarData.candidates.map((c: any) => {
                    const isAtBuy = c.proximity_status === 'AT_BEST_BUY'
                    const isSetting = settingSingleAlertSym === c.symbol
                    return (
                      <div key={c.symbol} style={{ padding: 12, borderRadius: 8, background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border)' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6, gap: 6 }}>
                          <strong>{c.symbol.replace('.NS', '')}</strong>
                          <span className={`badge ${isAtBuy ? 'badge-buy' : 'badge-watch'}`} style={{ fontSize: 10 }}>
                            {c.distance_pct > 0 ? '+' : ''}{c.distance_pct.toFixed(2)}%
                          </span>
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 6, fontSize: 12, marginBottom: 10 }}>
                          <div><div style={{ fontSize: 10, color: 'var(--color-text-muted)' }}>LTP</div><strong className="mono">₹{c.cmp.toFixed(2)}</strong></div>
                          <div><div style={{ fontSize: 10, color: 'var(--color-text-muted)' }}>Entry</div><strong className="mono" style={{ color: 'var(--color-accent-blue)' }}>₹{c.best_buy_price.toFixed(2)}</strong></div>
                          <div><div style={{ fontSize: 10, color: 'var(--color-text-muted)' }}>Target</div><strong className="mono" style={{ color: 'var(--color-bullish)' }}>₹{c.target_price.toFixed(2)}</strong></div>
                        </div>
                        <div style={{ display: 'flex', gap: 8 }}>
                          <button onClick={() => handleSetRadarAlert(c)} disabled={isSetting} className="btn btn-secondary" style={{ flex: 1, fontSize: 12 }}>
                            <Bell size={12} /> Alert
                          </button>
                          <button onClick={() => handleOpenRadarGtt(c)} className="btn btn-primary" style={{ flex: 1, fontSize: 12 }}>
                            <Target size={12} /> GTT
                          </button>
                        </div>
                      </div>
                    )
                  })}
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {/* TAB 4: 🔔 PERSISTED SYSTEM & AUTO-SELL NOTIFICATIONS INBOX */}
      {activeTab === 'INBOX' && (
        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12, marginBottom: 16 }}>
            <div>
              <div className="card-title" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <Bell size={17} style={{ color: '#ef4444' }} />
                <span>Auto-Sells &amp; Notifications</span>
                {inboxUnreadCount > 0 && (
                  <span style={{ background: 'rgba(59, 130, 246, 0.16)', color: 'var(--color-accent-blue)', fontSize: 11, padding: '2px 8px', borderRadius: 10, fontWeight: 700 }}>
                    {inboxUnreadCount} Unread
                  </span>
                )}
              </div>
              <div style={{ fontSize: 12, color: 'var(--color-text-muted)', marginTop: 2 }}>
                Per-stock automated exits, order fills, and system notices.
              </div>
            </div>

            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
              <button
                type="button"
                className="btn btn-secondary"
                style={{ fontSize: 12, padding: '6px 10px', display: 'inline-flex', alignItems: 'center', gap: 5 }}
                onClick={() => {
                  const next = !soundEnabled
                  setNotifSoundEnabled(next)
                  setSoundEnabled(next)
                  if (next) playNotificationChime('HIGH')
                }}
              >
                {soundEnabled ? <Volume2 size={14} style={{ color: '#38bdf8' }} /> : <VolumeX size={14} />}
                <span>{soundEnabled ? 'Sound Chime ON' : 'Muted'}</span>
              </button>

              <button
                type="button"
                className="btn btn-secondary"
                style={{ fontSize: 12, padding: '6px 10px', display: 'inline-flex', alignItems: 'center', gap: 5 }}
                onClick={async () => {
                  if (pushEnabled) {
                    setNotifPushEnabled(false)
                    setPushEnabled(false)
                    return
                  }
                  const ok = await requestDesktopPushPermission()
                  setPushEnabled(ok)
                  if (ok) {
                    triggerDesktopPushNotification({
                      title: '🔔 Desktop Notifications Ready',
                      body: 'Live Auto-Sell executions and important system alerts will now chime and appear on desktop.',
                      severity: 'HIGH',
                      tag: 'stockai-alerts-tab-test',
                    })
                  }
                }}
              >
                <BellRing size={14} style={{ color: pushEnabled ? '#10b981' : undefined }} />
                <span>{pushEnabled ? 'Desktop Push ON' : 'Enable Desktop Push'}</span>
              </button>

              <button
                type="button"
                className="btn btn-secondary"
                style={{ fontSize: 12, padding: '6px 10px', display: 'inline-flex', alignItems: 'center', gap: 5 }}
                onClick={async () => {
                  await notificationsApi.markAllRead()
                  await loadInboxNotifications(true)
                  window.dispatchEvent(new CustomEvent('stockai:notifications-updated'))
                }}
                disabled={inboxUnreadCount === 0}
              >
                <CheckCheck size={14} /> Mark All Read
              </button>

              <button
                type="button"
                className="btn btn-secondary"
                style={{ fontSize: 12, padding: '6px 10px', display: 'inline-flex', alignItems: 'center', gap: 5 }}
                onClick={() => loadInboxNotifications(true)}
                disabled={loadingInbox}
              >
                <RefreshCw size={13} className={loadingInbox ? 'spin' : ''} /> Refresh
              </button>
            </div>
          </div>

          {/* Category Filter Pills */}
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 14 }}>
            {[
              { key: 'ALL', label: 'All' },
              { key: 'AUTO_SELL', label: 'Auto-Sells' },
              { key: 'ORDER_FILL', label: 'Order Fills' },
              { key: 'SYSTEM_NOTICE', label: 'System Notices' },
              { key: 'ALERT_TRIGGERED', label: 'Alert Triggers' },
            ].map((pill) => (
              <button
                key={pill.key}
                type="button"
                className={inboxCategory === pill.key && !inboxUnreadOnly ? 'btn btn-primary' : 'btn btn-secondary'}
                style={{ fontSize: 12, padding: '5px 12px' }}
                onClick={() => {
                  setInboxCategory(pill.key)
                  setInboxUnreadOnly(false)
                }}
              >
                {pill.label}
              </button>
            ))}

            <button
              type="button"
              className={inboxUnreadOnly ? 'btn btn-primary' : 'btn btn-secondary'}
              style={{ fontSize: 12, padding: '5px 12px' }}
              onClick={() => setInboxUnreadOnly((v) => !v)}
            >
              Unread ({inboxUnreadCount})
            </button>
          </div>

          {loadingInbox && inboxNotifications.length === 0 ? (
            <div className="loading" style={{ padding: 36, textAlign: 'center' }}>Loading notifications...</div>
          ) : inboxNotifications.length === 0 ? (
            <div className="empty-state" style={{ padding: 36, textAlign: 'center', color: 'var(--color-text-muted)' }}>
              No notifications match this filter yet. Whenever the system auto-sells a holding or publishes a system message, it will appear here.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {inboxNotifications.map((n: any) => {
                const isUnread = !n.is_read
                const meta = n.metadata || {}
                const pnl = meta.realized_pnl !== undefined && meta.realized_pnl !== null ? Number(meta.realized_pnl) : null
                return (
                  <div
                    key={n.id}
                    style={{
                      padding: 14,
                      borderRadius: 10,
                      border: `1px solid ${isUnread ? 'rgba(56, 189, 248, 0.45)' : 'var(--color-border)'}`,
                      borderLeft: n.category === 'AUTO_SELL'
                        ? `4px solid ${pnl !== null && pnl < 0 ? '#ef4444' : '#10b981'}`
                        : isUnread
                        ? '4px solid #38bdf8'
                        : '4px solid var(--color-border)',
                      background: isUnread ? 'rgba(56, 189, 248, 0.05)' : 'rgba(255, 255, 255, 0.015)',
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'flex-start',
                      gap: 14,
                      flexWrap: 'wrap',
                    }}
                  >
                    <div style={{ flex: 1, minWidth: 260 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 6 }}>
                        <span
                          className="badge"
                          style={{
                            fontSize: 10,
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: 4,
                            background: n.category === 'AUTO_SELL'
                              ? 'rgba(16, 185, 129, 0.16)'
                              : n.category === 'SYSTEM_NOTICE'
                              ? 'rgba(168, 85, 247, 0.16)'
                              : 'rgba(56, 189, 248, 0.16)',
                            color: n.category === 'AUTO_SELL'
                              ? '#34d399'
                              : n.category === 'SYSTEM_NOTICE'
                              ? '#c084fc'
                              : '#38bdf8',
                          }}
                        >
                          {n.category === 'AUTO_SELL' ? <Bot size={11} /> : n.category === 'SYSTEM_NOTICE' ? <Megaphone size={11} /> : <Zap size={11} />}
                          {n.category || 'GENERAL'}
                        </span>
                        {n.symbol && <span className="badge badge-secondary mono" style={{ fontSize: 10 }}>{n.symbol}</span>}
                        {isUnread && (
                          <span style={{ fontSize: 10, fontWeight: 800, color: '#38bdf8', background: 'rgba(56,189,248,0.16)', padding: '1px 6px', borderRadius: 4 }}>
                            UNREAD
                          </span>
                        )}
                        <span style={{ fontSize: 11, color: 'var(--color-text-muted)' }}>
                          {n.created_at_ist || (n.created_at ? new Date(n.created_at).toLocaleString() : '')}
                        </span>
                      </div>

                      <div style={{ fontWeight: 700, fontSize: 14, marginBottom: 4 }}>{n.title}</div>
                      <div style={{ fontSize: 13, color: 'var(--color-text-secondary)', lineHeight: 1.45 }}>{n.message}</div>

                      {n.category === 'AUTO_SELL' && meta.exit_price != null && (
                        <div className="mono" style={{ display: 'flex', gap: 14, flexWrap: 'wrap', fontSize: 11, marginTop: 8, color: 'var(--color-text-muted)' }}>
                          <span>Qty: <strong>{meta.quantity}</strong></span>
                          <span>Buy: <strong>₹{Number(meta.entry_price || 0).toFixed(2)}</strong></span>
                          <span>Sell: <strong>₹{Number(meta.exit_price || 0).toFixed(2)}</strong></span>
                          <span>Charges: <strong>₹{Number(meta.total_charges || 0).toFixed(2)}</strong></span>
                          {meta.holding_duration && <span>Held: <strong>{meta.holding_duration}</strong></span>}
                        </div>
                      )}
                    </div>

                    <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                      {meta.link && (
                        <button
                          type="button"
                          className="btn btn-secondary"
                          style={{ fontSize: 12, padding: '5px 10px' }}
                          onClick={async () => {
                            if (isUnread) await notificationsApi.markRead(n.id)
                            window.dispatchEvent(new CustomEvent('stockai:notifications-updated'))
                            navigate(meta.link)
                          }}
                        >
                          Open Ledger <ExternalLink size={12} style={{ marginLeft: 4 }} />
                        </button>
                      )}
                      {isUnread && (
                        <button
                          type="button"
                          className="btn btn-ghost"
                          style={{ fontSize: 12, padding: '5px 10px' }}
                          onClick={async () => {
                            await notificationsApi.markRead(n.id)
                            await loadInboxNotifications(true)
                            window.dispatchEvent(new CustomEvent('stockai:notifications-updated'))
                          }}
                        >
                          Mark Read
                        </button>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}

      {/* TAB 1: HOLDINGS GUARD */}
      {activeTab === 'HOLDINGS' && (
        <div>
          {/* Compact 3-Metric Strip */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 160px), 1fr))', gap: 10, marginBottom: 16 }}>
            <div className="card" style={{ padding: '12px 14px', borderLeft: '3px solid var(--color-accent-blue)' }}>
              <div style={{ fontSize: 11, color: 'var(--color-text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>Monitored</div>
              <div className="mono" style={{ fontSize: 20, fontWeight: 700, marginTop: 2 }}>{holdings.length}</div>
            </div>
            <div className="card" style={{ padding: '12px 14px', borderLeft: '3px solid var(--color-bullish)' }}>
              <div style={{ fontSize: 11, color: 'var(--color-bullish)', textTransform: 'uppercase', fontWeight: 600 }}>Near Target</div>
              <div className="mono" style={{ fontSize: 20, fontWeight: 700, marginTop: 2, color: 'var(--color-bullish)' }}>{holdingsSummary.targets_approaching}</div>
            </div>
            <div className="card" style={{ padding: '12px 14px', borderLeft: '3px solid var(--color-bearish)' }}>
              <div style={{ fontSize: 11, color: 'var(--color-bearish)', textTransform: 'uppercase', fontWeight: 600 }}>SL Warnings</div>
              <div className="mono" style={{ fontSize: 20, fontWeight: 700, marginTop: 2, color: 'var(--color-bearish)' }}>{holdingsSummary.sl_warnings}</div>
            </div>
          </div>

          <div className="card">
            <div className="card-header">
              <div className="card-title" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <ShieldCheck size={16} style={{ color: '#10b981' }} />
                <span>Position Risk Monitor</span>
              </div>
              <button onClick={() => loadHoldingsMonitor()} className="btn btn-ghost" style={{ padding: '4px 10px', fontSize: 12 }}>
                <RefreshCw size={13} className={loadingHoldings ? 'spin' : ''} /> Refresh
              </button>
            </div>

            {loadingHoldings && holdings.length === 0 && <div className="loading">Loading holdings monitor…</div>}

            {!loadingHoldings && holdings.length === 0 && (
              <div className="empty-state" style={{ padding: '32px 16px' }}>
                No active holdings to monitor right now.
              </div>
            )}

            {holdings.length > 0 && (
              <>
                <div className="table-container desktop-only-table" style={{ marginBottom: 0 }}>
                  <table className="table" style={{ minWidth: '860px' }}>
                    <thead>
                      <tr>
                        <th>Stock</th>
                        <th>Qty &amp; Entry</th>
                        <th>LTP</th>
                        <th>P&amp;L</th>
                        <th>Target</th>
                        <th>Stop Loss</th>
                        <th>Status</th>
                        <th style={{ textAlign: 'right' }}>Exit</th>
                      </tr>
                    </thead>
                    <tbody>
                      {holdings.map(h => {
                        const isProfit = h.unrealized_pnl >= 0
                        const pnlColor = isProfit ? 'var(--color-bullish)' : 'var(--color-bearish)'
                        const statusMap: Record<string, { label: string; cls: string }> = {
                          TARGET_HIT: { label: 'Target Reached', cls: 'badge-buy' },
                          TARGET_APPROACHING: { label: `Near Target (${h.distance_to_target_pct}%)`, cls: 'badge-watch' },
                          SL_HIT: { label: 'Stop Loss Hit', cls: 'badge-sell' },
                          SL_APPROACHING: { label: `Near SL (${h.distance_to_sl_pct}%)`, cls: 'badge-hold' },
                        }
                        const st = statusMap[h.risk_status] || { label: 'Safe Zone', cls: 'badge-buy' }
                        return (
                          <tr key={h.trade_id}>
                            <td>
                              <div style={{ fontWeight: 700 }}>{h.symbol}</div>
                              <div style={{ fontSize: 11, color: 'var(--color-text-muted)' }}>{h.product_type}</div>
                            </td>
                            <td className="mono">{h.quantity} @ ₹{h.entry_price.toFixed(2)}</td>
                            <td className="mono" style={{ fontWeight: 700 }}>₹{h.cmp.toFixed(2)}</td>
                            <td className="mono" style={{ color: pnlColor, fontWeight: 700 }}>
                              <div>{isProfit ? '+' : ''}₹{h.unrealized_pnl.toFixed(2)}</div>
                              <div style={{ fontSize: 11 }}>{isProfit ? '+' : ''}{h.pnl_pct.toFixed(2)}%</div>
                            </td>
                            <td className="mono" style={{ color: 'var(--color-bullish)', fontWeight: 600 }}>₹{h.target_price.toFixed(2)}</td>
                            <td className="mono" style={{ color: 'var(--color-bearish)', fontWeight: 600 }}>₹{h.stop_loss.toFixed(2)}</td>
                            <td><span className={`badge ${st.cls}`} style={{ fontSize: 10.5 }}>{st.label}</span></td>
                            <td style={{ textAlign: 'right' }}>
                              <button onClick={() => handleDirectExitHolding(h)} disabled={exitingTradeId === h.trade_id} className="btn btn-danger" style={{ padding: '4px 10px', fontSize: 12 }}>
                                {exitingTradeId === h.trade_id ? 'Closing…' : 'Exit'}
                              </button>
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>

                <div className="mobile-only-cards">
                  {holdings.map(h => {
                    const isProfit = h.unrealized_pnl >= 0
                    const pnlColor = isProfit ? 'var(--color-bullish)' : 'var(--color-bearish)'
                    return (
                      <div key={h.trade_id} style={{ padding: 12, borderRadius: 8, background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border)' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                          <strong>{h.symbol.replace('.NS', '')} · {h.quantity} qty</strong>
                          <strong className="mono" style={{ color: pnlColor }}>{isProfit ? '+' : ''}₹{h.unrealized_pnl.toFixed(2)}</strong>
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 6, fontSize: 11.5, marginBottom: 8 }}>
                          <div><div style={{ fontSize: 10, color: 'var(--color-text-muted)' }}>LTP</div><strong className="mono">₹{h.cmp.toFixed(2)}</strong></div>
                          <div><div style={{ fontSize: 10, color: 'var(--color-text-muted)' }}>Target</div><strong className="mono" style={{ color: 'var(--color-bullish)' }}>₹{h.target_price.toFixed(2)}</strong></div>
                          <div><div style={{ fontSize: 10, color: 'var(--color-text-muted)' }}>SL</div><strong className="mono" style={{ color: 'var(--color-bearish)' }}>₹{h.stop_loss.toFixed(2)}</strong></div>
                        </div>
                        <button onClick={() => handleDirectExitHolding(h)} disabled={exitingTradeId === h.trade_id} className="btn btn-danger w-100" style={{ fontSize: 12 }}>
                          {exitingTradeId === h.trade_id ? 'Closing…' : 'Exit Position'}
                        </button>
                      </div>
                    )
                  })}
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {/* TAB 2: GTT TRIGGERS */}
      {activeTab === 'RADAR' && (
        <div className="card">
          <div className="card-header">
            <div>
              <div className="card-title" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <Target size={16} style={{ color: 'var(--color-accent-blue)' }} />
                <span>GTT Triggers ({radarAlerts.length})</span>
              </div>
              <div style={{ fontSize: 12, color: 'var(--color-text-muted)', marginTop: 2 }}>
                Good-Till-Triggered price alerts for entry, target, and stop levels.
              </div>
            </div>
            <button className="btn btn-primary" onClick={() => setShowGttSearchPrompt(true)} style={{ fontSize: 12, padding: '6px 12px' }}>
              <Target size={13} /> New GTT
            </button>
          </div>

          {loadingAlerts && <div className="loading">Loading GTT triggers…</div>}

          {!loadingAlerts && radarAlerts.length === 0 && (
            <div className="empty-state" style={{ padding: '28px 16px' }}>
              No GTT triggers active yet.
            </div>
          )}

          {radarAlerts.length > 0 && (
            <>
              <div className="table-container desktop-only-table" style={{ marginBottom: 0 }}>
                <table className="table" style={{ minWidth: '680px' }}>
                  <thead>
                    <tr>
                      <th>Symbol</th>
                      <th>Trigger Type</th>
                      <th>Level</th>
                      <th>Status</th>
                      <th>Rule</th>
                      <th>Last Triggered</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {radarAlerts.map(a => {
                      const typeLabelMap: Record<string, { label: string; cls: string }> = {
                        TARGET_PROXIMITY: { label: 'Near Target', cls: 'badge-buy' },
                        TARGET_HIT: { label: 'Target Hit', cls: 'badge-buy' },
                        STOP_LOSS_PROXIMITY: { label: 'Near SL', cls: 'badge-sell' },
                        STOP_LOSS_HIT: { label: 'SL Hit', cls: 'badge-sell' },
                        BUY_PROXIMITY: { label: 'Pullback Entry', cls: 'badge-watch' },
                      }
                      const info = typeLabelMap[a.condition_type] || { label: a.condition_type, cls: 'badge-watch' }
                      return (
                        <tr key={a.alert_id}>
                          <td className="mono" style={{ fontWeight: 700 }}>{a.symbol}</td>
                          <td><span className={`badge ${info.cls}`} style={{ fontSize: 10.5 }}>{info.label}</span></td>
                          <td className="mono" style={{ fontWeight: 600 }}>₹{a.condition_value}</td>
                          <td style={{ color: a.is_active ? 'var(--color-bullish)' : 'var(--color-text-muted)', fontSize: 12.5 }}>{a.is_active ? 'Active' : 'Inactive'}</td>
                          <td style={{ fontSize: 12, color: 'var(--color-text-secondary)', maxWidth: 240 }}>{a.message || '—'}</td>
                          <td style={{ color: 'var(--color-text-muted)', fontSize: 12 }}>{a.triggered_at ? new Date(a.triggered_at).toLocaleString('en-IN') : 'Pending'}</td>
                          <td>
                            <div style={{ display: 'flex', gap: 6 }}>
                              {a.is_active && <button className="btn btn-ghost" style={{ padding: '4px 8px' }} onClick={() => handleDeactivate(a.alert_id)}><BellOff size={13} /></button>}
                              <button className="btn btn-danger" style={{ padding: '4px 8px' }} onClick={() => handleDelete(a.alert_id)}><Trash2 size={13} /></button>
                            </div>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>

              <div className="mobile-only-cards">
                {radarAlerts.map(a => (
                  <div key={a.alert_id} style={{ padding: 12, borderRadius: 8, background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                    <div>
                      <strong className="mono">{a.symbol.replace('.NS', '')} · ₹{a.condition_value}</strong>
                      <div style={{ fontSize: 11.5, color: 'var(--color-text-muted)' }}>{a.condition_type.replace(/_/g, ' ')}</div>
                    </div>
                    <div style={{ display: 'flex', gap: 6 }}>
                      {a.is_active && <button className="btn btn-ghost" style={{ padding: '5px 8px' }} onClick={() => handleDeactivate(a.alert_id)}><BellOff size={13} /></button>}
                      <button className="btn btn-danger" style={{ padding: '5px 8px' }} onClick={() => handleDelete(a.alert_id)}><Trash2 size={13} /></button>
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      )}

      {/* TAB 3: CUSTOM TECHNICAL ALERTS */}
      {activeTab === 'CUSTOM' && (
        <div className="card">
          <div className="card-title" style={{ marginBottom: 14 }}>
            Custom Technical Alerts ({customAlerts.length})
          </div>

          {loadingAlerts && <div className="loading">Loading custom alerts…</div>}

          {!loadingAlerts && customAlerts.length === 0 && (
            <div className="empty-state" style={{ padding: '28px 16px' }}>
              No custom technical alerts configured yet.
            </div>
          )}

          {customAlerts.length > 0 && (
            <>
              <div className="table-container desktop-only-table" style={{ marginBottom: 0 }}>
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
                        <td className="mono" style={{ fontWeight: 600 }}>{a.symbol}</td>
                        <td style={{ color: 'var(--color-text-secondary)' }}>{CONDITION_TYPES.find(c => c.value === a.condition_type)?.label || a.condition_type}</td>
                        <td className="mono">{a.condition_type === 'PATTERN' ? (PATTERN_TYPES.find(p => String(p.value) === String(a.condition_value))?.label || a.condition_value) : a.condition_value}</td>
                        <td style={{ color: a.is_active ? 'var(--color-bullish)' : 'var(--color-text-muted)', fontSize: 12.5 }}>{a.is_active ? 'Active' : 'Inactive'}</td>
                        <td style={{ color: 'var(--color-text-muted)', fontSize: 12 }}>{a.triggered_at ? new Date(a.triggered_at).toLocaleString('en-IN') : 'Never'}</td>
                        <td>
                          <div style={{ display: 'flex', gap: 6 }}>
                            {a.is_active && <button className="btn btn-ghost" style={{ padding: '4px 8px' }} onClick={() => handleDeactivate(a.alert_id)}><BellOff size={13} /></button>}
                            <button className="btn btn-danger" style={{ padding: '4px 8px' }} onClick={() => handleDelete(a.alert_id)}><Trash2 size={13} /></button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="mobile-only-cards">
                {customAlerts.map(a => (
                  <div key={a.alert_id} style={{ padding: 12, borderRadius: 8, background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                    <div>
                      <strong className="mono">{a.symbol.replace('.NS', '')}</strong>
                      <div style={{ fontSize: 11.5, color: 'var(--color-text-muted)' }}>
                        {CONDITION_TYPES.find(c => c.value === a.condition_type)?.label || a.condition_type}: {a.condition_value}
                      </div>
                    </div>
                    <div style={{ display: 'flex', gap: 6 }}>
                      {a.is_active && <button className="btn btn-ghost" style={{ padding: '5px 8px' }} onClick={() => handleDeactivate(a.alert_id)}><BellOff size={13} /></button>}
                      <button className="btn btn-danger" style={{ padding: '5px 8px' }} onClick={() => handleDelete(a.alert_id)}><Trash2 size={13} /></button>
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
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
                <span>Create GTT Trigger Order</span>
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
          target1={gttOrderData.target1}
          target2={gttOrderData.target2}
          target3={gttOrderData.target3}
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
