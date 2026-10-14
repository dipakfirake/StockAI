import React from 'react'

interface AnimatedNumberProps {
  value: number
  duration?: number // retained for backwards compatibility
  decimals?: number
  prefix?: string
  suffix?: string
  className?: string
  style?: React.CSSProperties
}

/**
 * AnimatedNumber — Clean, instant financial display.
 * Renders real market prices instantaneously without count-up/count-down animations
 * to match institutional terminal standards (Bloomberg / Zerodha Kite / TradingView).
 */
export default function AnimatedNumber({
  value,
  decimals = 2,
  prefix = '',
  suffix = '',
  className,
  style,
}: AnimatedNumberProps) {
  const safeValue = typeof value === 'number' && !isNaN(value) ? value : 0
  const formatted = safeValue.toLocaleString('en-IN', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })

  return (
    <span className={className} style={style}>
      {prefix}{formatted}{suffix}
    </span>
  )
}
