import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom'
import NavBar from './components/NavBar'
import Dashboard from './pages/Dashboard'
import ChartPage from './pages/ChartPage'
import AlertsPage from './pages/AlertsPage'
import PaperTradingPage from './pages/PaperTradingPage'
import BacktestPage from './pages/BacktestPage'
import PortfolioPage from './pages/PortfolioPage'
import ScannerPage from './pages/ScannerPage'
import HeatmapPage from './pages/HeatmapPage'
import OptionsChainPage from './pages/OptionsChainPage'
import SMCWatchlist from './pages/SMCWatchlist'
import LoginPage from './pages/LoginPage'
import PricingPage from './pages/PricingPage'
import SettingsPage from './pages/SettingsPage'
import SwingScreenerPage from './pages/SwingScreenerPage'
import AdminPage from './pages/AdminPage'
import SentinelMonitorPage from './pages/SentinelMonitorPage'
import { AuthProvider } from './AuthContext'
import { ThemeProvider } from './ThemeContext'
import { PresenceProvider } from './PresenceContext'

import AIAssistantWidget from './components/AIAssistantWidget'
import { ToastContainer, toast } from './components/Toast'
import { ReconnectingBanner } from './components/ReconnectingBanner'
import ProtectedRoute from './components/ProtectedRoute'
import CookieConsentBanner from './components/CookieConsentBanner'
import { alertWebSocket } from './services/websocket'
import { useEffect } from 'react'

export default function App() {
  useEffect(() => {
    // Listen for server-side manual alerts from Auto-Trader
    alertWebSocket.onAlert((payload: any) => {
      if (payload.type === 'alert_toast' && payload.data) {
        const { title, message, type } = payload.data
        if (type === 'success') toast.success(title, message)
        else if (type === 'warning') toast.warning(title, message)
        else if (type === 'error') toast.error(title, message)
        else toast.info(title, message)
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
              <Route path="/admin" element={<ProtectedRoute><AdminPage /></ProtectedRoute>} />
              <Route path="/admin/sentinel" element={<ProtectedRoute><SentinelMonitorPage /></ProtectedRoute>} />
              <Route path="/login" element={<LoginPage />} />
              {/* AI Forecast & Prediction Route Aliases */}
              <Route path="/predictions" element={<ProtectedRoute><ChartPage /></ProtectedRoute>} />
              <Route path="/prediction" element={<ProtectedRoute><ChartPage /></ProtectedRoute>} />
              <Route path="/forecast" element={<ProtectedRoute><ChartPage /></ProtectedRoute>} />
              {/* Catch-all fallback so unmatched routes never show a blank screen */}
              <Route path="*" element={<Navigate to="/dashboard" replace />} />
            </Routes>
          </main>
          <AIAssistantWidget />
          <ToastContainer />
          <CookieConsentBanner />
        </div>
      </Router>
      </PresenceProvider>
      </AuthProvider>
    </ThemeProvider>
  )
}
