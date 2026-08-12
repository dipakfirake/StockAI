import React, { useEffect, useRef, useState } from 'react'

interface AnimatedNumberProps {
  value: number
  duration?: number // ms
  decimals?: number
  prefix?: string
  suffix?: string
  className?: string
  style?: React.CSSProperties
}

/**
 * AnimatedNumber — counts up from 0 (or previous value) to the target value
 * with a smooth easeOut animation. Perfect for dashboard index prices.
 */
export default function AnimatedNumber({
  value,
  duration = 800,
  decimals = 2,
  prefix = '',
  suffix = '',
  className,
  style,
}: AnimatedNumberProps) {
  const [displayValue, setDisplayValue] = useState(0)
  const startRef = useRef(0)
  const startTimeRef = useRef<number | null>(null)
  const rafRef = useRef<number | null>(null)

  useEffect(() => {
    const start = startRef.current
    const end = value
    startTimeRef.current = null

    const easeOut = (t: number) => 1 - Math.pow(1 - t, 3)

    const animate = (timestamp: number) => {
      if (!startTimeRef.current) startTimeRef.current = timestamp
      const elapsed = timestamp - startTimeRef.current
      const progress = Math.min(elapsed / duration, 1)
      const easedProgress = easeOut(progress)

      setDisplayValue(start + (end - start) * easedProgress)

      if (progress < 1) {
        rafRef.current = requestAnimationFrame(animate)
      } else {
        startRef.current = end
        setDisplayValue(end)
      }
    }

    if (rafRef.current) cancelAnimationFrame(rafRef.current)
    rafRef.current = requestAnimationFrame(animate)

    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current)
    }
  }, [value, duration])

  const formatted = displayValue.toLocaleString('en-IN', {
    maximumFractionDigits: decimals,
    minimumFractionDigits: decimals,
  })

  return (
    <span className={className} style={style}>
      {prefix}{formatted}{suffix}
    </span>
  )
}
