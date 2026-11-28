import axios from 'axios'

const BASE_URL = '/api'

// Short-lived in-memory Admin Step-Up Re-Auth token (never stored in localStorage)
let _inMemoryAdminStepUpToken: string | null = null
let _stepUpExpiresAt = 0

export function setAdminStepUpToken(token: string | null, expiresInSeconds: number = 600) {
  _inMemoryAdminStepUpToken = token
  _stepUpExpiresAt = token ? Date.now() + expiresInSeconds * 1000 : 0
}

export function getAdminStepUpToken(): string | null {
  if (!_inMemoryAdminStepUpToken || Date.now() >= _stepUpExpiresAt) {
    _inMemoryAdminStepUpToken = null
    _stepUpExpiresAt = 0
    return null
  }
  return _inMemoryAdminStepUpToken
}

function readCookieValue(name: string): string | null {
  if (typeof document === 'undefined' || !document.cookie) return null
  const prefix = `${name}=`
  const parts = document.cookie.split(';')
  for (const part of parts) {
    const trimmed = part.trim()
    if (trimmed.startsWith(prefix)) {
      return decodeURIComponent(trimmed.slice(prefix.length))
    }
  }
  return null
}

const api = axios.create({
  baseURL: BASE_URL,
  timeout: 60000,
  withCredentials: true,
  headers: { 'Content-Type': 'application/json' },
})

// Attach double-submit CSRF header + optional in-memory Admin Step-Up token on every request
api.interceptors.request.use((config) => {
  const method = String(config.method || 'get').toLowerCase()
  if (['post', 'put', 'patch', 'delete'].includes(method)) {
    const csrf = readCookieValue('stockai_csrf_token')
    if (csrf) {
      config.headers['X-CSRF-Token'] = csrf
    }
  }
  const stepUpTok = getAdminStepUpToken()
  if (stepUpTok) {
    config.headers['X-Admin-StepUp-Token'] = stepUpTok
  }
  return config
})

// Interface for retry tracking
interface RetryConfig {
  __retryCount?: number;
  skipRetry?: boolean;
  method?: string;
  url?: string;
  params?: any;
  headers?: any;
}

// Handle responses, silent exponential backoff retry on server restart (502/503/network), and auth errors safely
api.interceptors.response.use(
  (res) => {
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('api_connection_state', { detail: { state: 'connected' } }))
    }
    return res
  },
  async (err) => {
    const config = err.config as (RetryConfig & typeof err.config) | undefined
    const isNetworkError = !err.response || err.code === 'ERR_NETWORK' || err.code === 'ECONNABORTED' || err.message?.includes('Network Error')
    const isServerRestart = err.response && (err.response.status === 502 || err.response.status === 503 || err.response.status === 504)

    // If client browser is completely offline, do not execute retries that flood the console
    if (typeof navigator !== 'undefined' && !navigator.onLine) {
      return Promise.reject(err)
    }

    // Never auto-retry heavy market scan or force-refresh endpoints — multiplying 60s scans causes cascading 504 storms
    const urlStr = String(config?.url || '')
    const isHeavyOrForced =
      Boolean(config?.skipRetry) ||
      Boolean(config?.params?.force_refresh) ||
      urlStr.includes('/market/screener') ||
      urlStr.includes('/market/bulk-screener') ||
      urlStr.includes('/alerts/screener-proximity-radar') ||
      urlStr.includes('/swing-audit/recalculate')

    // Silently retry lightweight GET requests up to 3 times during brief server restarts
    const isRetryableMethod = !config?.method || ['get', 'head', 'options'].includes(config.method.toLowerCase())
    const canRetry = !isHeavyOrForced && config && isRetryableMethod && (isNetworkError || isServerRestart) && (config.__retryCount || 0) < 3

    if (canRetry) {
      config.__retryCount = (config.__retryCount || 0) + 1
      const delayMs = Math.min(2500, 500 * Math.pow(2, config.__retryCount - 1)) + Math.random() * 150

      if (typeof window !== 'undefined') {
        window.dispatchEvent(new CustomEvent('api_connection_state', { detail: { state: 'reconnecting', attempt: config.__retryCount } }))
      }

      await new Promise((resolve) => setTimeout(resolve, delayMs))
      return api(config)
    }

    // Only redirect on authentic HTTP 401 from protected routes when a user session was active
    if (err.response?.status === 401) {
      const isAuthRoute =
        urlStr.includes('/auth/login') ||
        urlStr.includes('/auth/register') ||
        urlStr.includes('/auth/mfa/verify-login') ||
        urlStr.includes('/auth/me')
      if (!isAuthRoute && localStorage.getItem('auth_user_cache')) {
        localStorage.removeItem('auth_token')
        localStorage.removeItem('auth_user_cache')
        setAdminStepUpToken(null)
        if (typeof window !== 'undefined') {
          window.dispatchEvent(new CustomEvent('auth_session_expired'))
        }
      }
    }

    return Promise.reject(err)
  }
)

