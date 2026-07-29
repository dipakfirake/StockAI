import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { marketApi } from '../services/api'
import { Activity, Target, ShieldAlert, Zap } from 'lucide-react'

export default function OptionsChainPage() {
  const { symbol = 'NIFTY.NS' } = useParams<{ symbol?: string }>()
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [viewGreeks, setViewGreeks] = useState(false)

  // Use a simple local input to change symbol
  const [inputSymbol, setInputSymbol] = useState(symbol)

  useEffect(() => {
    fetchOptions(symbol)
  }, [symbol])

  async function fetchOptions(sym: string) {
    setLoading(true)
    setError('')
    try {
      const res = await marketApi.getOptions(sym)
      setData(res.data)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to fetch options chain')
    } finally {
      setLoading(false)
    }
  }

  function handleSearch(e: React.FormEvent) {
    e.preventDefault()
    if (inputSymbol.trim()) {
      window.history.pushState(null, '', `/options/${inputSymbol.trim().toUpperCase()}`)
      fetchOptions(inputSymbol.trim().toUpperCase())
    }
  }

  return (
    <div>
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1 className="page-title">Options Chain</h1>
          <p className="page-subtitle">Real-time simulation via Black-Scholes Engine</p>
        </div>
        
        <form onSubmit={handleSearch} style={{ display: 'flex', gap: 8 }}>
          <input 
            className="input" 
            value={inputSymbol} 
            onChange={(e) => setInputSymbol(e.target.value)} 
            placeholder="NIFTY.NS, RELIANCE.NS..."
          />
          <button className="button" type="submit">Load</button>
        </form>
      </div>

      {loading ? (
        <div style={{ textAlign: 'center', padding: '40px 0', color: 'var(--color-text-muted)' }}>
          <Activity size={32} className="spinner" style={{ marginBottom: 16, opacity: 0.5 }} />
          <p>Generating Options Chain...</p>
        </div>
      ) : error ? (
        <div style={{ color: 'var(--color-bearish)', padding: 20 }}>{error}</div>
      ) : data ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          
          {/* Summary Dashboard */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 16 }}>
            <div className="card" style={{ padding: 16, display: 'flex', alignItems: 'center', gap: 12 }}>
              <div style={{ background: 'var(--color-bg-secondary)', padding: 12, borderRadius: 8 }}><Target color="var(--primary-color)" /></div>
              <div>
                <div style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>Underlying Spot ({data.symbol})</div>
                <div style={{ fontSize: 20, fontWeight: 'bold' }}>{(data.spot_price || 0).toFixed(2)}</div>
              </div>
            </div>
            <div className="card" style={{ padding: 16, display: 'flex', alignItems: 'center', gap: 12 }}>
              <div style={{ background: 'var(--color-bg-secondary)', padding: 12, borderRadius: 8 }}><Zap color="var(--color-bullish)" /></div>
              <div>
                <div style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>Put-Call Ratio (PCR)</div>
                <div style={{ fontSize: 20, fontWeight: 'bold', color: data.pcr > 1 ? 'var(--color-bullish)' : 'var(--color-bearish)' }}>{(data.pcr || 0).toFixed(2)}</div>
              </div>
            </div>
            <div className="card" style={{ padding: 16, display: 'flex', alignItems: 'center', gap: 12 }}>
              <div style={{ background: 'var(--color-bg-secondary)', padding: 12, borderRadius: 8 }}><ShieldAlert color="var(--color-accent)" /></div>
              <div>
                <div style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>Max Pain Strike</div>
                <div style={{ fontSize: 20, fontWeight: 'bold' }}>{data.max_pain}</div>
              </div>
            </div>
            <div className="card" style={{ padding: 16, display: 'flex', alignItems: 'center', gap: 12 }}>
              <div style={{ background: 'var(--color-bg-secondary)', padding: 12, borderRadius: 8 }}>
                <span style={{ fontSize: 16, fontWeight: 'bold' }}>EXP</span>
              </div>
              <div>
                <div style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>Expiry Date</div>
                <div style={{ fontSize: 16, fontWeight: 'bold' }}>{data.expiry_date} ({data.days_to_expiry} days)</div>
              </div>
            </div>
          </div>

          <div className="card" style={{ overflow: 'hidden' }}>
            <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span className="card-title">Option Chain Data</span>
              <button 
                className="button button-outline" 
                onClick={() => setViewGreeks(!viewGreeks)}
                style={{ padding: '4px 12px', fontSize: 12 }}
              >
                {viewGreeks ? 'View Standard Data' : 'View Options Greeks'}
              </button>
            </div>
            
            <div style={{ overflowX: 'auto' }}>
              <table className="data-table" style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'right' }}>
                <thead>
                  <tr style={{ background: 'var(--color-bg-tertiary)' }}>
                    <th colSpan={viewGreeks ? 5 : 3} style={{ textAlign: 'center', borderRight: '1px solid var(--color-border)', padding: 8 }}>CALLS</th>
                    <th style={{ textAlign: 'center', padding: 8, background: 'var(--color-bg-primary)' }}>STRIKE</th>
                    <th colSpan={viewGreeks ? 5 : 3} style={{ textAlign: 'center', borderLeft: '1px solid var(--color-border)', padding: 8 }}>PUTS</th>
                  </tr>
                  <tr style={{ fontSize: 12, color: 'var(--color-text-muted)', borderBottom: '1px solid var(--color-border)' }}>
                    {/* Calls Header */}
                    {viewGreeks ? (
                      <><th>Vega</th><th>Theta</th><th>Gamma</th><th>Delta</th><th>IV</th></>
                    ) : (
                      <><th>OI</th><th>IV</th><th>LTP</th></>
                    )}
                    
                    <th style={{ textAlign: 'center', background: 'var(--color-bg-primary)' }}>PRICE</th>
                    
                    {/* Puts Header */}
                    {viewGreeks ? (
                      <><th>IV</th><th>Delta</th><th>Gamma</th><th>Theta</th><th>Vega</th></>
                    ) : (
                      <><th>LTP</th><th>IV</th><th>OI</th></>
                    )}
                  </tr>
                </thead>
                <tbody>
                  {(data.chain || []).map((row: any) => {
                    const isCallITM = row.strike <= data.spot_price;
                    const isPutITM = row.strike >= data.spot_price;
                    
                    const callBg = isCallITM ? 'rgba(234, 179, 8, 0.1)' : 'transparent';
                    const putBg = isPutITM ? 'rgba(234, 179, 8, 0.1)' : 'transparent';
                    const isATM = Math.abs(row.strike - data.spot_price) < ((data.chain[1]?.strike - data.chain[0]?.strike) || 50) / 2;

                    return (
                      <tr key={row.strike} style={{ borderBottom: '1px solid rgba(255,255,255,0.05)', fontSize: 13, fontFamily: 'var(--font-mono)' }}>
                        {/* Calls */}
                        {viewGreeks ? (
                          <>
                            <td style={{ background: callBg, padding: 8 }}>{row.CE.vega.toFixed(2)}</td>
                            <td style={{ background: callBg, padding: 8 }}>{row.CE.theta.toFixed(2)}</td>
                            <td style={{ background: callBg, padding: 8 }}>{row.CE.gamma.toFixed(4)}</td>
                            <td style={{ background: callBg, padding: 8 }}>{row.CE.delta.toFixed(2)}</td>
                            <td style={{ background: callBg, padding: 8 }}>{row.CE.impliedVolatility}%</td>
                          </>
                        ) : (
                          <>
                            <td style={{ background: callBg, padding: 8 }}>{(row.CE.openInterest / 100000).toFixed(1)}L</td>
                            <td style={{ background: callBg, padding: 8 }}>{row.CE.impliedVolatility}%</td>
                            <td style={{ background: callBg, padding: 8, color: 'var(--color-bullish)', fontWeight: 'bold' }}>{row.CE.lastPrice.toFixed(2)}</td>
                          </>
                        )}
                        
                        {/* Strike */}
                        <td style={{ textAlign: 'center', padding: 8, background: isATM ? 'rgba(59, 130, 246, 0.2)' : 'var(--color-bg-secondary)', fontWeight: 'bold', borderLeft: '1px solid var(--color-border)', borderRight: '1px solid var(--color-border)' }}>
                          {row.strike}
                        </td>
                        
                        {/* Puts */}
                        {viewGreeks ? (
                          <>
                            <td style={{ background: putBg, padding: 8 }}>{row.PE.impliedVolatility}%</td>
                            <td style={{ background: putBg, padding: 8 }}>{row.PE.delta.toFixed(2)}</td>
                            <td style={{ background: putBg, padding: 8 }}>{row.PE.gamma.toFixed(4)}</td>
                            <td style={{ background: putBg, padding: 8 }}>{row.PE.theta.toFixed(2)}</td>
                            <td style={{ background: putBg, padding: 8 }}>{row.PE.vega.toFixed(2)}</td>
                          </>
                        ) : (
                          <>
                            <td style={{ background: putBg, padding: 8, color: 'var(--color-bearish)', fontWeight: 'bold' }}>{row.PE.lastPrice.toFixed(2)}</td>
                            <td style={{ background: putBg, padding: 8 }}>{row.PE.impliedVolatility}%</td>
                            <td style={{ background: putBg, padding: 8 }}>{(row.PE.openInterest / 100000).toFixed(1)}L</td>
                          </>
                        )}
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}
