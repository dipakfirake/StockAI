import { useEffect, useRef, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { createChart, IChartApi, ISeriesApi, CandlestickData, Time, HistogramData, LineData } from 'lightweight-charts'
import { stocksApi, aiApi } from '../services/api'
import { Search, TrendingUp, BarChart2, Activity, ListFilter, Lock } from 'lucide-react'
import { useAuth } from '../AuthContext'
import StockSearchBox from '../components/StockSearchBox'

const TIMEFRAMES = ['1m', '5m', '15m', '30m', '1h', '1d', '1w']

interface Signal {
  type: string
  strength: string
  reason: string
  score: number
  holding_period?: { label: string; basis: string }
}

interface AIScore {
  score: string
  confidence: number
  model?: string
  probabilities: { buy: number; hold: number; sell: number }
  explanation: { feature: string; value: any; contribution: number; direction: string; reason: string }[]
}

// Helper to convert standard OHLC to Heikin Ashi
function toHeikinAshi(candles: any[]) {
  const ha: any[] = []
  for (let i = 0; i < candles.length; i++) {
    const c = candles[i]
    if (i === 0) {
      ha.push({ ...c, open: (c.open + c.close) / 2, close: (c.open + c.high + c.low + c.close) / 4 })
    } else {
      const prev = ha[i - 1]
      const open = (prev.open + prev.close) / 2
      const close = (c.open + c.high + c.low + c.close) / 4
      ha.push({
        ...c,
        open,
        close,
        high: Math.max(c.high, open, close),
        low: Math.min(c.low, open, close)
      })
    }
  }
  return ha
}

export default function ChartPage() {
  const { symbol: paramSymbol } = useParams()
  const navigate = useNavigate()
  const { user } = useAuth()

  // Chart Containers
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const legendRef = useRef<HTMLDivElement>(null)
  const rsiContainerRef = useRef<HTMLDivElement>(null)
  const macdContainerRef = useRef<HTMLDivElement>(null)

  // Chart Instances
  const chartRef = useRef<IChartApi | null>(null)
  const rsiChartRef = useRef<IChartApi | null>(null)
  const macdChartRef = useRef<IChartApi | null>(null)

  // Series References
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null)
  const ema9SeriesRef = useRef<ISeriesApi<'Line'> | null>(null)
  const ema21SeriesRef = useRef<ISeriesApi<'Line'> | null>(null)
  const vwapSeriesRef = useRef<ISeriesApi<'Line'> | null>(null)
  
  const rsiSeriesRef = useRef<ISeriesApi<'Line'> | null>(null)
  const macdSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null)
  const macdLineSeriesRef = useRef<ISeriesApi<'Line'> | null>(null)
  const macdSignalSeriesRef = useRef<ISeriesApi<'Line'> | null>(null)

  const [symbol, setSymbol] = useState(paramSymbol || 'RELIANCE.NS')
  const [searchInput, setSearchInput] = useState(symbol)
  const [timeframe, setTimeframe] = useState('1d')
  const [isHeikinAshi, setIsHeikinAshi] = useState(false)
  const [showIndicators, setShowIndicators] = useState(true)

  const [signals, setSignals] = useState<Signal[]>([])
  const [aiScore, setAiScore] = useState<AIScore | null>(null)
  const [sentiment, setSentiment] = useState<any>(null)
  const [indicators, setIndicators] = useState<any>(null)
  const [patterns, setPatterns] = useState<any[]>([])
  const [quote, setQuote] = useState<any>(null)
  const [info, setInfo] = useState<any>(null)
  const [risk, setRisk] = useState<any>(null)
  const [swingTrade, setSwingTrade] = useState<any>(null)
  const [loading, setLoading] = useState(false)

  // Raw data store to quickly toggle Heikin Ashi without refetching
  const [rawCandles, setRawCandles] = useState<any[]>([])

  // Sync route params
  useEffect(() => {
    if (paramSymbol && paramSymbol !== symbol) {
      setSymbol(paramSymbol)
    }
  }, [paramSymbol])

  // Setup Charts on Mount
  useEffect(() => {
    if (!chartContainerRef.current || !rsiContainerRef.current || !macdContainerRef.current) return

    // 1. Main Chart (Candles, Volume, EMAs)
    const chart = createChart(chartContainerRef.current, {
      height: 400,
      layout: { background: { color: '#0f1629' }, textColor: '#8b9dc3' },
      grid: { vertLines: { color: '#1e2d4a' }, horzLines: { color: '#1e2d4a' } },
      crosshair: { mode: 1 },
      rightPriceScale: { borderColor: '#1e2d4a' },
      timeScale: { borderColor: '#1e2d4a', timeVisible: true },
    })

    const candleSeries = chart.addCandlestickSeries({
      upColor: '#10b981', downColor: '#ef4444',
      borderUpColor: '#10b981', borderDownColor: '#ef4444',
      wickUpColor: '#10b981', wickDownColor: '#ef4444',
    })

    const ema9Series = chart.addLineSeries({ color: '#3b82f6', lineWidth: 1, title: 'EMA 9' })
    const ema21Series = chart.addLineSeries({ color: '#f59e0b', lineWidth: 1, title: 'EMA 21' })
    const vwapSeries = chart.addLineSeries({ color: '#d946ef', lineWidth: 2, title: 'VWAP', lineStyle: 2 })
    const supertrendSeries = chart.addLineSeries({ color: '#10b981', lineWidth: 2, title: 'SuperTrend', lineStyle: 0 })
    
    const volumeSeries = chart.addHistogramSeries({
      color: '#26a69a',
      priceFormat: { type: 'volume' },
      priceScaleId: '', // Set as an overlay
    })
    
    chart.priceScale('').applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    })

    chartRef.current = chart
    candleSeriesRef.current = candleSeries
    ema9SeriesRef.current = ema9Series
    ema21SeriesRef.current = ema21Series;
    vwapSeriesRef.current = vwapSeries;
    (chartRef as any).supertrendSeries = supertrendSeries;
    volumeSeriesRef.current = volumeSeries;

    chart.subscribeCrosshairMove((param) => {
      if (
        param.point === undefined ||
        !param.time ||
        param.point.x < 0 ||
        param.point.x > chartContainerRef.current!.clientWidth ||
        param.point.y < 0 ||
        param.point.y > chartContainerRef.current!.clientHeight
      ) {
        if (legendRef.current) legendRef.current.style.display = 'none';
      } else {
        const data = param.seriesData.get(candleSeries) as any;
        const vol = param.seriesData.get(volumeSeries) as any;
        if (data && legendRef.current) {
          legendRef.current.style.display = 'block';
          const isBullish = data.close >= data.open;
          const color = isBullish ? '#10b981' : '#ef4444';
          legendRef.current.innerHTML = `
            <div style="font-size: 13px; display: flex; gap: 12px; color: #8b9dc3;">
              <span>O: <span style="color: ${color}">${data.open.toFixed(2)}</span></span>
              <span>H: <span style="color: ${color}">${data.high.toFixed(2)}</span></span>
              <span>L: <span style="color: ${color}">${data.low.toFixed(2)}</span></span>
              <span>C: <span style="color: ${color}">${data.close.toFixed(2)}</span></span>
              ${vol ? `<span>V: <span style="color: #cbd5e1">${vol.value.toLocaleString('en-IN')}</span></span>` : ''}
            </div>
          `;
        }
      }
    });

    // 2. RSI Sub-chart
    const rsiChart = createChart(rsiContainerRef.current, {
      height: 120,
      layout: { background: { color: '#0f1629' }, textColor: '#8b9dc3' },
      grid: { vertLines: { color: '#1e2d4a' }, horzLines: { color: '#1e2d4a' } },
      rightPriceScale: { borderColor: '#1e2d4a' },
      timeScale: { visible: false }, // Hide time axis, sync with main
    })
    
    const rsiSeries = rsiChart.addLineSeries({ color: '#a855f7', lineWidth: 2, title: 'RSI' })
    rsiChartRef.current = rsiChart
    rsiSeriesRef.current = rsiSeries

    // 3. MACD Sub-chart
    const macdChart = createChart(macdContainerRef.current, {
      height: 150,
      layout: { background: { color: '#0f1629' }, textColor: '#8b9dc3' },
      grid: { vertLines: { color: '#1e2d4a' }, horzLines: { color: '#1e2d4a' } },
      rightPriceScale: { borderColor: '#1e2d4a' },
      timeScale: { visible: true, borderColor: '#1e2d4a', timeVisible: true },
    })

    const macdSeries = macdChart.addHistogramSeries({ title: 'MACD Hist' })
    const macdLineSeries = macdChart.addLineSeries({ color: '#3b82f6', lineWidth: 1 })
    const macdSignalSeries = macdChart.addLineSeries({ color: '#f59e0b', lineWidth: 1 })
    
    macdChartRef.current = macdChart
    macdSeriesRef.current = macdSeries
    macdLineSeriesRef.current = macdLineSeries
    macdSignalSeriesRef.current = macdSignalSeries

    // Synchronize Time Scales
    const syncTimeScale = (sourceChart: IChartApi, targetCharts: IChartApi[]) => {
      sourceChart.timeScale().subscribeVisibleTimeRangeChange((timeRange) => {
        if (timeRange) {
          targetCharts.forEach(target => {
            try {
              target.timeScale().setVisibleRange(timeRange as any)
            } catch (e) {
              // Target chart might be empty
            }
          })
        }
      })
    }

    syncTimeScale(chart, [rsiChart, macdChart])
    syncTimeScale(macdChart, [chart, rsiChart])

    // Handle Resize
    const handleResize = () => {
      if (chartContainerRef.current && rsiContainerRef.current && macdContainerRef.current) {
        chart.applyOptions({ width: chartContainerRef.current.clientWidth })
        rsiChart.applyOptions({ width: rsiContainerRef.current.clientWidth })
        macdChart.applyOptions({ width: macdContainerRef.current.clientWidth })
      }
    }
    window.addEventListener('resize', handleResize)

    return () => {
      window.removeEventListener('resize', handleResize)
      chart.remove()
      rsiChart.remove()
      macdChart.remove()
    }
  }, [])

  // Load Data
  useEffect(() => {
    loadChartData()
  }, [symbol, timeframe])

  // Process Candles on rawCandles or HA toggle change
  useEffect(() => {
    if (rawCandles.length > 0 && candleSeriesRef.current && volumeSeriesRef.current) {
      const candlesToUse = isHeikinAshi ? toHeikinAshi(rawCandles) : rawCandles
      
      const chartData: CandlestickData[] = candlesToUse.map((c: any) => ({
        time: (new Date(c.timestamp).getTime() / 1000) as Time,
        open: c.open, high: c.high, low: c.low, close: c.close,
      }))
      
      const volumeData: HistogramData[] = rawCandles.map((c: any) => ({
        time: (new Date(c.timestamp).getTime() / 1000) as Time,
        value: c.volume,
        color: c.close > c.open ? 'rgba(16, 185, 129, 0.4)' : 'rgba(239, 68, 68, 0.4)'
      }))

      candleSeriesRef.current.setData(chartData)
      volumeSeriesRef.current.setData(volumeData)
      
      // Set Candlestick Pattern Markers
      if (patterns.length > 0 && candleSeriesRef.current) {
        const markers: any[] = patterns.map(p => {
          const isBullish = p.pattern.includes('Bullish') || p.pattern.includes('Hammer')
          return {
            time: (new Date(p.timestamp).getTime() / 1000) as Time,
            position: isBullish ? 'belowBar' : 'aboveBar',
            color: isBullish ? '#10b981' : '#ef4444',
            shape: isBullish ? 'arrowUp' : 'arrowDown',
            text: p.pattern
          }
        }).sort((a, b) => (a.time as number) - (b.time as number))
        
        candleSeriesRef.current.setMarkers(markers)
      }

      // Compute overlay lines if requested
      if (showIndicators && ema9SeriesRef.current && ema21SeriesRef.current && rsiSeriesRef.current && vwapSeriesRef.current) {
         const ema9Data: LineData[] = []
         const ema21Data: LineData[] = []
         const vwapData: LineData[] = []
         const rsiData: LineData[] = []
         const supertrendData: LineData[] = []
         const macdHistData: HistogramData[] = []
         const macdData: LineData[] = []
         const macdSignalData: LineData[] = []
         const obMarkers: any[] = []

         candlesToUse.forEach((c: any) => {
           const time = (new Date(c.timestamp).getTime() / 1000) as Time
           if (c.ema_9 !== null && c.ema_9 !== undefined) ema9Data.push({ time, value: c.ema_9 })
           if (c.ema_21 !== null && c.ema_21 !== undefined) ema21Data.push({ time, value: c.ema_21 })
           if (c.vwap !== null && c.vwap !== undefined) vwapData.push({ time, value: c.vwap })
           if (c.rsi_14 !== null && c.rsi_14 !== undefined) rsiData.push({ time, value: c.rsi_14 })
           if (c.supertrend !== null && c.supertrend !== undefined) supertrendData.push({ time, value: c.supertrend })
           if (c.macd_hist !== null && c.macd_hist !== undefined) macdHistData.push({ time, value: c.macd_hist, color: c.macd_hist >= 0 ? 'rgba(16, 185, 129, 0.6)' : 'rgba(239, 68, 68, 0.6)' })
           if (c.macd !== null && c.macd !== undefined) macdData.push({ time, value: c.macd })
           if (c.macd_signal !== null && c.macd_signal !== undefined) macdSignalData.push({ time, value: c.macd_signal })
           
           if (c.order_block === 'bullish_ob') {
             obMarkers.push({ time, position: 'belowBar', color: '#10b981', shape: 'arrowUp', text: 'Bullish OB' })
           } else if (c.order_block === 'bearish_ob') {
             obMarkers.push({ time, position: 'aboveBar', color: '#ef4444', shape: 'arrowDown', text: 'Bearish OB' })
           }
         })

         ema9SeriesRef.current.setData(ema9Data)
         ema21SeriesRef.current.setData(ema21Data)
         vwapSeriesRef.current.setData(vwapData)
         rsiSeriesRef.current.setData(rsiData)
         
         if (macdSeriesRef.current) macdSeriesRef.current.setData(macdHistData)
         if (macdLineSeriesRef.current) macdLineSeriesRef.current.setData(macdData)
         if (macdSignalSeriesRef.current) macdSignalSeriesRef.current.setData(macdSignalData)
         if ((chartRef.current as any).supertrendSeries) {
           (chartRef.current as any).supertrendSeries.setData(supertrendData)
         }
         
         // Merge pattern markers with OB markers
         if (candleSeriesRef.current) {
            const markers: any[] = patterns.map(p => {
              const isBullish = p.pattern.includes('Bullish') || p.pattern.includes('Hammer')
              return {
                time: (new Date(p.timestamp).getTime() / 1000) as Time,
                position: isBullish ? 'belowBar' : 'aboveBar',
                color: isBullish ? '#10b981' : '#ef4444',
                shape: isBullish ? 'arrowUp' : 'arrowDown',
                text: p.pattern
              }
            })
            const allMarkers = [...markers, ...obMarkers].sort((a, b) => (a.time as number) - (b.time as number))
            candleSeriesRef.current.setMarkers(allMarkers)
         }
      } else {
         ema9SeriesRef.current?.setData([])
         ema21SeriesRef.current?.setData([])
         vwapSeriesRef.current?.setData([])
         rsiSeriesRef.current?.setData([])
         if ((chartRef.current as any).supertrendSeries) {
           (chartRef.current as any).supertrendSeries.setData([])
         }
         if (candleSeriesRef.current) {
            const markers: any[] = patterns.map(p => {
              const isBullish = p.pattern.includes('Bullish') || p.pattern.includes('Hammer')
              return {
                time: (new Date(p.timestamp).getTime() / 1000) as Time,
                position: isBullish ? 'belowBar' : 'aboveBar',
                color: isBullish ? '#10b981' : '#ef4444',
                shape: isBullish ? 'arrowUp' : 'arrowDown',
                text: p.pattern
              }
            }).sort((a, b) => (a.time as number) - (b.time as number))
            candleSeriesRef.current.setMarkers(markers)
         }
      }
      
      chartRef.current?.timeScale().fitContent()
      macdChartRef.current?.timeScale().fitContent()
    }
  }, [rawCandles, isHeikinAshi, showIndicators, patterns])


  async function loadChartData() {
    setLoading(true)
    try {
      const [insightRes, sentimentRes, infoRes] = await Promise.allSettled([
        stocksApi.getInsight(symbol, timeframe),
        aiApi.sentiment(symbol),
        stocksApi.getInfo(symbol),
      ])

      if (insightRes.status === 'fulfilled') {
        const insight = insightRes.value.data
        setRawCandles(insight.candles || [])
        setSignals(insight.signals || [])
        setAiScore(insight.ai_score)
        setQuote(insight.quote)
        setIndicators(insight.indicators)
        setPatterns(insight.patterns || [])
        setRisk(insight.risk)
        setSwingTrade(insight.swing_trade)
      }
      if (sentimentRes.status === 'fulfilled') setSentiment(sentimentRes.value.data)
      if (infoRes.status === 'fulfilled') setInfo(infoRes.value.data)

    } catch (err) {
      console.error('Chart load error:', err)
    } finally {
      setLoading(false)
    }
  }

  // WebSocket for live quote updates
  useEffect(() => {
    if (!symbol) return

    const token = localStorage.getItem('auth_token')
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const ws = new WebSocket(`${protocol}//${window.location.host}/ws?token=${token}`)

    ws.onopen = () => {
      ws.send(JSON.stringify({ type: 'subscribe', channel: 'market_data', symbol }))
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        if (data.type === 'market_update' && data.symbol.replace(/\.NS$/, '') === symbol.replace(/\.NS$/, '')) {
          setQuote((prev: any) => prev ? {
            ...prev,
            price: data.price,
            change: data.change,
            change_pct: data.change_pct,
          } : prev)
        }
      } catch (err) {
        console.error(err)
      }
    }

    return () => {
      ws.close()
    }
  }, [symbol])

  function handleSearch(e: React.FormEvent) {
    e.preventDefault()
    const cleaned = searchInput.toUpperCase().trim().replace('.NS', '')
    setSymbol(cleaned)
    navigate(`/chart/${cleaned}`)
  }

  const signal = signals[0]
  const signalClass = signal?.type === 'BUY' ? 'badge-buy' : signal?.type === 'SELL' ? 'badge-sell' : signal?.type === 'WATCH' ? 'badge-watch' : 'badge-hold'
  const aiClass = aiScore?.score === 'BUY' ? 'badge-buy' : aiScore?.score === 'SELL' ? 'badge-sell' : 'badge-hold'

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Chart Analysis</h1>
        <p className="page-subtitle">TradingView-style candlestick charts with Indicators</p>
      </div>

      {/* Search + Controls */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 16, alignItems: 'center', flexWrap: 'wrap' }}>
        <div style={{ flex: 1, minWidth: 240 }}>
          <StockSearchBox placeholder="Search stocks, indices..." width="100%" />
        </div>

        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <button onClick={() => setIsHeikinAshi(!isHeikinAshi)} className={`btn ${isHeikinAshi ? 'btn-primary' : 'btn-secondary'}`} style={{fontSize: 13, padding: '6px 12px'}}>
            <ListFilter size={14}/> Heikin Ashi
          </button>
          
          <div style={{ display: 'flex', gap: 4, marginLeft: 16, borderLeft: '1px solid var(--color-border)', paddingLeft: 16 }}>
            {TIMEFRAMES.map(tf => (
              <button
                key={tf}
                onClick={() => setTimeframe(tf)}
                className={`btn ${timeframe === tf ? 'btn-primary' : 'btn-ghost'}`}
                style={{ padding: '6px 12px', fontSize: 13 }}
              >
                {tf}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Quote Summary */}
      {quote && (
        <div className="card" style={{ marginBottom: 16, display: 'flex', gap: 32, alignItems: 'center' }}>
          <div>
            <div style={{ fontSize: 13, color: 'var(--color-text-muted)' }}>{symbol.replace('.NS', '')}</div>
            <div style={{ fontSize: 28, fontWeight: 700, fontFamily: 'var(--font-mono)' }}>
              ₹{quote.price?.toLocaleString('en-IN', { maximumFractionDigits: 2 })}
              {quote.change !== undefined && (
                <span style={{ fontSize: 16, marginLeft: 8, color: quote.change >= 0 ? '#10b981' : '#ef4444' }}>
                  {quote.change > 0 ? '+' : ''}{quote.change.toFixed(2)} ({quote.change_pct?.toFixed(2)}%)
                </span>
              )}
            </div>
          </div>
          <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
            <div><div style={{ fontSize: 11, color: 'var(--color-text-muted)' }}>52W High</div><div className="mono">₹{quote['52w_high']?.toLocaleString('en-IN')}</div></div>
            <div><div style={{ fontSize: 11, color: 'var(--color-text-muted)' }}>52W Low</div><div className="mono">₹{quote['52w_low']?.toLocaleString('en-IN')}</div></div>
            <div><div style={{ fontSize: 11, color: 'var(--color-text-muted)' }}>Volume</div><div className="mono">{quote.volume?.toLocaleString('en-IN')}</div></div>
            <div><div style={{ fontSize: 11, color: 'var(--color-text-muted)' }}>Market Cap</div><div className="mono">₹{(quote.market_cap / 1e9)?.toFixed(0)}B</div></div>
          </div>
        {/* AI Score Badge in Quote Summary */}
          <div style={{ marginLeft: 'auto', textAlign: 'center' }}>
            <div style={{ fontSize: 11, color: 'var(--color-text-muted)', marginBottom: 6 }}>AI Score</div>
            {user?.subscription_tier === 'PRO' ? (
              aiScore ? (
                <>
                  <span className={`badge ${aiClass}`} style={{ fontSize: 16, padding: '6px 18px' }}>{aiScore.score}</span>
                  <div style={{ fontSize: 11, color: 'var(--color-text-muted)', marginTop: 4 }}>{Math.round(aiScore.confidence * 100)}% confidence</div>
                </>
              ) : <span className="badge badge-neutral" style={{ fontSize: 14 }}>Loading...</span>
            ) : (
              <button onClick={() => navigate('/pricing')} className="badge badge-neutral" style={{ fontSize: 12, padding: '6px 12px', cursor: 'pointer', border: '1px solid var(--primary-color)' }}>
                <Lock size={12} style={{ display: 'inline', marginRight: 4 }}/> PRO
              </button>
            )}
          </div>
        </div>
      )}

      {/* Main Chart + Sub-charts */}
      <div className="card" style={{ padding: '0', overflow: 'hidden' }}>
        <div ref={chartContainerRef} style={{ width: '100%', position: 'relative' }}>
          <div 
            ref={legendRef} 
            style={{ 
              position: 'absolute', 
              top: 12, 
              left: 12, 
              zIndex: 10, 
              display: 'none',
              pointerEvents: 'none',
            }} 
          />
        </div>
        <div ref={rsiContainerRef} style={{ width: '100%', borderTop: '1px solid var(--color-border)' }} />
        <div ref={macdContainerRef} style={{ width: '100%' }} />
      </div>

      {risk && risk.level !== 'UNKNOWN' && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="card-header">
            <span className="card-title"><Activity size={15} style={{ marginRight: 6 }} />Risk &amp; Return — selected range</span>
            <span className={`badge ${risk.level === 'HIGH' ? 'badge-sell' : risk.level === 'MEDIUM' ? 'badge-hold' : 'badge-buy'}`}>{risk.level} risk</span>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(155px, 1fr))', gap: 12 }}>
            {[
              ['Period return', `${risk.period_return_pct >= 0 ? '+' : ''}${risk.period_return_pct}%`],
              ['Annualized volatility', `${risk.annualized_volatility_pct}%`],
              ['Downside volatility', `${risk.downside_volatility_pct}%`],
              ['Maximum drawdown', `${risk.max_drawdown_pct}%`],
              ['Data points', risk.observations],
            ].map(([label, value]) => <div key={String(label)} style={{ background: 'var(--color-bg-secondary)', padding: '10px 12px', borderRadius: 8 }}><div style={{ fontSize: 11, color: 'var(--color-text-muted)' }}>{label}</div><div className="mono" style={{ fontWeight: 600, marginTop: 2 }}>{value}</div></div>)}
          </div>
          <p style={{ color: 'var(--color-text-muted)', fontSize: 11, marginTop: 12 }}>{risk.methodology}</p>
        </div>
      )}

      <div className="grid-2" style={{ gap: 16 }}>
        {/* Signal Panel */}
        {signal && (
          <div className="card">
            <div className="card-header">
              <span className="card-title"><Activity size={15} style={{ marginRight: 6 }} />Rule-Based Signal</span>
              <span className={`badge ${signalClass}`}>{signal.type}</span>
            </div>
            <div style={{ marginBottom: 8, fontSize: 12, color: 'var(--color-text-muted)' }}>
              Strength: <strong style={{ color: 'var(--color-text-primary)' }}>{signal.strength}</strong>
              &nbsp;· Score: <strong style={{ color: signal.score > 0 ? 'var(--color-bullish)' : signal.score < 0 ? 'var(--color-bearish)' : 'var(--color-neutral)' }}>{signal.score > 0 ? '+' : ''}{signal.score}</strong>
            </div>
            {signal.holding_period && (
              <div style={{ marginBottom: 8, padding: '8px 10px', background: 'var(--color-bg-secondary)', borderRadius: 6, fontSize: 12 }}>
                <span style={{ color: 'var(--color-text-muted)' }}>Suggested review horizon: </span>
                <strong>{signal.holding_period.label}</strong>
                <span style={{ color: 'var(--color-text-muted)' }}> · {signal.holding_period.basis}</span>
              </div>
            )}
            <div style={{ fontSize: 13, color: 'var(--color-text-secondary)', lineHeight: 1.6, background: 'var(--color-bg-secondary)', padding: 12, borderRadius: 8 }}>
              {signal.reason}
            </div>
          </div>
        )}

        {/* Indicators Grid */}
        {indicators && (
          <div className="card" style={{ gridColumn: '1 / -1' }}>
            <div className="card-header">
              <span className="card-title"><BarChart2 size={15} style={{ marginRight: 6 }} />Technical Indicators (Latest)</span>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: 12 }}>
              {[
                { label: 'RSI (14)', value: indicators.rsi_14?.toFixed(2), color: indicators.rsi_14 < 30 ? 'var(--color-bullish)' : indicators.rsi_14 > 70 ? 'var(--color-bearish)' : 'var(--color-text-primary)' },
                { label: 'EMA 9', value: indicators.ema_9?.toFixed(2) },
                { label: 'EMA 21', value: indicators.ema_21?.toFixed(2) },
                { label: 'EMA 50', value: indicators.ema_50?.toFixed(2) },
                { label: 'EMA 200', value: indicators.ema_200?.toFixed(2) },
                { label: 'ADX (14)', value: indicators.adx_14?.toFixed(2), color: indicators.adx_14 > 25 ? 'var(--color-accent-blue)' : 'var(--color-text-secondary)' },
                { label: 'ATR (14)', value: indicators.atr_14?.toFixed(2) },
                { label: 'Stoch K', value: indicators.stoch_k?.toFixed(1) },
                { label: 'MACD', value: indicators.macd?.macd?.toFixed(4) },
                { label: 'MACD Signal', value: indicators.macd?.signal?.toFixed(4) },
                { label: 'BB Upper', value: indicators.bb?.upper?.toFixed(2) },
                { label: 'BB Lower', value: indicators.bb?.lower?.toFixed(2) },
              ].filter(i => i.value !== null && i.value !== undefined).map((ind, i) => (
                <div key={i} style={{ background: 'var(--color-bg-secondary)', padding: '10px 12px', borderRadius: 8 }}>
                  <div style={{ fontSize: 11, color: 'var(--color-text-muted)', marginBottom: 2 }}>{ind.label}</div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 15, fontWeight: 600, color: ind.color || 'var(--color-text-primary)' }}>
                    {ind.value}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Fundamental Analysis Grid */}
        {info && (
          <div className="card" style={{ gridColumn: '1 / -1' }}>
            <div className="card-header">
              <span className="card-title"><BarChart2 size={15} style={{ marginRight: 6 }} />Fundamental Analysis (Balance Sheet & Valuations)</span>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: 12 }}>
              {[
                { label: 'PE Ratio', value: info.pe_ratio?.toFixed(2) },
                { label: 'Forward PE', value: info.forward_pe?.toFixed(2) },
                { label: 'PB Ratio', value: info.price_to_book?.toFixed(2) },
                { label: 'ROE (%)', value: info.roe ? (info.roe * 100).toFixed(2) + '%' : null, color: info.roe > 0.15 ? 'var(--color-bullish)' : '' },
                { label: 'ROA (%)', value: info.roa ? (info.roa * 100).toFixed(2) + '%' : null },
                { label: 'Debt to Equity', value: info.debt_to_equity?.toFixed(2), color: info.debt_to_equity > 1 ? 'var(--color-bearish)' : 'var(--color-bullish)' },
                { label: 'Div Yield', value: info.dividend_yield ? (info.dividend_yield * 100).toFixed(2) + '%' : null },
                { label: 'Current Ratio', value: info.current_ratio?.toFixed(2) },
                { label: 'Revenue', value: info.total_revenue ? `₹${(info.total_revenue / 1e9).toFixed(1)}B` : null },
                { label: 'Rev Growth', value: info.revenue_growth ? (info.revenue_growth * 100).toFixed(2) + '%' : null, color: info.revenue_growth > 0 ? 'var(--color-bullish)' : 'var(--color-bearish)' },
              ].filter(i => i.value !== null && i.value !== undefined).map((ind, i) => (
                <div key={i} style={{ background: 'var(--color-bg-secondary)', padding: '10px 12px', borderRadius: 8 }}>
                  <div style={{ fontSize: 11, color: 'var(--color-text-muted)', marginBottom: 2 }}>{ind.label}</div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 15, fontWeight: 600, color: ind.color || 'var(--color-text-primary)' }}>
                    {ind.value}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* SHAP Explanations Grid */}
        <div className="card" style={{ gridColumn: '1 / -1', position: 'relative', overflow: 'hidden' }}>
          <div className="card-header">
            <span className="card-title"><Activity size={15} style={{ marginRight: 6 }} />ML Feature Contributions (SHAP)</span>
            {aiScore?.model && <span className="badge badge-hold" style={{ fontSize: 11 }}>Model: {aiScore.model}</span>}
          </div>
          
          {user?.subscription_tier !== 'PRO' ? (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '40px 0', background: 'rgba(15, 22, 41, 0.8)' }}>
              <Lock size={32} style={{ color: 'var(--text-secondary)', marginBottom: 12 }} />
              <h3 style={{ marginBottom: 8 }}>PRO Feature</h3>
              <p style={{ color: 'var(--text-secondary)', marginBottom: 16, fontSize: 13 }}>Upgrade to unlock AI predictions and SHAP explanations.</p>
              <button onClick={() => navigate('/pricing')} className="btn btn-primary">Upgrade Now</button>
            </div>
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 12 }}>
              {aiScore?.explanation?.map((exp: any, i: number) => (
                <div key={i} style={{ padding: '12px', border: '1px solid var(--color-border)', borderRadius: 8, background: exp.direction === 'bullish' ? 'rgba(16, 185, 129, 0.05)' : exp.direction === 'bearish' ? 'rgba(239, 68, 68, 0.05)' : 'transparent' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                    <span style={{ fontSize: 13, fontWeight: 600 }}>{exp.feature}</span>
                    <span style={{ fontSize: 13, fontFamily: 'var(--font-mono)' }}>{exp.value}</span>
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--color-text-muted)' }}>
                    Impact: <strong style={{ color: exp.direction === 'bullish' ? 'var(--color-bullish)' : exp.direction === 'bearish' ? 'var(--color-bearish)' : 'var(--color-text-primary)' }}>
                      {exp.direction.toUpperCase()} ({exp.contribution})
                    </strong>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* NLP News Sentiment Grid */}
        <div className="card" style={{ gridColumn: '1 / -1', position: 'relative', overflow: 'hidden' }}>
          <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span className="card-title"><Activity size={15} style={{ marginRight: 6 }} />Real-time News Sentiment (NLP)</span>
            {sentiment && sentiment.sentiment && (
              <span className={`badge ${sentiment.sentiment.overall_sentiment === 'BULLISH' ? 'badge-buy' : sentiment.sentiment.overall_sentiment === 'BEARISH' ? 'badge-sell' : 'badge-hold'}`}>
                {sentiment.sentiment.overall_sentiment} (Score: {sentiment.sentiment.compound_score})
              </span>
            )}
          </div>

          {user?.subscription_tier !== 'PRO' ? (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '40px 0', background: 'rgba(15, 22, 41, 0.8)' }}>
              <Lock size={32} style={{ color: 'var(--text-secondary)', marginBottom: 12 }} />
              <h3 style={{ marginBottom: 8 }}>PRO Feature</h3>
              <p style={{ color: 'var(--text-secondary)', marginBottom: 16, fontSize: 13 }}>Upgrade to unlock real-time financial NLP sentiment analysis.</p>
              <button onClick={() => navigate('/pricing')} className="btn btn-primary">Upgrade Now</button>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {sentiment?.sentiment?.scored_articles?.map((article: any, i: number) => (
                <div key={i} style={{ padding: '12px', border: '1px solid var(--color-border)', borderRadius: 8 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                    <a href={article.link} target="_blank" rel="noreferrer" style={{ fontSize: 13, fontWeight: 600, color: 'var(--color-text-primary)', textDecoration: 'none' }}>
                      {article.title}
                    </a>
                    <span className={`badge ${article.sentiment_label === 'POSITIVE' ? 'badge-buy' : article.sentiment_label === 'NEGATIVE' ? 'badge-sell' : 'badge-hold'}`} style={{ fontSize: 11, padding: '2px 8px', height: 'fit-content' }}>
                      {article.sentiment_label}
                    </span>
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--color-text-muted)' }}>
                    {article.source} · {new Date(article.published).toLocaleString('en-IN')}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
        
        {/* Swing Trade Analysis */}
        {swingTrade && !swingTrade.error && (
          <div className="card" style={{ gridColumn: '1 / -1', position: 'relative', overflow: 'hidden' }}>
            <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid var(--color-border)', paddingBottom: 12, marginBottom: 16 }}>
              <span className="card-title" style={{ fontSize: 16, fontWeight: 600 }}>
                Swing Trade Analysis
              </span>
              <span className={`badge ${swingTrade.action === 'BUY' ? 'badge-buy' : swingTrade.action === 'SELL' ? 'badge-sell' : 'badge-hold'}`} style={{ fontSize: 14, padding: '4px 12px' }}>
                {swingTrade.action} (Score: {swingTrade.total_score?.toFixed(1)})
              </span>
            </div>
            
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 16 }}>
              <div style={{ padding: 12, background: 'rgba(255,255,255,0.02)', borderRadius: 8 }}>
                <div style={{ fontSize: 12, color: 'var(--color-text-muted)', marginBottom: 4 }}>Expected Duration</div>
                <div style={{ fontSize: 16, fontWeight: 600, color: 'var(--color-text-primary)' }}>{swingTrade.trade_plan?.estimated_hold_time}</div>
              </div>
              <div style={{ padding: 12, background: 'rgba(255,255,255,0.02)', borderRadius: 8 }}>
                <div style={{ fontSize: 12, color: 'var(--color-text-muted)', marginBottom: 4 }}>Potential Gain</div>
                <div style={{ fontSize: 16, fontWeight: 600, color: 'var(--color-bullish)' }}>+{swingTrade.trade_plan?.expected_gain_pct?.toFixed(2)}%</div>
              </div>
              <div style={{ padding: 12, background: 'rgba(255,255,255,0.02)', borderRadius: 8 }}>
                <div style={{ fontSize: 12, color: 'var(--color-text-muted)', marginBottom: 4 }}>Max Risk (Stop Loss)</div>
                <div style={{ fontSize: 16, fontWeight: 600, color: 'var(--color-bearish)' }}>-{swingTrade.trade_plan?.risk_pct?.toFixed(2)}%</div>
              </div>
              <div style={{ padding: 12, background: 'rgba(255,255,255,0.02)', borderRadius: 8 }}>
                <div style={{ fontSize: 12, color: 'var(--color-text-muted)', marginBottom: 4 }}>Stop Loss Level</div>
                <div style={{ fontSize: 16, fontWeight: 600, color: 'var(--color-text-primary)' }}>₹{swingTrade.trade_plan?.stop_loss?.toFixed(2)}</div>
              </div>
              <div style={{ padding: 12, background: 'rgba(255,255,255,0.02)', borderRadius: 8 }}>
                <div style={{ fontSize: 12, color: 'var(--color-text-muted)', marginBottom: 4 }}>Target Price</div>
                <div style={{ fontSize: 16, fontWeight: 600, color: 'var(--color-text-primary)' }}>₹{swingTrade.trade_plan?.target_price?.toFixed(2)}</div>
              </div>
            </div>
            
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, marginTop: 16, paddingTop: 16, borderTop: '1px solid var(--color-border)' }}>
               <div style={{ textAlign: 'center' }}>
                 <div style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>Technical Score</div>
                 <div style={{ fontSize: 14, fontWeight: 500 }}>{swingTrade.scores?.technical?.toFixed(1)} / 100</div>
               </div>
               <div style={{ textAlign: 'center', borderLeft: '1px solid var(--color-border)', borderRight: '1px solid var(--color-border)' }}>
                 <div style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>Fundamental Score</div>
                 <div style={{ fontSize: 14, fontWeight: 500 }}>{swingTrade.scores?.fundamental?.toFixed(1)} / 100</div>
               </div>
               <div style={{ textAlign: 'center' }}>
                 <div style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>News Sentiment</div>
                 <div style={{ fontSize: 14, fontWeight: 500 }}>{swingTrade.scores?.sentiment?.toFixed(1)} / 100</div>
               </div>
            </div>
          </div>
        )}

      </div>
    </div>
  )
}