// Helper for safely encoding stock symbols with special characters (e.g. M&M.NS -> M%26M.NS)
export const encodeSymbol = (symbol: string) => encodeURIComponent((symbol || '').trim())

// ===== Stock endpoints =====
export const stocksApi = {
  search: (q: string) => api.get('/stocks/search', { params: { q } }),
  getQuote: (symbol: string) => api.get(`/stocks/${encodeSymbol(symbol)}/quote`),
  getCandles: (symbol: string, timeframe = '1d', limit = 750) =>
    api.get(`/stocks/${encodeSymbol(symbol)}/candles`, { params: { timeframe, limit } }),
  getIndicators: (symbol: string, timeframe = '1d') =>
    api.get(`/stocks/${encodeSymbol(symbol)}/indicators`, { params: { timeframe } }),
  getSignals: (symbol: string, timeframe = '1d') =>
    api.get(`/stocks/${encodeSymbol(symbol)}/signals`, { params: { timeframe } }),
  getAIScore: (symbol: string, timeframe = '1d', mode = 'SWING', segment = 'AUTO') =>
    api.get(`/stocks/${encodeSymbol(symbol)}/ai-score`, { params: { timeframe, mode, segment } }),
  getInfo: (symbol: string) => api.get(`/stocks/${encodeSymbol(symbol)}/info`),
  getPatterns: (symbol: string, timeframe = '1d', limit = 250) =>
    api.get(`/stocks/${encodeSymbol(symbol)}/patterns`, { params: { timeframe, limit } }),
  getInsight: (symbol: string, timeframe = '1d', anchorDate?: string | null) =>
    api.get(`/stocks/${encodeSymbol(symbol)}/insight`, { params: { timeframe, ...(anchorDate && { anchor_date: anchorDate }) } }),
  getVolumeProfile: (symbol: string, timeframe = '1d') =>
    api.get(`/stocks/${encodeSymbol(symbol)}/volume-profile`, { params: { timeframe } }),
  getDepth: (symbol: string, simulate = false) => api.get(`/stocks/${encodeSymbol(symbol)}/depth`, { params: { simulate } }),
  scanMarket: (rule: string) => api.get(`/scanner/nifty50`, { params: { rule } }),
  customScan: (data: { universe: string; timeframe?: string; conditions: Array<{ indicator: string; operator: string; value: number | string }> }) => api.post(`/scanner/custom`, data),
}

// ===== Watchlist endpoints =====
export const watchlistApi = {
  get: () => api.get('/watchlist'),
  add: (symbol: string) => api.post('/watchlist', { symbol }),
  remove: (symbol: string) => api.delete(`/watchlist/${encodeSymbol(symbol)}`),
}

