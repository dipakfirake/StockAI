import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { stocksApi } from '../services/api'
import api from '../services/api'
import { Search, Filter, Activity, BarChart2, Plus, Trash2 } from 'lucide-react'
import { useLocalStorage } from '../hooks/useLocalStorage'

const SCANNER_RULES = [
  { id: 'EMA_BULLISH_CROSS', name: 'EMA9 / EMA21 Bullish Cross', desc: 'Fast 9-EMA trading above slow 21-EMA' },
  { id: 'MACD_BULLISH', name: 'MACD Histogram Positive', desc: 'Upward trend acceleration via positive MACD histogram' },
  { id: 'SUPERTREND_BUY', name: 'SuperTrend Bullish', desc: 'Price holds above SuperTrend support band' },
  { id: 'RSI_BULLISH_MOMENTUM', name: 'RSI Momentum Zone 50–70', desc: 'Sustained bullish momentum without extreme overbought extension' },
  { id: 'PRICE_ABOVE_200SMA', name: 'Above 200-Day SMA', desc: 'Long-term institutional uptrend structure' },
  { id: 'RSI_OVERSOLD', name: 'RSI Oversold < 30', desc: 'Mean-reversion pullback setup in oversold territory' },
  { id: 'RSI_OVERBOUGHT', name: 'RSI Breakout > 70', desc: 'High-velocity momentum breakout territory' },
  { id: 'BB_SQUEEZE', name: 'Bollinger Volatility Squeeze', desc: 'Tight bandwidth below 8% preceding directional expansion' },
]

const SECTORS = [
  { id: 'Nifty 50', name: 'Nifty 50' },
  { id: 'Nifty Bank', name: 'Nifty Bank' },
  { id: 'Nifty IT', name: 'Nifty IT' },
  { id: 'Nifty Auto', name: 'Nifty Auto' },
  { id: 'Nifty FMCG', name: 'Nifty FMCG' },
  { id: 'Nifty Metal', name: 'Nifty Metal' },
  { id: 'Nifty Pharma', name: 'Nifty Pharma' },
  { id: 'Nifty Realty', name: 'Nifty Realty' },
  { id: 'Nifty Energy', name: 'Nifty Energy' },
]

