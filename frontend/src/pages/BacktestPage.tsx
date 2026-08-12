import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { backtestApi } from '../services/api'
import { FlaskConical, Play, TrendingUp, TrendingDown, Lock, History, BarChart3, Search } from 'lucide-react'
import StockSearchBox from '../components/StockSearchBox'
import { useAuth } from '../AuthContext'
import { useLocalStorage } from '../hooks/useLocalStorage'

const STRATEGIES = [
  { id: 'rsi_mean_reversion', name: 'RSI Mean Reversion', defaultParams: { rsi_buy: 30, rsi_sell: 70, quantity: 10 }, description: 'Buy when RSI < 30 (oversold), sell when RSI > 70 (overbought)' },
  { id: 'ema_crossover', name: 'EMA Crossover', defaultParams: { fast_ema: 9, slow_ema: 21, quantity: 10 }, description: 'Buy when EMA9 crosses above EMA21, sell on cross down' },
  { id: 'macd_signal', name: 'MACD Signal Cross', defaultParams: { quantity: 10 }, description: 'Buy when MACD histogram turns positive, sell when negative' },
  { id: 'ai_machine_learning', name: 'AI LightGBM Probabilistic', defaultParams: { qty_mode: 'atr', risk_pct: 0.02 }, description: 'Simulates AI predictions using LightGBM. Uses ATR-based dynamic position sizing and trailing stop losses.' },
]

