import { Suspense, lazy, useEffect } from 'react'
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom'
import NavBar from './components/NavBar'
import ErrorBoundary from './components/ErrorBoundary'
import { AuthProvider } from './AuthContext'
import { ThemeProvider } from './ThemeContext'
import { PresenceProvider } from './PresenceContext'

import AIAssistantWidget from './components/AIAssistantWidget'
import { ToastContainer, toast } from './components/Toast'
import { ReconnectingBanner } from './components/ReconnectingBanner'
import ProtectedRoute from './components/ProtectedRoute'
import CookieConsentBanner from './components/CookieConsentBanner'
import { alertWebSocket } from './services/websocket'
import { triggerDesktopPushNotification } from './utils/notificationSound'

const Dashboard = lazy(() => import('./pages/Dashboard'))
const ChartPage = lazy(() => import('./pages/ChartPage'))
const AlertsPage = lazy(() => import('./pages/AlertsPage'))
const PaperTradingPage = lazy(() => import('./pages/PaperTradingPage'))
const BacktestPage = lazy(() => import('./pages/BacktestPage'))
const PortfolioPage = lazy(() => import('./pages/PortfolioPage'))
const ScannerPage = lazy(() => import('./pages/ScannerPage'))
const HeatmapPage = lazy(() => import('./pages/HeatmapPage'))
const OptionsChainPage = lazy(() => import('./pages/OptionsChainPage'))
const SMCWatchlist = lazy(() => import('./pages/SMCWatchlist'))
const LoginPage = lazy(() => import('./pages/LoginPage'))
const PricingPage = lazy(() => import('./pages/PricingPage'))
const SettingsPage = lazy(() => import('./pages/SettingsPage'))
const SwingScreenerPage = lazy(() => import('./pages/SwingScreenerPage'))
const AdminPage = lazy(() => import('./pages/AdminPage'))
const SentinelMonitorPage = lazy(() => import('./pages/SentinelMonitorPage'))
const LegalPage = lazy(() => import('./pages/LegalPage'))

function PageLoadFallback() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '42vh', color: 'var(--color-text-muted)', fontSize: 13 }}>
      Loading module...
    </div>
  )
}

