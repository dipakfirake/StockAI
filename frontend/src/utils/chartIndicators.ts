/**
 * Pure chart indicator catalog, toggle state helpers, preset configs,
 * and viewport-safe dropdown horizontal alignment calculations.
 */

export type IndicatorCategory = 'overlay' | 'oscillator'

export type IndicatorPresetKey = 'clean' | 'ema21' | 'trend' | 'bb' | 'momentum' | 'all'

export interface ChartIndicatorDefinition {
  key: string
  label: string
  category: IndicatorCategory
  group: string
  color: string
  desc: string
}

export const CHART_INDICATOR_CATALOG: ChartIndicatorDefinition[] = [
  { key: 'ema21', label: 'EMA 21', category: 'overlay', group: 'Moving Averages', color: '#f59e0b', desc: 'Pullback Base & Dynamic Support' },
  { key: 'ema9', label: 'EMA 9', category: 'overlay', group: 'Moving Averages', color: '#3b82f6', desc: 'Fast Momentum & Short-Term Trend' },
  { key: 'ema50', label: 'EMA 50', category: 'overlay', group: 'Moving Averages', color: '#8b5cf6', desc: 'Intermediate Trend & Crossover Line' },
  { key: 'ema200', label: 'EMA 200', category: 'overlay', group: 'Moving Averages', color: '#ec4899', desc: 'Long-Term Macro Institutional Line' },
  { key: 'vwap', label: 'VWAP', category: 'overlay', group: 'Volume Weighted', color: '#d946ef', desc: 'Volume Weighted Average Price Benchmark' },
  { key: 'supertrend', label: 'Supertrend', category: 'overlay', group: 'Trend Following', color: '#10b981', desc: 'Dynamic Trailing Stop & Direction' },
  { key: 'bb', label: 'Bollinger Bands', category: 'overlay', group: 'Volatility', color: '#06b6d4', desc: '20-SMA Upper/Lower Volatility Bands' },
  { key: 'rsi', label: 'RSI (14)', category: 'oscillator', group: 'Oscillators', color: '#a855f7', desc: 'Relative Strength Index (30 / 70 Levels)' },
  { key: 'macd', label: 'MACD (12, 26, 9)', category: 'oscillator', group: 'Oscillators', color: '#3b82f6', desc: 'Moving Average Convergence Divergence' },
  { key: 'volume', label: 'Volume', category: 'oscillator', group: 'Volume', color: '#26a69a', desc: 'Trading Volume with Up/Down Bars' },
]

export const DEFAULT_INDICATOR_TOGGLES: Record<string, boolean> = {
  volume: true,
  ema21: true,
  ema9: false,
  ema50: false,
  ema200: false,
  vwap: false,
  supertrend: false,
  bb: false,
  rsi: false,
  macd: false,
}

const ALL_OFF_TOGGLES: Record<string, boolean> = {
  volume: false,
  ema9: false,
  ema21: false,
  ema50: false,
  ema200: false,
  vwap: false,
  supertrend: false,
  bb: false,
  rsi: false,
  macd: false,
}

export function applyChartPreset(preset: IndicatorPresetKey): Record<string, boolean> {
  if (preset === 'clean') {
    return { ...ALL_OFF_TOGGLES }
  }
  if (preset === 'ema21') {
    return { ...ALL_OFF_TOGGLES, volume: true, ema21: true }
  }
  if (preset === 'trend') {
    return { ...ALL_OFF_TOGGLES, volume: true, ema21: true, ema50: true }
  }
  if (preset === 'bb') {
    return { ...ALL_OFF_TOGGLES, volume: true, bb: true }
  }
  if (preset === 'momentum') {
    return { ...ALL_OFF_TOGGLES, volume: true, rsi: true, ema9: true }
  }
  return {
    volume: true,
    ema9: true,
    ema21: true,
    ema50: true,
    ema200: true,
    vwap: true,
    supertrend: true,
    bb: true,
    rsi: true,
    macd: true,
  }
}

export function toggleChartIndicator(
  currentToggles: Record<string, boolean>,
  showIndicators: boolean,
  key: string,
): Record<string, boolean> {
  const currentlyActive = showIndicators && Boolean(currentToggles[key])
  return {
    ...currentToggles,
    [key]: !currentlyActive,
  }
}

export function getActiveIndicatorKeys(
  showIndicators: boolean,
  toggles: Record<string, boolean>,
): string[] {
  if (!showIndicators) return []
  return CHART_INDICATOR_CATALOG.filter(ind => Boolean(toggles[ind.key])).map(ind => ind.key)
}

/**
 * Computes CSS `left` offset (relative to the trigger wrapper) so the indicator dropdown
 * stays within `[margin, viewportWidth - margin]` on narrow mobile and desktop viewports alike.
 */
export function computeDropdownLeftOffset(
  triggerLeft: number,
  dropdownWidth: number,
  viewportWidth: number,
  margin: number = 12,
): number {
  const rightEdge = triggerLeft + dropdownWidth
  const maxRight = viewportWidth - margin
  if (rightEdge <= maxRight) return 0
  const minLeftOffset = margin - triggerLeft
  return Math.max(minLeftOffset, maxRight - rightEdge)
}
