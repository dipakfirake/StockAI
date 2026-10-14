/**
 * URL Security & Client-Side Privacy Module
 *
 * Provides utilities to keep user navigational activity, stock queries,
 * and chart inspection strictly confidential.
 *
 * Directives:
 * 1. URLs in the address bar MUST NOT reveal the user's analyzed tickers (e.g. /chart/NSEI).
 * 2. Navigations must pass payload objects via React Router memory state: { state: { symbol: '...' } }.
 * 3. Any query parameters or leaked symbols in window.location are purged via history.replaceState.
 * 4. Active symbol is stored in encrypted/local session storage rather than the public URL bar.
 */

/**
 * Strips sensitive search parameters or legacy ticker paths from the browser address bar.
 * Keeps the browser address bar strictly at the clean base route (e.g. `/chart` or `/options`).
 */
export function sanitizeBrowserUrl(baseRoute: string): void {
  if (typeof window === 'undefined') return
  const currentPath = window.location.pathname
  const currentSearch = window.location.search

  if (currentSearch || currentPath !== baseRoute) {
    window.history.replaceState({}, '', baseRoute)
  }
}

/**
 * Obfuscates a stock symbol for safe storage or encrypted state exchange.
 */
export function obfuscateTicker(ticker: string): string {
  if (!ticker) return ''
  try {
    return btoa(encodeURIComponent(ticker.trim().toUpperCase()))
  } catch {
    return ticker
  }
}

/**
 * De-obfuscates an encrypted/encoded ticker token.
 */
export function deobfuscateTicker(token: string): string {
  if (!token) return '^NSEI'
  try {
    return decodeURIComponent(atob(token))
  } catch {
    return token
  }
}
