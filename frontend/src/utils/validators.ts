/**
 * Centralized Input Validations & Security Sanitizers — StockAI.
 * 
 * Provides client-side defense-in-depth:
 * - RFC 5322 email syntax validation
 * - Password complexity analysis and live checklist state
 * - Display name length checking and HTML injection sanitization
 * - 6-digit numeric OTP format validation
 * - Dynamic MM:SS timer formatting
 */

export interface PasswordCriteria {
  hasMinLength: boolean
  hasLetter: boolean
  hasDigitOrSpecial: boolean
  isStrong: boolean
}

/**
 * Validates email syntax, length, and rejects control characters.
 */
export function validateEmail(email: string): { isValid: boolean; error?: string } {
  const clean = email.trim()
  if (!clean) {
    return { isValid: false, error: 'Email address is required.' }
  }
  if (clean.length < 5) {
    return { isValid: false, error: 'Email address is too short.' }
  }
  if (clean.length > 254) {
    return { isValid: false, error: 'Email address must not exceed 254 characters.' }
  }
  // Standard RFC 5322 regex
  const emailRegex = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/
  if (!emailRegex.test(clean)) {
    return { isValid: false, error: 'Please enter a valid email address (e.g., name@domain.com).' }
  }
  return { isValid: true }
}

/**
 * Evaluates password against enterprise complexity rules.
 */
export function evaluatePasswordStrength(password: string): PasswordCriteria {
  const hasMinLength = password.length >= 8 && password.length <= 128
  const hasLetter = /[a-zA-Z]/.test(password)
  const hasDigitOrSpecial = /[0-9!@#$%^&*(),.?":{}|<>]/.test(password)

  return {
    hasMinLength,
    hasLetter,
    hasDigitOrSpecial,
    isStrong: hasMinLength && hasLetter && hasDigitOrSpecial,
  }
}

/**
 * Sanitizes and validates user display names against XSS and control characters.
 */
export function sanitizeDisplayName(name: string): { isValid: boolean; sanitized: string; error?: string } {
  // Strip HTML / script tags
  let clean = name.replace(/<[^>]*>?/gm, '').trim()
  // Replace multiple spaces
  clean = clean.replace(/\s+/g, ' ')

  if (!clean) {
    return { isValid: false, sanitized: '', error: 'Full name is required.' }
  }
  if (clean.length < 2) {
    return { isValid: false, sanitized: clean, error: 'Name must be at least 2 characters.' }
  }
  if (clean.length > 50) {
    return { isValid: false, sanitized: clean.slice(0, 50), error: 'Name must not exceed 50 characters.' }
  }
  return { isValid: true, sanitized: clean }
}

/**
 * Validates strictly 6-digit numeric OTP code.
 */
export function validateOtpCode(otp: string): boolean {
  return /^\d{6}$/.test(otp.trim())
}

/**
 * Formats duration in seconds to standard MM:SS string.
 */
export function formatTimeRemaining(seconds: number): string {
  if (seconds <= 0) return '00:00'
  const mins = Math.floor(seconds / 60)
  const secs = seconds % 60
  const paddedMins = mins < 10 ? `0${mins}` : `${mins}`
  const paddedSecs = secs < 10 ? `0${secs}` : `${secs}`
  return `${paddedMins}:${paddedSecs}`
}
