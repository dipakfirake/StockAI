import { useState } from 'react'
import { stocksApi } from '../services/api'
import api from '../services/api'
import { Search, Filter, Activity, BarChart2, Plus, Trash2 } from 'lucide-react'
import { useLocalStorage } from '../hooks/useLocalStorage'

const SCANNER_RULES = [
  { id: 'RSI_OVERSOLD', name: 'RSI Oversold (< 30)', desc: 'Stocks where RSI is below 30 (Potential Reversal)' },
  { id: 'RSI_OVERBOUGHT', name: 'RSI Overbought (> 70)', desc: 'Stocks where RSI is above 70 (Potential Pullback)' },
  { id: 'MACD_BULLISH', name: 'MACD Bullish', desc: 'MACD Histogram is positive' },
  { id: 'EMA_BULLISH_CROSS', name: 'EMA Bullish Cross', desc: 'EMA 9 has crossed above EMA 21' },
  { id: 'SUPERTREND_BUY', name: 'SuperTrend Buy', desc: 'SuperTrend indicator is currently green (up)' },
  { id: 'BB_SQUEEZE', name: 'Bollinger Band Squeeze', desc: 'Bollinger Bands are very tight (Bandwidth < 5%)' },
]

const SECTORS = [
  { id: 'Nifty 50', name: 'Nifty 50 (Full Universe)' },
  { id: 'Nifty Bank', name: 'Nifty Bank' },
  { id: 'Nifty IT', name: 'Nifty IT' },
  { id: 'Nifty Auto', name: 'Nifty Auto' },
]

