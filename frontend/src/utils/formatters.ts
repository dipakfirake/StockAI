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
 * Strict 3-tier color resolver for P&L and prices:
 * - Profit (> 0): Vibrant Green (#10b981)
 * - Loss (< 0): Crimson Red (#ef4444)
 * - Zero / No profit no loss (== 0): Pure White (#ffffff)
 */
export function getPnlColor(val: number | string | null | undefined): string {
  if (val === null || val === undefined || val === '') return '#ffffff'
  const num = typeof val === 'number' ? val : Number(val)
  if (isNaN(num) || Math.abs(num) <= 0.0001) return '#ffffff'
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