export default function ScannerPage() {
  const navigate = useNavigate()
  // Persisted filter state — restores on page revisit
  const [selectedRule, setSelectedRule] = useLocalStorage('scanner_rule', SCANNER_RULES[0].id)
  const [selectedSector, setSelectedSector] = useLocalStorage('scanner_sector', SECTORS[0].id)
  const [scanMode, setScanMode] = useLocalStorage<'basic' | 'custom'>('scanner_mode', 'basic')
  const [timeframe, setTimeframe] = useLocalStorage('scanner_timeframe', '1d')
  const [customConditions, setCustomConditions] = useState([{ indicator: 'rsi_14', operator: '<', value: '30' }])

  const [results, setResults] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [scannedCount, setScannedCount] = useState(0)

  async function handleScan(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true)
    setResults([])
    
    try {
      let response;
      if (scanMode === 'basic') {
        if (selectedSector === 'Nifty 50') {
          response = await stocksApi.scanMarket(selectedRule)
        } else {
          response = await api.get(`/scanner/sector/${selectedSector}`, { params: { rule: selectedRule } })
        }
      } else {
        response = await stocksApi.customScan({
          universe: selectedSector,
          timeframe: timeframe,
          conditions: customConditions.map(c => ({
            ...c,
            value: isNaN(Number(c.value)) ? c.value : Number(c.value)
          }))
        })
      }
      
      setResults(response.data.matches || [])
      setScannedCount(response.data.total_scanned || 0)
    } catch (err) {
      console.error("Scan failed:", err)
    } finally {
      setLoading(false)
    }
  }

  const activeRuleDesc = SCANNER_RULES.find(r => r.id === selectedRule)?.desc

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Market Scanner</h1>
        <p className="page-subtitle">Scan NSE indices using preset signals or custom multi-condition rules</p>
      </div>

      <div className="card" style={{ marginBottom: 20 }}>
        <div style={{ display: 'flex', gap: 10, marginBottom: 16, borderBottom: '1px solid var(--color-border)', paddingBottom: 14, flexWrap: 'wrap' }}>
          <button type="button" onClick={() => setScanMode('basic')} className={`btn ${scanMode === 'basic' ? 'btn-primary' : 'btn-ghost'}`}>Presets</button>
          <button type="button" onClick={() => setScanMode('custom')} className={`btn ${scanMode === 'custom' ? 'btn-primary' : 'btn-ghost'}`}>Custom Rules</button>
        </div>
        
        <form onSubmit={handleScan} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          {scanMode === 'basic' ? (
            <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap' }}>
              <div style={{ flex: '1 1 200px', minWidth: 0 }}>
                <label style={{ display: 'block', fontSize: 12.5, marginBottom: 6, color: 'var(--color-text-secondary)', fontWeight: 600 }}>
                  Universe
                </label>
                <select 
                  className="input" 
                  value={selectedSector} 
                  onChange={e => setSelectedSector(e.target.value)}
                  style={{ width: '100%', cursor: 'pointer' }}
                >
                  {SECTORS.map(s => (
                    <option key={s.id} value={s.id}>{s.name}</option>
                  ))}
                </select>
              </div>

              <div style={{ flex: '2 1 240px', minWidth: 0 }}>
                <label style={{ display: 'block', fontSize: 12.5, marginBottom: 6, color: 'var(--color-text-secondary)', fontWeight: 600 }}>
                  Signal Preset
                </label>
                <select 
                  className="input" 
                  value={selectedRule} 
                  onChange={e => setSelectedRule(e.target.value)}
                  style={{ width: '100%', cursor: 'pointer' }}
                >
                  {SCANNER_RULES.map(r => (
                    <option key={r.id} value={r.id}>{r.name}</option>
                  ))}
                </select>
                <div style={{ fontSize: 12, color: 'var(--color-text-muted)', marginTop: 6 }}>
                  {activeRuleDesc}
                </div>
              </div>
            </div>
          ) : (
            <div style={{ background: 'var(--color-bg-secondary)', padding: 14, borderRadius: 8, border: '1px solid var(--color-border)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12, flexWrap: 'wrap', gap: 10 }}>
                <h3 style={{ fontSize: 14, margin: 0 }}>Custom Conditions</h3>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                  <select className="input" value={selectedSector} onChange={e => setSelectedSector(e.target.value)} style={{ width: 'auto', minWidth: 130, padding: '5px 10px', fontSize: 12.5 }}>
                    {SECTORS.map(s => (
                      <option key={s.id} value={s.id}>{s.name}</option>
                    ))}
                  </select>
                  <select className="input" value={timeframe} onChange={e => setTimeframe(e.target.value)} style={{ width: 'auto', padding: '5px 10px', fontSize: 12.5 }}>
                    <option value="1m">1 Min</option>
                    <option value="5m">5 Min</option>
                    <option value="15m">15 Min</option>
                    <option value="1d">1 Day</option>
                  </select>
                </div>
              </div>
              {customConditions.map((cond, idx) => (
                <div key={idx} style={{ display: 'flex', gap: 8, marginBottom: 10, alignItems: 'center', flexWrap: 'wrap' }}>
                  <select 
                    className="input" 
                    value={cond.indicator} 
                    onChange={e => {
                      const newConds = [...customConditions];
                      newConds[idx].indicator = e.target.value;
                      setCustomConditions(newConds);
                    }}
                    style={{ flex: '2 1 140px', minWidth: 0 }}
                  >
                    <option value="rsi_14">RSI 14</option>
                    <option value="macd_macd">MACD Line</option>
                    <option value="macd_histogram">MACD Histogram</option>
                    <option value="ema_9">EMA 9</option>
                    <option value="ema_21">EMA 21</option>
                    <option value="ema_50">EMA 50</option>
                    <option value="ema_200">EMA 200</option>
                    <option value="sma_50">SMA 50</option>
                    <option value="sma_200">SMA 200</option>
                    <option value="adx_14">ADX 14</option>
                    <option value="atr_14">ATR 14</option>
                    <option value="bb_upper">BB Upper</option>
                    <option value="bb_lower">BB Lower</option>
                    <option value="vwap">VWAP</option>
                    <option value="close">Close Price</option>
                    <option value="volume">Volume</option>
                  </select>
                  
                  <select 
                    className="input" 
                    value={cond.operator} 
                    onChange={e => {
                      const newConds = [...customConditions];
                      newConds[idx].operator = e.target.value;
                      setCustomConditions(newConds);
                    }}
                    style={{ flex: '0 0 72px' }}
                  >
                    <option value=">">&gt;</option>
                    <option value="<">&lt;</option>
                    <option value="==">==</option>
                  </select>

                  <input 
                    className="input" 
                    value={cond.value} 
                    onChange={e => {
                      const newConds = [...customConditions];
                      newConds[idx].value = e.target.value;
                      setCustomConditions(newConds);
                    }}
                    placeholder="Value"
                    style={{ flex: '1 1 90px', minWidth: 0 }}
                  />
                  
                  {customConditions.length > 1 && (
                    <button type="button" onClick={() => setCustomConditions(customConditions.filter((_, i) => i !== idx))} className="btn btn-ghost" style={{ padding: '8px', color: 'var(--color-bearish)' }}>
                      <Trash2 size={16} />
                    </button>
                  )}
                </div>
              ))}
              
              <button type="button" onClick={() => setCustomConditions([...customConditions, { indicator: 'rsi_14', operator: '<', value: '30' }])} className="btn btn-secondary" style={{ fontSize: 12.5 }}>
                <Plus size={14} /> Add Condition
              </button>
            </div>
          )}

          <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
            <button type="submit" className="btn btn-primary mobile-w-100" disabled={loading}>
              <Filter size={15} />
              {loading ? `Scanning ${selectedSector}…` : 'Run Scan'}
            </button>
          </div>
        </form>
      </div>

      {loading && (
        <div style={{ textAlign: 'center', padding: '40px 0', color: 'var(--color-text-muted)' }}>
          <Activity size={28} className="spinner" style={{ marginBottom: 12, opacity: 0.5 }} />
          <p>Scanning {selectedSector}…</p>
        </div>
      )}

      {!loading && scannedCount > 0 && (
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12, flexWrap: 'wrap', gap: 8 }}>
            <h2 style={{ fontSize: 16, fontWeight: 600, margin: 0 }}>Scan Results</h2>
            <div style={{ fontSize: 12.5, color: 'var(--color-text-muted)' }}>
              {results.length} matches across {scannedCount} stocks
            </div>
          </div>

          {results.length === 0 ? (
            <div className="card" style={{ textAlign: 'center', padding: '48px 16px', color: 'var(--color-text-muted)' }}>
              <BarChart2 size={28} style={{ marginBottom: 12, opacity: 0.35 }} />
              <p>No stocks matched the selected criteria.</p>
            </div>
          ) : (
            <>
              <div className="card table-container desktop-only-table" style={{ padding: 0 }}>
                <table className="table" style={{ margin: 0 }}>
                  <thead>
                    <tr>
                      <th>Symbol</th>
                      <th>Rule</th>
                      <th>Details</th>
                      <th style={{ textAlign: 'right' }}>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {results.map((r, i) => (
                      <tr key={i}>
                        <td style={{ fontWeight: 600 }}>{r.symbol}</td>
                        <td><span className="badge badge-watch">{scanMode === 'basic' ? r.rule : 'CUSTOM'}</span></td>
                        <td style={{ fontSize: 13, color: 'var(--color-text-muted)' }}>{r.detail}</td>
                        <td style={{ textAlign: 'right' }}>
                          <button
                            onClick={() => navigate('/chart', { state: { symbol: r.symbol } })}
                            className="btn btn-secondary"
                            style={{ fontSize: 12, padding: '5px 12px' }}
                          >
                            Chart
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="mobile-only-cards">
                {results.map((r, i) => (
                  <div key={i} className="card" style={{ padding: 14 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                      <strong style={{ fontSize: 15 }}>{r.symbol.replace('.NS', '')}</strong>
                      <span className="badge badge-watch">{scanMode === 'basic' ? r.rule : 'CUSTOM'}</span>
                    </div>
                    <div style={{ fontSize: 12.5, color: 'var(--color-text-muted)', marginBottom: 10 }}>{r.detail}</div>
                    <button
                      onClick={() => navigate('/chart', { state: { symbol: r.symbol } })}
                      className="btn btn-secondary w-100"
                      style={{ fontSize: 13 }}
                    >
                      Open Chart
                    </button>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}
