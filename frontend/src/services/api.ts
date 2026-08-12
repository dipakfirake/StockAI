import axios from 'axios'

const BASE_URL = '/api'

const api = axios.create({
  baseURL: BASE_URL,
  timeout: 60000,
  headers: { 'Content-Type': 'application/json' },
})

// Attach JWT token on every request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('auth_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// Handle auth errors globally
api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('auth_token')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

// ===== Stock endpoints =====
export const stocksApi = {
  search: (q: string) => api.get('/stocks/search', { params: { q } }),
  getQuote: (symbol: string) => api.get(`/stocks/${symbol}/quote`),
  getCandles: (symbol: string, timeframe = '1d', limit = 200) =>
    api.get(`/stocks/${symbol}/candles`, { params: { timeframe, limit } }),
  getIndicators: (symbol: string, timeframe = '1d') =>
    api.get(`/stocks/${symbol}/indicators`, { params: { timeframe } }),
  getSignals: (symbol: string, timeframe = '1d') =>
    api.get(`/stocks/${symbol}/signals`, { params: { timeframe } }),
  getAIScore: (symbol: string, timeframe = '1d') =>
    api.get(`/stocks/${symbol}/ai-score`, { params: { timeframe } }),
  getInfo: (symbol: string) => api.get(`/stocks/${symbol}/info`),
  getPatterns: (symbol: string, timeframe = '1d', limit = 250) =>
    api.get(`/stocks/${symbol}/patterns`, { params: { timeframe, limit } }),
  getInsight: (symbol: string, timeframe = '1d') =>
    api.get(`/stocks/${symbol}/insight`, { params: { timeframe } }),
  scanMarket: (rule: string) => api.get(`/scanner/nifty50`, { params: { rule } }),
  customScan: (data: { universe: string; timeframe?: string; conditions: Array<{ indicator: string; operator: string; value: number | string }> }) => api.post(`/scanner/custom`, data),
}

// ===== Watchlist endpoints =====
export const watchlistApi = {
  get: () => api.get('/watchlist'),
  add: (symbol: string) => api.post('/watchlist', { symbol }),
  remove: (symbol: string) => api.delete(`/watchlist/${symbol}`),
}

// ===== Alert endpoints =====
export const alertsApi = {
  list: () => api.get('/alerts'),
  create: (data: { symbol: string; condition_type: string; condition_value: number; message?: string; priority?: 'HIGH' | 'MEDIUM' | 'LOW'; delivery_method?: 'IN_APP' | 'EMAIL' | 'BOTH' }) =>
    api.post('/alerts', data),
  delete: (alertId: string) => api.delete(`/alerts/${alertId}`),
  deactivate: (alertId: string) => api.put(`/alerts/${alertId}/deactivate`),
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
export const marketApi = {
  getRegime: () => api.get('/market/regime'),
  getIndices: () => api.get('/market/indices'),
  getVix: () => api.get('/market/vix'),
  getEvents: () => api.get('/market/events'),
  getSectors: () => api.get('/market/sectors'),
  getHeatmap: () => api.get('/market/heatmap'),
  getOptions: (symbol: string) => api.get(`/market/options/${symbol}`),
}

// ===== AI endpoints =====
export const aiApi = {
  score: (symbol: string, timeframe = '1d') =>
    api.get(`/ai/score/${symbol}`, { params: { timeframe } }),
  scan: (symbols: string[], timeframe = '1d') =>
    api.get('/ai/scan', { params: { symbols: symbols.join(','), timeframe } }),
  sentiment: (symbol: string) => api.get(`/ml/sentiment/${symbol}`),
  chat: (message: string, symbol?: string) => api.post('/ai/chat', { message, symbol }),
}

// ===== Auth endpoints =====
export const authApi = {
  login: (email: string, password: string) =>
    api.post('/auth/login', new URLSearchParams({ username: email, password }), {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    }),
  register: (email: string, password: string, name: string) =>
    api.post('/auth/register', { email, password, name }),
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

export default api
