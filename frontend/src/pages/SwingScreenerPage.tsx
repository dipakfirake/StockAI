import { useEffect, useState, useMemo, useRef } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { marketApi, paperTradingApi, alertsApi, swingAuditApi } from '../services/api'
import { useAuth } from '../AuthContext'
import { 
  TrendingUp, TrendingDown, Minus, RefreshCw, Search, Filter, 
  ExternalLink, Briefcase, Bell, CheckCircle2, ShieldAlert, 
  ArrowUpRight, ArrowDownRight, Layers, LayoutGrid, List, Sparkles, AlertCircle, Target, Download,
  FileSpreadsheet, History, Calendar, X
} from 'lucide-react'
import { toast } from '../components/Toast'
import ZerodhaOrderModal from '../components/ZerodhaOrderModal'

interface TargetLevel {
  level: string
  price: number
  gain_pct: number
  cmp_gain_pct?: number
  reward_to_risk: number
}

interface TradePlan {
  entry_price: number
  current_price?: number
  cmp?: number
  best_buy_price?: number
  optimal_entry_price?: number
  entry_type?: 'PULLBACK_DIP' | 'BREAKOUT' | 'MARKET_CMP' | 'RALLY_SELL' | 'BREAKDOWN' | 'CONSOLIDATION' | string
  entry_zone?: string
  entry_advice?: string
  optimal_expected_gain_pct?: number
  optimal_reward_to_risk?: number
  stop_loss: number
  target_price: number
  target_1?: number
  target_2?: number
  target_3?: number
  expected_gain_pct: number
  risk_pct: number
  reward_to_risk: number
  cmp_gain_pct?: number
  cmp_risk_pct?: number
  estimated_hold_time: string
  targets?: TargetLevel[]
}

interface SwingStock {
  symbol: string
  name: string
  action: 'BUY' | 'SELL' | 'HOLD'
  total_score: number
  scores: {
    technical: number
    fundamental: number
    sentiment: number
  }
  market_regime?: string
  market_defense_active?: boolean
  cap_segment?: string
  is_fast_growth?: boolean
  trade_plan: TradePlan | null
  news_sentiment?: string
  error?: string
}

interface ScreenerResponse {
  timestamp: string
  sector: string
  stocks_scanned: number
  setups_found: number
  summary: {
    total_scanned: number
    valid_results: number
    buy_count: number
    sell_count: number
    hold_count: number
    avg_buy_gain_pct: number
    avg_buy_rr: number
    avg_sell_drop_pct: number
    top_buy_pick: string | null
    top_sell_pick: string | null
  }
  buy_stocks: SwingStock[]
  sell_stocks: SwingStock[]
  hold_stocks: SwingStock[]
  top_setups: SwingStock[]
  all_results: SwingStock[]
}

const SECTOR_OPTIONS = [
  { id: 'NIFTY_50', label: 'Nifty 50 (Benchmark 25)' },
  { id: 'BANKING', label: 'Banking & Financials (10)' },
  { id: 'IT', label: 'IT & Technology (8)' },
  { id: 'AUTO', label: 'Automotive & Ancillaries (8)' },
  { id: 'PHARMA', label: 'Pharma & Healthcare (7)' },
  { id: 'ENERGY', label: 'Energy & Utilities (8)' },
  { id: 'FMCG', label: 'FMCG & Consumer (8)' },
  { id: 'METAL', label: 'Metals & Mining (7)' },
  { id: 'MID_CAP', label: 'Midcap Growth (10)' },
  { id: 'SMALL_CAP', label: 'Smallcap Momentum (10)' },
]

