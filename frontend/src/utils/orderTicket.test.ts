import { describe, it, expect } from 'vitest'
import {
  resolveEntryBasePrice,
  resolveInitialTriggerPrice,
  resolveInitialOrderType,
  resolveActiveOrderPrice,
  buildOrderExecutionSummary,
  buildPaperOrderPayload,
} from './orderTicket'

describe('orderTicket helpers — ASIANPAINT.NS SL-M & GTT regression guards', () => {
  it('defaults SL-M BUY triggerPrice to entry/CMP price, never downside stopLoss', () => {
    const cmp = 2532.6
    const bestBuy = 2532.6
    const trigger = resolveInitialTriggerPrice(cmp, bestBuy)
    expect(trigger).toBe(2532.6)
    expect(trigger).not.toBe(2457.28)
    expect(resolveEntryBasePrice(2532.6, 0)).toBe(2532.6)
  })

  it('defaults At Best Buy GTT setups to MARKET and dip setups to LIMIT', () => {
    expect(resolveInitialOrderType(true, 2532.6, 2532.6)).toBe('MARKET')
    expect(resolveInitialOrderType(true, 2532.6, 2480.0)).toBe('LIMIT')
    expect(resolveInitialOrderType(false, 2532.6, 2480.0)).toBe('MARKET')
  })

  it('computes activePrice from triggerPrice in SL-M mode rather than disabled limitPrice', () => {
    const active = resolveActiveOrderPrice({
      orderType: 'SL_M',
      currentPrice: 2532.6,
      limitPrice: 2490.0,
      triggerPrice: 2550.0,
    })
    expect(active).toBe(2550.0)

    const limitActive = resolveActiveOrderPrice({
      orderType: 'LIMIT',
      currentPrice: 2532.6,
      limitPrice: 2490.0,
      triggerPrice: 2550.0,
    })
    expect(limitActive).toBe(2490.0)
  })

  it('maps SL-M orders cleanly to backend SL + stop_price without limit cap', () => {
    const payload = buildPaperOrderPayload({
      symbol: 'asianpaint.ns',
      direction: 'BUY',
      quantity: 10,
      orderType: 'SL_M',
      productType: 'CNC',
      currentPrice: 2532.6,
      limitPrice: 2480.0,
      triggerPrice: 2532.6,
      enableGtt: true,
      targetPrice: 2711.82,
      stopLoss: 2457.28,
      idempotencyKey: 'test-key-123',
    })

    expect(payload.symbol).toBe('ASIANPAINT.NS')
    expect(payload.order_type).toBe('SL')
    expect(payload.product_type).toBe('DELIVERY')
    expect(payload.stop_price).toBe(2532.6)
    expect(payload.limit_price).toBeUndefined()
    expect(payload.target_price).toBe(2711.82)
    expect(payload.stop_loss).toBe(2457.28)
    expect(payload.target_1).toBe(2631.17)
    expect(payload.target_2).toBe(2711.82)
    expect(payload.trailing_enabled).toBe(true)
  })

  it('communicates NSE 09:15-15:30 IST Mon-Fri and Pending queuing clearly', () => {
    const slmSummary = buildOrderExecutionSummary({
      orderType: 'SL_M',
      direction: 'BUY',
      limitPrice: 2532.6,
      triggerPrice: 2532.6,
    })
    expect(slmSummary).toContain('Pending')
    expect(slmSummary).toContain('2532.60')
    expect(slmSummary).toContain('NSE hours')

    const mktSummary = buildOrderExecutionSummary({
      orderType: 'MARKET',
      direction: 'BUY',
      limitPrice: 2532.6,
      triggerPrice: 2532.6,
    })
    expect(mktSummary).toContain('09:15–15:30 IST Mon–Fri')
    expect(mktSummary).toContain('Pending')
  })
})