// ===== Alert endpoints =====
export const alertsApi = {
  list: () => api.get('/alerts'),
  create: (data: { symbol: string; condition_type: string; condition_value: number; message?: string; priority?: 'HIGH' | 'MEDIUM' | 'LOW'; delivery_method?: 'IN_APP' | 'EMAIL' | 'BOTH' }) =>
    api.post('/alerts', data),
  screenerSetup: (data: {
    symbol: string;
    current_price: number;
    best_buy_price?: number;
    target_price?: number;
    stop_loss?: number;
    proximity_pct?: number;
  }) => api.post('/alerts/screener-setup', data),
  getHoldingsMonitor: () => api.get('/alerts/holdings-monitor'),
  syncHoldings: () => api.post('/alerts/holdings-sync'),
  getScreenerRadar: (sector?: string, proximityPct?: number, minScore?: number, stage?: string, forceRefresh?: boolean) =>
    api.get('/alerts/screener-proximity-radar', {
      params: {
        ...(sector && { sector }),
        ...(proximityPct !== undefined && { proximity_pct: proximityPct }),
        ...(minScore !== undefined && { min_score: minScore }),
        ...(stage && { stage }),
        ...(forceRefresh !== undefined && { force_refresh: forceRefresh }),
      },
    }),
  bulkScreenerSetup: (items: Array<{
    symbol: string;
    current_price: number;
    best_buy_price?: number;
    target_price?: number;
    stop_loss?: number;
    proximity_pct?: number;
  }>) => api.post('/alerts/screener-bulk-setup', { items }),
  delete: (alertId: string) => api.delete(`/alerts/${alertId}`),
  deactivate: (alertId: string) => api.put(`/alerts/${alertId}/deactivate`),
}

// ===== Persistent Notifications Inbox endpoints =====
export const notificationsApi = {
  list: (params?: { category?: string; unread_only?: boolean; limit?: number }) =>
    api.get('/notifications', { params }),
  markSeen: () => api.post('/notifications/mark-seen'),
  markAllRead: () => api.post('/notifications/mark-all-read'),
  markRead: (notificationId: number) => api.post(`/notifications/${notificationId}/read`),
}

// ===== Paper trading endpoints =====
export const paperTradingApi = {
  list: () => api.get('/paper-trades'),
  place: (data: { 
    symbol: string; 
    direction: string; 
    quantity: number;
    order_type?: string;
    product_type?: string;
    limit_price?: number;
    stop_price?: number;
    target_price?: number;
    stop_loss?: number;
    target_1?: number;
    target_2?: number;
    target_3?: number;
    trailing_enabled?: boolean;
    idempotency_key?: string;
  }) => api.post('/paper-trades', data),
  close: (tradeId: string) => api.put(`/paper-trades/${tradeId}/close`),
}

// ===== Portfolio endpoints =====
export const portfolioApi = {
  get: () => api.get('/portfolio'),
}

// ===== Backtest endpoints =====
export const backtestApi = {
  run: (data: object) => api.post('/backtest/run', data),
  getResults: (backtestId: string) => api.get(`/backtest/${backtestId}/results`),
  listStrategies: () => api.get('/backtest/strategies'),
}

// ===== Market endpoints =====
// Consolidated Single-Flight request cache & cloning for /market/indices
let inFlightIndicesPromise: Promise<any> | null = null
let cachedIndicesResponse: { data: any; timestamp: number } | null = null
const INDICES_CLIENT_CACHE_TTL_MS = 2500

const getMonotonicTime = (): number => {
  if (typeof performance !== 'undefined' && typeof performance.now === 'function') {
    return performance.now()
  }
  return Date.now()
}

const cloneIndicesResponse = (res: any) => {
  if (!res) return res
  try {
    return {
      ...res,
      data: res.data ? JSON.parse(JSON.stringify(res.data)) : res.data,
    }
  } catch {
    let clonedData = res.data
    if (Array.isArray(res.data)) {
      clonedData = [...res.data]
    } else if (res.data && typeof res.data === 'object') {
      clonedData = { ...res.data }
    }
    return {
      ...res,
      data: clonedData,
    }
  }
}

export const _resetIndicesCache = () => {
  cachedIndicesResponse = null
  inFlightIndicesPromise = null
}