export default function SwingScreenerPage() {
  const navigate = useNavigate()
  const { user } = useAuth()
  const isAdmin = Boolean(user?.is_admin)
  const [sector, setSector] = useState('NIFTY_50')
  const [activeTab, setActiveTab] = useState<'BUY' | 'SELL' | 'HOLD' | 'ALL'>('BUY')
  const [expandedCards, setExpandedCards] = useState<Record<string, boolean>>({})
  const [viewMode, setViewMode] = useState<'cards' | 'table'>('cards')
  const [searchQuery, setSearchQuery] = useState('')
  const [minScore, setMinScore] = useState<number>(0)
  
  const [data, setData] = useState<ScreenerResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [scanProgress, setScanProgress] = useState<number | null>(null)
  const scanGenerationRef = useRef(0)
  const [syncingAudit, setSyncingAudit] = useState(false)
  const [tradingSymbol, setTradingSymbol] = useState<string | null>(null)
  const [showArchiveModal, setShowArchiveModal] = useState(false)
  const [archiveFiles, setArchiveFiles] = useState<any[]>([])
  const [loadingArchives, setLoadingArchives] = useState(false)
  const [downloadingExcel, setDownloadingExcel] = useState(false)
  const [rollingOver, setRollingOver] = useState(false)
  const [cycleData, setCycleData] = useState<any>(null)
  const [orderModalStock, setOrderModalStock] = useState<SwingStock | null>(null)
  const [orderModalOpen, setOrderModalOpen] = useState(false)
  const [isGttMode, setIsGttMode] = useState(false)

  const fetchCurrentCycle = async () => {
    try {
      const res = await swingAuditApi.getCurrentCycle()
      if (res.data?.cycle) {
        setCycleData(res.data.cycle)
      }
    } catch (e) {
      console.debug('Failed to load current cycle summary:', e)
    }
  }

  const handleDownloadLatestExcel = async () => {
    setDownloadingExcel(true)
    try {
      const filename = await swingAuditApi.downloadLatestExcel()
      toast.success('Audit Excel Downloaded', filename)
    } catch (err: any) {
      console.error('Audit Excel download failed:', err)
      toast.error('Download Failed', err.message || 'Could not download audit Excel spreadsheet')
    } finally {
      setDownloadingExcel(false)
    }
  }

  const handleDownloadArchiveExcel = async (filename: string) => {
    try {
      await swingAuditApi.downloadArchiveExcel(filename)
      toast.success('Archive Downloaded', filename)
    } catch (err: any) {
      console.error('Archive download failed:', err)
      toast.error('Download Failed', err.message || 'Could not download archive file')
    }
  }

  const handleRolloverCycle = async () => {
    const cycleNum = cycleData?.cycle_number || 1
    const confirmMsg = `Finalize and archive Audit Cycle #${cycleNum} (freezing its scorecard into a permanent .xlsx file) and initialize Cycle #${cycleNum + 1}?`
    if (!window.confirm(confirmMsg)) return

    setRollingOver(true)
    try {
      const res = await swingAuditApi.rolloverCycle(true)
      const data = res.data
      toast.success(
        `Cycle #${cycleNum} Finalized!`,
        `Scorecard frozen into ${data?.completed_cycle?.archive_file || 'archive'}. Cycle #${data?.active_cycle?.cycle_number || cycleNum + 1} is now ACTIVE.`
      )
      await fetchCurrentCycle()
      await fetchArchiveFiles()
    } catch (err: any) {
      console.error('Cycle rollover failed:', err)
      toast.error('Rollover Failed', err?.response?.data?.message || err.message)
    } finally {
      setRollingOver(false)
    }
  }

  const fetchArchiveFiles = async () => {
    setLoadingArchives(true)
    try {
      const res = await swingAuditApi.listFiles()
      setArchiveFiles(res.data?.files || [])
    } catch (err: any) {
      console.error('Failed to load audit archives:', err)
      toast.error('Failed to load audit archives', err?.response?.data?.detail || err.message)
    } finally {
      setLoadingArchives(false)
    }
  }

  const handleOpenArchives = () => {
    setShowArchiveModal(true)
    fetchArchiveFiles()
  }

  const handleSyncAudit = async () => {
    setSyncingAudit(true)
    try {
      toast.info('Synchronizing Audit', 'Evaluating 11-day price milestones and ratchet stops...')
      const res = await swingAuditApi.sync(false)
      const cataloged = res.data.cataloged_count || 0
      const updated = res.data.updated_count || 0
      if (res.data.status === 'partial_success' || (updated === 0 && (res.data.total_trades || 0) > 0)) {
        toast.warning(
          'Audit Sync Incomplete',
          res.data.message || `0 active stock prices could be updated. Please verify database columns.`
        )
      } else {
        toast.success(
          '11-Day Audit Synced!',
          `Evaluated ${updated} stocks (${cataloged} new cataloged) | Win Rate: ${res.data.win_rate ?? 0}% | P&L: ₹${res.data.total_pnl_rupees ?? 0}`
        )
      }
      // Refresh screener, cycle summary, and archives to display latest state
      fetchScreener(false)
      fetchCurrentCycle()
      fetchArchiveFiles()
    } catch (err: any) {
      console.error('Audit sync failed:', err)
      toast.error('Audit sync failed', err?.response?.data?.detail || err.message)
    } finally {
      setSyncingAudit(false)
    }
  }

  const fetchScreener = async (forceRefresh = false) => {
    const gen = ++scanGenerationRef.current
    if (forceRefresh) setRefreshing(true)
    else setLoading(true)
    setScanProgress(null)

    try {
      const startRes = await marketApi.startScreenerScan(sector, forceRefresh)
      if (scanGenerationRef.current !== gen) return

      const initialJob = startRes.data
      if (initialJob?.status === 'completed' && initialJob?.result) {
        setData(initialJob.result)
        setScanProgress(null)
        if (forceRefresh) toast.success('Market scan updated successfully')
        return
      }

      // Immediately show LKG snapshot while background scan progresses if available
      if (initialJob?.cached_data) {
        setData(initialJob.cached_data)
        setLoading(false)
      }
      setScanProgress(typeof initialJob?.progress === 'number' ? initialJob.progress : 5)

      const jobId = initialJob?.job_id
      if (!jobId) {
        const fallbackRes = await marketApi.getScreener(sector, forceRefresh)
        if (scanGenerationRef.current !== gen) return
        setData(fallbackRes.data)
        if (forceRefresh) toast.success('Market scan updated successfully')
        return
      }

      // Poll lightweight status endpoint every 2s (max ~180s) with transient error tolerance
      let consecutiveErrors = 0
      for (let attempt = 0; attempt < 90; attempt++) {
        await new Promise((resolve) => setTimeout(resolve, 2000))
        if (scanGenerationRef.current !== gen) return

        let pollRes: any = null
        try {
          pollRes = await marketApi.getScreenerScanStatus(jobId)
          consecutiveErrors = 0
        } catch (pollErr: any) {
          consecutiveErrors++
          if (consecutiveErrors >= 3) {
            throw pollErr
          }
          continue
        }

        if (scanGenerationRef.current !== gen) return
        const job = pollRes?.data

        if (typeof job?.progress === 'number') {
          setScanProgress(job.progress)
        }
        if (job?.status === 'completed' && job?.result) {
          setData(job.result)
          setScanProgress(null)
          if (forceRefresh) toast.success('Market scan updated successfully')
          return
        }
        if (job?.status === 'failed') {
          throw new Error(job.error || 'Background scan failed')
        }
      }

      // If background scan takes longer than 180s, gracefully hydrate latest verified setups rather than failing blank
      try {
        const fallbackRes = await marketApi.getScreener(sector, false)
        if (scanGenerationRef.current !== gen) return
        if (fallbackRes?.data && (fallbackRes.data.buy_stocks?.length || fallbackRes.data.hold_stocks?.length || fallbackRes.data.all_results?.length)) {
          setData(fallbackRes.data)
          toast.info('Market scan is finalizing in the background. Showing latest verified setups.')
          return
        }
      } catch (fallbackErr) {
        console.debug('LKG fallback retrieval skipped:', fallbackErr)
      }

      throw new Error('Market scan timed out after 180s')
    } catch (err: any) {
      if (scanGenerationRef.current !== gen) return
      console.error('Failed to fetch screener:', err)
      toast.error('Failed to load swing trade screener', err?.message || 'Network error')
    } finally {
      if (scanGenerationRef.current === gen) {
        setLoading(false)
        setRefreshing(false)
        setScanProgress(null)
      }
    }
  }

  useEffect(() => {
    fetchScreener(false)
    fetchCurrentCycle()
    return () => {
      scanGenerationRef.current += 1
    }
  }, [sector])

  // Interactive Zerodha-style order modal launcher
  const handleOpenOrderModal = (stock: SwingStock) => {
    setOrderModalStock(stock)
    setIsGttMode(false)
    setOrderModalOpen(true)
  }

  // Interactive Zerodha GTT (Good-Till-Triggered) modal launcher
  const handleOpenGttModal = (stock: SwingStock) => {
    setOrderModalStock(stock)
    setIsGttMode(true)
    setOrderModalOpen(true)
  }

  // Quick Coupled Alerts action (Buy Pre-Alert, Target Pre-Alert, and Stop Loss)
  const handleQuickAlert = async (stock: SwingStock) => {
    if (!stock.trade_plan) return
    try {
      const cmp = stock.trade_plan.current_price || stock.trade_plan.cmp || stock.trade_plan.entry_price || 100.0
      await alertsApi.screenerSetup({
        symbol: stock.symbol,
        current_price: cmp,
        best_buy_price: stock.trade_plan.best_buy_price || stock.trade_plan.optimal_entry_price,
        target_price: stock.trade_plan.target_price,
        stop_loss: stock.trade_plan.stop_loss,
        proximity_pct: 1.0,
      })
      toast.success(
        `Coupled Alerts Set: ${stock.symbol}`,
        `Pre-alerts active for Buy Zone, Target (Sell before loss), and Stop Loss!`
      )
    } catch (err: any) {
      toast.error('Failed to set coupled alerts', err?.response?.data?.detail || err.message)
    }
  }

  // Filtered stocks based on tab, query, and score
  const displayedStocks = useMemo(() => {
    if (!data) return []
    let list: SwingStock[] = []
    if (activeTab === 'BUY') list = data.buy_stocks || []
    else if (activeTab === 'SELL') list = data.sell_stocks || []
    else if (activeTab === 'HOLD') list = data.hold_stocks || []
    else list = data.all_results || []

    return list.filter(stock => {
      const matchesSearch = 
        stock.symbol.toLowerCase().includes(searchQuery.toLowerCase()) ||
        (stock.name && stock.name.toLowerCase().includes(searchQuery.toLowerCase()))
      const matchesScore = stock.total_score >= minScore
      return matchesSearch && matchesScore
    })
  }, [data, activeTab, searchQuery, minScore])

  return (
    <div style={{ maxWidth: 1400, margin: '0 auto', paddingBottom: 60 }}>
      {/* Page Header */}
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 12 }}>
        <div style={{ flex: '1 1 280px', minWidth: 0 }}>
          <h1 className="page-title" style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <TrendingUp size={22} style={{ color: 'var(--color-accent-blue)', flexShrink: 0 }} />
            Swing Screener
          </h1>
          <p className="page-subtitle">
            Multi-factor BUY, SELL, and HOLD setups with entry, target tiers, and risk levels.
          </p>
        </div>

        <div className="mobile-w-100" style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <select
            className="input"
            value={sector}
            onChange={(e) => setSector(e.target.value)}
            style={{ flex: '1 1 170px', minWidth: 0, fontWeight: 500, padding: '7px 10px' }}
          >
            {SECTOR_OPTIONS.map(opt => (
              <option key={opt.id} value={opt.id}>{opt.label}</option>
            ))}
          </select>

          <button
            onClick={() => fetchScreener(true)}
            disabled={refreshing || loading || scanProgress !== null}
            className="btn btn-secondary"
            style={{ gap: 6 }}
            title="Scan selected sector"
          >
            <RefreshCw size={14} className={(refreshing || scanProgress !== null) ? 'spin' : ''} />
            <span>
              {(refreshing || scanProgress !== null)
                ? (scanProgress !== null ? `Scanning ${scanProgress}%` : 'Scanning…')
                : 'Run Scan'}
            </span>
          </button>

          {isAdmin && (
            <button
              onClick={handleSyncAudit}
              disabled={syncingAudit}
              className="btn btn-secondary"
              style={{ gap: 6, color: '#10b981', borderColor: 'rgba(16, 185, 129, 0.35)' }}
              title="Update cycle close prices & P&L"
            >
              <RefreshCw size={14} className={syncingAudit ? 'spin' : ''} />
              <span>{syncingAudit ? 'Syncing…' : 'Sync Prices'}</span>
            </button>
          )}

          <button
            onClick={handleDownloadLatestExcel}
            disabled={downloadingExcel}
            className="btn btn-secondary"
            style={{ gap: 6, color: 'var(--color-accent-blue)' }}
            title="Download current 11-day audit Excel workbook"
          >
            <Download size={14} className={downloadingExcel ? 'spin' : ''} />
            <span>{downloadingExcel ? 'Exporting…' : 'Export Excel'}</span>
          </button>

          <button
            onClick={handleOpenArchives}
            className="btn btn-ghost"
            style={{ gap: 6 }}
            title="View past 11-day audit cycle reports"
          >
            <History size={14} />
            <span>Archives{archiveFiles.length > 0 ? ` (${archiveFiles.length})` : ''}</span>
          </button>
        </div>
      </div>

      {/* Active Audit Cycle Summary Bar */}
      {cycleData && (
        <div className="card" style={{
          marginBottom: 14,
          padding: '12px 16px',
          borderLeft: '3px solid var(--color-accent-blue)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: 10
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', fontSize: 12.5 }}>
            <span style={{
              background: 'rgba(59, 130, 246, 0.14)',
              color: 'var(--color-accent-blue)',
              padding: '3px 8px',
              borderRadius: 6,
              fontWeight: 700,
              fontSize: 11,
              textTransform: 'uppercase'
            }}>
              Cycle #{cycleData.cycle_number} · {cycleData.status}
            </span>
            <span style={{ color: 'var(--color-text-primary)', fontWeight: 600 }}>
              {cycleData.from_date} – {cycleData.to_date}
            </span>
            <span style={{ color: 'var(--color-text-muted)' }}>
              Tracked <strong className="mono" style={{ color: 'var(--color-text-primary)' }}>{cycleData.total_trades || 0}</strong>
              {cycleData.closed_trades !== undefined && ` · ${cycleData.closed_trades} closed / ${cycleData.in_progress_trades ?? 0} open`}
            </span>
            <span style={{ color: 'var(--color-text-muted)' }}>
              Win <strong className="mono" style={{ color: (cycleData.win_rate || 0) >= 50 ? 'var(--color-bullish)' : 'var(--color-neutral)' }}>{cycleData.win_rate || 0}%</strong>
              {cycleData.profit_factor !== undefined && (
                <> · PF <strong className="mono">{cycleData.profit_factor}x</strong></>
              )}
            </span>
            <span style={{ color: 'var(--color-text-muted)' }}>
              Gross P&amp;L <strong className="mono" style={{ color: (cycleData.total_pnl_rupees || 0) >= 0 ? 'var(--color-bullish)' : 'var(--color-bearish)' }}>₹{(cycleData.total_pnl_rupees || 0).toLocaleString('en-IN')}</strong>
              {cycleData.user_executed_trades > 0 && (
                <> · My Buys <strong className="mono">{cycleData.user_executed_trades}</strong></>
              )}
            </span>
          </div>

          {isAdmin && (
            <button
              onClick={handleRolloverCycle}
              disabled={rollingOver}
              className="btn btn-secondary"
              style={{
                gap: 6,
                fontSize: 12,
                padding: '6px 12px',
                borderColor: 'rgba(16, 185, 129, 0.35)',
                color: '#10b981',
              }}
              title="Finalize current cycle and start the next 11-day cycle"
            >
              <RefreshCw size={13} className={rollingOver ? 'spin' : ''} />
              <span>{rollingOver ? 'Rolling Over…' : `Start Cycle #${(cycleData?.cycle_number || 1) + 1}`}</span>
            </button>
          )}
        </div>
      )}

      {/* Institutional Summary Strip */}
      {data && data.summary && (
        <div className="responsive-grid-summary" style={{ marginBottom: 16 }}>
          <div
            className="card"
            style={{
              padding: '12px 14px',
              borderLeft: '3px solid var(--color-bullish)',
              cursor: 'pointer',
              background: activeTab === 'BUY' ? 'var(--color-bullish-dim)' : undefined
            }}
            onClick={() => setActiveTab('BUY')}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
              <span style={{ fontSize: 12, color: 'var(--color-bullish)', fontWeight: 700, display: 'flex', alignItems: 'center', gap: 5 }}>
                <TrendingUp size={14} /> BUY
              </span>
              <span className="badge badge-buy">{data.summary.buy_count} {data.summary.buy_count === 1 ? 'Stock' : 'Stocks'}</span>
            </div>
            <div className="mono" style={{ fontSize: 21, fontWeight: 700, color: 'var(--color-bullish)' }}>
              +{data.summary.avg_buy_gain_pct}% <span style={{ fontSize: 11.5, fontWeight: 400, color: 'var(--color-text-muted)' }}>Avg Target</span>
            </div>
            <div style={{ fontSize: 11.5, color: 'var(--color-text-muted)', marginTop: 2 }}>
              Avg R:R <strong>{data.summary.avg_buy_rr}:1</strong> · Top <strong>{data.summary.top_buy_pick || '—'}</strong>
            </div>
          </div>

          <div
            className="card"
            style={{
              padding: '12px 14px',
              borderLeft: '3px solid var(--color-bearish)',
              cursor: 'pointer',
              background: activeTab === 'SELL' ? 'var(--color-bearish-dim)' : undefined
            }}
            onClick={() => setActiveTab('SELL')}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
              <span style={{ fontSize: 12, color: 'var(--color-bearish)', fontWeight: 700, display: 'flex', alignItems: 'center', gap: 5 }}>
                <TrendingDown size={14} /> SELL / SHORT
              </span>
              <span className="badge badge-sell">{data.summary.sell_count} {data.summary.sell_count === 1 ? 'Stock' : 'Stocks'}</span>
            </div>
            <div className="mono" style={{ fontSize: 21, fontWeight: 700, color: 'var(--color-bearish)' }}>
              -{data.summary.avg_sell_drop_pct}% <span style={{ fontSize: 11.5, fontWeight: 400, color: 'var(--color-text-muted)' }}>Avg Drop</span>
            </div>
            <div style={{ fontSize: 11.5, color: 'var(--color-text-muted)', marginTop: 2 }}>
              Top <strong>{data.summary.top_sell_pick || '—'}</strong>
            </div>
          </div>

          <div
            className="card"
            style={{
              padding: '12px 14px',
              borderLeft: '3px solid var(--color-neutral)',
              cursor: 'pointer',
              background: activeTab === 'HOLD' ? 'var(--color-neutral-dim)' : undefined
            }}
            onClick={() => setActiveTab('HOLD')}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
              <span style={{ fontSize: 12, color: 'var(--color-neutral)', fontWeight: 700, display: 'flex', alignItems: 'center', gap: 5 }}>
                <Minus size={14} /> HOLD
              </span>
              <span className="badge badge-hold">{data.summary.hold_count} {data.summary.hold_count === 1 ? 'Stock' : 'Stocks'}</span>
            </div>
            <div style={{ fontSize: 18, fontWeight: 700, color: 'var(--color-neutral)', marginTop: 2 }}>
              Consolidation
            </div>
            <div style={{ fontSize: 11.5, color: 'var(--color-text-muted)', marginTop: 2 }}>
              Neutral trading range
            </div>
          </div>

          <div className="card" style={{ padding: '12px 14px' }}>
            <div style={{ fontSize: 12, color: 'var(--color-text-muted)', fontWeight: 700, marginBottom: 8, display: 'flex', justifyContent: 'space-between' }}>
              <span>BREADTH</span>
              <span className="mono">{data.summary.valid_results} / {data.summary.total_scanned}</span>
            </div>
            <div style={{ height: 8, background: 'var(--color-bg-secondary)', borderRadius: 4, overflow: 'hidden', display: 'flex', marginBottom: 10 }}>
              <div style={{ width: `${(data.summary.buy_count / (data.summary.valid_results || 1)) * 100}%`, background: 'var(--color-bullish)' }} />
              <div style={{ width: `${(data.summary.hold_count / (data.summary.valid_results || 1)) * 100}%`, background: 'var(--color-neutral)' }} />
              <div style={{ width: `${(data.summary.sell_count / (data.summary.valid_results || 1)) * 100}%`, background: 'var(--color-bearish)' }} />
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11.5, color: 'var(--color-text-secondary)' }}>
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                <span style={{ width: 7, height: 7, borderRadius: '50%', background: 'var(--color-bullish)' }} /> {data.summary.buy_count} Buy
              </span>
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                <span style={{ width: 7, height: 7, borderRadius: '50%', background: 'var(--color-neutral)' }} /> {data.summary.hold_count} Hold
              </span>
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                <span style={{ width: 7, height: 7, borderRadius: '50%', background: 'var(--color-bearish)' }} /> {data.summary.sell_count} Sell
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Tabs & View Controls */}
      <div className="card" style={{ marginBottom: 16, padding: '10px 14px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10 }}>
          <div className="mobile-scroll-tabs" style={{ display: 'flex', gap: 6, maxWidth: '100%' }}>
            <button
              onClick={() => setActiveTab('BUY')}
              className={`btn ${activeTab === 'BUY' ? 'btn-primary' : 'btn-ghost'} no-shrink`}
              style={{ fontSize: 12.5, padding: '6px 12px', whiteSpace: 'nowrap' }}
            >
              <TrendingUp size={14} /> BUY ({data?.summary?.buy_count ?? 0})
            </button>
            <button
              onClick={() => setActiveTab('SELL')}
              className={`btn ${activeTab === 'SELL' ? 'btn-primary' : 'btn-ghost'} no-shrink`}
              style={{ fontSize: 12.5, padding: '6px 12px', whiteSpace: 'nowrap' }}
            >
              <TrendingDown size={14} /> SELL ({data?.summary?.sell_count ?? 0})
            </button>
            <button
              onClick={() => setActiveTab('HOLD')}
              className={`btn ${activeTab === 'HOLD' ? 'btn-primary' : 'btn-ghost'} no-shrink`}
              style={{ fontSize: 12.5, padding: '6px 12px', whiteSpace: 'nowrap' }}
            >
              <Minus size={14} /> HOLD ({data?.summary?.hold_count ?? 0})
            </button>
            <button
              onClick={() => setActiveTab('ALL')}
              className={`btn ${activeTab === 'ALL' ? 'btn-primary' : 'btn-ghost'} no-shrink`}
              style={{ fontSize: 12.5, padding: '6px 12px', whiteSpace: 'nowrap' }}
            >
              <Layers size={14} /> All ({data?.summary?.valid_results ?? 0})
            </button>
          </div>

          <div className="mobile-w-100" style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <div style={{ position: 'relative', flex: '1 1 140px', minWidth: 0 }}>
              <Search size={14} style={{ position: 'absolute', left: 10, top: 10, color: 'var(--color-text-muted)' }} />
              <input
                type="text"
                placeholder="Search symbol..."
                className="input"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                style={{ paddingLeft: 30, height: 34, fontSize: 12.5, width: '100%' }}
              />
            </div>

            <select
              className="input"
              value={minScore}
              onChange={(e) => setMinScore(Number(e.target.value))}
              style={{ flex: '1 1 115px', minWidth: 0, height: 34, fontSize: 12.5, padding: '6px 10px' }}
            >
              <option value={0}>Score: All</option>
              <option value={50}>Score &gt; 50</option>
              <option value={60}>Score &gt; 60</option>
              <option value={70}>Score &gt; 70</option>
            </select>

            <div style={{ display: 'flex', background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border)', borderRadius: 6, padding: 2, flexShrink: 0 }}>
              <button
                onClick={() => setViewMode('cards')}
                className="btn btn-ghost"
                style={{ border: 'none', padding: '4px 8px', minHeight: 28, background: viewMode === 'cards' ? 'var(--color-bg-card-hover)' : 'transparent' }}
                title="Card View"
              >
                <LayoutGrid size={14} />
              </button>
              <button
                onClick={() => setViewMode('table')}
                className="btn btn-ghost"
                style={{ border: 'none', padding: '4px 8px', minHeight: 28, background: viewMode === 'table' ? 'var(--color-bg-card-hover)' : 'transparent' }}
                title="Table View"
              >
                <List size={14} />
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Loading State */}
      {loading && (
        <div style={{ textAlign: 'center', padding: '60px 20px' }}>
          <RefreshCw size={36} className="spin" style={{ color: 'var(--color-accent-blue)', marginBottom: 16 }} />
          <div style={{ fontSize: 18, fontWeight: 600 }}>Screening Market Stocks...</div>
          <p style={{ color: 'var(--color-text-muted)', fontSize: 14 }}>
            Evaluating Multi-Timeframe Technicals, Corporate Balance Sheets, and Real-Time Sentiment...
          </p>
        </div>
      )}

      {/* Empty State */}
      {!loading && displayedStocks.length === 0 && (
        <div className="card" style={{ textAlign: 'center', padding: '50px 20px' }}>
          <AlertCircle size={36} style={{ color: '#f59e0b', marginBottom: 12, margin: '0 auto' }} />
          <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 6 }}>No stocks match the current filter</div>
          <p style={{ color: 'var(--color-text-muted)', fontSize: 13, maxWidth: 450, margin: '0 auto 16px' }}>
            No stocks found in category <strong>{activeTab}</strong> for {sector} with current search or score thresholds.
          </p>
          <button onClick={() => { setSearchQuery(''); setMinScore(0); setActiveTab('ALL') }} className="btn btn-secondary">
            Reset Filters
          </button>
        </div>
      )}

      {/* CARDS VIEW */}
      {!loading && viewMode === 'cards' && displayedStocks.length > 0 && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(min(100%, 310px), 1fr))', gap: 14 }}>
          {displayedStocks.map((stock) => {
            const isBuy = stock.action === 'BUY'
            const isSell = stock.action === 'SELL'
            const isHold = stock.action === 'HOLD'
            const plan = stock.trade_plan
            const isExpanded = Boolean(expandedCards[stock.symbol])
            const ltpVal = plan ? (plan.current_price || plan.cmp || plan.entry_price) : 0
            const bestBuyVal = plan ? (plan.best_buy_price || plan.optimal_entry_price || plan.entry_price) : 0

            return (
              <div
                key={stock.symbol}
                className="card"
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  borderTop: `3px solid ${isBuy ? 'var(--color-bullish)' : isSell ? 'var(--color-bearish)' : 'var(--color-neutral)'}`,
                  padding: '14px',
                  width: '100%',
                  boxSizing: 'border-box'
                }}
              >
                {/* Header */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 10, gap: 8 }}>
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                      <span
                        onClick={() => navigate('/chart', { state: { symbol: stock.symbol } })}
                        style={{ fontSize: 16, fontWeight: 700, color: 'var(--color-text-primary)', cursor: 'pointer' }}
                      >
                        {stock.symbol.replace('.NS', '')}
                      </span>
                      <span className={`badge ${isBuy ? 'badge-buy' : isSell ? 'badge-sell' : 'badge-hold'}`} style={{ fontSize: 11, padding: '2px 8px' }}>
                        {stock.action}
                      </span>
                      {stock.cap_segment && (
                        <span style={{ fontSize: 10, background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border)', color: 'var(--color-text-muted)', padding: '1px 6px', borderRadius: 4, fontWeight: 600 }}>
                          {stock.cap_segment.replace('_', ' ')}
                        </span>
                      )}
                      {stock.market_defense_active && (
                        <span style={{ fontSize: 10, background: 'var(--color-bearish-dim)', color: 'var(--color-bearish)', padding: '1px 6px', borderRadius: 4, fontWeight: 700 }}>
                          DEFENSIVE
                        </span>
                      )}
                    </div>
                    <div style={{ fontSize: 11.5, color: 'var(--color-text-muted)', marginTop: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {stock.name}
                    </div>
                  </div>

                  <div style={{ textAlign: 'right', flexShrink: 0 }}>
                    <div className="mono" style={{ fontSize: 17, fontWeight: 700, color: isBuy ? 'var(--color-bullish)' : isSell ? 'var(--color-bearish)' : 'var(--color-neutral)' }}>
                      {stock.total_score.toFixed(1)}
                    </div>
                    <div style={{ fontSize: 10, color: 'var(--color-text-muted)' }}>Score</div>
                  </div>
                </div>

                {/* Compact Factor Breakdown */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '5px 8px', background: 'var(--color-bg-secondary)', borderRadius: 6, marginBottom: 10, fontSize: 11, color: 'var(--color-text-muted)' }}>
                  <span>Tech <strong className="mono" style={{ color: 'var(--color-text-primary)' }}>{stock.scores.technical.toFixed(0)}</strong></span>
                  <span>Fund <strong className="mono" style={{ color: 'var(--color-text-primary)' }}>{stock.scores.fundamental.toFixed(0)}</strong></span>
                  <span>Sent <strong className="mono" style={{ color: 'var(--color-text-primary)' }}>{stock.scores.sentiment.toFixed(0)}</strong></span>
                  {stock.is_fast_growth && <span style={{ color: '#eab308', fontWeight: 700 }}>Momentum</span>}
                </div>

                {/* Trade Setup Metrics */}
                {plan ? (
                  <div style={{ background: 'var(--color-bg-secondary)', borderRadius: 8, padding: '10px', marginBottom: 12 }}>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 6, marginBottom: 8 }}>
                      <div style={{ minWidth: 0 }}>
                        <div style={{ fontSize: 10, color: 'var(--color-text-muted)' }}>Best Entry</div>
                        <div className="mono" style={{ fontSize: 13.5, fontWeight: 700, color: 'var(--color-accent-blue)' }}>
                          ₹{bestBuyVal.toFixed(2)}
                        </div>
                        <div className="mono" style={{ fontSize: 10, color: 'var(--color-text-muted)' }}>
                          LTP ₹{ltpVal.toFixed(2)}
                        </div>
                      </div>
                      <div style={{ minWidth: 0 }}>
                        <div style={{ fontSize: 10, color: 'var(--color-text-muted)' }}>
                          {isHold ? 'Resistance' : 'Target'}
                        </div>
                        <div className="mono" style={{ fontSize: 13.5, fontWeight: 700, color: isSell ? 'var(--color-bearish)' : isHold ? 'var(--color-text-primary)' : 'var(--color-bullish)' }}>
                          ₹{plan.target_price.toFixed(2)}
                        </div>
                        <div className="mono" style={{ fontSize: 10, fontWeight: 600, color: isSell ? 'var(--color-bearish)' : 'var(--color-bullish)' }}>
                          {isSell ? '-' : '+'}{plan.expected_gain_pct.toFixed(1)}%
                        </div>
                      </div>
                      <div style={{ minWidth: 0 }}>
                        <div style={{ fontSize: 10, color: 'var(--color-text-muted)' }}>
                          {isHold ? 'Support' : 'Stop Loss'}
                        </div>
                        <div className="mono" style={{ fontSize: 13.5, fontWeight: 700, color: isHold ? 'var(--color-text-primary)' : 'var(--color-bearish)' }}>
                          ₹{plan.stop_loss.toFixed(2)}
                        </div>
                        <div className="mono" style={{ fontSize: 10, fontWeight: 600, color: 'var(--color-bearish)' }}>
                          -{plan.risk_pct.toFixed(1)}%
                        </div>
                      </div>
                    </div>

                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 6, fontSize: 11, color: 'var(--color-text-secondary)', borderTop: '1px solid var(--color-border)', paddingTop: 7 }}>
                      <span>R:R <strong className="mono" style={{ color: plan.reward_to_risk >= 2 ? 'var(--color-bullish)' : 'inherit' }}>{plan.reward_to_risk}:1</strong></span>
                      <span>Hold <strong>{plan.estimated_hold_time}</strong></span>
                      <button
                        type="button"
                        onClick={() => setExpandedCards(prev => ({ ...prev, [stock.symbol]: !prev[stock.symbol] }))}
                        style={{ background: 'none', border: 'none', color: 'var(--color-accent-blue)', fontSize: 11, fontWeight: 600, cursor: 'pointer', padding: 0 }}
                      >
                        {isExpanded ? 'Hide Notes ▴' : 'Setup Notes ▾'}
                      </button>
                    </div>

                    {/* Staged Targets */}
                    {plan.targets && plan.targets.length > 0 && !isHold && (
                      <div style={{ marginTop: 7, paddingTop: 7, borderTop: '1px solid var(--color-border)', display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 6, fontSize: 10.5, color: 'var(--color-text-muted)' }}>
                        {plan.targets.map((tgt, i) => (
                          <span key={i} className="mono">
                            T{i+1}: <strong style={{ color: 'var(--color-text-primary)' }}>₹{tgt.price}</strong> (+{tgt.gain_pct}%)
                          </span>
                        ))}
                      </div>
                    )}

                    {/* Expandable Strategy Advice */}
                    {isExpanded && (plan.entry_zone || plan.entry_advice) && (
                      <div style={{ marginTop: 8, paddingTop: 8, borderTop: '1px solid var(--color-border)', fontSize: 11, color: 'var(--color-text-muted)', lineHeight: 1.4 }}>
                        {plan.entry_zone && <div><strong style={{ color: 'var(--color-text-secondary)' }}>Zone:</strong> {plan.entry_zone}</div>}
                        {plan.entry_advice && <div style={{ marginTop: 2 }}>{plan.entry_advice}</div>}
                      </div>
                    )}
                  </div>
                ) : (
                  <div style={{ padding: 10, background: 'var(--color-bg-secondary)', borderRadius: 8, marginBottom: 12, fontSize: 12, color: 'var(--color-text-muted)' }}>
                    Insufficient price history for setup calculation.
                  </div>
                )}

                {/* Bottom Actions */}
                <div style={{ marginTop: 'auto', display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                  <button
                    onClick={() => navigate('/chart', { state: { symbol: stock.symbol } })}
                    className="btn btn-ghost"
                    style={{ flex: '1 1 68px', fontSize: 12, padding: '6px 8px', minHeight: 34 }}
                  >
                    <ExternalLink size={13} /> Chart
                  </button>

                  {plan && !isHold && (
                    <>
                      <button
                        onClick={() => handleOpenGttModal(stock)}
                        className="btn btn-secondary"
                        style={{ flex: '1 1 64px', fontSize: 12, padding: '6px 8px', minHeight: 34, borderColor: 'rgba(59, 130, 246, 0.35)', color: 'var(--color-accent-blue)' }}
                      >
                        <Target size={13} /> GTT
                      </button>
                      <button
                        onClick={() => handleOpenOrderModal(stock)}
                        className={`btn ${isBuy ? 'btn-primary' : 'btn-danger'}`}
                        style={{ flex: '1.3 1 80px', fontSize: 12, padding: '6px 10px', minHeight: 34 }}
                      >
                        <Briefcase size={13} /> {stock.action}
                      </button>
                    </>
                  )}

                  {plan && (
                    <button
                      onClick={() => handleQuickAlert(stock)}
                      className="btn btn-ghost"
                      style={{ padding: '6px 9px', minHeight: 34, flex: '0 0 auto' }}
                      title="Create target alert"
                    >
                      <Bell size={13} />
                    </button>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* TABLE MATRIX VIEW */}
      {!loading && viewMode === 'table' && displayedStocks.length > 0 && (
        <div className="card table-container" style={{ padding: 0 }}>
          <table className="table" style={{ width: '100%', minWidth: 880, fontSize: 13 }}>
            <thead>
              <tr>
                <th>Stock</th>
                <th>Signal</th>
                <th>Score</th>
                <th>LTP</th>
                <th>Best Entry</th>
                <th>Target</th>
                <th>Stop Loss</th>
                <th>R:R</th>
                <th>Hold</th>
                <th>T / F / S</th>
                <th style={{ textAlign: 'right' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {displayedStocks.map((stock) => {
                const isBuy = stock.action === 'BUY'
                const isSell = stock.action === 'SELL'
                const plan = stock.trade_plan

                return (
                  <tr key={stock.symbol} style={{ borderBottom: '1px solid var(--color-border)' }}>
                    <td style={{ padding: '12px 16px' }}>
                      <span 
                        onClick={() => navigate('/chart', { state: { symbol: stock.symbol } })} 
                        style={{ fontWeight: 600, color: 'var(--color-text-primary)', cursor: 'pointer' }}
                        title="Open interactive chart"
                      >
                        {stock.symbol.replace('.NS', '')}
                      </span>
                      <div style={{ fontSize: 11, color: 'var(--color-text-muted)' }}>{stock.name}</div>
                    </td>
                    <td style={{ padding: '12px 16px' }}>
                      <span className={`badge ${isBuy ? 'badge-buy' : isSell ? 'badge-sell' : 'badge-hold'}`}>
                        {stock.action}
                      </span>
                    </td>
                    <td style={{ padding: '12px 16px', fontWeight: 600, color: isBuy ? 'var(--color-bullish)' : isSell ? 'var(--color-bearish)' : '#f59e0b' }}>
                      {stock.total_score.toFixed(1)}
                    </td>
                    <td style={{ padding: '12px 16px', fontWeight: 500 }}>
                      ₹{plan ? (plan.current_price || plan.cmp || plan.entry_price).toFixed(2) : '—'}
                    </td>
                    <td style={{ padding: '12px 16px' }}>
                      {plan ? (
                        <div>
                          <div style={{ fontWeight: 600, color: '#38bdf8' }}>
                            ₹{(plan.best_buy_price || plan.optimal_entry_price || plan.entry_price).toFixed(2)}
                          </div>
                          <div style={{ fontSize: 10, color: 'var(--color-text-muted)' }}>
                            {plan.entry_type === 'PULLBACK_DIP_BUY' || plan.entry_type === 'PULLBACK_DIP' ? 'Dip to 21-EMA' :
                             plan.entry_type === 'BREAKOUT_CONFIRMATION' || plan.entry_type === 'BREAKOUT' ? 'Breakout' :
                             plan.entry_type === 'RALLY_SELL' ? 'Rally Short' :
                             plan.entry_type === 'BREAKDOWN' ? 'Breakdown' : 'Support Base'}
                          </div>
                        </div>
                      ) : (
                        '—'
                      )}
                    </td>
                    <td style={{ padding: '12px 16px', color: isSell ? 'var(--color-bearish)' : (isBuy ? 'var(--color-bullish)' : 'inherit'), fontWeight: 500 }}>
                      {plan ? (
                        <div>
                          <div style={{ fontWeight: 600 }}>₹{plan.target_price.toFixed(2)}</div>
                          <div style={{ fontSize: 10, color: isSell ? 'var(--color-bearish)' : (isBuy ? 'var(--color-bullish)' : 'var(--color-text-muted)') }}>
                            {isSell ? '-' : '+'}{plan.expected_gain_pct.toFixed(1)}% from Best Buy
                          </div>
                          {plan.cmp_gain_pct !== undefined && Math.abs((plan.best_buy_price || plan.entry_price) - (plan.current_price || plan.cmp || 0)) > 0.05 && (
                            <div style={{ fontSize: 9, color: 'var(--color-text-muted)' }}>
                              ({plan.cmp_gain_pct >= 0 ? '+' : ''}{plan.cmp_gain_pct.toFixed(1)}% from CMP)
                            </div>
                          )}
                        </div>
                      ) : (
                        '—'
                      )}
                    </td>
                    <td style={{ padding: '12px 16px', color: isBuy ? 'var(--color-bearish)' : 'inherit', fontWeight: 500 }}>
                      {plan ? `₹${plan.stop_loss.toFixed(2)} (-${plan.risk_pct.toFixed(1)}%)` : '—'}
                    </td>
                    <td style={{ padding: '12px 16px', fontWeight: 600 }}>
                      {plan ? `${plan.reward_to_risk}:1` : '—'}
                    </td>
                    <td style={{ padding: '12px 16px', color: 'var(--color-text-secondary)' }}>
                      {plan ? plan.estimated_hold_time : '—'}
                    </td>
                    <td style={{ padding: '12px 16px', fontSize: 12, color: 'var(--color-text-muted)' }}>
                      {stock.scores.technical.toFixed(0)} / {stock.scores.fundamental.toFixed(0)} / {stock.scores.sentiment.toFixed(0)}
                    </td>
                    <td style={{ padding: '12px 16px', textAlign: 'right' }}>
                      <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
                        <button 
                          onClick={() => navigate('/chart', { state: { symbol: stock.symbol } })} 
                          className="btn btn-ghost" 
                          style={{ padding: '4px 8px', height: 28, cursor: 'pointer' }} 
                          title="Chart"
                        >
                          <ExternalLink size={13} />
                        </button>
                        {plan && stock.action !== 'HOLD' && (
                          <>
                            <button 
                              onClick={() => handleOpenGttModal(stock)}
                              className="btn btn-secondary"
                              style={{ padding: '4px 8px', height: 28, fontSize: 11, borderColor: 'rgba(56, 189, 248, 0.4)', color: '#38bdf8' }}
                              title="Set automated Zerodha GTT (Good-Till-Triggered) Trigger Order"
                            >
                              GTT
                            </button>
                            <button 
                              onClick={() => handleOpenOrderModal(stock)}
                              className={`btn ${isBuy ? 'btn-primary' : 'btn-secondary'}`}
                              style={{ padding: '4px 10px', height: 28, fontSize: 11 }}
                              title="Open Zerodha Kite-style order execution window"
                            >
                              Trade
                            </button>
                          </>
                        )}
                        {plan && (
                          <button 
                            onClick={() => handleQuickAlert(stock)}
                            className="btn btn-ghost" 
                            style={{ padding: '4px 8px', height: 28 }}
                            title="Set Target Alert"
                          >
                            <Bell size={13} />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* 11-Day Swing Audit Archives Modal */}
      {showArchiveModal && (
        <div 
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0, 0, 0, 0.75)',
            backdropFilter: 'blur(4px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 9999,
            padding: 16
          }}
          onClick={() => setShowArchiveModal(false)}
        >
          <div 
            style={{
              background: '#0f172a',
              border: '1px solid rgba(148, 163, 184, 0.2)',
              borderRadius: 12,
              width: '100%',
              maxWidth: 780,
              maxHeight: '85vh',
              display: 'flex',
              flexDirection: 'column',
              boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.5)',
              overflow: 'hidden'
            }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div style={{
              padding: '16px 20px',
              borderBottom: '1px solid rgba(148, 163, 184, 0.1)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              background: 'rgba(30, 41, 59, 0.5)'
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <FileSpreadsheet size={20} style={{ color: '#38bdf8' }} />
                <div>
                  <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: '#f8fafc' }}>
                    11-Day Swing Trade Audit Workbooks & Archives
                  </h3>
                  <p style={{ margin: 0, fontSize: 12, color: '#94a3b8' }}>
                    Download current & historical Excel reports with full price ledgers and P&L journals
                  </p>
                </div>
              </div>
              <button 
                onClick={() => setShowArchiveModal(false)}
                className="btn btn-ghost"
                style={{ padding: 6, borderRadius: 6, color: '#94a3b8' }}
              >
                <X size={18} />
              </button>
            </div>

            {/* Modal Actions */}
            <div style={{
              padding: '12px 20px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              background: 'rgba(15, 23, 42, 0.8)',
              borderBottom: '1px solid rgba(148, 163, 184, 0.1)',
              flexWrap: 'wrap',
              gap: 10
            }}>
              <button 
                onClick={handleDownloadLatestExcel} 
                disabled={downloadingExcel}
                className="btn btn-primary"
                style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, height: 34 }}
              >
                <Download size={14} className={downloadingExcel ? 'spin' : ''} />
                <span>{downloadingExcel ? 'Downloading...' : 'Download Current Active Cycle (.xlsx)'}</span>
              </button>
              <button 
                onClick={fetchArchiveFiles} 
                disabled={loadingArchives}
                className="btn btn-secondary"
                style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, height: 34 }}
              >
                <RefreshCw size={13} className={loadingArchives ? 'spin' : ''} />
                <span>Refresh List</span>
              </button>
            </div>

            {/* Modal Body */}
            <div style={{ padding: 20, overflowY: 'auto', flex: 1 }}>
              {loadingArchives ? (
                <div style={{ padding: 40, textAlign: 'center', color: '#94a3b8' }}>
                  <RefreshCw size={24} className="spin" style={{ margin: '0 auto 12px' }} />
                  <div>Loading audit archive workbooks...</div>
                </div>
              ) : archiveFiles.length === 0 ? (
                <div style={{ padding: 40, textAlign: 'center', color: '#94a3b8' }}>
                  <FileSpreadsheet size={32} style={{ margin: '0 auto 12px', opacity: 0.5 }} />
                  <div>No archived audit files found. Click "Sync 11-Day Prices" to generate the first workbook!</div>
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                  {archiveFiles.map((file, idx) => (
                    <div 
                      key={idx}
                      style={{
                        padding: '14px 16px',
                        background: 'rgba(30, 41, 59, 0.6)',
                        border: '1px solid rgba(148, 163, 184, 0.15)',
                        borderRadius: 8,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        gap: 16,
                        flexWrap: 'wrap'
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flex: '1 1 300px' }}>
                        <div style={{
                          width: 36,
                          height: 36,
                          borderRadius: 8,
                          background: file.status === 'ACTIVE' ? 'rgba(52, 211, 153, 0.15)' : 'rgba(56, 189, 248, 0.15)',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          color: file.status === 'ACTIVE' ? '#34d399' : '#38bdf8'
                        }}>
                          <FileSpreadsheet size={18} />
                        </div>
                        <div>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                            <span style={{ fontWeight: 700, fontSize: 14, color: '#f8fafc' }}>
                              Cycle #{file.cycle_number > 0 ? file.cycle_number : 'Archive'}
                            </span>
                            <span style={{
                              fontSize: 10,
                              padding: '2px 8px',
                              borderRadius: 4,
                              fontWeight: 600,
                              textTransform: 'uppercase',
                              background: file.status === 'ACTIVE' ? 'rgba(52, 211, 153, 0.2)' : 'rgba(148, 163, 184, 0.2)',
                              color: file.status === 'ACTIVE' ? '#34d399' : '#94a3b8'
                            }}>
                              {file.status}
                            </span>
                            <span style={{ fontSize: 12, color: '#94a3b8' }}>
                              {file.from_date} to {file.to_date}
                            </span>
                          </div>
                          <div style={{ fontSize: 12, color: '#64748b', marginTop: 4, display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                            <span>Trades: <strong style={{ color: '#e2e8f0' }}>{file.total_trades}</strong></span>
                            <span>Win Rate: <strong style={{ color: file.win_rate >= 50 ? '#34d399' : '#f87171' }}>{file.win_rate}%</strong></span>
                            <span>Return: <strong style={{ color: file.total_gain_loss_pct >= 0 ? '#34d399' : '#f87171' }}>{file.total_gain_loss_pct > 0 ? `+${file.total_gain_loss_pct}` : file.total_gain_loss_pct}%</strong></span>
                            <span>Realized P&L: <strong style={{ color: file.total_pnl_rupees >= 0 ? '#34d399' : '#f87171' }}>₹{file.total_pnl_rupees.toLocaleString('en-IN')}</strong></span>
                          </div>
                        </div>
                      </div>

                      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <span style={{ fontSize: 11, color: '#64748b' }}>
                          {file.size_bytes ? `${(file.size_bytes / 1024).toFixed(1)} KB` : ''}
                        </span>
                        <button 
                          onClick={() => handleDownloadArchiveExcel(file.filename)} 
                          className="btn btn-secondary"
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: 6,
                            height: 32,
                            fontSize: 12,
                            color: '#38bdf8',
                            borderColor: 'rgba(56, 189, 248, 0.3)',
                            background: 'rgba(56, 189, 248, 0.08)',
                            cursor: 'pointer'
                          }}
                        >
                          <Download size={13} />
                          <span>Download .xlsx</span>
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
      {orderModalStock && (
        <ZerodhaOrderModal
          isOpen={orderModalOpen}
          onClose={() => setOrderModalOpen(false)}
          symbol={orderModalStock.symbol}
          name={orderModalStock.name}
          currentPrice={orderModalStock.trade_plan?.current_price || orderModalStock.trade_plan?.cmp || orderModalStock.trade_plan?.entry_price || 100}
          bestBuyPrice={orderModalStock.trade_plan?.best_buy_price || orderModalStock.trade_plan?.optimal_entry_price}
          targetPrice={orderModalStock.trade_plan?.target_price}
          target1={orderModalStock.trade_plan?.target_1}
          target2={orderModalStock.trade_plan?.target_2 || orderModalStock.trade_plan?.target_price}
          target3={orderModalStock.trade_plan?.target_3}
          stopLoss={orderModalStock.trade_plan?.stop_loss}
          defaultDirection={orderModalStock.action === 'SELL' ? 'SELL' : 'BUY'}
          isGttMode={isGttMode}
          onOrderSuccess={async (tradeData) => {
            if (String(tradeData?.direction || orderModalStock.action).toUpperCase() === 'BUY') {
              try {
                await swingAuditApi.track({
                  symbol: orderModalStock.symbol,
                  buy_price: Number(orderModalStock.trade_plan?.best_buy_price || orderModalStock.trade_plan?.current_price || tradeData?.entry_price || 0),
                  target_price: Number(orderModalStock.trade_plan?.target_price || 0),
                  stop_loss: Number(orderModalStock.trade_plan?.stop_loss || 0),
                  target_1: orderModalStock.trade_plan?.target_1,
                  target_2: orderModalStock.trade_plan?.target_2,
                  target_3: orderModalStock.trade_plan?.target_3,
                  reward_to_risk: orderModalStock.trade_plan?.reward_to_risk,
                  total_score: orderModalStock.total_score,
                  company_name: orderModalStock.name,
                  user_bought: true,
                  user_buy_price: Number(tradeData?.entry_price || orderModalStock.trade_plan?.current_price || 0),
                  notes: 'Executed via Swing Screener Coupled Ratchet modal',
                })
                const cycleRes = await swingAuditApi.getCurrentCycle()
                if (cycleRes.data?.cycle) setCycleData(cycleRes.data.cycle)
              } catch {
                // Non-blocking audit sync
              }
            }
          }}
        />
      )}
    </div>
  )
}
