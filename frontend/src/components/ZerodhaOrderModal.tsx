import React, { useState, useEffect } from 'react'
import { X, ShieldCheck, Target } from 'lucide-react'
import { paperTradingApi, alertsApi } from '../services/api'
import { toast } from './Toast'
import {
  resolveEntryBasePrice,
  resolveInitialTriggerPrice,
  resolveInitialOrderType,
  resolveActiveOrderPrice,
  buildOrderExecutionSummary,
  buildPaperOrderPayload,
  type OrderTicketType,
} from '../utils/orderTicket'

export interface ZerodhaOrderModalProps {
  isOpen: boolean
  onClose: () => void
  symbol: string
  name?: string
  currentPrice: number
  bestBuyPrice?: number
  targetPrice?: number
  target1?: number
  target2?: number
  target3?: number
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
  target1,
  target2,
  target3,
  stopLoss: initialStopLoss,
  defaultDirection = 'BUY',
  isGttMode = false,
  onOrderSuccess,
}: ZerodhaOrderModalProps) {
  const [direction, setDirection] = useState<'BUY' | 'SELL'>(defaultDirection)
  const [productType, setProductType] = useState<'CNC' | 'MIS'>('CNC') // CNC is strict default
  const [orderType, setOrderType] = useState<OrderTicketType>('MARKET')
  
  const [quantity, setQuantity] = useState<number>(10)
  const [limitPrice, setLimitPrice] = useState<number>(() => resolveEntryBasePrice(currentPrice, bestBuyPrice))
  const [triggerPrice, setTriggerPrice] = useState<number>(() => resolveInitialTriggerPrice(currentPrice, bestBuyPrice))

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
    const baseP = resolveEntryBasePrice(currentPrice, bestBuyPrice)
    setLimitPrice(baseP)
    
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

    // Entry trigger for SL / SL-M defaults to entry/CMP (never the downside stop-loss level)
    setTriggerPrice(resolveInitialTriggerPrice(currentPrice, bestBuyPrice))
    // Reset orderType cleanly: MARKET for immediate entry or At Best Buy; LIMIT when GTT targets a lower dip
    setOrderType(resolveInitialOrderType(isGttMode, currentPrice, bestBuyPrice))
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
  const accentColor = isBuy ? '#2563eb' : '#ea580c'
  const activePrice = resolveActiveOrderPrice({
    orderType,
    currentPrice,
    limitPrice,
    triggerPrice,
  })

  // Calculations
  const grossTradeValue = activePrice * quantity
  const marginRequired = productType === 'MIS' ? grossTradeValue * 0.2 : grossTradeValue // 5x leverage for MIS
  
  // Virtual transaction & statutory fee estimate
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

      const payload = buildPaperOrderPayload({
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
        idempotencyKey: submissionKey,
      })

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

  const executionSummaryText = buildOrderExecutionSummary({
    orderType,
    direction,
    limitPrice,
    triggerPrice,
  })

  return (
    <div style={{
      position: 'fixed',
      inset: 0,
      backgroundColor: 'rgba(0, 0, 0, 0.68)',
      backdropFilter: 'blur(3px)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 10000,
      padding: 12,
    }}>
      <div style={{
        background: 'var(--color-bg-card)',
        border: '1px solid var(--color-border)',
        borderRadius: 12,
        width: '100%',
        maxWidth: 490,
        maxHeight: '92vh',
        overflowY: 'auto',
        boxShadow: '0 24px 60px rgba(0, 0, 0, 0.45)',
        display: 'flex',
        flexDirection: 'column',
      }}>
        {/* Top Bar Header */}
        <div style={{
          background: accentColor,
          color: '#ffffff',
          padding: '12px 16px',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: 10,
        }}>
          <div style={{ minWidth: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
              <span style={{ fontSize: 12, fontWeight: 700, letterSpacing: 0.4, textTransform: 'uppercase', background: 'rgba(255,255,255,0.2)', padding: '2px 8px', borderRadius: 4 }}>
                {direction}
              </span>
              <span style={{ fontSize: 16, fontWeight: 700 }}>
                {symbol.replace('.NS', '')}
              </span>
              <span style={{ fontSize: 11, background: 'rgba(0,0,0,0.22)', padding: '2px 6px', borderRadius: 4 }}>
                NSE · Virtual
              </span>
            </div>
            {name && <div style={{ fontSize: 11.5, opacity: 0.88, marginTop: 2 }}>{name}</div>}
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginLeft: 'auto' }}>
            <div style={{ textAlign: 'right' }}>
              <div className="mono" style={{ fontSize: 15, fontWeight: 700 }}>
                ₹{currentPrice.toFixed(2)}
              </div>
              <div style={{ fontSize: 10.5, opacity: 0.85 }}>
                Last Price
              </div>
            </div>

            <div style={{
              display: 'flex',
              background: 'rgba(0,0,0,0.28)',
              borderRadius: 18,
              padding: 2,
            }}>
              <button
                type="button"
                onClick={() => setDirection('BUY')}
                style={{
                  border: 'none',
                  background: isBuy ? '#ffffff' : 'transparent',
                  color: isBuy ? '#2563eb' : '#ffffff',
                  fontWeight: 700,
                  fontSize: 11.5,
                  padding: '4px 10px',
                  borderRadius: 14,
                  cursor: 'pointer',
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
                  color: !isBuy ? '#ea580c' : '#ffffff',
                  fontWeight: 700,
                  fontSize: 11.5,
                  padding: '4px 10px',
                  borderRadius: 14,
                  cursor: 'pointer',
                }}
              >
                SELL
              </button>
            </div>

            <button
              type="button"
              onClick={onClose}
              aria-label="Close order dialog"
              style={{
                background: 'rgba(255,255,255,0.16)',
                border: 'none',
                color: '#ffffff',
                borderRadius: '50%',
                width: 28,
                height: 28,
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                cursor: 'pointer',
                flexShrink: 0,
              }}
            >
              <X size={15} />
            </button>
          </div>
        </div>

        {/* GTT Mode Sub-bar */}
        {isGttMode && (
          <div style={{
            background: 'var(--color-bg-secondary)',
            borderBottom: '1px solid var(--color-border)',
            padding: '8px 16px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: 8,
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, fontWeight: 700, color: 'var(--color-accent-blue)' }}>
              <Target size={14} />
              <span>Paper GTT Bracket Order</span>
            </div>
            <span style={{ fontSize: 11, background: 'rgba(59, 130, 246, 0.14)', color: 'var(--color-accent-blue)', padding: '2px 8px', borderRadius: 4, fontWeight: 600 }}>
              OCO: Target + Stop Loss Auto-Exit
            </span>
          </div>
        )}

        {/* Order Form Body */}
        <form onSubmit={handleSubmitOrder} style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: 14 }}>
          {/* Product Type (CNC vs MIS) */}
          <div>
            <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--color-text-muted)', marginBottom: 6, textTransform: 'uppercase', letterSpacing: 0.4 }}>
              Product
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 150px), 1fr))', gap: 8 }}>
              <button
                type="button"
                onClick={() => setProductType('CNC')}
                style={{
                  padding: '8px 10px',
                  borderRadius: 6,
                  fontSize: 12.5,
                  fontWeight: 600,
                  border: productType === 'CNC' ? `2px solid ${accentColor}` : '1px solid var(--color-border)',
                  background: productType === 'CNC' ? (isBuy ? 'rgba(37, 99, 235, 0.12)' : 'rgba(234, 88, 12, 0.12)') : 'var(--color-bg-secondary)',
                  color: productType === 'CNC' ? accentColor : 'var(--color-text-secondary)',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 6,
                }}
              >
                <span>CNC</span>
                <span style={{ fontSize: 11, opacity: 0.75 }}>Delivery</span>
              </button>

              <button
                type="button"
                onClick={() => setProductType('MIS')}
                style={{
                  padding: '8px 10px',
                  borderRadius: 6,
                  fontSize: 12.5,
                  fontWeight: 600,
                  border: productType === 'MIS' ? `2px solid ${accentColor}` : '1px solid var(--color-border)',
                  background: productType === 'MIS' ? (isBuy ? 'rgba(37, 99, 235, 0.12)' : 'rgba(234, 88, 12, 0.12)') : 'var(--color-bg-secondary)',
                  color: productType === 'MIS' ? accentColor : 'var(--color-text-secondary)',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 6,
                }}
              >
                <span>MIS</span>
                <span style={{ fontSize: 11, opacity: 0.75 }}>Intraday 5x</span>
              </button>
            </div>
          </div>

          {/* Order Type Tabs */}
          <div>
            <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--color-text-muted)', marginBottom: 6, textTransform: 'uppercase', letterSpacing: 0.4 }}>
              Order Type
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(64px, 1fr))', gap: 6 }}>
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
                      border: isSelected ? `2px solid ${accentColor}` : '1px solid var(--color-border)',
                      background: isSelected ? (isBuy ? 'rgba(37, 99, 235, 0.12)' : 'rgba(234, 88, 12, 0.12)') : 'var(--color-bg-secondary)',
                      color: isSelected ? accentColor : 'var(--color-text-secondary)',
                      cursor: 'pointer',
                      textAlign: 'center',
                    }}
                  >
                    {t.label}
                  </button>
                )
              })}
            </div>
            <div style={{
              marginTop: 8,
              padding: '7px 10px',
              borderRadius: 6,
              background: 'var(--color-bg-secondary)',
              border: '1px solid var(--color-border)',
              fontSize: 11.5,
              color: 'var(--color-text-secondary)',
              lineHeight: 1.45,
            }}>
              {executionSummaryText}
            </div>
          </div>

          {/* Quantity & Price Grid */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 190px), 1fr))', gap: 12 }}>
            {/* Quantity */}
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4, gap: 4 }}>
                <label style={{ fontSize: 12, fontWeight: 600, color: 'var(--color-text-muted)' }}>Qty</label>
                <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                  {[10, 25, 50, 100].map(add => (
                    <button
                      key={add}
                      type="button"
                      onClick={() => handleQuickQty(add)}
                      style={{
                        background: 'transparent',
                        border: '1px solid var(--color-border)',
                        borderRadius: 4,
                        fontSize: 10,
                        padding: '1px 5px',
                        color: 'var(--color-text-muted)',
                        cursor: 'pointer',
                      }}
                    >
                      +{add}
                    </button>
                  ))}
                </div>
              </div>
              <input
                type="number"
                min={1}
                value={quantity}
                onChange={e => setQuantity(Math.max(1, parseInt(e.target.value) || 1))}
                className="input mono"
                style={{ width: '100%', padding: '8px 10px', fontSize: 14, fontWeight: 700 }}
                required
              />
            </div>

            {/* Price / Trigger Price */}
            {orderType === 'SL_M' ? (
              <div>
                <label style={{ fontSize: 12, fontWeight: 600, color: 'var(--color-text-muted)', display: 'block', marginBottom: 4 }}>
                  Trigger Price (₹)
                </label>
                <input
                  type="number"
                  step="0.05"
                  value={triggerPrice}
                  onChange={e => setTriggerPrice(parseFloat(e.target.value) || 0)}
                  className="input mono"
                  style={{ width: '100%', padding: '8px 10px', fontSize: 14, fontWeight: 700 }}
                  required
                />
              </div>
            ) : (
              <div>
                <label style={{ fontSize: 12, fontWeight: 600, color: 'var(--color-text-muted)', display: 'block', marginBottom: 4 }}>
                  {orderType === 'MARKET' ? 'Est. Price (₹)' : 'Limit Price (₹)'}
                </label>
                <input
                  type="number"
                  step="0.05"
                  disabled={orderType === 'MARKET'}
                  value={orderType === 'MARKET' ? currentPrice.toFixed(2) : limitPrice}
                  onChange={e => setLimitPrice(parseFloat(e.target.value) || 0)}
                  className="input mono"
                  style={{
                    width: '100%',
                    padding: '8px 10px',
                    fontSize: 14,
                    fontWeight: 700,
                    opacity: orderType === 'MARKET' ? 0.65 : 1,
                    cursor: orderType === 'MARKET' ? 'not-allowed' : 'text',
                  }}
                  required
                />
              </div>
            )}
          </div>

          {/* Separate Trigger Price for SL (Limit + Trigger) */}
          {orderType === 'SL' && (
            <div>
              <label style={{ fontSize: 12, fontWeight: 600, color: 'var(--color-text-muted)', display: 'block', marginBottom: 4 }}>
                Trigger Price (₹)
              </label>
              <input
                type="number"
                step="0.05"
                value={triggerPrice}
                onChange={e => setTriggerPrice(parseFloat(e.target.value) || 0)}
                className="input mono"
                style={{ width: '100%', padding: '8px 10px', fontSize: 14, fontWeight: 700 }}
                required
              />
            </div>
          )}

          {/* GTT Protection (Target & Stop Loss) */}
          <div style={{
            background: 'var(--color-bg-secondary)',
            border: '1px solid var(--color-border)',
            borderRadius: 8,
            padding: 12,
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8, marginBottom: enableGtt ? 10 : 0 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12.5, fontWeight: 700, color: 'var(--color-text-primary)' }}>
                <ShieldCheck size={15} style={{ color: 'var(--color-bullish)' }} />
                <span>GTT Auto-Exit (Target &amp; Stop Loss)</span>
              </div>
              <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', fontSize: 12, color: 'var(--color-text-secondary)' }}>
                <input
                  type="checkbox"
                  checked={enableGtt}
                  onChange={e => setEnableGtt(e.target.checked)}
                  style={{ accentColor }}
                />
                Enabled
              </label>
            </div>

            {enableGtt && (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 190px), 1fr))', gap: 12 }}>
                {/* Target Section */}
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                    <label style={{ fontSize: 11.5, color: 'var(--color-bullish)', fontWeight: 700 }}>
                      Target
                    </label>
                    <div style={{ display: 'flex', background: 'rgba(16, 185, 129, 0.12)', borderRadius: 10, padding: 2 }}>
                      <button
                        type="button"
                        onClick={() => setTargetMode('PERCENT')}
                        style={{
                          border: 'none',
                          background: targetMode === 'PERCENT' ? '#10b981' : 'transparent',
                          color: targetMode === 'PERCENT' ? '#ffffff' : 'var(--color-text-muted)',
                          fontSize: 10.5,
                          fontWeight: 700,
                          padding: '1px 7px',
                          borderRadius: 8,
                          cursor: 'pointer',
                        }}
                      >
                        %
                      </button>
                      <button
                        type="button"
                        onClick={() => setTargetMode('VALUE')}
                        style={{
                          border: 'none',
                          background: targetMode === 'VALUE' ? '#10b981' : 'transparent',
                          color: targetMode === 'VALUE' ? '#ffffff' : 'var(--color-text-muted)',
                          fontSize: 10.5,
                          fontWeight: 700,
                          padding: '1px 7px',
                          borderRadius: 8,
                          cursor: 'pointer',
                        }}
                      >
                        ₹
                      </button>
                    </div>
                  </div>

                  {targetMode === 'PERCENT' ? (
                    <div>
                      <input
                        type="text"
                        placeholder="e.g. 8%"
                        value={targetPercentInput}
                        onChange={e => handleTargetPercentChange(e.target.value)}
                        className="input mono"
                        style={{ width: '100%', padding: '6px 10px', fontSize: 13, fontWeight: 700, borderColor: 'rgba(16, 185, 129, 0.4)' }}
                      />
                      <div style={{ fontSize: 11, color: 'var(--color-text-muted)', marginTop: 3 }}>
                        Auto-Sell @ <strong style={{ color: 'var(--color-bullish)' }}>₹{targetPrice.toFixed(2)}</strong>
                      </div>
                    </div>
                  ) : (
                    <div>
                      <input
                        type="number"
                        step="0.05"
                        value={targetPrice}
                        onChange={e => handleTargetPriceChange(parseFloat(e.target.value) || 0)}
                        className="input mono"
                        style={{ width: '100%', padding: '6px 10px', fontSize: 13, fontWeight: 700, borderColor: 'rgba(16, 185, 129, 0.4)' }}
                      />
                      <div style={{ fontSize: 11, color: 'var(--color-text-muted)', marginTop: 3 }}>
                        Gain <strong style={{ color: 'var(--color-bullish)' }}>+{activePrice > 0 ? (((targetPrice - activePrice) / activePrice) * 100).toFixed(1) : '0.0'}%</strong>
                      </div>
                    </div>
                  )}
                </div>

                {/* Stop Loss Section */}
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                    <label style={{ fontSize: 11.5, color: 'var(--color-bearish)', fontWeight: 700 }}>
                      Stop Loss
                    </label>
                    <div style={{ display: 'flex', background: 'rgba(239, 68, 68, 0.12)', borderRadius: 10, padding: 2 }}>
                      <button
                        type="button"
                        onClick={() => setSlMode('PERCENT')}
                        style={{
                          border: 'none',
                          background: slMode === 'PERCENT' ? '#ef4444' : 'transparent',
                          color: slMode === 'PERCENT' ? '#ffffff' : 'var(--color-text-muted)',
                          fontSize: 10.5,
                          fontWeight: 700,
                          padding: '1px 7px',
                          borderRadius: 8,
                          cursor: 'pointer',
                        }}
                      >
                        %
                      </button>
                      <button
                        type="button"
                        onClick={() => setSlMode('VALUE')}
                        style={{
                          border: 'none',
                          background: slMode === 'VALUE' ? '#ef4444' : 'transparent',
                          color: slMode === 'VALUE' ? '#ffffff' : 'var(--color-text-muted)',
                          fontSize: 10.5,
                          fontWeight: 700,
                          padding: '1px 7px',
                          borderRadius: 8,
                          cursor: 'pointer',
                        }}
                      >
                        ₹
                      </button>
                    </div>
                  </div>

                  {slMode === 'PERCENT' ? (
                    <div>
                      <input
                        type="text"
                        placeholder="e.g. -4%"
                        value={slPercentInput}
                        onChange={e => handleSlPercentChange(e.target.value)}
                        className="input mono"
                        style={{ width: '100%', padding: '6px 10px', fontSize: 13, fontWeight: 700, borderColor: 'rgba(239, 68, 68, 0.4)' }}
                      />
                      <div style={{ fontSize: 11, color: 'var(--color-text-muted)', marginTop: 3 }}>
                        Auto-Sell @ <strong style={{ color: 'var(--color-bearish)' }}>₹{stopLoss.toFixed(2)}</strong>
                      </div>
                    </div>
                  ) : (
                    <div>
                      <input
                        type="number"
                        step="0.05"
                        value={stopLoss}
                        onChange={e => handleSlPriceChange(parseFloat(e.target.value) || 0)}
                        className="input mono"
                        style={{ width: '100%', padding: '6px 10px', fontSize: 13, fontWeight: 700, borderColor: 'rgba(239, 68, 68, 0.4)' }}
                      />
                      <div style={{ fontSize: 11, color: 'var(--color-text-muted)', marginTop: 3 }}>
                        Risk <strong style={{ color: 'var(--color-bearish)' }}>{activePrice > 0 ? (((stopLoss - activePrice) / activePrice) * 100).toFixed(1) : '0.0'}%</strong>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Coupled Alerts Option */}
            <div style={{ marginTop: 10, paddingTop: 8, borderTop: '1px dashed var(--color-border)' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: 7, cursor: 'pointer', fontSize: 12, color: 'var(--color-text-primary)' }}>
                <input
                  type="checkbox"
                  checked={autoSetAlerts}
                  onChange={e => setAutoSetAlerts(e.target.checked)}
                  style={{ accentColor }}
                />
                <span>Also add price alerts in Alerts tab</span>
              </label>
            </div>
          </div>

          {/* Expandable Fee Breakdown */}
          {showChargesBreakdown && (
            <div style={{
              background: 'var(--color-bg-secondary)',
              border: '1px solid var(--color-border)',
              borderRadius: 8,
              padding: '10px 12px',
              fontSize: 11.5,
              display: 'flex',
              flexDirection: 'column',
              gap: 4,
            }}>
              <div style={{ fontWeight: 700, marginBottom: 2, display: 'flex', justifyContent: 'space-between' }}>
                <span>Estimated Charges</span>
                <button type="button" onClick={() => setShowChargesBreakdown(false)} style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer' }}>Close</button>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--color-text-secondary)' }}><span>Brokerage</span><span className="mono">₹{brokerage.toFixed(2)}</span></div>
              <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--color-text-secondary)' }}><span>STT / CTT</span><span className="mono">₹{stt.toFixed(2)}</span></div>
              <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--color-text-secondary)' }}><span>Exchange Txn</span><span className="mono">₹{exchangeTxn.toFixed(2)}</span></div>
              <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--color-text-secondary)' }}><span>GST (18%)</span><span className="mono">₹{gst.toFixed(2)}</span></div>
              <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--color-text-secondary)' }}><span>Stamp Duty</span><span className="mono">₹{stampDuty.toFixed(2)}</span></div>
            </div>
          )}

          {/* Footer / Execution Bar */}
          <div style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            paddingTop: 12,
            borderTop: '1px solid var(--color-border)',
            flexWrap: 'wrap',
            gap: 10,
          }}>
            <div>
              <div style={{ fontSize: 11.5, color: 'var(--color-text-muted)' }}>
                Margin <strong className="mono" style={{ color: 'var(--color-text-primary)', fontSize: 13 }}>₹{marginRequired.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</strong>
              </div>
              <div style={{ fontSize: 11, color: 'var(--color-text-muted)', display: 'flex', alignItems: 'center', gap: 6, marginTop: 2 }}>
                <span>Est. Fees ~₹{totalCharges.toFixed(2)}</span>
                <button
                  type="button"
                  onClick={() => setShowChargesBreakdown(!showChargesBreakdown)}
                  style={{ background: 'none', border: 'none', color: accentColor, cursor: 'pointer', padding: 0, textDecoration: 'underline', fontSize: 11 }}
                >
                  {showChargesBreakdown ? 'hide' : 'details'}
                </button>
              </div>
            </div>

            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginLeft: 'auto' }}>
              <button
                type="button"
                onClick={onClose}
                className="btn btn-secondary"
                style={{ padding: '8px 14px', fontSize: 12.5 }}
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
                  padding: '9px 18px',
                  fontSize: 13,
                  fontWeight: 700,
                  cursor: submitting ? 'not-allowed' : 'pointer',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 6,
                }}
              >
                {submitting
                  ? 'Placing...'
                  : isGttMode
                  ? `Place ${direction} GTT`
                  : `${direction} ${quantity} ${symbol.replace('.NS', '')}`}
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  )
}