export const marketApi = {
  getRegime: () => api.get('/market/regime'),
  getIndices: async (forceRefresh = false) => {
    const now = getMonotonicTime()
    if (!forceRefresh && cachedIndicesResponse && now - cachedIndicesResponse.timestamp < INDICES_CLIENT_CACHE_TTL_MS) {
      // Return deep clone of cached response payload to guarantee complete reference isolation across consumers
      return cloneIndicesResponse(cachedIndicesResponse.data)
    }
    if (!forceRefresh && inFlightIndicesPromise) {
      const res = await inFlightIndicesPromise
      return cloneIndicesResponse(res)
    }
    inFlightIndicesPromise = api.get('/market/indices')
      .then((res) => {
        cachedIndicesResponse = { data: res, timestamp: getMonotonicTime() }
        inFlightIndicesPromise = null
        return res
      })
      .catch((err) => {
        inFlightIndicesPromise = null
        throw err
      })
    const res = await inFlightIndicesPromise
    return cloneIndicesResponse(res)
  },
  getVix: () => api.get('/market/vix'),
  getEvents: () => api.get('/market/events'),
  getSectors: () => api.get('/market/sectors'),
  getHeatmap: () => api.get('/market/heatmap'),
  getOptions: (symbol: string) => api.get(`/market/options/${encodeSymbol(symbol)}`),
  getScreener: (sector?: string, forceRefresh = false) =>
    api.get('/market/screener', {
      params: { ...(sector && { sector }), force_refresh: forceRefresh },
      timeout: 90000,
      skipRetry: true,
    } as any),
  startScreenerScan: (sector?: string, forceRefresh = true) =>
    api.post('/market/screener/scan', null, {
      params: { ...(sector && { sector }), force_refresh: forceRefresh },
      timeout: 30000,
    }),
  getScreenerScanStatus: (jobId: string) =>
    api.get(`/market/screener/scan/${encodeURIComponent(jobId)}`, {
      timeout: 20000,
      skipRetry: true,
    } as any),
  getBulkScreener: () => api.get('/market/bulk-screener'),
}

// ===== AI endpoints =====
export const aiApi = {
  score: (symbol: string, timeframe = '1d') =>
    api.get(`/ai/score/${encodeSymbol(symbol)}`, { params: { timeframe } }),
  scan: (symbols: string[], timeframe = '1d') =>
    api.get('/ai/scan', { params: { symbols: symbols.join(','), timeframe } }),
  sentiment: (symbol: string) => api.get(`/ml/sentiment/${encodeSymbol(symbol)}`),
  chat: (message: string, symbol?: string) => api.post('/ai/chat', { message, symbol }),
}

// ===== Auth endpoints =====
export const authApi = {
  getConfig: () => api.get('/auth/config'),
  login: (email: string, password: string) =>
    api.post('/auth/login', new URLSearchParams({ username: email, password }), {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    }),
  register: (email: string, password: string, name: string) =>
    api.post('/auth/register', { email, password, name }),
  sendRegistrationOtp: (data: { email: string; password: string; name: string }) =>
    api.post('/auth/send-registration-otp', data),
  verifyRegistrationOtp: (data: { email: string; otp: string }) =>
    api.post('/auth/verify-registration-otp', data),
  googleAuth: (credential: string) =>
    api.post('/auth/google', { credential }),
  verifyMfaLogin: (data: { challenge_token: string; code: string }) =>
    api.post('/auth/mfa/verify-login', data),
  logout: () => api.post('/auth/logout'),
  getWsTicket: () => api.post<{ ws_ticket: string; expires_in: number }>('/auth/ws-ticket'),
  me: () => api.get('/auth/me'),
  upgrade: () => api.post('/auth/upgrade'),
}

// ===== User Preferences endpoints =====
export const preferencesApi = {
  /** Load all saved preferences for the logged-in user */
  get: () => api.get<Record<string, any>>('/preferences/'),
  /** Bulk-upsert preferences. Only allow-listed keys are stored. */
  set: (preferences: Record<string, any>) => api.put('/preferences/', { preferences }),
}

// ===== Subscription endpoints =====
export const subscriptionApi = {
  getStatus: () => api.get('/subscription/status'),
  requestPro: (note?: string) => api.post('/subscription/request-pro', { note }),
  checkout: (data: { payment_method: string; payment_reference: string; amount?: number }) =>
    api.post('/subscription/checkout', data),
}

