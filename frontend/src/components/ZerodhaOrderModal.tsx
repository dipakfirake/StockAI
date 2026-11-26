import React, { useState, useEffect, useMemo } from 'react'
import { X, Info, ShieldCheck, TrendingUp, TrendingDown, ArrowRight, CheckCircle, Percent } from 'lucide-react'
import { paperTradingApi, alertsApi } from '../services/api'
import { toast } from './Toast'

export interface ZerodhaOrderModalProps {
  isOpen: boolean
  onClose: () => void
  symbol: string
  name?: string
  currentPrice: number
  bestBuyPrice?: number
  targetPrice?: number
  stopLoss?: number
  defaultDirection?: 'BUY' | 'SELL'
  isGttMode?: boolean
  onOrderSuccess?: (tradeData: any) => void
}

export default function ZerodhaOrderModal({
  isOpen,
  onClose,
  symbol,
  name,
  currentPrice,
  bestBuyPrice,
  targetPrice: initialTarget,
  stopLoss: initialStopLoss,
  defaultDirection = 'BUY',
  isGttMode = false,
  onOrderSuccess,
}: ZerodhaOrderModalProps) {
  const [direction, setDirection] = useState<'BUY' | 'SELL'>(defaultDirection)
  const [productType, setProductType] = useState<'CNC' | 'MIS'>('CNC') // CNC is strict default
  const [orderType, setOrderType] = useState<'MARKET' | 'LIMIT' | 'SL' | 'SL_M'>('MARKET')
  
  const [quantity, setQuantity] = useState<number>(10)
  const [limitPrice, setLimitPrice] = useState<number>(() => {
    return bestBuyPrice && bestBuyPrice > 0 ? Number(bestBuyPrice.toFixed(2)) : Number(currentPrice.toFixed(2))
  })
  const [triggerPrice, setTriggerPrice] = useState<number>(() => {
    return initialStopLoss ? Number(initialStopLoss.toFixed(2)) : Number((currentPrice * 0.98).toFixed(2))
  })

  // Advanced GTT / Coupled Alerts
  const [enableGtt, setEnableGtt] = useState<boolean>(true)
  const [targetPrice, setTargetPrice] = useState<number>(() => {
    return initialTarget ? Number(initialTarget.toFixed(2)) : Number((currentPrice * 1.08).toFixed(2))
  })
  const [stopLoss, setStopLoss] = useState<number>(() => {
    return initialStopLoss ? Number(initialStopLoss.toFixed(2)) : Number((currentPrice * 0.96).toFixed(2))
  })

  // Dual-mode Stop Loss & Target controls (Value in ₹ or Percent in %)
  const [slMode, setSlMode] = useState<'VALUE' | 'PERCENT'>('PERCENT')
  const [slPercentInput, setSlPercentInput] = useState<string>('-4.0')
  const [targetMode, setTargetMode] = useState<'VALUE' | 'PERCENT'>('PERCENT')
  const [targetPercentInput, setTargetPercentInput] = useState<string>('8.0')

  const [autoSetAlerts, setAutoSetAlerts] = useState<boolean>(true)
  const [showChargesBreakdown, setShowChargesBreakdown] = useState<boolean>(false)
  const [submitting, setSubmitting] = useState<boolean>(false)

  // Sync state whenever props change
  useEffect(() => {
    setDirection(defaultDirection)
    setProductType('CNC') // Ensure CNC is always default (not MIS)
    const baseP = bestBuyPrice && bestBuyPrice > 0 ? bestBuyPrice : currentPrice
    setLimitPrice(Number(baseP.toFixed(2)))
    
    // Stop Loss initial calculation
    const calculatedSl = initialStopLoss ? Number(initialStopLoss.toFixed(2)) : Number((baseP * 0.96).toFixed(2))
    setStopLoss(calculatedSl)
    const slPct = baseP > 0 ? Number((((calculatedSl - baseP) / baseP) * 100).toFixed(1)) : -4.0
    setSlPercentInput(slPct < 0 ? String(slPct) : `-${slPct}`)

    // Target initial calculation
    const calculatedTgt = initialTarget ? Number(initialTarget.toFixed(2)) : Number((baseP * 1.08).toFixed(2))
    setTargetPrice(calculatedTgt)
    const tgtPct = baseP > 0 ? Number((((calculatedTgt - baseP) / baseP) * 100).toFixed(1)) : 8.0
    setTargetPercentInput(String(tgtPct))

    setTriggerPrice(initialStopLoss ? Number(initialStopLoss.toFixed(2)) : Number((baseP * 0.98).toFixed(2)))
    // Reset orderType cleanly: MARKET for immediate BUY/SELL clicks (or GTT at CMP); LIMIT when GTT targets a lower dip
    const hasDistinctBestBuy = Boolean(
      isGttMode && bestBuyPrice && bestBuyPrice > 0 && currentPrice > 0 &&
      Math.abs(bestBuyPrice - currentPrice) / currentPrice >= 0.002
    )
    setOrderType(hasDistinctBestBuy ? 'LIMIT' : 'MARKET')
  }, [isOpen, isGttMode, symbol, currentPrice, bestBuyPrice, initialTarget, initialStopLoss, defaultDirection])

  // Close on Escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) onClose()
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, onClose])

  if (!isOpen) return null

  const isBuy = direction === 'BUY'
  const accentColor = isBuy ? '#387ed1' : '#ff5722'
  const hoverColor = isBuy ? '#2a6cb8' : '#e64a19'
  const activePrice = orderType === 'MARKET' ? currentPrice : limitPrice

  // Calculations
  const grossTradeValue = activePrice * quantity
  const marginRequired = productType === 'MIS' ? grossTradeValue * 0.2 : grossTradeValue // 5x leverage for MIS
  
  // Zerodha brokerage & statutory charges calculation
  const brokerage = productType === 'CNC' ? 0.0 : Math.min(20.0, grossTradeValue * 0.0003)
  const stt = productType === 'CNC' ? grossTradeValue * 0.001 : (isBuy ? 0 : grossTradeValue * 0.00025)
  const exchangeTxn = grossTradeValue * 0.0000345
  const sebiCharges = grossTradeValue * 0.000001
  const gst = (brokerage + exchangeTxn + sebiCharges) * 0.18
  const stampDuty = isBuy ? grossTradeValue * 0.00015 : 0.0
  const totalCharges = brokerage + stt + exchangeTxn + sebiCharges + gst + stampDuty

  const handleQuickQty = (add: number) => {
    setQuantity(prev => Math.max(1, prev + add))
  }

  // Handlers for dual-mode Stop Loss (₹ Value vs % Percent)
  const handleSlPercentChange = (valStr: string) => {
    setSlPercentInput(valStr)
    const cleaned = valStr.replace('%', '').trim()
    const parsed = parseFloat(cleaned)
    if (!isNaN(parsed) && activePrice > 0) {
      const riskPct = parsed > 0 ? -parsed : parsed
      const calculated = Number((activePrice * (1 + riskPct / 100)).toFixed(2))
      setStopLoss(calculated)
    }
  }

  const handleSlPriceChange = (val: number) => {
    setStopLoss(val)
    if (activePrice > 0 && val > 0) {
      const pct = Number((((val - activePrice) / activePrice) * 100).toFixed(1))
      setSlPercentInput(String(pct))
    }
  }

  // Handlers for dual-mode Target (₹ Value vs % Percent)
  const handleTargetPercentChange = (valStr: string) => {
    setTargetPercentInput(valStr)
    const cleaned = valStr.replace('%', '').replace('+', '').trim()
    const parsed = parseFloat(cleaned)
    if (!isNaN(parsed) && activePrice > 0) {
      const gainPct = Math.abs(parsed)
      const calculated = Number((activePrice * (1 + gainPct / 100)).toFixed(2))
      setTargetPrice(calculated)
    }
  }

  const handleTargetPriceChange = (val: number) => {
    setTargetPrice(val)
    if (activePrice > 0 && val > 0) {
      const pct = Number((((val - activePrice) / activePrice) * 100).toFixed(1))
      setTargetPercentInput(String(pct))
    }
  }

  const handleSubmitOrder = async (e: React.FormEvent) => {
    e.preventDefault()
    if (quantity <= 0) {
      toast.warning('Invalid Quantity', 'Please enter at least 1 share.')
      return
    }

    setSubmitting(true)
    try {
      // 1. Submit Paper Trade with per-submit Idempotency-Key to block double-clicks
      const submissionKey =
        typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
          ? crypto.randomUUID()
          : `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`

      const payload: any = {
        symbol: symbol.toUpperCase(),
        direction: direction,
        quantity: quantity,
        order_type: orderType === 'SL_M' ? 'SL' : orderType,
        product_type: productType === 'CNC' ? 'DELIVERY' : 'INTRADAY',
        limit_price: orderType === 'LIMIT' || orderType === 'SL' ? limitPrice : undefined,
        stop_price: orderType === 'SL' || orderType === 'SL_M' ? triggerPrice : undefined,
        target_price: enableGtt ? targetPrice : undefined,
        stop_loss: enableGtt ? stopLoss : undefined,
        idempotency_key: submissionKey,
      }

      const res = await paperTradingApi.place(payload)
      const tradeData = res.data

      // 2. Auto-set Coupled Pre-Alerts in Alerts Tab
      if (autoSetAlerts && isBuy) {
        try {
          await alertsApi.screenerSetup({
            symbol: symbol.toUpperCase(),
            current_price: currentPrice,
            best_buy_price: bestBuyPrice || limitPrice,
            target_price: enableGtt ? targetPrice : undefined,
            stop_loss: enableGtt ? stopLoss : undefined,
            proximity_pct: 1.0,
          })
        } catch (alertErr) {
          console.warn('Coupled alerts auto-setup warning:', alertErr)
        }
      }

      const execStatus = String(tradeData?.status || 'OPEN').toUpperCase()
      const filledPrice = Number(tradeData?.entry_price || activePrice)
      if (execStatus === 'OPEN') {
        toast.success(
          `Executed (${execStatus}): ${direction} ${quantity}x ${symbol}`,
          `Filled @ ₹${filledPrice.toFixed(2)} | Live in Holdings & Positions${autoSetAlerts ? ' | Coupled Alerts Active' : ''}`
        )
      } else {
        toast.info(
          `Order Queued (${execStatus}): ${direction} ${quantity}x ${symbol}`,
          `Trigger/Limit: ₹${activePrice.toFixed(2)} — Track in Orders & Positions -> Orders tab${autoSetAlerts ? ' | Coupled Alerts Active' : ''}`
        )
      }

      if (onOrderSuccess) onOrderSuccess(tradeData)
      onClose()
    } catch (err: any) {
      console.error('Order placement failed:', err)
      toast.error('Order Failed', err?.response?.data?.detail || err.message || 'Execution error')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div style={{
      position: 'fixed',
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      backgroundColor: 'rgba(0, 0, 0, 0.65)',
      backdropFilter: 'blur(3px)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 10000,
      padding: 16,
    }}>
      <div style={{
        background: 'var(--color-bg-card, #1a1e29)',
        border: `1px solid var(--color-border, #2d3343)`,
        borderRadius: 12,
        width: '100%',
        maxWidth: 520,
        boxShadow: '0 24px 60px rgba(0,0,0,0.5), 0 0 0 1px rgba(255,255,255,0.06)',
        overflow: 'hidden',
        animation: 'modalFadeIn 0.22s ease-out',
        display: 'flex',
        flexDirection: 'column',
      }}>
        {/* Zerodha Top Bar Header */}
        <div style={{
          background: accentColor,
          color: '#ffffff',
          padding: '14px 20px',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          transition: 'background 0.25s ease',
        }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ fontSize: 13, fontWeight: 700, letterSpacing: 0.5, textTransform: 'uppercase', background: 'rgba(255,255,255,0.2)', padding: '2px 8px', borderRadius: 4 }}>
                {direction}
              </span>
              <span style={{ fontSize: 17, fontWeight: 700, letterSpacing: 0.3 }}>
                {symbol}
              </span>
              <span style={{ fontSize: 11, background: 'rgba(0,0,0,0.25)', padding: '2px 6px', borderRadius: 4, opacity: 0.9 }}>
                NSE
              </span>
            </div>
            {name && <div style={{ fontSize: 12, opacity: 0.85, marginTop: 2 }}>{name}</div>}
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: 16, fontWeight: 700, fontFamily: 'monospace' }}>
                ₹{currentPrice.toFixed(2)}
              </div>
              <div style={{ fontSize: 11, opacity: 0.85 }}>
                Market Live
              </div>
            </div>

            {/* Buy / Sell Switch Toggle */}
            <div style={{
              display: 'flex',
              background: 'rgba(0,0,0,0.3)',
              borderRadius: 20,
              padding: 2,
            }}>
              <button
                type="button"
                onClick={() => setDirection('BUY')}
                style={{
                  border: 'none',
                  background: isBuy ? '#ffffff' : 'transparent',
                  color: isBuy ? '#387ed1' : '#ffffff',
                  fontWeight: 700,
                  fontSize: 12,
                  padding: '4px 12px',
                  borderRadius: 16,
                  cursor: 'pointer',
                  transition: 'all 0.15s ease',
                }}
              >
                BUY
              </button>
              <button
                type="button"
                onClick={() => setDirection('SELL')}
                style={{
                  border: 'none',
                  background: !isBuy ? '#ffffff' : 'transparent',
                  color: !isBuy ? '#ff5722' : '#ffffff',
                  fontWeight: 700,
                  fontSize: 12,
                  padding: '4px 12px',
                  borderRadius: 16,
                  cursor: 'pointer',
                  transition: 'all 0.15s ease',
                }}
              >
                SELL
              </button>
            </div>

            <button
              onClick={onClose}
              style={{
                background: 'rgba(255,255,255,0.15)',
                border: 'none',
                color: '#ffffff',
                borderRadius: '50%',
                width: 28,
                height: 28,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                cursor: 'pointer',
              }}
            >
              <X size={16} />
            </button>
          </div>
        </div>

        {/* Zerodha Kite GTT Mode Ribbon */}
        {isGttMode && (
          <div style={{
            background: 'linear-gradient(90deg, rgba(56, 126, 209, 0.18), rgba(16, 185, 129, 0.18))',
            borderBottom: '1px solid var(--color-border, #2d3343)',
            padding: '8px 20px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, fontWeight: 700, color: '#38bdf8' }}>
              <span>⚡ Zerodha Kite GTT (Good-Till-Triggered) Order</span>
            </div>
            <span style={{ fontSize: 10, background: 'rgba(56, 189, 248, 0.2)', color: '#38bdf8', padding: '2px 8px', borderRadius: 4, fontWeight: 700 }}>
              OCO: Stoploss + Target Triggers
            </span>
          </div>
        )}

        {/* Order Form Body */}
        <form onSubmit={handleSubmitOrder} style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: 18 }}>
          {/* Product Type (CNC vs MIS) */}
          <div>
            <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--color-text-muted, #8a92a6)', marginBottom: 6, textTransform: 'uppercase', letterSpacing: 0.5 }}>
              Product Type
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
              <button
                type="button"
                onClick={() => setProductType('CNC')}
                style={{
                  padding: '8px 12px',
                  borderRadius: 6,
                  fontSize: 13,
                  fontWeight: 600,
                  border: productType === 'CNC' ? `2px solid ${accentColor}` : '1px solid var(--color-border, #333a4d)',
                  background: productType === 'CNC' ? (isBuy ? 'rgba(56, 126, 209, 0.12)' : 'rgba(255, 87, 34, 0.12)') : 'var(--color-bg-subtle, #141721)',
                  color: productType === 'CNC' ? accentColor : 'var(--color-text-secondary, #b4bad0)',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 6,
                }}
              >
                <span>CNC</span>
                <span style={{ fontSize: 11, opacity: 0.7 }}>(Longterm / Delivery)</span>
              </button>

              <button
                type="button"
                onClick={() => setProductType('MIS')}
                style={{
                  padding: '8px 12px',
                  borderRadius: 6,
                  fontSize: 13,
                  fontWeight: 600,
                  border: productType === 'MIS' ? `2px solid ${accentColor}` : '1px solid var(--color-border, #333a4d)',
                  background: productType === 'MIS' ? (isBuy ? 'rgba(56, 126, 209, 0.12)' : 'rgba(255, 87, 34, 0.12)') : 'var(--color-bg-subtle, #141721)',
                  color: productType === 'MIS' ? accentColor : 'var(--color-text-secondary, #b4bad0)',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 6,
                }}
              >
                <span>MIS</span>
                <span style={{ fontSize: 11, opacity: 0.7 }}>(Intraday 5x)</span>
              </button>
            </div>
          </div>

          {/* Order Type Tabs */}
          <div>
            <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--color-text-muted, #8a92a6)', marginBottom: 6, textTransform: 'uppercase', letterSpacing: 0.5 }}>
              Order Type
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 6 }}>
              {[
                { id: 'MARKET', label: 'Market' },
                { id: 'LIMIT', label: 'Limit' },
                { id: 'SL', label: 'SL' },
                { id: 'SL_M', label: 'SL-M' },
              ].map(t => {
                const isSelected = orderType === t.id
                return (
                  <button
                    key={t.id}
                    type="button"
                    onClick={() => setOrderType(t.id as any)}
                    style={{
                      padding: '7px 4px',
                      borderRadius: 6,
                      fontSize: 12,
                      fontWeight: 600,
                      border: isSelected ? `2px solid ${accentColor}` : '1px solid var(--color-border, #333a4d)',
                      background: isSelected ? (isBuy ? 'rgba(56, 126, 209, 0.12)' : 'rgba(255, 87, 34, 0.12)') : 'var(--color-bg-subtle, #141721)',
                      color: isSelected ? accentColor : 'var(--color-text-secondary, #b4bad0)',
                      cursor: 'pointer',
                      textAlign: 'center',
                    }}
                  >
                    {t.label}
                  </button>
                )
              })}
            </div>
          </div>

          {/* Quantity & Price Grid */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
            {/* Quantity */}
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                <label style={{ fontSize: 12, fontWeight: 600, color: 'var(--color-text-muted, #8a92a6)' }}>Qty</label>
                <div style={{ display: 'flex', gap: 4 }}>
                  {[10, 25, 50, 100].map(add => (
                    <button
                      key={add}
                      type="button"
                      onClick={() => handleQuickQty(add)}
                      style={{
                        background: 'transparent',
                        border: '1px solid var(--color-border, #333a4d)',
                        borderRadius: 4,
                        fontSize: 10,
                        padding: '1px 4px',
                        color: 'var(--color-text-muted, #8a92a6)',
                        cursor: 'pointer',
                      }}
                    >
                      +{add}
                    </button>
                  ))}
                </div>
              </div>
              <div style={{ display: 'flex', alignItems: 'center' }}>
                <input
                  type="number"
                  min={1}
                  value={quantity}
                  onChange={e => setQuantity(Math.max(1, parseInt(e.target.value) || 1))}
                  className="input"
                  style={{
                    width: '100%',
                    padding: '8px 12px',
                    fontSize: 14,
                    fontWeight: 700,
                    fontFamily: 'monospace',
                    borderRadius: 6,
                    border: '1px solid var(--color-border, #333a4d)',
                    background: 'var(--color-bg-subtle, #141721)',
                    color: 'var(--color-text-primary, #ffffff)',
                  }}
                  required
                />
              </div>
            </div>

            {/* Price (Limit) */}
            <div>
              <label style={{ fontSize: 12, fontWeight: 600, color: 'var(--color-text-muted, #8a92a6)', display: 'block', marginBottom: 4 }}>
                Price (₹)
              </label>
              <input
                type="number"
                step="0.05"
                disabled={orderType === 'MARKET' || orderType === 'SL_M'}
                value={orderType === 'MARKET' || orderType === 'SL_M' ? currentPrice.toFixed(2) : limitPrice}
                onChange={e => setLimitPrice(parseFloat(e.target.value) || 0)}
                className="input"
                style={{
                  width: '100%',
                  padding: '8px 12px',
                  fontSize: 14,
                  fontWeight: 700,
                  fontFamily: 'monospace',
                  borderRadius: 6,
                  border: '1px solid var(--color-border, #333a4d)',
                  background: orderType === 'MARKET' || orderType === 'SL_M' ? 'rgba(255,255,255,0.04)' : 'var(--color-bg-subtle, #141721)',
                  color: orderType === 'MARKET' || orderType === 'SL_M' ? 'var(--color-text-muted, #8a92a6)' : 'var(--color-text-primary, #ffffff)',
                  cursor: orderType === 'MARKET' || orderType === 'SL_M' ? 'not-allowed' : 'text',
                }}
                required
              />
            </div>
          </div>

          {/* Trigger Price for SL orders */}
          {(orderType === 'SL' || orderType === 'SL_M') && (
            <div>
              <label style={{ fontSize: 12, fontWeight: 600, color: 'var(--color-text-muted, #8a92a6)', display: 'block', marginBottom: 4 }}>
                Trigger Price (₹)
              </label>
              <input
                type="number"
                step="0.05"
                value={triggerPrice}
                onChange={e => setTriggerPrice(parseFloat(e.target.value) || 0)}
                className="input"
                style={{
                  width: '100%',
                  padding: '8px 12px',
                  fontSize: 14,
                  fontWeight: 700,
                  fontFamily: 'monospace',
                  borderRadius: 6,
                  border: '1px solid var(--color-border, #333a4d)',
                  background: 'var(--color-bg-subtle, #141721)',
                  color: 'var(--color-text-primary, #ffffff)',
                }}
                required
              />
            </div>
          )}

          {/* Advanced Risk Protection & GTT (Target & Stop Loss) */}
          <div style={{
            background: 'var(--color-bg-subtle, #141721)',
            border: '1px solid var(--color-border, #333a4d)',
            borderRadius: 8,
            padding: 12,
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, fontWeight: 700, color: 'var(--color-text-primary, #ffffff)' }}>
                <ShieldCheck size={15} style={{ color: '#10b981' }} />
                <span>GTT Protection & Automated Risk Controls</span>
              </div>
              <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', fontSize: 11, color: 'var(--color-text-secondary, #b4bad0)' }}>
                <input
                  type="checkbox"
                  checked={enableGtt}
                  onChange={e => setEnableGtt(e.target.checked)}
                  style={{ accentColor }}
                />
                Enable GTT
              </label>
            </div>

            {enableGtt && (
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                {/* Target Section (₹ Value vs % Percent) */}
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                    <label style={{ fontSize: 11, color: '#10b981', fontWeight: 700 }}>
                      Target
                    </label>
                    <div style={{ display: 'flex', background: 'rgba(16, 185, 129, 0.12)', borderRadius: 12, padding: 2 }}>
                      <button
                        type="button"
                        onClick={() => setTargetMode('PERCENT')}
                        style={{
                          border: 'none',
                          background: targetMode === 'PERCENT' ? '#10b981' : 'transparent',
                          color: targetMode === 'PERCENT' ? '#ffffff' : 'var(--color-text-muted, #8a92a6)',
                          fontSize: 10,
                          fontWeight: 700,
                          padding: '1px 7px',
                          borderRadius: 10,
                          cursor: 'pointer',
                        }}
                      >
                        % Percent
                      </button>
                      <button
                        type="button"
                        onClick={() => setTargetMode('VALUE')}
                        style={{
                          border: 'none',
                          background: targetMode === 'VALUE' ? '#10b981' : 'transparent',
                          color: targetMode === 'VALUE' ? '#ffffff' : 'var(--color-text-muted, #8a92a6)',
                          fontSize: 10,
                          fontWeight: 700,
                          padding: '1px 7px',
                          borderRadius: 10,
                          cursor: 'pointer',
                        }}
                      >
                        ₹ Value
                      </button>
                    </div>
                  </div>

                  {targetMode === 'PERCENT' ? (
                    <div>
                      <input
                        type="text"
                        placeholder="e.g. 10%"
                        value={targetPercentInput}
                        onChange={e => handleTargetPercentChange(e.target.value)}
                        style={{
                          width: '100%',
                          padding: '6px 10px',
                          fontSize: 13,
                          fontFamily: 'monospace',
                          fontWeight: 700,
                          borderRadius: 4,
                          border: '1px solid rgba(16, 185, 129, 0.4)',
                          background: 'rgba(16, 185, 129, 0.05)',
                          color: 'var(--color-text-primary, #ffffff)',
                        }}
                      />
                      <div style={{ fontSize: 10, color: 'var(--color-text-muted, #8a92a6)', marginTop: 2 }}>
                        Target: <strong style={{ color: '#10b981' }}>₹{targetPrice.toFixed(2)}</strong> (+{targetPercentInput.includes('%') ? targetPercentInput : `${targetPercentInput}%`})
                      </div>
                    </div>
                  ) : (
                    <div>
                      <input
                        type="number"
                        step="0.05"
                        value={targetPrice}
                        onChange={e => handleTargetPriceChange(parseFloat(e.target.value) || 0)}
                        style={{
                          width: '100%',
                          padding: '6px 10px',
                          fontSize: 13,
                          fontFamily: 'monospace',
                          fontWeight: 700,
                          borderRadius: 4,
                          border: '1px solid rgba(16, 185, 129, 0.4)',
                          background: 'rgba(16, 185, 129, 0.05)',
                          color: 'var(--color-text-primary, #ffffff)',
                        }}
                      />
                      <div style={{ fontSize: 10, color: 'var(--color-text-muted, #8a92a6)', marginTop: 2 }}>
                        Gain: <strong style={{ color: '#10b981' }}>+{(((targetPrice - activePrice) / activePrice) * 100).toFixed(1)}%</strong> from ₹{activePrice.toFixed(2)}
                      </div>
                    </div>
                  )}
                </div>

                {/* Stop Loss Section (Dual Mode: ₹ Value vs % Percent) */}
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                    <label style={{ fontSize: 11, color: '#ef4444', fontWeight: 700 }}>
                      Stop Loss
                    </label>
                    <div style={{ display: 'flex', background: 'rgba(239, 68, 68, 0.12)', borderRadius: 12, padding: 2 }}>
                      <button
                        type="button"
                        onClick={() => setSlMode('PERCENT')}
                        style={{
                          border: 'none',
                          background: slMode === 'PERCENT' ? '#ef4444' : 'transparent',
                          color: slMode === 'PERCENT' ? '#ffffff' : 'var(--color-text-muted, #8a92a6)',
                          fontSize: 10,
                          fontWeight: 700,
                          padding: '1px 7px',
                          borderRadius: 10,
                          cursor: 'pointer',
                        }}
                      >
                        % Percent
                      </button>
                      <button
                        type="button"
                        onClick={() => setSlMode('VALUE')}
                        style={{
                          border: 'none',
                          background: slMode === 'VALUE' ? '#ef4444' : 'transparent',
                          color: slMode === 'VALUE' ? '#ffffff' : 'var(--color-text-muted, #8a92a6)',
                          fontSize: 10,
                          fontWeight: 700,
                          padding: '1px 7px',
                          borderRadius: 10,
                          cursor: 'pointer',
                        }}
                      >
                        ₹ Value
                      </button>
                    </div>
                  </div>

                  {slMode === 'PERCENT' ? (
                    <div>
                      <input
                        type="text"
                        placeholder="e.g. -5%"
                        value={slPercentInput}
                        onChange={e => handleSlPercentChange(e.target.value)}
                        style={{
                          width: '100%',
                          padding: '6px 10px',
                          fontSize: 13,
                          fontFamily: 'monospace',
                          fontWeight: 700,
                          borderRadius: 4,
                          border: '1px solid rgba(239, 68, 68, 0.4)',
                          background: 'rgba(239, 68, 68, 0.05)',
                          color: 'var(--color-text-primary, #ffffff)',
                        }}
                      />
                      <div style={{ fontSize: 10, color: 'var(--color-text-muted, #8a92a6)', marginTop: 2 }}>
                        Trigger: <strong style={{ color: '#ef4444' }}>₹{stopLoss.toFixed(2)}</strong> ({slPercentInput.includes('%') ? slPercentInput : `${slPercentInput}%`})
                      </div>
                    </div>
                  ) : (
                    <div>
                      <input
                        type="number"
                        step="0.05"
                        value={stopLoss}
                        onChange={e => handleSlPriceChange(parseFloat(e.target.value) || 0)}
                        style={{
                          width: '100%',
                          padding: '6px 10px',
                          fontSize: 13,
                          fontFamily: 'monospace',
                          fontWeight: 700,
                          borderRadius: 4,
                          border: '1px solid rgba(239, 68, 68, 0.4)',
                          background: 'rgba(239, 68, 68, 0.05)',
                          color: 'var(--color-text-primary, #ffffff)',
                        }}
                      />
                      <div style={{ fontSize: 10, color: 'var(--color-text-muted, #8a92a6)', marginTop: 2 }}>
                        Risk: <strong style={{ color: '#ef4444' }}>{(((stopLoss - activePrice) / activePrice) * 100).toFixed(1)}%</strong> from ₹{activePrice.toFixed(2)}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Auto-create Coupled Alerts Option */}
            <div style={{ marginTop: 10, paddingTop: 8, borderTop: '1px dashed var(--color-border, #333a4d)' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: 7, cursor: 'pointer', fontSize: 12, color: 'var(--color-text-primary, #ffffff)' }}>
                <input
                  type="checkbox"
                  checked={autoSetAlerts}
                  onChange={e => setAutoSetAlerts(e.target.checked)}
                  style={{ accentColor }}
                />
                <span>Auto-create Proximity & Target/SL Alerts in Alerts Tab</span>
              </label>
              <div style={{ fontSize: 10, color: 'var(--color-text-muted, #8a92a6)', marginLeft: 22, marginTop: 2 }}>
                Sends early warning toasts before hitting Target and triggers SL alarms to protect gains.
              </div>
            </div>
          </div>

          {/* Kite Footer / Execution Bar */}
          <div style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            paddingTop: 12,
            borderTop: '1px solid var(--color-border, #333a4d)',
            flexWrap: 'wrap',
            gap: 12,
          }}>
            <div>
              <div style={{ fontSize: 11, color: 'var(--color-text-muted, #8a92a6)' }}>
                Margin required: <strong style={{ color: 'var(--color-text-primary, #ffffff)', fontSize: 13, fontFamily: 'monospace' }}>₹{marginRequired.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</strong>
              </div>
              <div style={{ fontSize: 10, color: 'var(--color-text-muted, #8a92a6)', display: 'flex', alignItems: 'center', gap: 4, marginTop: 2 }}>
                <span>Charges: ~₹{totalCharges.toFixed(2)}</span>
                <button
                  type="button"
                  onClick={() => setShowChargesBreakdown(!showChargesBreakdown)}
                  style={{ background: 'none', border: 'none', color: accentColor, cursor: 'pointer', padding: 0, textDecoration: 'underline', fontSize: 10 }}
                >
                  breakdown
                </button>
              </div>

              {/* Charges Breakdown Popover */}
              {showChargesBreakdown && (
                <div style={{
                  position: 'absolute',
                  bottom: 75,
                  left: 20,
                  background: 'var(--color-bg-card, #1f2433)',
                  border: '1px solid var(--color-border, #3a4256)',
                  borderRadius: 8,
                  padding: 10,
                  fontSize: 11,
                  boxShadow: '0 8px 24px rgba(0,0,0,0.5)',
                  zIndex: 20,
                  width: 240,
                }}>
                  <div style={{ fontWeight: 700, marginBottom: 6, display: 'flex', justifyContent: 'space-between' }}>
                    <span>Estimated Charges</span>
                    <button type="button" onClick={() => setShowChargesBreakdown(false)} style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer' }}>×</button>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--color-text-secondary, #b4bad0)' }}>
                    <span>Brokerage:</span>
                    <span>₹{brokerage.toFixed(2)}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--color-text-secondary, #b4bad0)' }}>
                    <span>STT / CTT:</span>
                    <span>₹{stt.toFixed(2)}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--color-text-secondary, #b4bad0)' }}>
                    <span>Turnover Charges:</span>
                    <span>₹{exchangeTxn.toFixed(2)}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--color-text-secondary, #b4bad0)' }}>
                    <span>GST (18%):</span>
                    <span>₹{gst.toFixed(2)}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--color-text-secondary, #b4bad0)' }}>
                    <span>Stamp Duty:</span>
                    <span>₹{stampDuty.toFixed(2)}</span>
                  </div>
                </div>
              )}
            </div>

            <div style={{ display: 'flex', gap: 10 }}>
              <button
                type="button"
                onClick={onClose}
                className="btn btn-ghost"
                style={{ padding: '8px 16px', fontSize: 13 }}
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={submitting}
                style={{
                  background: accentColor,
                  color: '#ffffff',
                  border: 'none',
                  borderRadius: 6,
                  padding: '9px 24px',
                  fontSize: 14,
                  fontWeight: 700,
                  letterSpacing: 0.5,
                  cursor: submitting ? 'not-allowed' : 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                  boxShadow: `0 4px 14px ${isBuy ? 'rgba(56, 126, 209, 0.4)' : 'rgba(255, 87, 34, 0.4)'}`,
                  transition: 'background 0.2s ease',
                }}
              >
                {submitting
                  ? (isGttMode ? 'Placing GTT...' : 'Placing...')
                  : isGttMode
                  ? `⚡ Place GTT Trigger (${symbol})`
                  : `${direction} ${quantity} ${symbol}`}
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  )
}
