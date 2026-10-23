import React from 'react'
import { useNavigate } from 'react-router-dom'
import { 
  X, 
  Calendar, 
  Clock, 
  TrendingUp, 
  TrendingDown, 
  ExternalLink, 
  DollarSign, 
  BarChart2, 
  Percent, 
  Briefcase 
} from 'lucide-react'
import { formatINR, formatNumber2Dec, getPnlColor, getPnlClass, getPnlSign } from '../utils/formatters'

interface HoldingData {
  trade_id?: string
  symbol: string
  direction: string
  order_type?: string
  product_type?: string
  quantity: number
  entry_price: number
  current_price: number
  previous_close?: number
  invested?: number
  value?: number
  unrealized_pnl: number
  gross_pnl?: number
  total_charges?: number
  commission?: number
  stt_tax?: number
  pnl_pct?: number
  price_change_pct?: number
  day_change?: number
  day_change_pct?: number
  day_pnl?: number
  opened_at?: string
  buy_date_formatted?: string
  days_held?: number
  weight_pct?: number
  is_bought_today?: boolean
  day_baseline?: number
  day_baseline_type?: string
}

interface HoldingDetailModalProps {
  isOpen: boolean
  onClose: () => void
  holding: HoldingData | null
  onExit?: (tradeId: string) => void
}