// ===== Admin endpoints =====
export const adminApi = {
  listUsers: () => api.get('/admin/users'),
  approvePro: (userId: string) => api.post(`/admin/users/${userId}/approve-pro`),
  rejectPro: (userId: string) => api.post(`/admin/users/${userId}/reject-pro`),
  revokePro: (userId: string) => api.post(`/admin/users/${userId}/revoke-pro`),
  setAdmin: (userId: string, is_admin: boolean) => api.post(`/admin/users/${userId}/set-admin`, { is_admin }),
  revokeSessions: (userId: string) => api.post(`/admin/users/${userId}/revoke-sessions`),
  getMfaStatus: () => api.get('/admin/mfa/status'),
  startMfaEnroll: () => api.post('/admin/mfa/enroll/start'),
  confirmMfaEnroll: (data: { setup_token: string; code: string }) => api.post('/admin/mfa/enroll/confirm', data),
  stepUpMfa: (code: string) => api.post('/admin/mfa/step-up', { code }),
  disableMfa: (data: { password: string; code: string }) => api.post('/admin/mfa/disable', data),
  getAlertsHub: (params?: {
    category?: string
    severity?: string
    unseen_only?: boolean
    status_filter?: string
    search?: string
    limit?: number
  }) => api.get('/admin/alerts-hub', { params }),
  markAlertsHubSeen: () => api.post('/admin/alerts-hub/mark-seen'),
  acknowledgeAlertsHub: (data: {
    alert_id?: string
    action?: 'ACKNOWLEDGE' | 'RESOLVE'
    mark_all?: boolean
  }) => api.post('/admin/alerts-hub/acknowledge', data),
  broadcastNotice: (data: { title: string; message: string; priority?: string }) =>
    api.post('/admin/broadcast-notice', data),
}

// ===== Sentinel Watchdog endpoints =====
export const sentinelApi = {
  getStatus: () => api.get('/sentinel/status'),
  getIncidents: () => api.get('/sentinel/incidents'),
  auditNow: () => api.post('/sentinel/audit-now'),
  resolveIncident: (incidentId: string) => api.post(`/sentinel/resolve/${incidentId}`),
}

// ===== System Validator & Cybersecurity Scanner endpoints =====
export const validatorApi = {
  getStatus: () => api.get('/validator/status'),
  getHistory: () => api.get('/validator/history'),
  runAll: () => api.post('/validator/run'),
  runSingle: (testId: string) => api.post(`/validator/run/${testId}`),
  getParadigms: () => api.get('/validator/paradigms'),
  probeCustom: (data: { method: string; endpoint: string; payload?: any; headers?: any }) =>
    api.post('/validator/probe-custom', data),
}

// ===== System Settings & Fyers Mobile Token endpoints =====
export const settingsApi = {
  getAll: () => api.get('/settings/'),
  update: (values: Record<string, any>) => api.put('/settings/', { values }),
  getFyersStatus: () => api.get('/settings/fyers/status'),
  getFyersAuthUrl: () => api.get('/settings/fyers/auth-url'),
  updateFyersToken: (authInput: string) => api.post('/settings/fyers/update-token', { auth_input: authInput }),
}

// ===== Real-Time Presence & Live Users Online endpoints =====
export const presenceApi = {
  heartbeat: (data: any) => api.post('/presence/heartbeat', data),
  leave: (data: any) => api.post('/presence/leave', data),
  getCount: () => api.get('/presence/count'),
  getUsers: () => api.get('/presence/users'),
}

// ===== Health & SRE Telemetry endpoints =====
export const healthApi = {
  getLive: () => api.get('/health/live'),
  getReady: () => api.get('/health/ready'),
}

