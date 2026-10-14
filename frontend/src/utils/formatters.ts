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