export default function ScannerPage() {
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
        <p className="page-subtitle">Scan Nifty 50 universe for technical setups</p>
      </div>

      <div className="card" style={{ marginBottom: 24 }}>
        <div style={{ display: 'flex', gap: 16, marginBottom: 16, borderBottom: '1px solid var(--color-border)', paddingBottom: 16 }}>
          <button onClick={() => setScanMode('basic')} className={`btn ${scanMode === 'basic' ? 'btn-primary' : 'btn-ghost'}`}>Presets</button>
          <button onClick={() => setScanMode('custom')} className={`btn ${scanMode === 'custom' ? 'btn-primary' : 'btn-ghost'}`}>Custom Rules</button>
        </div>
        
        <form onSubmit={handleScan} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {scanMode === 'basic' ? (
            <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
              <div style={{ flex: 1, minWidth: 250 }}>
                <label style={{ display: 'block', fontSize: 13, marginBottom: 8, color: 'var(--color-text-secondary)' }}>
                  Scan Rule
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
            <div style={{ background: 'var(--color-bg-secondary)', padding: 16, borderRadius: 8 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                <h3 style={{ fontSize: 14 }}>Custom Rule Builder</h3>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <label style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>Timeframe:</label>
                  <select className="input" value={timeframe} onChange={e => setTimeframe(e.target.value)} style={{ padding: '4px 8px', fontSize: 12 }}>
                    <option value="1m">1 Min</option>
                    <option value="5m">5 Min</option>
                    <option value="15m">15 Min</option>
                    <option value="1d">1 Day</option>
                  </select>
                </div>
              </div>
              {customConditions.map((cond, idx) => (
                <div key={idx} style={{ display: 'flex', gap: 12, marginBottom: 12, alignItems: 'center' }}>
                  <select 
                    className="input" 
                    value={cond.indicator} 
                    onChange={e => {
                      const newConds = [...customConditions];
                      newConds[idx].indicator = e.target.value;
                      setCustomConditions(newConds);
                    }}
                  >
                    <option value="rsi_14">RSI (14)</option>
                    <option value="macd_macd">MACD Line</option>
                    <option value="macd_histogram">MACD Histogram</option>
                    <option value="ema_9">EMA 9</option>
                    <option value="ema_21">EMA 21</option>
                    <option value="ema_50">EMA 50</option>
                    <option value="ema_200">EMA 200</option>
                    <option value="sma_50">SMA 50</option>
                    <option value="sma_200">SMA 200</option>
                    <option value="adx_14">ADX (14)</option>
                    <option value="atr_14">ATR (14)</option>
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
                    style={{ width: 80 }}
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
                    placeholder="Value (e.g. 30)"
                    style={{ width: 120 }}
                  />
                  
                  {customConditions.length > 1 && (
                    <button type="button" onClick={() => setCustomConditions(customConditions.filter((_, i) => i !== idx))} className="btn btn-ghost" style={{ padding: '8px', color: 'var(--color-bearish)' }}>
                      <Trash2 size={16} />
                    </button>
                  )}
                </div>
              ))}
              
              <button type="button" onClick={() => setCustomConditions([...customConditions, { indicator: 'rsi_14', operator: '<', value: '30' }])} className="btn btn-secondary" style={{ fontSize: 13 }}>
                <Plus size={14} style={{ marginRight: 4 }}/> Add Condition
              </button>
            </div>
          )}

          <div style={{ display: 'flex', gap: 16, alignItems: 'flex-end', marginTop: 8 }}>
            <div style={{ flex: 1, minWidth: 200 }}>
              <label style={{ display: 'block', fontSize: 13, marginBottom: 8, color: 'var(--color-text-secondary)' }}>
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
            
            <button type="submit" className="btn btn-primary" disabled={loading}>
              {loading ? <span className="spinner" /> : <Filter size={16} />}
              {loading ? 'Scanning Universe...' : 'Run Scanner'}
            </button>
          </div>
        </form>
      </div>

      {loading && (
        <div style={{ textAlign: 'center', padding: '40px 0', color: 'var(--color-text-muted)' }}>
          <Activity size={32} className="spinner" style={{ marginBottom: 16, opacity: 0.5 }} />
          <p>Analyzing technicals for Nifty 50 stocks...</p>
        </div>
      )}

      {!loading && scannedCount > 0 && (
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
            <h2 style={{ fontSize: 16, fontWeight: 600 }}>Scan Results</h2>
            <div style={{ fontSize: 13, color: 'var(--color-text-muted)' }}>
              Found {results.length} matches out of {scannedCount} stocks scanned
            </div>
          </div>

          {results.length === 0 ? (
            <div className="card" style={{ textAlign: 'center', padding: '60px 0', color: 'var(--color-text-muted)' }}>
              <BarChart2 size={32} style={{ marginBottom: 16, opacity: 0.3 }} />
              <p>No stocks matched the selected criteria.</p>
            </div>
          ) : (
            <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--color-border)', backgroundColor: 'var(--color-bg-secondary)' }}>
                    <th style={{ padding: '12px 16px', fontWeight: 600, fontSize: 13, color: 'var(--color-text-secondary)' }}>Symbol</th>
                    <th style={{ padding: '12px 16px', fontWeight: 600, fontSize: 13, color: 'var(--color-text-secondary)' }}>Rule Matched</th>
                    <th style={{ padding: '12px 16px', fontWeight: 600, fontSize: 13, color: 'var(--color-text-secondary)' }}>Details</th>
                    <th style={{ padding: '12px 16px', fontWeight: 600, fontSize: 13, color: 'var(--color-text-secondary)', textAlign: 'right' }}>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {results.map((r, i) => (
                    <tr key={i} style={{ borderBottom: '1px solid var(--color-border)' }}>
                      <td style={{ padding: '12px 16px', fontWeight: 600 }}>{r.symbol}</td>
                      <td style={{ padding: '12px 16px' }}><span className="badge badge-watch">{scanMode === 'basic' ? r.rule : 'CUSTOM'}</span></td>
                      <td style={{ padding: '12px 16px', fontSize: 13, color: 'var(--color-text-muted)' }}>{r.detail}</td>
                      <td style={{ padding: '12px 16px', textAlign: 'right' }}>
                        <a href={`/chart/${r.symbol}`} className="btn btn-secondary" style={{ fontSize: 12, padding: '4px 12px' }}>
                          View Chart
                        </a>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
