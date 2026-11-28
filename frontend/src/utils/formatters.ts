/**
 * Utility functions for institutional-grade Indian financial price & number formatting.
 * Enforces strict 2 decimal places (e.g., 2302 -> 2,302.00, 2302.1 -> 2,302.10).
 */

/**
 * Formats a price value with the Indian Rupee symbol (₹), standard Indian commas (lakhs/crores),
 * and strictly 2 decimal places.
 *
 * @param val The numeric or string value to format.
 * @param fallback The fallback string if the value is null, undefined, or invalid (default: '—').
 * @returns Formatted currency string, e.g. '₹2,302.00', '₹2,302.10', '₹3,350.00'.
 */
export function formatINR(val: number | string | null | undefined, fallback: string = '—'): string {
  if (val === null || val === undefined || val === '') return fallback
  const num = typeof val === 'number' ? val : Number(val)
  if (isNaN(num)) return fallback

  return `₹${num.toLocaleString('en-IN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`
}

/**
 * Formats a number with standard Indian commas and strictly 2 decimal places WITHOUT currency symbol.
 *
 * @param val The numeric or string value to format.
 * @param fallback The fallback string if the value is null, undefined, or invalid (default: '—').
 * @returns Formatted number string, e.g. '2,302.00', '2,302.10', '3,350.00'.
 */
export function formatNumber2Dec(val: number | string | null | undefined, fallback: string = '—'): string {
  if (val === null || val === undefined || val === '') return fallback
  const num = typeof val === 'number' ? val : Number(val)
  if (isNaN(num)) return fallback

  return num.toLocaleString('en-IN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

/**
 * Returns 'var(--color-pnl-zero)' for zero so Light & Dark themes both render legibly.
 */
export function getPnlColor(val: number | string | null | undefined): string {
  if (val === null || val === undefined || val === '') return 'var(--color-pnl-zero, #f1f5f9)'
  const num = typeof val === 'number' ? val : Number(val)
  if (isNaN(num) || Math.abs(num) <= 0.0001) return 'var(--color-pnl-zero, #f1f5f9)'
  return num > 0 ? '#10b981' : '#ef4444'
}

/**
 * Resolves CSS class for 3-tier P&L styling:
 * - Profit (> 0): 'positive'
 * - Loss (< 0): 'negative'
 * - Zero (== 0): 'neutral-zero'
 */
export function getPnlClass(val: number | string | null | undefined): string {
  if (val === null || val === undefined || val === '') return 'neutral-zero'
  const num = typeof val === 'number' ? val : Number(val)
  if (isNaN(num) || Math.abs(num) <= 0.0001) return 'neutral-zero'
  return num > 0 ? 'positive' : 'negative'
}

/**
 * Returns '+' for positive values, and '' for zero or negative values.
 */
export function getPnlSign(val: number | string | null | undefined): string {
  if (val === null || val === undefined || val === '') return ''
  const num = typeof val === 'number' ? val : Number(val)
  if (isNaN(num) || Math.abs(num) <= 0.0001) return ''
  return num > 0 ? '+' : ''
}

/**
 * Formats ISO/Date timestamps concisely in IST (e.g., "27 Nov, 12:36 AM IST").
 */
export function formatISTTimestamp(raw?: string | Date | null, fallback = ''): string {
  if (!raw) return fallback
  const dt = raw instanceof Date ? raw : new Date(raw)
  if (Number.isNaN(dt.getTime())) return String(raw)
  return (
    dt.toLocaleString('en-IN', {
      timeZone: 'Asia/Kolkata',
      day: '2-digit',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit',
      hour12: true,
    }) + ' IST'
  )
}

/**
 * Strips raw Markdown tokens (### headers, **bold**, redundant bracket noise) into clean sentences.
 */
export function cleanBriefMarkdown(raw?: string | null): string {
  if (!raw) return ''
  return raw
    .replace(/^#{1,6}\s*/gm, '')
    .replace(/\*\*(.*?)\*\*/g, '$1')
    .replace(/__(.*?)__/g, '$1')
    .replace(/\[([^\]]+)\]/g, '$1')
    .replace(/\s*-\s+/g, ' · ')
    .replace(/\s{2,}/g, ' ')
    .trim()
}