export default function BacktestPage() {
  const { user } = useAuth()
  const navigate = useNavigate()
  
  // Persisted form state — restores last used config when user comes back
  const [form, setForm] = useLocalStorage('backtest_form', {
    symbol: 'RELIANCE.NS',
    strategy: 'rsi_mean_reversion',
    start_date: '2022-01-01',
    end_date: '2024-12-31',
    initial_capital: '100000',
    quantity: '10',
  })
  const [results, setResults] = useState<any>(null)
  const [running, setRunning] = useState(false)
  const [backtestId, setBacktestId] = useState<string | null>(null)
  const [polling, setPolling] = useState(false)

  const selectedStrategy = STRATEGIES.find(s => s.id === form.strategy)

  async function handleRun(e: React.FormEvent) {
    e.preventDefault()
    setRunning(true)
    setResults(null)
    try {
      const params: any = { quantity: parseInt(form.quantity) }
      if (form.strategy === 'rsi_mean_reversion') { params.rsi_buy = 30; params.rsi_sell = 70 }
      if (form.strategy === 'ema_crossover') { params.fast_ema = 9; params.slow_ema = 21 }
      if (form.strategy === 'ai_machine_learning') { params.qty_mode = 'atr'; params.risk_pct = 0.02 }

      const res = await backtestApi.run({
        symbol: form.symbol.toUpperCase(),
        strategy: form.strategy,
        params,
        start_date: form.start_date,
        end_date: form.end_date,
        initial_capital: parseFloat(form.initial_capital),
      })

      const id = res.data.backtest_id
      setBacktestId(id)
      setPolling(true)
      pollResults(id)
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Failed to start backtest')
      setRunning(false)
    }
  }

  async function pollResults(id: string) {
    let attempts = 0
    const poll = async () => {
      try {
        const res = await backtestApi.getResults(id)
        const data = res.data
        if (data.status === 'COMPLETED' || data.status === 'FAILED') {
          setResults(data)
          setRunning(false)
          setPolling(false)
        } else if (attempts < 30) {
          attempts++
          setTimeout(poll, 2000)
        } else {
          setRunning(false)
          setPolling(false)
        }
      } catch { setRunning(false); setPolling(false) }
    }
    setTimeout(poll, 2000)
  }

  const metrics = results?.metrics

  if (user?.subscription_tier !== 'PRO') {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '60vh' }}>
        <Lock size={64} style={{ color: 'var(--text-secondary)', marginBottom: '20px' }} />
        <h1 style={{ fontSize: '2rem', marginBottom: '10px' }}>PRO Feature</h1>
        <p style={{ color: 'var(--text-secondary)', marginBottom: '30px', textAlign: 'center', maxWidth: '400px' }}>
          Strategy Backtesting allows you to simulate your trading strategies over historical data. Upgrade to PRO to unlock this powerful tool.
        </p>
        <button onClick={() => navigate('/pricing')} style={{ background: 'var(--primary-color)', color: 'white', padding: '12px 24px', border: 'none', borderRadius: '8px', cursor: 'pointer', fontWeight: 'bold' }}>
          View Pricing
        </button>
      </div>
    )
  }

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Strategy Backtesting</h1>
        <p className="page-subtitle">Walk-forward historical simulation with Sharpe ratio, drawdown, win rate, and Nifty 50 benchmark</p>
      </div>

      <div className="grid-2" style={{ gap: 20, alignItems: 'flex-start' }}>
        {/* Config Panel */}
        <div className="card">
          <div className="card-title" style={{ marginBottom: 16 }}>Configure Backtest</div>
          <form onSubmit={handleRun} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <div>
              <label style={{ fontSize: 12, color: 'var(--color-text-muted)', marginBottom: 4, display: 'block' }}>Symbol</label>
              <StockSearchBox 
                placeholder="e.g. RELIANCE.NS" 
                width="100%" 
                autoNavigate={false} 
                clearOnSelect={false}
                value={form.symbol} 
                onChange={(val) => setForm({ ...form, symbol: val })} 
              />
            </div>
            <div>
              <label style={{ fontSize: 12, color: 'var(--color-text-muted)', marginBottom: 4, display: 'block' }}>Strategy</label>
              <select className="input" value={form.strategy} onChange={e => setForm({ ...form, strategy: e.target.value })}>
                {STRATEGIES.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
              {selectedStrategy && <div style={{ fontSize: 12, color: 'var(--color-text-muted)', marginTop: 6 }}>{selectedStrategy.description}</div>}
            </div>
            <div className="grid-2">
              <div>
                <label style={{ fontSize: 12, color: 'var(--color-text-muted)', marginBottom: 4, display: 'block' }}>Start Date</label>
                <input className="input" type="date" value={form.start_date} onChange={e => setForm({ ...form, start_date: e.target.value })} />
              </div>
              <div>
                <label style={{ fontSize: 12, color: 'var(--color-text-muted)', marginBottom: 4, display: 'block' }}>End Date</label>
                <input className="input" type="date" value={form.end_date} onChange={e => setForm({ ...form, end_date: e.target.value })} />
              </div>
            </div>
            <div className="grid-2">
              <div>
                <label style={{ fontSize: 12, color: 'var(--color-text-muted)', marginBottom: 4, display: 'block' }}>Initial Capital (₹)</label>
                <input className="input" type="number" value={form.initial_capital} onChange={e => setForm({ ...form, initial_capital: e.target.value })} />
              </div>
              <div>
                <label style={{ fontSize: 12, color: 'var(--color-text-muted)', marginBottom: 4, display: 'block' }}>Quantity per Trade</label>
                <input className="input" type="number" min="1" value={form.quantity} onChange={e => setForm({ ...form, quantity: e.target.value })} />
              </div>
            </div>
            <button type="submit" className="btn btn-primary" disabled={running}>
              <Play size={15} />{running ? 'Running…' : 'Run Backtest'}
            </button>
          </form>
        </div>

        {/* Results Panel */}
        <div>
          {running && <div className="card loading">Running backtest — please wait…</div>}

          {results?.status === 'FAILED' && (
            <div className="card" style={{ borderColor: 'var(--color-bearish)' }}>
              <div style={{ color: 'var(--color-bearish)', fontWeight: 600 }}>Backtest Failed</div>
              <div style={{ fontSize: 13, color: 'var(--color-text-secondary)', marginTop: 8 }}>{results.error}</div>
            </div>
          )}

          {metrics && (
            <div>
              {metrics.total_trades === 0 && (
                <div className="card" style={{ marginBottom: 16, borderColor: 'var(--color-neutral)', color: 'var(--color-text-secondary)' }}>
                  <strong>Note:</strong> No trades were executed during this period with the current parameters. Try adjusting your parameters or the date range.
                </div>
              )}
              {/* Benchmark Comparison */}
              {results.benchmark && (
                <div className="card" style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'var(--bg-secondary)' }}>
                  <div>
                    <div style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>Strategy Return</div>
                    <div style={{ fontSize: 24, fontWeight: 700, fontFamily: 'var(--font-mono)', color: metrics.total_return_pct >= 0 ? 'var(--color-bullish)' : 'var(--color-bearish)' }}>
                      {metrics.total_return_pct >= 0 ? '+' : ''}{metrics.total_return_pct}%
                    </div>
                    <div style={{ fontSize: 11, color: 'var(--color-text-muted)', marginTop: 4 }}>Max DD: {metrics.max_drawdown_pct}%</div>
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', opacity: 0.7 }}>
                    <div style={{ fontSize: 12, color: 'var(--color-text-muted)', marginBottom: 4 }}>VS</div>
                    <div style={{ fontSize: 12, fontWeight: 600, padding: '4px 12px', borderRadius: 12, background: 'var(--bg-primary)', border: '1px solid var(--border-color)' }}>
                      NIFTY 50
                    </div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>Benchmark Return</div>
                    <div style={{ fontSize: 24, fontWeight: 700, fontFamily: 'var(--font-mono)', color: results.benchmark.total_return_pct >= 0 ? 'var(--color-bullish)' : 'var(--color-bearish)' }}>
                      {results.benchmark.total_return_pct >= 0 ? '+' : ''}{results.benchmark.total_return_pct}%
                    </div>
                    <div style={{ fontSize: 11, color: 'var(--color-text-muted)', marginTop: 4 }}>Max DD: {results.benchmark.max_drawdown_pct}%</div>
                  </div>
                </div>
              )}

              {/* Metrics Grid */}
              <div className="grid-2" style={{ marginBottom: 16 }}>
                {[
                  { label: 'Total Return', value: `${metrics.total_return_pct >= 0 ? '+' : ''}${metrics.total_return_pct}%`, color: metrics.total_return_pct >= 0 ? 'var(--color-bullish)' : 'var(--color-bearish)' },
                  { label: 'Sharpe Ratio', value: metrics.sharpe_ratio, color: metrics.sharpe_ratio > 1 ? 'var(--color-bullish)' : metrics.sharpe_ratio > 0 ? 'var(--color-neutral)' : 'var(--color-bearish)' },
                  { label: 'Sortino Ratio', value: metrics.sortino_ratio, color: metrics.sortino_ratio > 1.5 ? 'var(--color-bullish)' : metrics.sortino_ratio > 0 ? 'var(--color-neutral)' : 'var(--color-bearish)' },
                  { label: 'Calmar Ratio', value: metrics.calmar_ratio, color: metrics.calmar_ratio > 1 ? 'var(--color-bullish)' : metrics.calmar_ratio > 0 ? 'var(--color-neutral)' : 'var(--color-bearish)' },
                  { label: 'Max Drawdown', value: `${metrics.max_drawdown_pct}%`, color: 'var(--color-bearish)' },
                  { label: 'Win Rate', value: `${Math.round((metrics.win_rate || 0) * 100)}%`, color: metrics.win_rate >= 0.5 ? 'var(--color-bullish)' : 'var(--color-bearish)' },
                  { label: 'Total Trades', value: metrics.total_trades },
                  { label: 'Profit Factor', value: metrics.profit_factor === Infinity ? '∞' : metrics.profit_factor, color: metrics.profit_factor > 1 ? 'var(--color-bullish)' : 'var(--color-bearish)' },
                ].map((m, i) => (
                  <div key={i} className="card" style={{ padding: '12px 16px', opacity: metrics.total_trades === 0 ? 0.5 : 1 }}>
                    <div style={{ fontSize: 11, color: 'var(--color-text-muted)', marginBottom: 4 }}>{m.label}</div>
                    <div style={{ fontSize: 20, fontWeight: 700, fontFamily: 'var(--font-mono)', color: m.color || 'var(--color-text-primary)' }}>{m.value}</div>
                  </div>
                ))}
              </div>

              <div className="card">
                <div style={{ fontSize: 12, color: 'var(--color-text-muted)', marginBottom: 4 }}>Final Equity</div>
                <div style={{ fontSize: 24, fontWeight: 700, fontFamily: 'var(--font-mono)', color: metrics.final_equity >= parseFloat(form.initial_capital) ? 'var(--color-bullish)' : 'var(--color-bearish)' }}>
                  ₹{metrics.final_equity?.toLocaleString('en-IN')}
                </div>
                <div style={{ fontSize: 12, color: 'var(--color-text-muted)', marginTop: 4 }}>
                  Started with ₹{parseFloat(form.initial_capital).toLocaleString('en-IN')}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
