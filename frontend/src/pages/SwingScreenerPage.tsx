import { useEffect, useState, useMemo } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { marketApi, paperTradingApi, alertsApi } from '../services/api'
import { 
  TrendingUp, TrendingDown, Minus, RefreshCw, Search, Filter, 
  ExternalLink, Briefcase, Bell, CheckCircle2, ShieldAlert, 
  ArrowUpRight, ArrowDownRight, Layers, LayoutGrid, List, Sparkles, AlertCircle, Target
} from 'lucide-react'
import { toast } from '../components/Toast'

interface TargetLevel {
  level: string
  price: number
  gain_pct: number
  reward_to_risk: number
}

interface TradePlan {
  entry_price: number
  current_price?: number
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
  const [sector, setSector] = useState('NIFTY_50')
  const [activeTab, setActiveTab] = useState<'BUY' | 'SELL' | 'HOLD' | 'ALL'>('BUY')
  const [viewMode, setViewMode] = useState<'cards' | 'table'>('cards')
  const [searchQuery, setSearchQuery] = useState('')
  const [minScore, setMinScore] = useState<number>(0)
  
  const [data, setData] = useState<ScreenerResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [tradingSymbol, setTradingSymbol] = useState<string | null>(null)

  const fetchScreener = async (forceRefresh = false) => {
    if (forceRefresh) setRefreshing(true)
    else setLoading(true)

    try {
      const res = await marketApi.getScreener(sector, forceRefresh)
      setData(res.data)
      if (forceRefresh) toast.success('Market scan updated successfully')
    } catch (err: any) {
      console.error('Failed to fetch screener:', err)
      toast.error('Failed to load swing trade screener', err?.message || 'Network error')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }

  useEffect(() => {
    fetchScreener(false)
  }, [sector])

  // Quick Paper Trade action directly from screener
  const handleQuickTrade = async (stock: SwingStock) => {
    if (!stock.trade_plan) return
    setTradingSymbol(stock.symbol)
    try {
      const direction = stock.action === 'SELL' ? 'SELL' : 'BUY'
      const productType = direction === 'SELL' ? 'INTRADAY' : 'DELIVERY'
      await paperTradingApi.place({
        symbol: stock.symbol,
        direction: direction,
        quantity: 10,
        order_type: 'MARKET',
        product_type: productType,
        target_price: stock.trade_plan.target_price,
        stop_loss: stock.trade_plan.stop_loss
      })
      toast.success(
        `Order Placed: ${direction} 10x ${stock.symbol}`,
        `Target: ₹${stock.trade_plan.target_price} | SL: ₹${stock.trade_plan.stop_loss}`
      )
    } catch (err: any) {
      console.error('Quick trade failed:', err)
      toast.error('Paper trade failed', err?.response?.data?.detail || err.message)
    } finally {
      setTradingSymbol(null)
    }
  }

  // Quick Alert action
  const handleQuickAlert = async (stock: SwingStock) => {
    if (!stock.trade_plan) return
    try {
      await alertsApi.create({
        symbol: stock.symbol,
        condition_type: stock.action === 'SELL' ? 'PRICE_BELOW' : 'PRICE_ABOVE',
        condition_value: stock.trade_plan.target_price,
        priority: 'MEDIUM',
        delivery_method: 'IN_APP',
        message: `Swing Trade Target Alert for ${stock.symbol} at ₹${stock.trade_plan.target_price}`
      })
      toast.success(`Alert Set for ${stock.symbol}`, `Trigger at ₹${stock.trade_plan.target_price}`)
    } catch (err: any) {
      toast.error('Failed to set alert', err?.response?.data?.detail || err.message)
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
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 16 }}>
        <div style={{ flex: '1 1 300px', minWidth: 0 }}>
          <h1 className="page-title" style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
            <Sparkles size={24} style={{ color: 'var(--color-accent-blue)', flexShrink: 0 }} />
            AI Swing Trade Screener
          </h1>
          <p className="page-subtitle">
            Systematic multi-factor market scanner categorizing liquid stocks into high-conviction <strong>BUY</strong>, <strong>SELL</strong>, and <strong>HOLD</strong> setups with exact profit targets and risk bounds.
          </p>
        </div>

        <div className="mobile-w-100" style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          <select 
            className="input" 
            value={sector} 
            onChange={(e) => setSector(e.target.value)}
            style={{ flex: '1 1 180px', minWidth: 160, height: 38, fontWeight: 500 }}
          >
            {SECTOR_OPTIONS.map(opt => (
              <option key={opt.id} value={opt.id}>{opt.label}</option>
            ))}
          </select>

          <button 
            onClick={() => fetchScreener(true)} 
            disabled={refreshing || loading}
            className="btn btn-secondary no-shrink"
            style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, height: 38, whiteSpace: 'nowrap', flex: '0 0 auto' }}
            title="Scan entire market now"
          >
            <RefreshCw size={15} className={refreshing ? 'spin' : ''} />
            <span>{refreshing ? 'Scanning...' : 'Run Fresh Scan'}</span>
          </button>
        </div>
      </div>

      {/* Institutional Summary Cards */}
      {data && data.summary && (
        <div className="responsive-grid-summary" style={{ marginBottom: 20 }}>
          {/* BUY Card */}
          <div 
            className="card" 
            style={{ 
              borderLeft: '4px solid var(--color-bullish)', 
              cursor: 'pointer',
              background: activeTab === 'BUY' ? 'rgba(16, 185, 129, 0.08)' : undefined
            }}
            onClick={() => setActiveTab('BUY')}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
              <span style={{ fontSize: 13, color: 'var(--color-bullish)', fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6 }}>
                <TrendingUp size={16} /> BUY SETUPS
              </span>
              <span className="badge badge-buy" style={{ fontSize: 13 }}>{data.summary.buy_count} Stocks</span>
            </div>
            <div style={{ fontSize: 26, fontWeight: 700, color: 'var(--color-bullish)', marginBottom: 4 }}>
              +{data.summary.avg_buy_gain_pct}% <span style={{ fontSize: 12, fontWeight: 400, color: 'var(--color-text-muted)' }}>Avg Target Gain</span>
            </div>
            <div style={{ fontSize: 12, color: 'var(--color-text-secondary)' }}>
              Avg Reward-to-Risk: <strong>{data.summary.avg_buy_rr}:1</strong> · Top Pick: <strong>{data.summary.top_buy_pick || 'None'}</strong>
            </div>
          </div>

          {/* SELL Card */}
          <div 
            className="card" 
            style={{ 
              borderLeft: '4px solid var(--color-bearish)', 
              cursor: 'pointer',
              background: activeTab === 'SELL' ? 'rgba(239, 68, 68, 0.08)' : undefined
            }}
            onClick={() => setActiveTab('SELL')}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
              <span style={{ fontSize: 13, color: 'var(--color-bearish)', fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6 }}>
                <TrendingDown size={16} /> SELL / SHORT SETUPS
              </span>
              <span className="badge badge-sell" style={{ fontSize: 13 }}>{data.summary.sell_count} Stocks</span>
            </div>
            <div style={{ fontSize: 26, fontWeight: 700, color: 'var(--color-bearish)', marginBottom: 4 }}>
              -{data.summary.avg_sell_drop_pct}% <span style={{ fontSize: 12, fontWeight: 400, color: 'var(--color-text-muted)' }}>Avg Expected Drop</span>
            </div>
            <div style={{ fontSize: 12, color: 'var(--color-text-secondary)' }}>
              Bearish Breakdown / Exit Setups · Top Pick: <strong>{data.summary.top_sell_pick || 'None'}</strong>
            </div>
          </div>

          {/* HOLD Card */}
          <div 
            className="card" 
            style={{ 
              borderLeft: '4px solid #f59e0b', 
              cursor: 'pointer',
              background: activeTab === 'HOLD' ? 'rgba(245, 158, 11, 0.08)' : undefined
            }}
            onClick={() => setActiveTab('HOLD')}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
              <span style={{ fontSize: 13, color: '#f59e0b', fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6 }}>
                <Minus size={16} /> RANGE-BOUND / HOLD
              </span>
              <span className="badge badge-hold" style={{ fontSize: 13 }}>{data.summary.hold_count} Stocks</span>
            </div>
            <div style={{ fontSize: 26, fontWeight: 700, color: '#f59e0b', marginBottom: 4 }}>
              Consolidation <span style={{ fontSize: 12, fontWeight: 400, color: 'var(--color-text-muted)' }}>Neutral Channel</span>
            </div>
            <div style={{ fontSize: 12, color: 'var(--color-text-secondary)' }}>
              Equilibrium trading channel (±ATR). Watch for channel breakouts.
            </div>
          </div>

          {/* Breadth Card */}
          <div className="card">
            <div style={{ fontSize: 13, color: 'var(--color-text-muted)', fontWeight: 600, marginBottom: 8, display: 'flex', justifyContent: 'space-between' }}>
              <span>MARKET BREADTH</span>
              <span>{data.summary.valid_results} / {data.summary.total_scanned} Active</span>
            </div>
            <div style={{ height: 10, background: 'rgba(255,255,255,0.06)', borderRadius: 5, overflow: 'hidden', display: 'flex', marginBottom: 12 }}>
              <div style={{ width: `${(data.summary.buy_count / (data.summary.valid_results || 1)) * 100}%`, background: 'var(--color-bullish)' }} title={`Buy: ${data.summary.buy_count}`} />
              <div style={{ width: `${(data.summary.hold_count / (data.summary.valid_results || 1)) * 100}%`, background: '#f59e0b' }} title={`Hold: ${data.summary.hold_count}`} />
              <div style={{ width: `${(data.summary.sell_count / (data.summary.valid_results || 1)) * 100}%`, background: 'var(--color-bearish)' }} title={`Sell: ${data.summary.sell_count}`} />
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: 'var(--color-text-secondary)' }}>
              <span>🟢 {data.summary.buy_count} Buy</span>
              <span>🟡 {data.summary.hold_count} Hold</span>
              <span>🔴 {data.summary.sell_count} Sell</span>
            </div>
          </div>
        </div>
      )}

      {/* Tabs & View Controls */}
      <div className="card" style={{ marginBottom: 20, padding: '12px 14px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
          {/* Main Action Tabs */}
          <div className="mobile-scroll-tabs" style={{ display: 'flex', gap: 8, maxWidth: '100%' }}>
            <button 
              onClick={() => setActiveTab('BUY')}
              className={`btn ${activeTab === 'BUY' ? 'btn-primary' : 'btn-ghost'} no-shrink`}
              style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, whiteSpace: 'nowrap' }}
            >
              <TrendingUp size={15} />
              BUY ({data?.summary?.buy_count ?? 0})
            </button>
            <button 
              onClick={() => setActiveTab('SELL')}
              className={`btn ${activeTab === 'SELL' ? 'btn-primary' : 'btn-ghost'} no-shrink`}
              style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, whiteSpace: 'nowrap' }}
            >
              <TrendingDown size={15} />
              SELL ({data?.summary?.sell_count ?? 0})
            </button>
            <button 
              onClick={() => setActiveTab('HOLD')}
              className={`btn ${activeTab === 'HOLD' ? 'btn-primary' : 'btn-ghost'} no-shrink`}
              style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, whiteSpace: 'nowrap' }}
            >
              <Minus size={15} />
              HOLD ({data?.summary?.hold_count ?? 0})
            </button>
            <button 
              onClick={() => setActiveTab('ALL')}
              className={`btn ${activeTab === 'ALL' ? 'btn-primary' : 'btn-ghost'} no-shrink`}
              style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, whiteSpace: 'nowrap' }}
            >
              <Layers size={15} />
              All ({data?.summary?.valid_results ?? 0})
            </button>
          </div>

          {/* Search, Filter & View Mode */}
          <div className="mobile-w-100" style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
            <div style={{ position: 'relative', flex: '1 1 150px', minWidth: 130 }}>
              <Search size={14} style={{ position: 'absolute', left: 10, top: 10, color: 'var(--color-text-muted)' }} />
              <input 
                type="text" 
                placeholder="Search symbol..." 
                className="input" 
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                style={{ paddingLeft: 30, height: 34, fontSize: 12, width: '100%' }}
              />
            </div>

            <select 
              className="input" 
              value={minScore} 
              onChange={(e) => setMinScore(Number(e.target.value))}
              style={{ flex: '1 1 120px', minWidth: 110, height: 34, fontSize: 12 }}
            >
              <option value={0}>Min Score: All</option>
              <option value={50}>Score &gt; 50</option>
              <option value={60}>Score &gt; 60 (High)</option>
              <option value={70}>Score &gt; 70 (Elite)</option>
            </select>

            <div style={{ display: 'flex', background: 'rgba(255,255,255,0.04)', borderRadius: 6, padding: 2, flexShrink: 0 }}>
              <button 
                onClick={() => setViewMode('cards')} 
                className="btn btn-ghost" 
                style={{ padding: '4px 8px', height: 30, background: viewMode === 'cards' ? 'rgba(255,255,255,0.1)' : 'transparent' }}
                title="Card View"
              >
                <LayoutGrid size={15} />
              </button>
              <button 
                onClick={() => setViewMode('table')} 
                className="btn btn-ghost" 
                style={{ padding: '4px 8px', height: 30, background: viewMode === 'table' ? 'rgba(255,255,255,0.1)' : 'transparent' }}
                title="Table Matrix View"
              >
                <List size={15} />
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
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(min(100%, 320px), 1fr))', gap: 16 }}>
          {displayedStocks.map((stock) => {
            const isBuy = stock.action === 'BUY'
            const isSell = stock.action === 'SELL'
            const isHold = stock.action === 'HOLD'
            const plan = stock.trade_plan

            return (
              <div 
                key={stock.symbol}
                className="card"
                style={{ 
                  display: 'flex', 
                  flexDirection: 'column', 
                  position: 'relative',
                  borderTop: `4px solid ${isBuy ? 'var(--color-bullish)' : isSell ? 'var(--color-bearish)' : '#f59e0b'}`,
                  transition: 'transform 0.15s ease, box-shadow 0.15s ease',
                  padding: '16px 14px',
                  width: '100%',
                  boxSizing: 'border-box'
                }}
              >
                {/* Header */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12, gap: 8 }}>
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                      <span 
                        onClick={() => navigate('/chart', { state: { symbol: stock.symbol } })}
                        style={{ fontSize: 17, fontWeight: 700, color: 'var(--color-text-primary)', cursor: 'pointer' }}
                        title="Open interactive chart"
                      >
                        {stock.symbol.replace('.NS', '')}
                      </span>
                      <span className={`badge ${isBuy ? 'badge-buy' : isSell ? 'badge-sell' : 'badge-hold'}`}>
                        {stock.action}
                      </span>
                    </div>
                    <div style={{ fontSize: 11, color: 'var(--color-text-muted)', marginTop: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {stock.name}
                    </div>
                  </div>

                  <div style={{ textAlign: 'right', flexShrink: 0 }}>
                    <div style={{ fontSize: 18, fontWeight: 700, color: isBuy ? 'var(--color-bullish)' : isSell ? 'var(--color-bearish)' : '#f59e0b', whiteSpace: 'nowrap' }}>
                      {stock.total_score.toFixed(1)} <span style={{ fontSize: 11, fontWeight: 400, color: 'var(--color-text-muted)' }}>/ 100</span>
                    </div>
                    <div style={{ fontSize: 10, color: 'var(--color-text-muted)', whiteSpace: 'nowrap' }}>Conviction Score</div>
                  </div>
                </div>

                {/* Score Breakdown Pills */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 6, marginBottom: 14 }}>
                  <div style={{ padding: '6px 4px', background: 'rgba(255,255,255,0.02)', borderRadius: 6, textAlign: 'center' }}>
                    <div style={{ fontSize: 10, color: 'var(--color-text-muted)' }}>Tech</div>
                    <div style={{ fontSize: 12, fontWeight: 600 }}>{stock.scores.technical.toFixed(1)}</div>
                  </div>
                  <div style={{ padding: '6px 4px', background: 'rgba(255,255,255,0.02)', borderRadius: 6, textAlign: 'center' }}>
                    <div style={{ fontSize: 10, color: 'var(--color-text-muted)' }}>Fund</div>
                    <div style={{ fontSize: 12, fontWeight: 600 }}>{stock.scores.fundamental.toFixed(1)}</div>
                  </div>
                  <div style={{ padding: '6px 4px', background: 'rgba(255,255,255,0.02)', borderRadius: 6, textAlign: 'center' }}>
                    <div style={{ fontSize: 10, color: 'var(--color-text-muted)' }}>Sentiment</div>
                    <div style={{ fontSize: 12, fontWeight: 600 }}>{stock.scores.sentiment.toFixed(1)}</div>
                  </div>
                </div>

                {/* Trade Setup Metrics */}
                {plan ? (
                  <div style={{ background: 'rgba(255,255,255,0.02)', borderRadius: 8, padding: '10px 12px', marginBottom: 14 }}>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 6, marginBottom: 8 }}>
                      <div>
                        <div style={{ fontSize: 10, color: 'var(--color-text-muted)', whiteSpace: 'nowrap' }}>
                          Current (CMP)
                        </div>
                        <div style={{ fontSize: 14, fontWeight: 600 }}>₹{plan.entry_price.toFixed(2)}</div>
                      </div>
                      <div>
                        <div style={{ fontSize: 10, color: 'var(--color-text-muted)', whiteSpace: 'nowrap' }}>
                          {isSell ? 'Target' : isHold ? 'Resistance' : 'Target'}
                        </div>
                        <div style={{ fontSize: 14, fontWeight: 600, color: isSell ? 'var(--color-bearish)' : (isHold ? 'var(--color-text-primary)' : 'var(--color-bullish)') }}>
                          ₹{plan.target_price.toFixed(2)}
                          <div style={{ fontSize: 10, fontWeight: 500 }}>({isSell ? '-' : '+'}{plan.expected_gain_pct.toFixed(1)}%)</div>
                        </div>
                      </div>
                      <div>
                        <div style={{ fontSize: 10, color: 'var(--color-text-muted)', whiteSpace: 'nowrap' }}>
                          {isHold ? 'Support' : 'Stop Loss'}
                        </div>
                        <div style={{ fontSize: 14, fontWeight: 600, color: isHold ? 'var(--color-text-primary)' : 'var(--color-bearish)' }}>
                          ₹{plan.stop_loss.toFixed(2)}
                          <div style={{ fontSize: 10, fontWeight: 500 }}>(-{plan.risk_pct.toFixed(1)}%)</div>
                        </div>
                      </div>
                    </div>

                    {/* AI Optimal Entry Strategy Box */}
                    {plan.optimal_entry_price && (
                      <div style={{ 
                        margin: '8px 0 10px 0', 
                        padding: '8px 10px', 
                        borderRadius: 6, 
                        background: isBuy 
                          ? 'rgba(16, 185, 129, 0.08)' 
                          : isSell 
                          ? 'rgba(239, 68, 68, 0.08)' 
                          : 'rgba(255, 255, 255, 0.03)',
                        border: `1px solid ${isBuy ? 'rgba(16, 185, 129, 0.25)' : isSell ? 'rgba(239, 68, 68, 0.25)' : 'rgba(255, 255, 255, 0.06)'}`
                      }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4, flexWrap: 'wrap', gap: 4 }}>
                          <span style={{ fontSize: 11, fontWeight: 700, color: isBuy ? 'var(--color-bullish)' : isSell ? 'var(--color-bearish)' : 'var(--color-text-primary)', display: 'flex', alignItems: 'center', gap: 4 }}>
                            <Target size={13} />
                            {plan.entry_type === 'PULLBACK_DIP' ? 'Best Dip Entry: ' : 
                             plan.entry_type === 'BREAKOUT' ? 'Breakout Entry: ' : 
                             plan.entry_type === 'RALLY_SELL' ? 'Best Short Rally: ' : 
                             plan.entry_type === 'BREAKDOWN' ? 'Breakdown Short: ' : 'Optimal Entry: '}
                            ₹{plan.optimal_entry_price.toFixed(2)}
                          </span>
                          {plan.optimal_expected_gain_pct !== undefined && !isHold && (
                            <span style={{ fontSize: 10, fontWeight: 700, color: 'var(--color-bullish)', background: 'rgba(16, 185, 129, 0.15)', padding: '1px 6px', borderRadius: 4 }}>
                              +{plan.optimal_expected_gain_pct.toFixed(1)}% Max Gain ({plan.optimal_reward_to_risk || plan.reward_to_risk}:1 R:R)
                            </span>
                          )}
                        </div>
                        {plan.entry_zone && (
                          <div style={{ fontSize: 10, color: 'var(--color-text-secondary)', marginBottom: 2 }}>
                            <strong style={{ color: 'var(--color-text-primary)' }}>Strategy Zone:</strong> {plan.entry_zone}
                          </div>
                        )}
                        {plan.entry_advice && (
                          <div style={{ fontSize: 10, color: 'var(--color-text-muted)', lineHeight: 1.35 }}>
                            💡 {plan.entry_advice}
                          </div>
                        )}
                      </div>
                    )}

                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 6, fontSize: 11, color: 'var(--color-text-secondary)', borderTop: '1px solid rgba(255,255,255,0.04)', paddingTop: 8 }}>
                      <span>R:R: <strong style={{ color: plan.reward_to_risk >= 2 ? 'var(--color-bullish)' : 'inherit' }}>{plan.reward_to_risk}:1</strong></span>
                      <span>Hold: <strong>{plan.estimated_hold_time}</strong></span>
                      <span>News: <strong>{stock.news_sentiment || 'NEUTRAL'}</strong></span>
                    </div>

                    {/* Staged Targets (if BUY or SELL) */}
                    {plan.targets && plan.targets.length > 0 && !isHold && (
                      <div style={{ marginTop: 8, paddingTop: 8, borderTop: '1px solid rgba(255,255,255,0.04)', display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 6, fontSize: 10, color: 'var(--color-text-muted)' }}>
                        {plan.targets.map((tgt, i) => (
                          <div key={i} style={{ whiteSpace: 'nowrap' }}>
                            <span>T{i+1}: <strong>₹{tgt.price}</strong> (+{tgt.gain_pct}%)</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ) : (
                  <div style={{ padding: 12, background: 'rgba(255,255,255,0.02)', borderRadius: 8, marginBottom: 14, fontSize: 12, color: 'var(--color-text-muted)' }}>
                    Trade setup calculation pending or insufficient candle depth.
                  </div>
                )}

                {/* Bottom Actions */}
                <div style={{ marginTop: 'auto', display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                  <button 
                    onClick={() => navigate('/chart', { state: { symbol: stock.symbol } })}
                    className="btn btn-ghost" 
                    style={{ flex: '1 1 70px', fontSize: 12, height: 32, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 4, padding: '0 8px' }}
                  >
                    <ExternalLink size={13} /> Chart
                  </button>

                  {plan && !isHold && (
                    <button 
                      onClick={() => handleQuickTrade(stock)}
                      disabled={tradingSymbol === stock.symbol}
                      className={`btn ${isBuy ? 'btn-primary' : 'btn-secondary'}`}
                      style={{ flex: '1.4 1 100px', fontSize: 12, height: 32, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 4, padding: '0 8px', whiteSpace: 'nowrap' }}
                    >
                      <Briefcase size={13} /> {tradingSymbol === stock.symbol ? 'Placing...' : `Paper ${stock.action}`}
                    </button>
                  )}

                  {plan && (
                    <button 
                      onClick={() => handleQuickAlert(stock)}
                      className="btn btn-ghost" 
                      style={{ padding: '0 10px', height: 32, flex: '0 0 auto' }}
                      title="Set alert at target level"
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
        <div className="card" style={{ padding: 0, overflowX: 'auto' }}>
          <table className="table" style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--color-border)', textAlign: 'left', background: 'rgba(255,255,255,0.02)' }}>
                <th style={{ padding: '12px 16px' }}>Stock</th>
                <th style={{ padding: '12px 16px' }}>Signal</th>
                <th style={{ padding: '12px 16px' }}>Score</th>
                <th style={{ padding: '12px 16px' }}>Current (CMP)</th>
                <th style={{ padding: '12px 16px' }}>Best Entry & Strategy</th>
                <th style={{ padding: '12px 16px' }}>Target (Gain)</th>
                <th style={{ padding: '12px 16px' }}>Stop Loss (Risk)</th>
                <th style={{ padding: '12px 16px' }}>R:R</th>
                <th style={{ padding: '12px 16px' }}>Duration</th>
                <th style={{ padding: '12px 16px' }}>Sub-Scores (T/F/S)</th>
                <th style={{ padding: '12px 16px', textAlign: 'right' }}>Actions</th>
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
                      ₹{plan ? plan.entry_price.toFixed(2) : '—'}
                    </td>
                    <td style={{ padding: '12px 16px' }}>
                      {plan?.optimal_entry_price ? (
                        <div>
                          <div style={{ fontWeight: 600, color: isBuy ? 'var(--color-bullish)' : isSell ? 'var(--color-bearish)' : 'inherit' }}>
                            ₹{plan.optimal_entry_price.toFixed(2)}
                          </div>
                          <div style={{ fontSize: 10, color: 'var(--color-text-muted)' }}>
                            {plan.entry_type === 'PULLBACK_DIP' ? 'Dip to 21-EMA' :
                             plan.entry_type === 'BREAKOUT' ? 'Breakout' :
                             plan.entry_type === 'RALLY_SELL' ? 'Rally Short' :
                             plan.entry_type === 'BREAKDOWN' ? 'Breakdown' : 'At CMP'}
                          </div>
                        </div>
                      ) : (
                        '—'
                      )}
                    </td>
                    <td style={{ padding: '12px 16px', color: isSell ? 'var(--color-bearish)' : (isBuy ? 'var(--color-bullish)' : 'inherit'), fontWeight: 500 }}>
                      {plan ? `₹${plan.target_price.toFixed(2)} (${isSell ? '-' : '+'}${plan.expected_gain_pct.toFixed(1)}%)` : '—'}
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
                          <button 
                            onClick={() => handleQuickTrade(stock)}
                            disabled={tradingSymbol === stock.symbol}
                            className={`btn ${isBuy ? 'btn-primary' : 'btn-secondary'}`}
                            style={{ padding: '4px 10px', height: 28, fontSize: 11 }}
                            title="Place paper trade"
                          >
                            Trade
                          </button>
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
    </div>
  )
}
