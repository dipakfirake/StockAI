import { useEffect, useRef, useState, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { createChart, IChartApi, ISeriesApi, CandlestickData, Time, HistogramData, LineData } from 'lightweight-charts'
import { stocksApi, aiApi } from '../services/api'
import { Search, TrendingUp, BarChart2, Activity, ListFilter, Lock, Play, Pencil, Zap, ShoppingCart, Scale, FastForward, Clock } from 'lucide-react'
import { useAuth } from '../AuthContext'
import { useTheme } from '../ThemeContext'
import { toast } from '../components/Toast'
import StockSearchBox from '../components/StockSearchBox'
import ChartReplayControls from '../components/ChartReplayControls'
import { useLocalStorage } from '../hooks/useLocalStorage'
import { TrendlinePrimitive, Point } from '../components/DrawingEngine'

const TIMEFRAMES = ['1m', '5m', '15m', '30m', '1h', '1d', '1w', '1mo']
const TIMEFRAME_LABELS: Record<string, string> = {
  '1m': '1 Minute',
  '5m': '5 Minutes',
  '15m': '15 Minutes',
  '30m': '30 Minutes',
  '1h': '1 Hour',
  '1d': '1 Day',
  '1w': '1 Week',
  '1mo': '1 Month'
}

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
  const { user, savePreferences } = useAuth()
  const { theme } = useTheme()

  // ─── Persisted chart state (localStorage → instant restore, no flicker) ─────
  const [symbol, setSymbol] = useLocalStorage('chart_symbol', paramSymbol || '^NSEI')
  const [timeframe, setTimeframe] = useLocalStorage<string>('chart_timeframe', '1d')
  const [isHeikinAshi, setIsHeikinAshi] = useLocalStorage('chart_is_heikin_ashi', false)
  const [showIndicators, setShowIndicators] = useLocalStorage('chart_show_indicators', true)
  const [showPatterns, setShowPatterns] = useLocalStorage('chart_show_patterns', false)
  const [showEvents, setShowEvents] = useLocalStorage('chart_show_events', false)

  const [searchInput, setSearchInput] = useState(symbol)
  const [visiblePatterns, setVisiblePatterns] = useState<any[]>([])
  
  // Pattern Scanner State
  const [selectedPattern, setSelectedPattern] = useState<string | null>(null)

  // Chart Comparison State
  const [compareSymbol, setCompareSymbol] = useState<string | null>(null)
  const [compareInput, setCompareInput] = useState('')
  const [compareData, setCompareData] = useState<any[]>([])
  
  // Bar Replay State
  const [replayMode, setReplayMode] = useState(false)
  const [isReplaying, setIsReplaying] = useState(false)
  const [replayIndex, setReplayIndex] = useState(-1)
  const [replaySpeed, setReplaySpeed] = useState(500)


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
  
  const compareSeriesRef = useRef<ISeriesApi<'Line'> | null>(null)
  
  const tradePriceLinesRef = useRef<any[]>([])

  const patternsRef = useRef<any[]>([])
  const lastCandleRef = useRef<CandlestickData | null>(null)
  const lastVolumeRef = useRef<HistogramData | null>(null)

  const [signals, setSignals] = useState<Signal[]>([])
  const [aiScore, setAiScore] = useState<AIScore | null>(null)
  const [sentiment, setSentiment] = useState<any>(null)
  const [indicators, setIndicators] = useState<any>(null)
  const [patterns, setPatterns] = useState<any[]>([])
  const [quote, setQuote] = useState<any>(null)
  const [events, setEvents] = useState<any>(null)
  const [info, setInfo] = useState<any>(null)
  const [risk, setRisk] = useState<any>(null)
  const [swingTrade, setSwingTrade] = useState<any>(null)
  const [loading, setLoading] = useState(false)

  const [rawCandles, setRawCandles] = useState<any[]>([])

  // Drawing Engine State
  const [isDrawing, setIsDrawing] = useState(false)
  const isDrawingRef = useRef(false)
  const currentDrawPrimitiveRef = useRef<TrendlinePrimitive | null>(null)
  const activePrimitivesRef = useRef<TrendlinePrimitive[]>([])

  useEffect(() => {
    isDrawingRef.current = isDrawing;
  }, [isDrawing])

  // ─── Sync persisted chart state to backend (cross-device) ───────────────────
  // Debounced: waits 2s after the last change before sending to server
  useEffect(() => {
    const timer = setTimeout(() => {
      savePreferences({
        chart_symbol: symbol,
        chart_timeframe: timeframe,
        chart_is_heikin_ashi: isHeikinAshi,
        chart_show_indicators: showIndicators,
        chart_show_patterns: showPatterns,
        chart_show_events: showEvents,
      })
    }, 2000)
    return () => clearTimeout(timer)
  }, [symbol, timeframe, isHeikinAshi, showIndicators, showPatterns, showEvents])

  // Sync route params
  useEffect(() => {
    if (paramSymbol && paramSymbol !== symbol) {
      setSymbol(paramSymbol)
    }
  }, [paramSymbol])

  // Bug Fix: Clear selectedPattern when symbol changes (old pattern of TCS shouldn't show on RELIANCE)
  useEffect(() => {
    setSelectedPattern(null)
  }, [symbol])

  // Keyboard Shortcuts: G = go to search, Esc = clear pattern, I = toggle indicators, E = toggle events
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return
      switch (e.key.toLowerCase()) {
        case 'i': setShowIndicators(v => !v); toast.info('Indicators toggled'); break;
        case 'e': setShowEvents(v => !v); toast.info('Events toggled'); break;
        case 'escape': setSelectedPattern(null); setIsDrawing(false); break;
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [])

  // Derive Premium Live Setup
  const getLiveSetup = () => {
    if (!patterns || patterns.length === 0 || !indicators || !rawCandles || rawCandles.length === 0) return null;
    const latestPattern = patterns[patterns.length - 1];
    const latestCandle = rawCandles[rawCandles.length - 1];
    
    // Ensure the pattern is RECENT (within the last 5 candles)
    // Otherwise, it's just an old historical pattern, not a "Live Setup"
    const patternTime = new Date(latestPattern.timestamp).getTime();
    const candleTime = new Date(latestCandle.timestamp).getTime();
    
    // Find the index of the pattern in rawCandles
    const patternCandleIdx = rawCandles.findIndex(c => new Date(c.timestamp).getTime() === patternTime);
    if (patternCandleIdx === -1 || rawCandles.length - 1 - patternCandleIdx > 5) {
      return null; // Pattern is too old (older than 5 candles)
    }
    
    const isBullish = latestPattern.pattern.includes('Bullish') || latestPattern.pattern.includes('Hammer') || latestPattern.pattern.includes('Morning');
    const isBearish = latestPattern.pattern.includes('Bearish') || latestPattern.pattern.includes('Hanging') || latestPattern.pattern.includes('Evening') || latestPattern.pattern.includes('Shooting');
    const isNeutral = latestPattern.pattern.includes('Doji');
    
    let action = 'WAIT';
    let entry = latestCandle.close;
    let sl = 0;
    let target = 0;
    
    if (isBullish && indicators.rsi_14 < 60) { // Relaxed RSI slightly to allow more setups
      action = 'BUY';
      sl = latestCandle.low - (indicators.atr_14 || entry * 0.01);
      target = entry + (entry - sl) * 2; // 1:2 RR
    } else if (isBearish && indicators.rsi_14 > 40) { // Relaxed RSI slightly
      action = 'SELL';
      sl = latestCandle.high + (indicators.atr_14 || entry * 0.01);
      target = entry - (sl - entry) * 2; // 1:2 RR
    } else if (isNeutral) {
      action = 'WATCH';
      sl = entry * 0.98;
      target = entry * 1.04;
    } else {
      return null;
    }
    
    return {
      pattern: latestPattern.pattern,
      action,
      entry,
      sl,
      target,
      time: latestPattern.timestamp
    }
  }
  
  const liveSetup = getLiveSetup();

  // Keep ref in sync for lightweight-charts callbacks
  useEffect(() => {
    patternsRef.current = patterns
  }, [patterns])

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
      // 1. Handle Drawing Preview
      if (currentDrawPrimitiveRef.current && param.point && param.time) {
        const price = candleSeries.coordinateToPrice(param.point.y);
        if (price !== null) {
          currentDrawPrimitiveRef.current.updatePoints(null, { time: param.time, price });
        }
      }

      // 2. Handle Legend update
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

    // Update Visible Patterns for Scanner
    let timeoutId: any = null
    chart.timeScale().subscribeVisibleTimeRangeChange((range: any) => {
      if (range && range.from && range.to) {
        if (timeoutId) clearTimeout(timeoutId)
        timeoutId = setTimeout(() => {
          let fromTime: number = 0;
          let toTime: number = 0;
          
          if (typeof range.from === 'number') {
            fromTime = range.from * 1000;
            toTime = range.to * 1000;
          } else if (typeof range.from === 'string') {
            fromTime = new Date(range.from).getTime();
            toTime = new Date(range.to).getTime();
          } else if (range.from && typeof range.from === 'object') {
            fromTime = new Date(range.from.year, range.from.month - 1, range.from.day).getTime();
            toTime = new Date(range.to.year, range.to.month - 1, range.to.day).getTime();
          }

          const visible = patternsRef.current.filter(p => {
            const t = new Date(p.timestamp).getTime()
            return t >= fromTime && t <= toTime
          })
          setVisiblePatterns(visible.slice(-10).reverse()) // Last 10 visible
        }, 100) // Debounce react state updates
      }
    })

    // Handle Click for Drawing Tool
    chart.subscribeClick((param) => {
      if (!isDrawingRef.current || !param.point || !param.time) return;
      
      const price = candleSeries.coordinateToPrice(param.point.y);
      if (price === null) return;
      const p: Point = { time: param.time, price };

      if (!currentDrawPrimitiveRef.current) {
        // Start drawing
        const primitive = new TrendlinePrimitive(p, p);
        candleSeries.attachPrimitive(primitive);
        currentDrawPrimitiveRef.current = primitive;
        activePrimitivesRef.current.push(primitive);
      } else {
        // Finish drawing
        currentDrawPrimitiveRef.current.updatePoints(null, p);
        currentDrawPrimitiveRef.current = null;
        setIsDrawing(false); // Auto-turn off draw mode after 1 line
      }
    });

    // Handle Resize
    const handleResize = () => {
      if (chartContainerRef.current && rsiContainerRef.current && macdContainerRef.current) {
        chart.applyOptions({ width: chartContainerRef.current.clientWidth })
        rsiChart.applyOptions({ width: rsiContainerRef.current.clientWidth })
        macdChart.applyOptions({ width: macdContainerRef.current.clientWidth })
      }
    }

    // Attach clear function to window or state so UI button can call it
    (window as any).clearDrawings = () => {
      activePrimitivesRef.current.forEach(primitive => {
        candleSeries.detachPrimitive(primitive);
      });
      activePrimitivesRef.current = [];
      setIsDrawing(false);
      currentDrawPrimitiveRef.current = null;
    };
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

  // Load Compare Data
  useEffect(() => {
    if (compareSymbol) {
      stocksApi.getInsight(compareSymbol, timeframe).then(res => {
        setCompareData(res.data.candles || [])
      }).catch(err => console.error(err))
    } else {
      setCompareData([])
    }
  }, [compareSymbol, timeframe])

  // Replay Engine Loop
  useEffect(() => {
    if (!isReplaying || !replayMode || rawCandles.length === 0) return;
    
    const timer = setInterval(() => {
      setReplayIndex(prev => {
        if (prev >= rawCandles.length - 1) {
          setIsReplaying(false);
          return prev;
        }
        return prev + 1;
      })
    }, replaySpeed);
    
    return () => clearInterval(timer);
  }, [isReplaying, replayMode, rawCandles, replaySpeed])

  // Process Candles on rawCandles or HA toggle change
  useEffect(() => {
    let sourceCandles = rawCandles;
    if (replayMode && replayIndex >= 0) {
      sourceCandles = rawCandles.slice(0, replayIndex + 1);
    }
    
    if (sourceCandles.length > 0 && candleSeriesRef.current && volumeSeriesRef.current) {
      // Defensively deduplicate and sort source candles to prevent lightweight-charts assertion crashes
      const uniqueCandlesMap = new Map();
      sourceCandles.forEach((c: any) => uniqueCandlesMap.set(c.timestamp, c));
      const deduplicatedCandles = Array.from(uniqueCandlesMap.values()).sort((a: any, b: any) => 
        new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
      );

      const candlesToUse = isHeikinAshi ? toHeikinAshi(deduplicatedCandles) : deduplicatedCandles
      
      const getTime = (timestamp: string): Time => {
        const isDaily = timeframe === '1d' || timeframe === '1w' || timeframe === '1mo';
        if (isDaily) {
          return timestamp.split('T')[0] as Time;
        }
        // Force the exchange local time to render perfectly by faking UTC
        const fakeUtcString = timestamp.substring(0, 19) + 'Z';
        return (new Date(fakeUtcString).getTime() / 1000) as Time;
      }

      // Track seen times to rigorously prevent duplicates in the final chart data
      const seenTimes = new Set();
      const chartData: CandlestickData[] = [];
      const volumeData: HistogramData[] = [];
      const validCandlesToUse: any[] = [];
      
      candlesToUse.forEach((c: any) => {
        const time = getTime(c.timestamp);
        if (!seenTimes.has(time)) {
          seenTimes.add(time);
          validCandlesToUse.push(c);
          chartData.push({ time, open: c.open, high: c.high, low: c.low, close: c.close });
        }
      });
      
      const validTimes = new Set(chartData.map(c => c.time));
      
      validCandlesToUse.forEach((c: any) => {
        volumeData.push({
          time: getTime(c.timestamp),
          value: c.volume,
          color: c.close > c.open ? 'rgba(16, 185, 129, 0.4)' : 'rgba(239, 68, 68, 0.4)'
        });
      });

      // Remove old price lines BEFORE setting new data to prevent scale corruption
      if (tradePriceLinesRef.current.length > 0) {
        tradePriceLinesRef.current.forEach(pl => candleSeriesRef.current?.removePriceLine(pl));
        tradePriceLinesRef.current = [];
      }

      candleSeriesRef.current.setData(chartData)
      volumeSeriesRef.current.setData(volumeData)
      lastCandleRef.current = chartData.length > 0 ? { ...chartData[chartData.length - 1] } : null
      lastVolumeRef.current = volumeData.length > 0 ? { ...volumeData[volumeData.length - 1] } : null
      
      // Force auto-scale reset for the price axis when data changes (e.g. from 1500 to 7)
      if (chartRef.current) {
         chartRef.current.priceScale('right').applyOptions({ autoScale: true });
      }
      
      // Base markers will be assembled below based on toggles
      const obMarkers: any[] = []

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

         validCandlesToUse.forEach((c: any) => {
           const time = getTime(c.timestamp)
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
      } else {
         ema9SeriesRef.current?.setData([])
         ema21SeriesRef.current?.setData([])
         vwapSeriesRef.current?.setData([])
         rsiSeriesRef.current?.setData([])
         if ((chartRef.current as any).supertrendSeries) {
           (chartRef.current as any).supertrendSeries.setData([])
         }
      }
      
      // Merge pattern markers, OB markers, and Event markers
         if (candleSeriesRef.current) {
            const allMarkers: any[] = []
            
            if (showIndicators) {
                allMarkers.push(...obMarkers)
            }
            
            if (selectedPattern) {
              const markers: any[] = patterns.filter(p => p.pattern === selectedPattern).map(p => {
                const isBullish = p.pattern.includes('Bullish') || p.pattern.includes('Hammer')
                return {
                  time: getTime(p.timestamp),
                  position: isBullish ? 'belowBar' : 'aboveBar',
                  color: isBullish ? '#10b981' : '#ef4444',
                  shape: isBullish ? 'arrowUp' : 'arrowDown',
                  text: p.pattern
                }
              })
              allMarkers.push(...markers)
            }
            
            if (showEvents && events) {
              // Rewritten snap: find closest candle by epoch, return EXACTLY that candle's chartData.time
              // This guarantees the returned value is always in validTimes
              const snapToValidTime = (isoDateStr: string): Time | null => {
                 if (!isoDateStr || chartData.length === 0) return null;
                 
                 // Normalize: handle timezone offset like +05:30 and spaces
                 const safeDateStr = isoDateStr.toString().trim()
                   .replace(' ', 'T')  // "2024-01-15 00:00:00" → "2024-01-15T00:00:00"
                   .replace(/([+-]\d{2})(\d{2})$/, '$1:$2') // Fix missing colon in +0530 → +05:30
                 
                 const targetEpoch = new Date(safeDateStr).getTime();
                 if (isNaN(targetEpoch)) {
                   console.warn('[Events] Could not parse date:', isoDateStr);
                   return null;
                 }
 
                 let closestIndex = 0;
                 let minDiff = Infinity;
                 
                 for (let i = 0; i < rawCandles.length; i++) {
                    const cEpoch = new Date(rawCandles[i].timestamp.replace(' ', 'T')).getTime();
                    const diff = Math.abs(cEpoch - targetEpoch);
                    if (diff < minDiff) {
                       minDiff = diff;
                       closestIndex = i;
                    }
                 }
                 // Return the EXACT chartData time so validTimes.has() always passes
                 return chartData[closestIndex]?.time ?? null;
              };

              events.dividends?.forEach((d: any) => {
                const snappedTime = snapToValidTime(d.date);
                if (snappedTime !== null) {
                  allMarkers.push({
                    time: snappedTime,
                    position: 'belowBar',
                    color: '#8b5cf6',
                    shape: 'arrowUp',
                    text: `₹${d.amount?.toFixed(2) ?? '?'} Div`
                  })
                }
              })
              if (events.earnings_date) {
                const snappedTime = snapToValidTime(events.earnings_date);
                if (snappedTime !== null) {
                  allMarkers.push({
                    time: snappedTime,
                    position: 'aboveBar',
                    color: '#3b82f6',
                    shape: 'arrowDown',
                    text: 'Earnings'
                  })
                }
              }
            }
            
            allMarkers.sort((a, b) => {
              const tA = typeof a.time === 'string' ? new Date(a.time).getTime() : a.time as number
              const tB = typeof b.time === 'string' ? new Date(b.time).getTime() : b.time as number
              return tA - tB
            })
            
            // validTimes contains chartData[i].time exactly; snapped times are guaranteed to match
            const validMarkers = allMarkers.filter(m => validTimes.has(m.time));
            candleSeriesRef.current.setMarkers(validMarkers)
            
            // Render Strategy Tester Visual Markers (Price Lines)

            if (swingTrade && !swingTrade.error && swingTrade.action !== 'HOLD' && swingTrade.trade_plan) {
              const entryLine = candleSeriesRef.current?.createPriceLine({
                  price: swingTrade.trade_plan.entry_price,
                  color: 'rgba(59, 130, 246, 0.8)', // blue
                  lineWidth: 2,
                  lineStyle: 2,
                  axisLabelVisible: true,
                  title: 'Entry',
              });
              const slLine = candleSeriesRef.current?.createPriceLine({
                  price: swingTrade.trade_plan.stop_loss,
                  color: 'rgba(239, 68, 68, 0.8)', // red
                  lineWidth: 2,
                  lineStyle: 2,
                  axisLabelVisible: true,
                  title: 'Stop Loss',
              });
              const targetLine = candleSeriesRef.current?.createPriceLine({
                  price: swingTrade.trade_plan.target_price,
                  color: 'rgba(16, 185, 129, 0.8)', // green
                  lineWidth: 2,
                  lineStyle: 2,
                  axisLabelVisible: true,
                  title: 'Target',
              });
              if (entryLine) tradePriceLinesRef.current.push(entryLine);
              if (slLine) tradePriceLinesRef.current.push(slLine);
              if (targetLine) tradePriceLinesRef.current.push(targetLine);
            }
         }
      
      // Handle Compare Series Render
      if (compareData.length > 0 && chartRef.current) {
        if (!compareSeriesRef.current) {
          compareSeriesRef.current = chartRef.current.addLineSeries({ 
            color: '#fbbf24', 
            lineWidth: 2,
            priceScaleId: 'right'
          });
          chartRef.current.priceScale('right').applyOptions({
            mode: 2, // Percentage scale
          });
        }
        const compChartData: LineData[] = compareData.map((c: any) => ({
          time: getTime(c.timestamp),
          value: c.close,
        })).filter(c => validTimes.has(c.time));
        
        let visibleCompData = compChartData;
        if (replayMode && replayIndex >= 0) {
           visibleCompData = compChartData.slice(0, replayIndex + 1);
        }
        compareSeriesRef.current.setData(visibleCompData);
      } else {
        if (compareSeriesRef.current && chartRef.current) {
          chartRef.current.removeSeries(compareSeriesRef.current);
          compareSeriesRef.current = null;
          chartRef.current.priceScale('right').applyOptions({
            mode: 0, // Normal scale
          });
        }
      }
      
      const totalCandles = sourceCandles.length;
      if (totalCandles > 0) {
        // By default, don't squish all data. Show the last 60 candles (e.g. ~3 months on 1D, ~2 days on 15m)
        const visibleCandles = Math.min(60, totalCandles);
        const fromIndex = totalCandles - visibleCandles;
        const toIndex = totalCandles - 1;
        
        chartRef.current?.timeScale().setVisibleLogicalRange({ from: fromIndex, to: toIndex })
        macdChartRef.current?.timeScale().setVisibleLogicalRange({ from: fromIndex, to: toIndex })
      } else {
        chartRef.current?.timeScale().fitContent()
        macdChartRef.current?.timeScale().fitContent()
      }

      
      const isDaily = timeframe === '1d' || timeframe === '1w' || timeframe === '1mo';
      chartRef.current?.applyOptions({ timeScale: { timeVisible: !isDaily } })
    }
  }, [rawCandles, isHeikinAshi, showIndicators, patterns, showEvents, events, timeframe, swingTrade, selectedPattern, compareData, replayMode, replayIndex])

  // Auto-pan to selected pattern
  useEffect(() => {
    if (selectedPattern && chartRef.current && rawCandles.length > 0 && patterns.length > 0) {
      // Find the most recent occurrence of this pattern
      const matchingPatterns = patterns.filter(p => p.pattern === selectedPattern);
      if (matchingPatterns.length > 0) {
        const latestPattern = matchingPatterns[matchingPatterns.length - 1];
        const patternIndex = rawCandles.findIndex(c => c.timestamp === latestPattern.timestamp);
        
        if (patternIndex !== -1) {
          // Pan to show this pattern (40 candles before, 10 after)
          const fromIndex = Math.max(0, patternIndex - 40);
          const toIndex = Math.min(rawCandles.length - 1, patternIndex + 10);
          chartRef.current.timeScale().setVisibleLogicalRange({ from: fromIndex, to: toIndex });
        }
      }
    }
  }, [selectedPattern, patterns, rawCandles]);

  // Fix Lightweight Charts 0-width issue when container changes from display: none to display: block
  useEffect(() => {
    if (showIndicators) {
      setTimeout(() => {
        if (rsiContainerRef.current && rsiChartRef.current) {
          rsiChartRef.current.applyOptions({ width: rsiContainerRef.current.clientWidth });
        }
        if (macdContainerRef.current && macdChartRef.current) {
          macdChartRef.current.applyOptions({ width: macdContainerRef.current.clientWidth });
        }
      }, 50); // allow DOM to update
    }
  }, [showIndicators]);

  // Apply Theme to Lightweight Charts Dynamically
  useEffect(() => {
    const bgColor = theme === 'light' ? '#ffffff' : '#0f1629';
    const textColor = theme === 'light' ? '#444444' : '#8b9dc3';
    const gridColor = theme === 'light' ? '#f0f0f0' : '#1e2d4a';
    
    const applyThemeToChart = (chart: IChartApi | null) => {
      if (!chart) return;
      chart.applyOptions({
        layout: { background: { color: bgColor }, textColor: textColor },
        grid: { vertLines: { color: gridColor }, horzLines: { color: gridColor } },
        timeScale: { borderColor: gridColor },
        rightPriceScale: { borderColor: gridColor },
      });
    };

    applyThemeToChart(chartRef.current);
    applyThemeToChart(rsiChartRef.current);
    applyThemeToChart(macdChartRef.current);
  }, [theme]);

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
        setQuote(insight.quote || null)
        setPatterns(insight.patterns || [])
        setSignals(insight.signals || [])
        setAiScore(insight.ai_score || null)
        setRisk(insight.risk || null)
        setSwingTrade(insight.swing_trade || null)
        setEvents(insight.events || null)
        setIndicators(insight.indicators)
      } else {
        // Handle failed API insights (like timeouts) safely without showing fake data
        setRawCandles([])
        setSwingTrade(null)
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
    if (!token) return

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    let ws: WebSocket | null = null

    try {
      ws = new WebSocket(`${protocol}//${window.location.host}/ws?token=${token}`)

      ws.onopen = () => {
        if (ws && ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'subscribe', channel: 'market_data', symbol }))
        }
      }

      ws.onerror = () => {
        // Suppress unhandled socket disconnect errors in dev
      }

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          const cleanParam = symbol.replace(/\.NS$/, '').replace(/\.BO$/, '').toUpperCase()
          const cleanMsg = (data.symbol || '').replace(/\.NS$/, '').replace(/\.BO$/, '').toUpperCase()
          
          if (data.type === 'market_update' && (cleanMsg === cleanParam || cleanMsg === symbol.toUpperCase())) {
            const newPrice = Number(data.price)
            if (newPrice > 0) {
              setQuote((prev: any) => prev ? {
                ...prev,
                price: newPrice,
                change: data.change !== undefined ? data.change : prev.change,
                change_pct: data.change_pct !== undefined ? data.change_pct : prev.change_pct,
              } : prev)

              // Dynamically update the latest live candle in the chart in real-time
              if (candleSeriesRef.current && lastCandleRef.current) {
                const currentLast = lastCandleRef.current
                const updatedCandle: CandlestickData = {
                  time: currentLast.time,
                  open: currentLast.open,
                  high: Math.max(Number(currentLast.high), newPrice),
                  low: Math.min(Number(currentLast.low), newPrice),
                  close: newPrice,
                }
                lastCandleRef.current = updatedCandle
                try {
                  candleSeriesRef.current.update(updatedCandle)
                } catch (_) {}
              }

              // Dynamically update volume bar if provided
              if (volumeSeriesRef.current && lastVolumeRef.current && data.volume) {
                const currentVol = lastVolumeRef.current
                const updatedVol: HistogramData = {
                  time: currentVol.time,
                  value: Number(data.volume),
                  color: (lastCandleRef.current && lastCandleRef.current.close >= lastCandleRef.current.open)
                    ? 'rgba(16, 185, 129, 0.4)' 
                    : 'rgba(239, 68, 68, 0.4)'
                }
                lastVolumeRef.current = updatedVol
                try {
                  volumeSeriesRef.current.update(updatedVol)
                } catch (_) {}
              }
            }
          }
        } catch (err) {
          console.error('WebSocket tick processing error:', err)
        }
      }
    } catch (e) {
      console.warn('WebSocket init skipped:', e)
    }

    return () => {
      if (ws) {
        if (ws.readyState === WebSocket.OPEN) {
          ws.close()
        } else if (ws.readyState === WebSocket.CONNECTING) {
          ws.onopen = () => {
            try { ws?.close() } catch (_) {}
          }
        }
      }
    }
  }, [symbol])

  function handleSearch(e: React.FormEvent) {
    e.preventDefault()
    const cleaned = searchInput.toUpperCase().trim().replace('.NS', '')
    setSymbol(cleaned)
    navigate(`/chart/${cleaned}`)
  }

  function handleCompareSearch(e: React.FormEvent) {
    e.preventDefault()
    if (!compareInput.trim()) {
      setCompareSymbol(null)
      return
    }
    const cleaned = compareInput.toUpperCase().trim().replace('.NS', '') + '.NS'
    setCompareSymbol(cleaned)
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
        <div style={{ flex: 1, minWidth: 240, display: 'flex', gap: 8 }}>
          <StockSearchBox placeholder="Search symbol or company..." width="300px" />
          
          <div style={{ position: 'relative' }}>
            <StockSearchBox 
              placeholder="Compare company..." 
              width={220}
              autoNavigate={false}
              clearOnSelect={false}
              value={compareInput}
              onChange={setCompareInput}
              onSelect={(symbol) => {
                const cleaned = symbol.toUpperCase().trim().replace('.NS', '') + '.NS';
                setCompareSymbol(cleaned);
              }}
            />
            {compareSymbol && (
              <button type="button" onClick={() => { setCompareSymbol(null); setCompareInput(''); }} style={{ position: 'absolute', right: 10, top: 10, background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-muted)', zIndex: 10 }}>×</button>
            )}
          </div>
        </div>

        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <select 
             value={selectedPattern || ""}
             onChange={(e) => {
               const val = e.target.value;
               if (val === 'clear') setSelectedPattern(null);
               else setSelectedPattern(val);
             }}
             className="input"
             style={{ padding: '6px 12px', fontSize: 13, height: '34px', cursor: 'pointer', borderRadius: '6px', maxWidth: 160 }}
          >
             <option value="" disabled>👁️ Patterns Overlay</option>
             <option value="clear">None (Hide Patterns)</option>
             <option disabled>──────────</option>
             {Array.from(new Set(visiblePatterns.map(p => p.pattern))).map(patternName => (
               <option key={patternName as string} value={patternName as string}>
                 {patternName as string}
               </option>
             ))}
          </select>

          <div style={{ display: 'flex', gap: 4, alignItems: 'center', background: 'var(--color-bg-secondary)', padding: '4px', borderRadius: '8px', border: '1px solid var(--color-border)' }}>
            <button 
              onClick={() => setShowIndicators(!showIndicators)}
              className="btn btn-ghost" 
              style={{ fontSize: 13, padding: '4px 10px', height: '28px', color: showIndicators ? 'var(--color-accent-blue)' : 'var(--color-text-muted)', fontWeight: showIndicators ? 600 : 400 }}
              title="Toggle RSI, MACD & EMAs"
            >
              <Activity size={14} style={{ marginRight: 4 }} /> Indicators
            </button>
            <button 
              onClick={() => setShowEvents(!showEvents)}
              className="btn btn-ghost" 
              style={{ fontSize: 13, padding: '4px 10px', height: '28px', color: showEvents ? 'var(--color-accent-blue)' : 'var(--color-text-muted)', fontWeight: showEvents ? 600 : 400 }}
              title="Toggle Dividends & Earnings"
            >
              <Zap size={14} style={{ marginRight: 4 }} /> Events
            </button>
            <div style={{ width: 1, height: 16, background: 'var(--color-border)', margin: '0 4px' }} />
            <button 
              onClick={() => setIsDrawing(!isDrawing)}
              className="btn btn-ghost" 
              style={{ fontSize: 13, padding: '4px 10px', height: '28px', color: isDrawing ? 'var(--color-accent-blue)' : 'var(--color-text-muted)', fontWeight: isDrawing ? 600 : 400 }}
              title="Draw Custom Trendline"
            >
              <Pencil size={14} style={{ marginRight: 4 }} /> {isDrawing ? 'Cancel' : 'Draw'}
            </button>
            <button 
              onClick={() => (window as any).clearDrawings?.()}
              className="btn btn-ghost" 
              style={{ fontSize: 13, padding: '4px 10px', height: '28px', color: 'var(--color-text-muted)' }}
              title="Clear all drawings"
            >
              Clear
            </button>
            <div style={{ width: 1, height: 16, background: 'var(--color-border)', margin: '0 4px' }} />
            <button 
              onClick={() => {
                if (!replayMode) {
                  setReplayMode(true);
                  setReplayIndex(Math.floor(rawCandles.length * 0.7)); // start replay from 70% of history
                } else {
                  setReplayMode(false);
                  setIsReplaying(false);
                }
              }}
              className="btn btn-ghost" 
              style={{ fontSize: 13, padding: '4px 10px', height: '28px', color: replayMode ? '#f59e0b' : 'var(--color-text-muted)', fontWeight: replayMode ? 600 : 400 }}
              title="Bar Replay Simulator"
            >
              <Clock size={14} style={{ marginRight: 4 }} /> Replay
            </button>
          </div>
          
          <button onClick={() => setIsHeikinAshi(!isHeikinAshi)} className={`btn ${isHeikinAshi ? 'btn-primary' : 'btn-secondary'}`} style={{fontSize: 13, padding: '6px 12px'}}>
            <ListFilter size={14}/> Heikin Ashi
          </button>
          
          <div style={{ marginLeft: 16, borderLeft: '1px solid var(--color-border)', paddingLeft: 16 }}>
            <select
              value={timeframe}
              onChange={(e) => setTimeframe(e.target.value)}
              className="input"
              style={{ padding: '6px 12px', fontSize: 13, height: '34px', cursor: 'pointer', borderRadius: '6px' }}
            >
              {TIMEFRAMES.map(tf => (
                <option key={tf} value={tf}>
                  {TIMEFRAME_LABELS[tf]}
                </option>
              ))}
            </select>
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
            <div><div style={{ fontSize: 11, color: 'var(--color-text-muted)' }}>52W High</div><div className="mono">₹{quote['52w_high'] ? Number(quote['52w_high']).toLocaleString('en-IN', { maximumFractionDigits: 2 }) : '—'}</div></div>
            <div><div style={{ fontSize: 11, color: 'var(--color-text-muted)' }}>52W Low</div><div className="mono">₹{quote['52w_low'] ? Number(quote['52w_low']).toLocaleString('en-IN', { maximumFractionDigits: 2 }) : '—'}</div></div>
            <div><div style={{ fontSize: 11, color: 'var(--color-text-muted)' }}>Volume</div><div className="mono">{quote.volume ? Number(quote.volume).toLocaleString('en-IN') : '—'}</div></div>
            <div><div style={{ fontSize: 11, color: 'var(--color-text-muted)' }}>Market Cap</div><div className="mono">{quote.market_cap ? (quote.market_cap >= 1e7 ? `₹${(quote.market_cap / 1e7).toLocaleString('en-IN', { maximumFractionDigits: 1 })} Cr` : `₹${(quote.market_cap / 1e9).toFixed(1)} B`) : '—'}</div></div>
          </div>
        {/* AI Score Ring */}
          <div style={{ marginLeft: 'auto', textAlign: 'center', flexShrink: 0 }}>
            {user?.subscription_tier === 'PRO' ? (
              aiScore ? (() => {
                const confidence = Math.round(aiScore.confidence * 100);
                const r = 28;
                const circ = 2 * Math.PI * r;
                const offset = circ - (confidence / 100) * circ;
                const color = aiScore.score === 'BUY' ? '#10b981' : aiScore.score === 'SELL' ? '#ef4444' : '#f59e0b';
                return (
                  <div style={{ position: 'relative', width: 76, height: 76, display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>
                    <svg width="76" height="76" style={{ transform: 'rotate(-90deg)', position: 'absolute' }}>
                      <circle cx="38" cy="38" r={r} fill="none" stroke="var(--color-border)" strokeWidth="5" />
                      <circle cx="38" cy="38" r={r} fill="none" stroke={color} strokeWidth="5"
                        strokeDasharray={circ} strokeDashoffset={offset} strokeLinecap="round"
                        style={{ transition: 'stroke-dashoffset 1.2s cubic-bezier(0.16,1,0.3,1), stroke 0.4s ease' }}
                      />
                    </svg>
                    <div style={{ textAlign: 'center', zIndex: 1 }}>
                      <div style={{ fontSize: 15, fontWeight: 800, color }}>{aiScore.score}</div>
                      <div style={{ fontSize: 10, color: 'var(--color-text-muted)' }}>{confidence}%</div>
                    </div>
                  </div>
                );
              })()
                : <div style={{ width: 76, height: 76, display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div className="skeleton" style={{ width: 60, height: 60, borderRadius: '50%' }} /></div>
            ) : (
              <button onClick={() => navigate('/pricing')} className="badge badge-neutral" style={{ fontSize: 12, padding: '6px 12px', cursor: 'pointer', border: '1px solid var(--color-accent-blue)' }}>
                <Lock size={12} style={{ display: 'inline', marginRight: 4 }}/> PRO
              </button>
            )}
          </div>
        </div>
      )}

      {/* Main Chart + Sub-charts */}
      <div style={{ position: 'relative' }}>
        {replayMode && (
          <ChartReplayControls 
            isReplaying={isReplaying}
            onToggleReplay={() => setIsReplaying(!isReplaying)}
            onStep={() => setReplayIndex(i => Math.min(i + 1, rawCandles.length - 1))}
            speed={replaySpeed}
            onSpeedChange={setReplaySpeed}
            onClose={() => { setReplayMode(false); setIsReplaying(false); }}
          />
        )}
        <div className="card" style={{ padding: '0', overflow: 'hidden' }}>
          <div ref={chartContainerRef} style={{ width: '100%', position: 'relative', minHeight: 450 }}>
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
          <div ref={rsiContainerRef} style={{ width: '100%', borderTop: '1px solid var(--color-border)', display: showIndicators ? 'block' : 'none' }} />
          <div ref={macdContainerRef} style={{ width: '100%', display: showIndicators ? 'block' : 'none' }} />
        </div>
      </div>

      {/* UX Redesign: Pattern Scanner & Live Setup */}
      <div className="grid-2" style={{ gap: 16, marginBottom: 16 }}>
        {/* Pattern Scanner (Visible Area) */}
        <div className="card">
          <div className="card-header">
            <span className="card-title"><ListFilter size={15} style={{ marginRight: 6 }} />Pattern Scanner (Visible Area)</span>
            <span className="badge badge-secondary">{visiblePatterns.length} found</span>
          </div>
          {visiblePatterns.length === 0 ? (
            <div style={{ color: 'var(--color-text-muted)', fontSize: 13, textAlign: 'center', padding: '20px 0' }}>
              No patterns detected in the current visible area. Zoom out or pan to scan more data.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8, maxHeight: '200px', overflowY: 'auto' }}>
              {visiblePatterns.map((p, idx) => {
                const isBull = p.pattern.includes('Bullish') || p.pattern.includes('Hammer');
                return (
                  <div key={idx} style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 12px', background: 'var(--color-bg-secondary)', borderRadius: 6 }}>
                    <span style={{ fontSize: 13, fontWeight: 500, color: isBull ? 'var(--color-bullish)' : 'var(--color-bearish)' }}>
                      {p.pattern}
                    </span>
                    <span className="mono" style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>
                      {new Date(p.timestamp).toLocaleDateString()} {timeframe !== '1d' && timeframe !== '1w' ? new Date(p.timestamp).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}) : ''}
                    </span>
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* Premium Live Setup */}
        <div className="card" style={{ border: '1px solid var(--color-accent-blue)', position: 'relative', overflow: 'hidden' }}>
          <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: 3, background: 'linear-gradient(90deg, #3b82f6, #8b5cf6, #06b6d4)', backgroundSize: '200% 100%', animation: 'gradientShift 3s ease infinite' }} />
          <div className="card-header">
            <span className="card-title" style={{ color: 'var(--color-accent-blue)' }}>★ Premium Live Setup</span>
            {liveSetup && <span className={`badge ${liveSetup.action === 'BUY' ? 'badge-buy' : liveSetup.action === 'SELL' ? 'badge-sell' : 'badge-watch'}`}>{liveSetup.action}</span>}
          </div>
          
          {!liveSetup ? (
            <div style={{ color: 'var(--color-text-muted)', fontSize: 13, textAlign: 'center', padding: '20px 0' }}>
              Scanning latest price action... No high-probability actionable setups detected right now.
            </div>
          ) : (
            <div>
              <div style={{ marginBottom: 12, fontSize: 13, color: 'var(--color-text-secondary)' }}>
                Triggered by <strong>{liveSetup.pattern}</strong> pattern combined with indicator confluence.
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8, marginBottom: 16 }}>
                <div style={{ background: 'var(--color-bg-secondary)', padding: '10px', borderRadius: 8 }}>
                  <div style={{ fontSize: 11, color: 'var(--color-text-muted)' }}>Entry</div>
                  <div className="mono" style={{ fontWeight: 600, color: 'var(--color-text-primary)' }}>₹{liveSetup.entry.toFixed(2)}</div>
                </div>
                <div style={{ background: 'rgba(239, 68, 68, 0.1)', padding: '10px', borderRadius: 8, border: '1px solid rgba(239, 68, 68, 0.2)' }}>
                  <div style={{ fontSize: 11, color: 'var(--color-bearish)' }}>Stop Loss</div>
                  <div className="mono" style={{ fontWeight: 600, color: 'var(--color-bearish)' }}>₹{liveSetup.sl.toFixed(2)}</div>
                </div>
                <div style={{ background: 'rgba(16, 185, 129, 0.1)', padding: '10px', borderRadius: 8, border: '1px solid rgba(16, 185, 129, 0.2)' }}>
                  <div style={{ fontSize: 11, color: 'var(--color-bullish)' }}>Target</div>
                  <div className="mono" style={{ fontWeight: 600, color: 'var(--color-bullish)' }}>₹{liveSetup.target.toFixed(2)}</div>
                </div>
              </div>
              <button
                className={`btn ${liveSetup.action === 'BUY' ? 'btn-success' : liveSetup.action === 'SELL' ? 'btn-danger' : 'btn-primary'}`}
                style={{ width: '100%', padding: '10px', fontWeight: 600, letterSpacing: '0.5px', justifyContent: 'center' }}
                onClick={async () => {
                  try {
                    const { paperTradingApi } = await import('../services/api')
                    await paperTradingApi.place({
                      symbol: symbol.endsWith('.NS') ? symbol : `${symbol}.NS`,
                      direction: liveSetup.action === 'SELL' ? 'SELL' : 'BUY',
                      quantity: 1,
                      order_type: 'MARKET',
                      stop_loss: liveSetup.sl,
                      target_price: liveSetup.target,
                    })
                    toast.success(`Paper ${liveSetup.action} order placed!`, `${symbol} @ ₹${liveSetup.entry.toFixed(2)} | SL: ₹${liveSetup.sl.toFixed(2)} | Target: ₹${liveSetup.target.toFixed(2)}`)
                  } catch (err: any) {
                    toast.error('Trade failed', err?.response?.data?.detail || 'Could not place paper trade. Check positions page.')
                  }
                }}
              >
                <ShoppingCart size={15} /> 1-Click Paper {liveSetup.action}
              </button>
              <div style={{ fontSize: 10, color: 'var(--color-text-muted)', textAlign: 'center', marginTop: 6 }}>
                Paper trade only · Not financial advice · <kbd style={{ background: 'var(--color-border)', padding: '1px 4px', borderRadius: 3, fontSize: 10 }}>I</kbd> Indicators · <kbd style={{ background: 'var(--color-border)', padding: '1px 4px', borderRadius: 3, fontSize: 10 }}>E</kbd> Events · <kbd style={{ background: 'var(--color-border)', padding: '1px 4px', borderRadius: 3, fontSize: 10 }}>Esc</kbd> Clear
              </div>
            </div>
          )}
        </div>
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
                {swingTrade.action || 'HOLD'} (Score: {(swingTrade.total_score ?? 50).toFixed(1)})
              </span>
            </div>
            
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 16 }}>
              <div style={{ padding: 12, background: 'rgba(255,255,255,0.02)', borderRadius: 8 }}>
                <div style={{ fontSize: 12, color: 'var(--color-text-muted)', marginBottom: 4 }}>Expected Duration</div>
                <div style={{ fontSize: 16, fontWeight: 600, color: 'var(--color-text-primary)' }}>{swingTrade.trade_plan?.estimated_hold_time || '3 to 4 Days'}</div>
              </div>
              <div style={{ padding: 12, background: 'rgba(255,255,255,0.02)', borderRadius: 8 }}>
                <div style={{ fontSize: 12, color: 'var(--color-text-muted)', marginBottom: 4 }}>
                  {swingTrade.action === 'SELL' ? 'Expected Drop' : (swingTrade.action === 'HOLD' ? 'Upper Resistance' : 'Potential Gain')}
                </div>
                <div style={{ fontSize: 16, fontWeight: 600, color: swingTrade.action === 'SELL' ? 'var(--color-bearish)' : (swingTrade.action === 'HOLD' ? 'var(--color-text-primary)' : 'var(--color-bullish)') }}>
                  {swingTrade.action === 'SELL' ? '-' : '+'}{(swingTrade.trade_plan?.expected_gain_pct ?? 15).toFixed(2)}%
                </div>
              </div>
              <div style={{ padding: 12, background: 'rgba(255,255,255,0.02)', borderRadius: 8 }}>
                <div style={{ fontSize: 12, color: 'var(--color-text-muted)', marginBottom: 4 }}>
                  {swingTrade.action === 'HOLD' ? 'Lower Support' : 'Max Risk (Stop Loss)'}
                </div>
                <div style={{ fontSize: 16, fontWeight: 600, color: swingTrade.action === 'HOLD' ? 'var(--color-text-primary)' : 'var(--color-bearish)' }}>
                  -{(swingTrade.trade_plan?.risk_pct ?? 7).toFixed(2)}%
                </div>
              </div>
              <div style={{ padding: 12, background: 'rgba(255,255,255,0.02)', borderRadius: 8 }}>
                <div style={{ fontSize: 12, color: 'var(--color-text-muted)', marginBottom: 4 }}>
                  {swingTrade.action === 'HOLD' ? 'Current Level' : 'Entry Price'}
                </div>
                <div style={{ fontSize: 16, fontWeight: 600, color: 'var(--color-text-primary)' }}>₹{(swingTrade.trade_plan?.entry_price ?? 0).toFixed(2)}</div>
              </div>
              <div style={{ padding: 12, background: 'rgba(255,255,255,0.02)', borderRadius: 8 }}>
                <div style={{ fontSize: 12, color: 'var(--color-text-muted)', marginBottom: 4 }}>
                  {swingTrade.action === 'HOLD' ? 'Lower Bound' : 'Stop Loss Level'}
                </div>
                <div style={{ fontSize: 16, fontWeight: 600, color: 'var(--color-text-primary)' }}>₹{(swingTrade.trade_plan?.stop_loss ?? 1400).toFixed(2)}</div>
              </div>
              <div style={{ padding: 12, background: 'rgba(255,255,255,0.02)', borderRadius: 8 }}>
                <div style={{ fontSize: 12, color: 'var(--color-text-muted)', marginBottom: 4 }}>
                  {swingTrade.action === 'HOLD' ? 'Upper Bound' : 'Target Price'}
                </div>
                <div style={{ fontSize: 16, fontWeight: 600, color: 'var(--color-text-primary)' }}>₹{(swingTrade.trade_plan?.target_price ?? 1700).toFixed(2)}</div>
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