export default function App() {
  useEffect(() => {
    // Listen for server-side alerts, persisted Notification inbox pushes, Admin threats, and toasts
    alertWebSocket.onAlert((payload: any) => {
      if (payload.type === 'NOTIFICATION_NEW' && payload.notification) {
        const n = payload.notification
        triggerDesktopPushNotification({
          title: n.title || 'StockAI Notification',
          body: n.message || '',
          severity: n.priority || 'INFO',
          tag: `notif-${n.id}`,
          url: n.metadata?.link || '/alerts',
        })
        window.dispatchEvent(new CustomEvent('stockai:notifications-updated', { detail: n }))
        return
      }

      if (payload.type === 'ADMIN_ALERT_NEW' && payload.alert) {
        const a = payload.alert
        triggerDesktopPushNotification({
          title: `🚨 [ADMIN] ${a.title}`,
          body: a.detail || '',
          severity: a.severity || 'CRITICAL',
          tag: `admin-alert-${a.id}`,
          url: '/admin',
        })
        if (a.severity === 'CRITICAL') {
          toast.error(`🚨 ${a.title}`, (a.detail || '').slice(0, 140))
        } else {
          toast.warning(`⚠️ ${a.title}`, (a.detail || '').slice(0, 140))
        }
        window.dispatchEvent(new CustomEvent('stockai:admin-alerts-updated', { detail: a }))
        return
      }

      if (payload.type === 'alert_toast' && payload.data) {
        const { title, message, type } = payload.data
        if (type === 'success') toast.success(title, message)
        else if (type === 'warning') toast.warning(title, message)
        else if (type === 'error') toast.error(title, message)
        else toast.info(title, message)
      } else if (payload.type === 'ALERT_TRIGGERED') {
        const isPreBuy = payload.condition_type === 'BUY_PROXIMITY' || payload.condition_type?.includes('BUY')
        const isTargetHit = payload.condition_type === 'TARGET_HIT'
        const isSellPreAlert = payload.condition_type === 'TARGET_PROXIMITY'
        const isSL = payload.condition_type?.includes('STOP_LOSS')

        if (isPreBuy) {
          toast.info(`⚡ Pre-Buy Alert: ${payload.symbol}`, payload.message)
        } else if (isSellPreAlert) {
          toast.warning(`🎯 Sell Pre-Alert (Near Target): ${payload.symbol}`, payload.message)
        } else if (isTargetHit) {
          toast.success(`🎯 Target Achieved: ${payload.symbol}`, payload.message)
        } else if (isSL) {
          toast.error(`🛑 Stop Loss Alert: ${payload.symbol}`, payload.message)
        } else {
          toast.info(`🔔 ${payload.symbol} Alert Triggered`, payload.message)
        }
        window.dispatchEvent(new CustomEvent('stockai:notifications-updated'))
      } else if (payload.type === 'ALERT_CREATED') {
        toast.info(`🔔 Alert Active: ${payload.symbol}`, payload.message)
      }
    })
  }, [])

  return (
    <ThemeProvider>
      <AuthProvider>
        <PresenceProvider>
          <Router future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
          <div className="app">
          <ReconnectingBanner />
          <NavBar />
          <main className="main-content">
            <ErrorBoundary sectionLabel="Workspace View">
              <Suspense fallback={<PageLoadFallback />}>
                <Routes>
                  <Route path="/" element={<Navigate to="/dashboard" replace />} />
                  <Route path="/dashboard" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
                  <Route path="/chart" element={<ProtectedRoute><ChartPage /></ProtectedRoute>} />
                  <Route path="/chart/:symbol" element={<ProtectedRoute><ChartPage /></ProtectedRoute>} />
                  <Route path="/screener" element={<ProtectedRoute><SwingScreenerPage /></ProtectedRoute>} />
                  <Route path="/scanner" element={<ProtectedRoute><ScannerPage /></ProtectedRoute>} />
                  <Route path="/heatmap" element={<ProtectedRoute><HeatmapPage /></ProtectedRoute>} />
                  <Route path="/options" element={<ProtectedRoute><OptionsChainPage /></ProtectedRoute>} />
                  <Route path="/options/:symbol" element={<ProtectedRoute><OptionsChainPage /></ProtectedRoute>} />
                  <Route path="/smc-watchlist" element={<ProtectedRoute><SMCWatchlist /></ProtectedRoute>} />
                  <Route path="/alerts" element={<ProtectedRoute><AlertsPage /></ProtectedRoute>} />
                  <Route path="/paper-trading" element={<ProtectedRoute><PaperTradingPage /></ProtectedRoute>} />
                  <Route path="/backtest" element={<ProtectedRoute><BacktestPage /></ProtectedRoute>} />
                  <Route path="/portfolio" element={<ProtectedRoute><PortfolioPage /></ProtectedRoute>} />
                  <Route path="/settings" element={<ProtectedRoute><SettingsPage /></ProtectedRoute>} />
                  <Route path="/pricing" element={<PricingPage />} />
                  <Route path="/privacy" element={<LegalPage mode="privacy" />} />
                  <Route path="/terms" element={<LegalPage mode="terms" />} />
                  <Route path="/admin" element={<ProtectedRoute adminOnly><AdminPage /></ProtectedRoute>} />
                  <Route path="/admin/sentinel" element={<ProtectedRoute adminOnly><SentinelMonitorPage /></ProtectedRoute>} />
                  <Route path="/login" element={<LoginPage />} />
                  {/* AI Forecast & Prediction Route Aliases */}
                  <Route path="/predictions" element={<ProtectedRoute><ChartPage /></ProtectedRoute>} />
                  <Route path="/prediction" element={<ProtectedRoute><ChartPage /></ProtectedRoute>} />
                  <Route path="/forecast" element={<ProtectedRoute><ChartPage /></ProtectedRoute>} />
                  {/* Catch-all fallback so unmatched routes never show a blank screen */}
                  <Route path="*" element={<Navigate to="/dashboard" replace />} />
                </Routes>
              </Suspense>
            </ErrorBoundary>
          </main>
          <ErrorBoundary sectionLabel="Market Assistant">
            <AIAssistantWidget />
          </ErrorBoundary>
          <ToastContainer />
          <CookieConsentBanner />
        </div>
      </Router>
      </PresenceProvider>
      </AuthProvider>
    </ThemeProvider>
  )
}