export default function HoldingDetailModal({
  isOpen,
  onClose,
  holding,
  onExit,
}: HoldingDetailModalProps) {
  const navigate = useNavigate()

  if (!isOpen || !holding) return null

  const isBuy = holding.direction === 'BUY'
  const overallPnl = holding.unrealized_pnl ?? 0
  const dayPnl = holding.day_pnl ?? 0
  const daysHeld = holding.days_held ?? 0

  const investedAmt = holding.invested ?? (holding.entry_price * holding.quantity)
  const currentVal = holding.value ?? (holding.current_price * holding.quantity)
  const buyReturnPct = holding.pnl_pct ?? (
    investedAmt > 0 
      ? Number(((overallPnl / investedAmt) * 100).toFixed(2))
      : 0
  )
  const dayGainAmt = dayPnl
  const dayGainPct = holding.day_change_pct ?? 0

  const overallBorder = overallPnl > 0.0001
    ? 'rgba(16, 185, 129, 0.4)'
    : overallPnl < -0.0001
    ? 'rgba(239, 68, 68, 0.4)'
    : 'rgba(255, 255, 255, 0.2)'
  const overallBg = overallPnl > 0.0001
    ? 'rgba(16, 185, 129, 0.08)'
    : overallPnl < -0.0001
    ? 'rgba(239, 68, 68, 0.08)'
    : 'rgba(255, 255, 255, 0.04)'

  const dayBorder = dayPnl > 0.0001
    ? 'rgba(16, 185, 129, 0.4)'
    : dayPnl < -0.0001
    ? 'rgba(239, 68, 68, 0.4)'
    : 'rgba(255, 255, 255, 0.2)'
  const dayBg = dayPnl > 0.0001
    ? 'rgba(16, 185, 129, 0.08)'
    : dayPnl < -0.0001
    ? 'rgba(239, 68, 68, 0.08)'
    : 'rgba(255, 255, 255, 0.04)'

  return (
    <div 
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: 'rgba(5, 10, 20, 0.75)',
        backdropFilter: 'blur(6px)',
        zIndex: 99999,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '16px',
        animation: 'fadeIn 0.2s ease-out',
      }}
      onClick={onClose}
    >
      <div 
        className="card"
        style={{
          width: '100%',
          maxWidth: 580,
          maxHeight: '90vh',
          overflowY: 'auto',
          padding: 0,
          background: 'var(--color-bg-card, #131722)',
          border: '1px solid var(--color-border, #2a2e39)',
          borderRadius: 16,
          boxShadow: '0 20px 40px rgba(0, 0, 0, 0.45)',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header Bar */}
        <div style={{
          padding: '20px 24px',
          borderBottom: '1px solid var(--color-border, #2a2e39)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
          background: 'rgba(255, 255, 255, 0.02)',
        }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
              <h2 style={{ margin: 0, fontSize: 22, fontWeight: 700, letterSpacing: '0.5px' }} className="mono">
                {holding.symbol}
              </h2>
              <span className={`badge ${isBuy ? 'badge-buy' : 'badge-sell'}`} style={{ fontSize: 11, padding: '2px 8px' }}>
                {holding.direction}
              </span>
              {holding.product_type && (
                <span className="badge badge-secondary" style={{ fontSize: 11, padding: '2px 8px' }}>
                  {holding.product_type}
                </span>
              )}
            </div>
            <div style={{ fontSize: 12, color: 'var(--color-text-muted)', display: 'flex', alignItems: 'center', gap: 6 }}>
              <Briefcase size={13} />
              Holding Position • {holding.quantity} {holding.quantity === 1 ? 'Share' : 'Shares'}
            </div>
          </div>
          <button 
            onClick={onClose}
            aria-label="Close modal"
            style={{
              background: 'rgba(255, 255, 255, 0.05)',
              border: 'none',
              borderRadius: '50%',
              width: 34,
              height: 34,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'var(--color-text-secondary)',
              cursor: 'pointer',
              transition: 'background 0.2s',
            }}
          >
            <X size={18} />
          </button>
        </div>

        {/* Modal Body */}
        <div style={{ padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: 20 }}>
          
          {/* Days Held & Purchase Date Banner */}
          <div style={{
            background: 'linear-gradient(135deg, rgba(37, 99, 235, 0.12), rgba(79, 70, 229, 0.06))',
            border: '1px solid rgba(59, 130, 246, 0.3)',
            borderRadius: 12,
            padding: '14px 18px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <div style={{
                width: 40,
                height: 40,
                borderRadius: 10,
                background: 'rgba(59, 130, 246, 0.2)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#60a5fa',
              }}>
                <Calendar size={20} />
              </div>
              <div>
                <div style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.5px', color: '#93c5fd', fontWeight: 600 }}>
                  Holding Duration
                </div>
                <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--color-text-primary)' }}>
                  {daysHeld === 0 ? 'Bought Today (Day 0)' : `${daysHeld} ${daysHeld === 1 ? 'Day' : 'Days'} Held`}
                </div>
              </div>
            </div>
            {holding.buy_date_formatted && (
              <div style={{ textAlign: 'right' }}>
                <div style={{ fontSize: 11, color: 'var(--color-text-muted)', marginBottom: 2 }}>Bought On</div>
                <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--color-text-secondary)' }}>
                  {holding.buy_date_formatted}
                </div>
              </div>
            )}
          </div>

          {/* Primary Metrics: Buy Return % and Today's P&L (Strict Red / Green / White) */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
            {/* Overall Return on Buying */}
            <div style={{
              background: overallBg,
              border: `1px solid ${overallBorder}`,
              borderRadius: 12,
              padding: '16px',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
                <span style={{ fontSize: 11, textTransform: 'uppercase', fontWeight: 600, color: 'var(--color-text-muted)' }}>
                  Return on Buying
                </span>
                {overallPnl > 0.0001 ? (
                  <TrendingUp size={16} style={{ color: '#10b981' }} />
                ) : overallPnl < -0.0001 ? (
                  <TrendingDown size={16} style={{ color: '#ef4444' }} />
                ) : (
                  <Clock size={16} style={{ color: '#ffffff' }} />
                )}
              </div>
              <div style={{ fontSize: 24, fontWeight: 700, letterSpacing: '-0.5px', color: getPnlColor(overallPnl) }} className="mono">
                {getPnlSign(buyReturnPct)}{buyReturnPct.toFixed(2)}%
              </div>
              <div style={{ fontSize: 13, marginTop: 4, fontWeight: 500, color: getPnlColor(overallPnl) }} className="mono">
                {getPnlSign(overallPnl)}{formatINR(overallPnl)}
              </div>
              <div style={{ fontSize: 10, color: 'var(--color-text-muted)', marginTop: 6 }}>
                Net profit/loss after charges
              </div>
            </div>

            {/* Today's Profit & Loss for Current Stock */}
            <div style={{
              background: dayBg,
              border: `1px solid ${dayBorder}`,
              borderRadius: 12,
              padding: '16px',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
                <span style={{ fontSize: 11, textTransform: 'uppercase', fontWeight: 600, color: 'var(--color-text-muted)' }}>
                  Today's Day P&L
                </span>
                <Clock size={15} style={{ color: getPnlColor(dayPnl) }} />
              </div>
              <div style={{ fontSize: 24, fontWeight: 700, letterSpacing: '-0.5px', color: getPnlColor(dayPnl) }} className="mono">
                {getPnlSign(dayGainAmt)}{formatINR(dayGainAmt)}
              </div>
              <div style={{ fontSize: 13, marginTop: 4, fontWeight: 500, color: getPnlColor(dayGainPct) }} className="mono">
                {getPnlSign(dayGainPct)}{dayGainPct.toFixed(2)}% Today
              </div>
              <div style={{ fontSize: 10, color: 'var(--color-text-muted)', marginTop: 6 }}>
                {holding.is_bought_today || daysHeld === 0
                  ? 'Calculated from buy price at purchase time today'
                  : 'Calculated from today session starting price (Prev Close)'}
              </div>
            </div>
          </div>

          {/* Breakdown Details Table */}
          <div style={{
            background: 'var(--color-bg-secondary, rgba(255, 255, 255, 0.03))',
            borderRadius: 12,
            border: '1px solid var(--color-border, #2a2e39)',
            padding: '16px',
          }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--color-text-secondary)', marginBottom: 12, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
              Price & Investment Breakdown
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '12px 20px' }}>
              <div>
                <div style={{ fontSize: 11, color: 'var(--color-text-muted)' }}>Purchase / Buy Price</div>
                <div style={{ fontSize: 15, fontWeight: 600, marginTop: 2 }} className="mono">
                  {formatINR(holding.entry_price)}
                </div>
              </div>
              <div>
                <div style={{ fontSize: 11, color: 'var(--color-text-muted)' }}>Current Market Price (LTP)</div>
                <div style={{ fontSize: 15, fontWeight: 600, marginTop: 2 }} className="mono">
                  {formatINR(holding.current_price)}
                </div>
              </div>
              <div>
                <div style={{ fontSize: 11, color: 'var(--color-text-muted)' }}>Total Invested (Cost)</div>
                <div style={{ fontSize: 15, fontWeight: 600, marginTop: 2 }} className="mono">
                  {formatINR(investedAmt)}
                </div>
              </div>
              <div>
                <div style={{ fontSize: 11, color: 'var(--color-text-muted)' }}>Current Market Value</div>
                <div style={{ fontSize: 15, fontWeight: 600, marginTop: 2 }} className="mono">
                  {formatINR(currentVal)}
                </div>
              </div>
              <div>
                <div style={{ fontSize: 11, color: 'var(--color-text-muted)' }}>Gross Market Movement</div>
                <div style={{ fontSize: 14, fontWeight: 500, marginTop: 2, color: getPnlColor(holding.price_change_pct ?? (holding.current_price - holding.entry_price)) }} className="mono">
                  {getPnlSign(holding.price_change_pct ?? (holding.current_price - holding.entry_price))}
                  {holding.price_change_pct !== undefined 
                    ? `${holding.price_change_pct.toFixed(2)}%` 
                    : `${(((holding.current_price - holding.entry_price) / holding.entry_price) * 100 * (isBuy ? 1 : -1)).toFixed(2)}%`}
                  {holding.gross_pnl !== undefined && ` (${getPnlSign(holding.gross_pnl)}${formatINR(holding.gross_pnl)})`}
                </div>
              </div>
              {holding.total_charges !== undefined && (
                <div>
                  <div style={{ fontSize: 11, color: 'var(--color-text-muted)' }}>Charges (Brokerage + STT)</div>
                  <div style={{ fontSize: 14, fontWeight: 500, marginTop: 2, color: 'var(--color-text-secondary)' }} className="mono">
                    {formatINR(holding.total_charges)}
                  </div>
                </div>
              )}
              <div>
                <div style={{ fontSize: 11, color: 'var(--color-text-muted)' }}>Today's Baseline Reference</div>
                <div style={{ fontSize: 14, fontWeight: 500, marginTop: 2, color: 'var(--color-text-secondary)' }} className="mono">
                  {holding.is_bought_today || daysHeld === 0 ? `${formatINR(holding.entry_price)} (Buy Price)` : `${formatINR(holding.previous_close)} (Prev Close)`}
                </div>
              </div>
              {holding.day_change !== undefined && (
                <div>
                  <div style={{ fontSize: 11, color: 'var(--color-text-muted)' }}>Today's Price Change / Share</div>
                  <div style={{ fontSize: 14, fontWeight: 500, marginTop: 2, color: getPnlColor(holding.day_change) }} className="mono">
                    {getPnlSign(holding.day_change)}{formatINR(holding.day_change)}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Quick Actions Footer */}
          <div style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 12,
            paddingTop: 8,
          }}>
            <button
              className="btn btn-secondary"
              onClick={() => {
                onClose()
                navigate('/chart', { state: { symbol: holding.symbol } })
              }}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                padding: '9px 16px',
                fontSize: 13,
                fontWeight: 600,
              }}
            >
              <BarChart2 size={16} /> Open Chart
            </button>

            <button
              className="btn btn-secondary"
              onClick={() => {
                onClose()
                navigate('/chart', { state: { symbol: holding.symbol, focus: 'ai' } })
              }}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                padding: '9px 16px',
                fontSize: 13,
                fontWeight: 600,
              }}
            >
              <ExternalLink size={16} /> AI Forecast
            </button>

            {onExit && holding.trade_id && (
              <button
                className="btn btn-danger"
                onClick={() => {
                  if (confirm(`Exit position for ${holding.symbol}?`)) {
                    onExit(holding.trade_id!)
                    onClose()
                  }
                }}
                style={{
                  padding: '9px 16px',
                  fontSize: 13,
                  fontWeight: 600,
                }}
              >
                Square Off / Exit
              </button>
            )}

            <button
              className="btn"
              onClick={onClose}
              style={{
                background: 'var(--color-bg-secondary)',
                border: '1px solid var(--color-border)',
                padding: '9px 16px',
                fontSize: 13,
              }}
            >
              Close
            </button>
          </div>

        </div>
      </div>
    </div>
  )
}
