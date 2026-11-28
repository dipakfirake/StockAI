/**
 * Pure helper utilities for virtual paper-order ticket pricing,
 * trigger defaults, execution timing copy, and API payload mapping.
 */

export type OrderTicketType = 'MARKET' | 'LIMIT' | 'SL' | 'SL_M'
export type OrderDirection = 'BUY' | 'SELL'
export type OrderProductType = 'CNC' | 'MIS'

export interface PaperOrderPayload {
  symbol: string
  direction: OrderDirection
  quantity: number
  order_type: 'MARKET' | 'LIMIT' | 'SL'
  product_type: 'DELIVERY' | 'INTRADAY'
  limit_price?: number
  stop_price?: number
  target_price?: number
  stop_loss?: number
  target_1?: number
  target_2?: number
  target_3?: number
  trailing_enabled: boolean
  idempotency_key: string
}

/**
 * Resolves the baseline entry price for Limit/Trigger controls.
 * Prefers a positive screener Best Buy price; falls back to current LTP.
 */
export function resolveEntryBasePrice(currentPrice: number, bestBuyPrice?: number): number {
  const base = bestBuyPrice && bestBuyPrice > 0 ? bestBuyPrice : currentPrice
  return Number(Math.max(0, base).toFixed(2))
}

/**
 * Default SL / SL-M entry trigger price.
 * Always anchors to the entry/CMP price rather than the downside Stop Loss.
 */
export function resolveInitialTriggerPrice(currentPrice: number, bestBuyPrice?: number): number {
  return resolveEntryBasePrice(currentPrice, bestBuyPrice)
}

/**
 * Chooses MARKET when buying at CMP ("At Best Buy") and LIMIT when GTT targets a distinct dip.
 */
export function resolveInitialOrderType(
  isGttMode: boolean,
  currentPrice: number,
  bestBuyPrice?: number,
): 'MARKET' | 'LIMIT' {
  const hasDistinctBestBuy = Boolean(
    isGttMode &&
      bestBuyPrice &&
      bestBuyPrice > 0 &&
      currentPrice > 0 &&
      Math.abs(bestBuyPrice - currentPrice) / currentPrice >= 0.002,
  )
  return hasDistinctBestBuy ? 'LIMIT' : 'MARKET'
}

/**
 * Resolves the active valuation price used for margin estimation and OCO % calculations.
 */
export function resolveActiveOrderPrice({
  orderType,
  currentPrice,
  limitPrice,
  triggerPrice,
}: {
  orderType: OrderTicketType
  currentPrice: number
  limitPrice: number
  triggerPrice: number
}): number {
  if (orderType === 'MARKET') return currentPrice
  if (orderType === 'SL_M') return triggerPrice > 0 ? triggerPrice : currentPrice
  return limitPrice > 0 ? limitPrice : currentPrice
}

/**
 * Builds the 1-line NSE-aware execution & queuing summary for the active order mode.
 */
export function buildOrderExecutionSummary({
  orderType,
  direction,
  limitPrice,
  triggerPrice,
}: {
  orderType: OrderTicketType
  direction: OrderDirection
  limitPrice: number
  triggerPrice: number
}): string {
  const isBuy = direction === 'BUY'
  if (orderType === 'MARKET') {
    return isBuy
      ? 'Buys at market open or live price (09:15–15:30 IST Mon–Fri). Queues Pending outside NSE hours.'
      : 'Sells at market open or live price (09:15–15:30 IST Mon–Fri). Queues Pending outside NSE hours.'
  }
  if (orderType === 'LIMIT') {
    return isBuy
      ? `Queues Pending and auto-buys when LTP reaches ₹${limitPrice.toFixed(2)} or lower during NSE hours.`
      : `Queues Pending and auto-sells when LTP reaches ₹${limitPrice.toFixed(2)} or higher during NSE hours.`
  }
  return isBuy
    ? `Breakout entry: queues Pending and buys when LTP rises to ₹${triggerPrice.toFixed(2)} or above during NSE hours.`
    : `Breakdown trigger: queues Pending and sells when LTP drops to ₹${triggerPrice.toFixed(2)} or below during NSE hours.`
}

/**
 * Builds the validated payload expected by POST /api/paper-trading/place.
 * Maps SL-M to backend order_type 'SL' with stop_price and no limit cap.
 */
export function buildPaperOrderPayload({
  symbol,
  direction,
  quantity,
  orderType,
  productType,
  currentPrice,
  limitPrice,
  triggerPrice,
  enableGtt,
  targetPrice,
  stopLoss,
  target1,
  target2,
  target3,
  idempotencyKey,
}: {
  symbol: string
  direction: OrderDirection
  quantity: number
  orderType: OrderTicketType
  productType: OrderProductType
  currentPrice: number
  limitPrice: number
  triggerPrice: number
  enableGtt: boolean
  targetPrice: number
  stopLoss: number
  target1?: number
  target2?: number
  target3?: number
  idempotencyKey: string
}): PaperOrderPayload {
  const activePrice = resolveActiveOrderPrice({
    orderType,
    currentPrice,
    limitPrice,
    triggerPrice,
  })
  const effT2 = target2 && target2 > 0 ? Number(target2.toFixed(2)) : targetPrice
  const effT1 =
    target1 && target1 > 0
      ? Number(target1.toFixed(2))
      : Number((activePrice + 0.55 * (effT2 - activePrice)).toFixed(2))
  const effT3 = target3 && target3 > 0 ? Number(target3.toFixed(2)) : undefined

  return {
    symbol: symbol.toUpperCase(),
    direction,
    quantity,
    order_type: orderType === 'SL_M' ? 'SL' : orderType,
    product_type: productType === 'CNC' ? 'DELIVERY' : 'INTRADAY',
    limit_price: orderType === 'LIMIT' || orderType === 'SL' ? limitPrice : undefined,
    stop_price: orderType === 'SL' || orderType === 'SL_M' ? triggerPrice : undefined,
    target_price: enableGtt ? targetPrice : undefined,
    stop_loss: enableGtt ? stopLoss : undefined,
    target_1: enableGtt ? effT1 : undefined,
    target_2: enableGtt ? effT2 : undefined,
    target_3: enableGtt ? effT3 : undefined,
    trailing_enabled: enableGtt,
    idempotency_key: idempotencyKey,
  }
}
