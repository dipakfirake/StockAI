import { describe, it, expect } from 'vitest'
import {
  CHART_INDICATOR_CATALOG,
  DEFAULT_INDICATOR_TOGGLES,
  applyChartPreset,
  toggleChartIndicator,
  getActiveIndicatorKeys,
  computeDropdownLeftOffset,
} from './chartIndicators'

describe('chartIndicators helpers', () => {
  it('defines 10 unique indicators across overlay and oscillator categories', () => {
    const keys = CHART_INDICATOR_CATALOG.map(i => i.key)
    expect(new Set(keys).size).toBe(10)
    expect(CHART_INDICATOR_CATALOG.some(i => i.category === 'overlay')).toBe(true)
    expect(CHART_INDICATOR_CATALOG.some(i => i.category === 'oscillator')).toBe(true)
  })

  it('toggles individual indicator capsules cleanly even if master visibility was OFF', () => {
    const next = toggleChartIndicator({ ...DEFAULT_INDICATOR_TOGGLES, rsi: false }, false, 'rsi')
    expect(next.rsi).toBe(true)

    const turnedOff = toggleChartIndicator(next, true, 'rsi')
    expect(turnedOff.rsi).toBe(false)
  })

  it('applies Clean (All Off) to zero active indicators and Trend to EMA 21 + 50 + Volume', () => {
    const clean = applyChartPreset('clean')
    expect(getActiveIndicatorKeys(true, clean)).toEqual([])

    const trend = applyChartPreset('trend')
    expect(getActiveIndicatorKeys(true, trend)).toEqual(['ema21', 'ema50', 'volume'])

    const all = applyChartPreset('all')
    expect(getActiveIndicatorKeys(true, all)).toHaveLength(10)
  })

  it('clamps dropdown left offset so narrow 390px mobile screens never overflow right', () => {
    // Desktop 1440px: trigger at left=180, dropdown 340 fits cleanly without shift
    expect(computeDropdownLeftOffset(180, 340, 1440)).toBe(0)

    // Mobile 390px: trigger at left=180, dropdown 340 would reach 520px; shifts to stay >= 12px margin
    const shift = computeDropdownLeftOffset(180, 340, 390, 12)
    expect(180 + shift + 340).toBeLessThanOrEqual(390 - 12)
    expect(180 + shift).toBeGreaterThanOrEqual(12)
  })
})
