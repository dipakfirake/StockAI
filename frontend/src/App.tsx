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
import LoginPage from './pages/LoginPage'
import PricingPage from './pages/PricingPage'
import SettingsPage from './pages/SettingsPage'
import { AuthProvider } from './AuthContext'
import { ThemeProvider } from './ThemeContext'

import AIAssistantWidget from './components/AIAssistantWidget'
import { ToastContainer } from './components/Toast'

export default function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <Router future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
          <div className="app">
          <NavBar />
          <main className="main-content">
            <Routes>
              <Route path="/" element={<Navigate to="/dashboard" replace />} />
              <Route path="/dashboard" element={<Dashboard />} />
              <Route path="/chart/:symbol?" element={<ChartPage />} />
              <Route path="/scanner" element={<ScannerPage />} />
              <Route path="/heatmap" element={<HeatmapPage />} />
              <Route path="/options/:symbol?" element={<OptionsChainPage />} />
              <Route path="/alerts" element={<AlertsPage />} />
              <Route path="/paper-trading" element={<PaperTradingPage />} />
              <Route path="/backtest" element={<BacktestPage />} />
              <Route path="/portfolio" element={<PortfolioPage />} />
              <Route path="/settings" element={<SettingsPage />} />
              <Route path="/pricing" element={<PricingPage />} />
              <Route path="/login" element={<LoginPage />} />
            </Routes>
          </main>
          <AIAssistantWidget />
          <ToastContainer />
        </div>
      </Router>
      </AuthProvider>
    </ThemeProvider>
  )
}
