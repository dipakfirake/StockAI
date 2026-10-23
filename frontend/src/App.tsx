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
              <Route path="/dashboard" element={<Dashboard />} />
              <Route path="/chart" element={<ChartPage />} />
              <Route path="/screener" element={<SwingScreenerPage />} />
              <Route path="/scanner" element={<ScannerPage />} />
              <Route path="/heatmap" element={<HeatmapPage />} />
              <Route path="/options" element={<OptionsChainPage />} />
              <Route path="/smc-watchlist" element={<SMCWatchlist />} />
              <Route path="/alerts" element={<AlertsPage />} />
              <Route path="/paper-trading" element={<PaperTradingPage />} />
              <Route path="/backtest" element={<BacktestPage />} />
              <Route path="/portfolio" element={<PortfolioPage />} />
              <Route path="/settings" element={<SettingsPage />} />
              <Route path="/pricing" element={<PricingPage />} />
              <Route path="/admin" element={<AdminPage />} />
              <Route path="/admin/sentinel" element={<SentinelMonitorPage />} />
              <Route path="/login" element={<LoginPage />} />
              {/* AI Forecast & Prediction Route Aliases */}
              <Route path="/predictions" element={<ChartPage />} />
              <Route path="/prediction" element={<ChartPage />} />
              <Route path="/forecast" element={<ChartPage />} />
              {/* Catch-all fallback so unmatched routes never show a blank screen */}
              <Route path="*" element={<Navigate to="/dashboard" replace />} />
            </Routes>
          </main>
          <AIAssistantWidget />
          <ToastContainer />
        </div>
      </Router>
      </PresenceProvider>
      </AuthProvider>
    </ThemeProvider>
  )
}
