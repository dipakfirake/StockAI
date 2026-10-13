import { NavLink } from 'react-router-dom'
import { useState } from 'react'
import {
  LayoutDashboard,
  CandlestickChart,
  Bell,
  Briefcase,
  FlaskConical,
  PieChart,
  TrendingUp,
  Search,
  Crown,
  LogOut,
  Menu,
  X,
  Sun,
  Moon,
  Activity,
  Settings,
  Target,
  Radar,
  Shield,
  ShieldAlert
} from 'lucide-react'
import { useAuth } from '../AuthContext'
import { useTheme } from '../ThemeContext'
import StockSearchBox from './StockSearchBox'
import LiveTicker from './LiveTicker'
import WatchlistSidebar from './WatchlistSidebar'

export default function NavBar() {
  const { user, logout } = useAuth()
  const { theme, toggleTheme } = useTheme()
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const [watchlistOpen, setWatchlistOpen] = useState(false)

  const isAdmin = Boolean(user?.is_admin || user?.email?.toLowerCase() === 'admin@stockai.com')

  const links = [
    { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
    { to: '/screener', label: 'Swing Screener', icon: Radar },
    { to: '/paper-trading', label: 'Orders & Positions', icon: Briefcase },
    { to: '/portfolio', label: 'Holdings', icon: PieChart },
    { to: '/options/^NSEI', label: 'F&O Chain', icon: Activity },
    { to: '/chart/^NSEI', label: 'Charts', icon: CandlestickChart },
    { to: '/smc-watchlist', label: 'Pre-Market SMC', icon: Target },
    { to: '/backtest', label: 'Backtest', icon: FlaskConical },
    { to: '/scanner', label: 'Scanner', icon: Search },
    { to: '/alerts', label: 'Alerts', icon: Bell },
    { to: '/settings', label: 'Settings', icon: Settings },
  ]

  if (isAdmin) {
    links.push({ to: '/admin', label: 'Admin Control', icon: Shield })
    links.push({ to: '/admin/sentinel', label: 'Sentinel 24/7', icon: ShieldAlert })
  }

  const isPro = user?.subscription_tier === 'PRO'

  return (
    <nav className="navbar">
      {/* =========================================================================
          DESKTOP VIEW (Screens > 768px): Dual-Row Header
         ========================================================================= */}
      <div className="navbar-desktop-row" style={{ display: 'flex', alignItems: 'center', height: '60px', padding: '0 20px', borderBottom: '1px solid var(--color-border)', width: '100%', boxSizing: 'border-box' }}>
        <div className="navbar-brand" style={{ flexShrink: 0, marginRight: 20 }}>
          <TrendingUp size={22} />
          AI<span>Stock</span>
        </div>

        {user && <LiveTicker />}

        {user && (
          <div className="nav-actions" style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '12px' }}>
            <StockSearchBox width={220} placeholder="Search symbol or company..." />
            
            {!isPro ? (
              <NavLink to="/pricing" style={{ 
                flexShrink: 0,
                background: 'linear-gradient(90deg, #3b82f6, #2563eb)', 
                color: 'white', 
                padding: '6px 12px', 
                borderRadius: '20px', 
                textDecoration: 'none',
                fontSize: '0.82rem',
                fontWeight: 700,
                display: 'flex',
                alignItems: 'center',
                gap: '5px',
                whiteSpace: 'nowrap'
              }}>
                <Crown size={14} /> Upgrade PRO
              </NavLink>
            ) : (
              <span style={{ 
                flexShrink: 0, 
                whiteSpace: 'nowrap', 
                color: '#4ade80', 
                background: 'rgba(34,197,94,0.15)',
                padding: '4px 10px',
                borderRadius: '16px',
                fontWeight: 700, 
                fontSize: '0.8rem', 
                display: 'flex', 
                alignItems: 'center', 
                gap: '4px' 
              }}>
                <Crown size={14} /> PRO
              </span>
            )}
            
            <button 
              onClick={toggleTheme}
              title="Toggle Theme"
              style={{
                flexShrink: 0,
                background: 'transparent', border: 'none', color: 'var(--color-text-primary)', cursor: 'pointer',
                display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '6px', borderRadius: '50%'
              }}
            >
              {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
            </button>
            
            <button 
              onClick={() => setWatchlistOpen(true)}
              title="Open Watchlist"
              style={{
                flexShrink: 0,
                background: 'transparent', border: '1px solid var(--border-color)', color: 'var(--color-text-primary)', cursor: 'pointer',
                display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '6px 10px', borderRadius: '6px', fontSize: '0.8rem', fontWeight: 600
              }}
            >
              Watchlist
            </button>

            <span style={{ flexShrink: 0, whiteSpace: 'nowrap', fontSize: '0.85rem', color: 'var(--color-text-secondary)', maxWidth: '120px', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {user.name}
            </span>

            <button 
              onClick={logout} 
              title="Logout" 
              style={{ 
                flexShrink: 0,
                background: 'rgba(239, 68, 68, 0.1)', 
                border: '1px solid rgba(239, 68, 68, 0.2)', 
                color: '#ef4444', 
                cursor: 'pointer', 
                display: 'flex', alignItems: 'center', justifyContent: 'center', 
                padding: '6px', borderRadius: '50%'
              }}
            >
              <LogOut size={16} />
            </button>
          </div>
        )}
      </div>

      {/* Desktop Bottom Row: Nav Links */}
      <div className="navbar-desktop-row" style={{ display: 'flex', alignItems: 'center', height: '50px', padding: '0 20px', overflowX: 'auto', borderBottom: '1px solid var(--color-border)', width: '100%', boxSizing: 'border-box' }}>
        <div style={{ display: 'flex', gap: '4px', alignItems: 'center', flexWrap: 'nowrap' }}>
          {links.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) => `navbar-link${isActive ? ' active' : ''}`}
              style={{ display: 'inline-flex', alignItems: 'center', gap: '5px' }}
            >
              <Icon size={14} />
              <span>{label}</span>
            </NavLink>
          ))}
        </div>
      </div>

      {/* =========================================================================
          MOBILE VIEW (Screens <= 768px): Unified Single Row + Drawer
         ========================================================================= */}
      <div className="navbar-mobile-header" style={{
        display: 'none',
        alignItems: 'center',
        justifyContent: 'space-between',
        height: '56px',
        padding: '0 14px',
        width: '100%',
        boxSizing: 'border-box',
        borderBottom: '1px solid var(--color-border)',
        background: 'var(--color-bg-secondary)'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <button 
            className="nav-menu-button" 
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)} 
            aria-label="Toggle navigation menu"
            style={{
              background: 'transparent',
              border: 'none',
              color: 'var(--color-text-primary)',
              cursor: 'pointer',
              padding: '6px',
              display: 'flex',
              alignItems: 'center'
            }}
          >
            {mobileMenuOpen ? <X size={22} /> : <Menu size={22} />}
          </button>

          <NavLink to="/dashboard" style={{ display: 'flex', alignItems: 'center', gap: '6px', textDecoration: 'none', color: 'inherit' }}>
            <TrendingUp size={20} color="#3b82f6" />
            <span style={{ fontWeight: 800, fontSize: '1.1rem' }}>AI<span style={{ color: '#3b82f6' }}>Stock</span></span>
          </NavLink>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          {user && !isPro && (
            <NavLink to="/pricing" style={{
              background: '#3b82f6',
              color: 'white',
              padding: '4px 8px',
              borderRadius: '12px',
              fontSize: '0.72rem',
              fontWeight: 700,
              textDecoration: 'none',
              display: 'flex',
              alignItems: 'center',
              gap: '4px'
            }}>
              <Crown size={12} /> PRO
            </NavLink>
          )}

          {user && isPro && (
            <span style={{
              background: 'rgba(34,197,94,0.2)',
              color: '#4ade80',
              padding: '3px 8px',
              borderRadius: '12px',
              fontSize: '0.72rem',
              fontWeight: 700
            }}>
              PRO
            </span>
          )}

          <button 
            onClick={toggleTheme}
            style={{
              background: 'transparent',
              border: 'none',
              color: 'var(--color-text-primary)',
              cursor: 'pointer',
              padding: '6px',
              display: 'flex'
            }}
          >
            {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
          </button>

          {user && (
            <button 
              onClick={() => setWatchlistOpen(true)}
              style={{
                background: 'rgba(255,255,255,0.06)',
                border: '1px solid var(--border-color)',
                color: 'var(--color-text-primary)',
                borderRadius: '6px',
                padding: '4px 8px',
                fontSize: '0.75rem',
                fontWeight: 600,
                cursor: 'pointer'
              }}
            >
              ⭐
            </button>
          )}
        </div>
      </div>

      {/* Mobile Slide-Down Navigation Drawer */}
      {mobileMenuOpen && (
        <div style={{
          position: 'fixed',
          top: '56px',
          left: 0,
          right: 0,
          bottom: 0,
          background: 'rgba(0,0,0,0.6)',
          backdropFilter: 'blur(4px)',
          zIndex: 9999,
          display: 'flex',
          flexDirection: 'column'
        }}
        onClick={() => setMobileMenuOpen(false)}
        >
          <div 
            style={{
              background: 'var(--color-bg-secondary)',
              borderBottom: '1px solid var(--color-border)',
              padding: '16px',
              maxHeight: '80vh',
              overflowY: 'auto',
              boxShadow: '0 10px 25px rgba(0,0,0,0.5)'
            }}
            onClick={(e) => e.stopPropagation()}
          >
            {user && (
              <div style={{ marginBottom: '14px' }}>
                <StockSearchBox width={undefined} placeholder="Search symbol..." />
              </div>
            )}

            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              {links.map(({ to, label, icon: Icon }) => (
                <NavLink
                  key={to}
                  to={to}
                  onClick={() => setMobileMenuOpen(false)}
                  className={({ isActive }) => `navbar-link${isActive ? ' active' : ''}`}
                  style={{
                    padding: '12px 14px',
                    borderRadius: '8px',
                    fontSize: '0.95rem',
                    fontWeight: 600,
                    display: 'flex',
                    alignItems: 'center',
                    gap: '12px',
                    color: 'var(--text-color)'
                  }}
                >
                  <Icon size={18} color="#3b82f6" />
                  <span>{label}</span>
                </NavLink>
              ))}
            </div>

            {user && (
              <div style={{ marginTop: '16px', paddingTop: '16px', borderTop: '1px solid var(--color-border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <div style={{ fontWeight: 700, fontSize: '0.9rem' }}>{user.name}</div>
                  <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>{user.email}</div>
                </div>
                <button
                  onClick={() => { setMobileMenuOpen(false); logout(); }}
                  style={{
                    padding: '8px 14px',
                    background: 'rgba(239, 68, 68, 0.15)',
                    border: '1px solid #ef4444',
                    borderRadius: '8px',
                    color: '#f87171',
                    fontWeight: 600,
                    fontSize: '0.85rem',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                    cursor: 'pointer'
                  }}
                >
                  <LogOut size={14} /> Logout
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      <WatchlistSidebar isOpen={watchlistOpen} onClose={() => setWatchlistOpen(false)} />
    </nav>
  )
}