// ===== 11-Day Swing Trade Audit & Excel Tracker endpoints =====
export const swingAuditApi = {
  getCurrentCycle: () => api.get('/swing-audit/current-cycle'),
  track: (data: {
    symbol: string;
    buy_price: number;
    target_price: number;
    stop_loss: number;
    target_1?: number;
    target_2?: number;
    target_3?: number;
    reward_to_risk?: number;
    total_score?: number;
    company_name?: string;
    recommendation_date?: string;
    allocated_capital?: number;
    user_bought?: boolean;
    user_buy_price?: number;
    notes?: string;
  }) => api.post('/swing-audit/track', data),
  sync: (runScan: boolean = false) => api.post(`/swing-audit/sync${runScan ? '?run_scan=true' : ''}`),
  listFiles: () => api.get<{ files: any[]; count: number }>(`/swing-audit/files?t=${Date.now()}`),
  downloadLatestUrl: () => `/api/swing-audit/download-latest?t=${Date.now()}`,
  downloadLatestDirectFileUrl: () => `/api/swing-audit/download-latest-file?t=${Date.now()}`,
  downloadFileUrl: (filename: string) => `/api/swing-audit/download/${encodeURIComponent(filename)}?t=${Date.now()}`,
  downloadLatestExcel: () =>
    downloadBlobFile(
      () => api.get(`/swing-audit/download-latest?t=${Date.now()}`, { 
        responseType: 'blob',
        headers: { 'Cache-Control': 'no-cache, no-store', 'Pragma': 'no-cache' }
      }),
      'Swing_Trade_Audit_Latest.xlsx'
    ),
  downloadArchiveExcel: (filename: string) =>
    downloadBlobFile(
      () => api.get(`/swing-audit/download/${encodeURIComponent(filename)}?t=${Date.now()}`, { 
        responseType: 'blob',
        headers: { 'Cache-Control': 'no-cache, no-store', 'Pragma': 'no-cache' }
      }),
      filename.endsWith('.xlsx') ? filename : `${filename}.xlsx`
    ),
  rolloverCycle: (squareOffRemaining: boolean = true) =>
    api.post('/swing-audit/cycle/rollover', null, { params: { square_off_remaining: squareOffRemaining } }),
}

/**
 * Triggers a file download using either an Axios request returning a Blob or a Blob directly.
 * Handles filename extraction from Content-Disposition header, object URL creation/revocation,
 * and decodes error payloads if the server returned a JSON error (e.g. 404/500).
 */
export async function downloadBlobFile(
  target: (() => Promise<any>) | Blob,
  fallbackFilename: string = 'download.xlsx',
  contentDisposition?: string
): Promise<string> {
  try {
    let blob: Blob
    let disposition = contentDisposition

    if (typeof target === 'function') {
      const response = await target()
      blob = response.data instanceof Blob ? response.data : new Blob([response.data])
      disposition = disposition || response.headers?.['content-disposition'] || response.headers?.['Content-Disposition']
    } else if (target instanceof Blob) {
      blob = target
    } else {
      blob = new Blob([target])
    }

    // Check if the response is actually an error JSON masquerading as a blob
    if (blob.type === 'application/json') {
      const text = await blob.text()
      try {
        const errorJson = JSON.parse(text)
        throw new Error(errorJson.detail || 'Failed to download file from server.')
      } catch (parseErr: any) {
        if (parseErr.message && !parseErr.message.includes('JSON')) throw parseErr
        throw new Error(text || 'Failed to download file from server.')
      }
    }

    // Extract filename from Content-Disposition header if present
    let filename = fallbackFilename
    if (disposition) {
      const match = disposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/)
      if (match && match[1]) {
        filename = match[1].replace(/['"]/g, '').trim()
      }
    }

    // Trigger browser download via temporary anchor element
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.setAttribute('download', filename)
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(url)

    return filename
  } catch (err: any) {
    if (err.response && err.response.data && err.response.data instanceof Blob) {
      try {
        const text = await err.response.data.text()
        const errorJson = JSON.parse(text)
        throw new Error(errorJson.detail || `Server error (${err.response.status}): ${text}`)
      } catch (e: any) {
        if (e.message && !e.message.includes('JSON')) throw e
      }
    }
    const message = err.response?.data?.detail || err.message || 'Failed to download file.'
    throw new Error(message)
  }
}

export default api
