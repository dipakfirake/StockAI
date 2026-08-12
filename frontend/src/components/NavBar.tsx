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
  LogOut, Menu, X, Radio, Sun, Moon, MoreHorizontal, Activity
} from 'lucide-react'
import { useAuth } from '../AuthContext'
import { useTheme } from '../ThemeContext'
import StockSearchBox from './StockSearchBox'
import LiveTicker from './LiveTicker'
import WatchlistSidebar from './WatchlistSidebar'

const links = [
  { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/paper-trading', label: 'Orders & Positions', icon: Briefcase },
  { to: '/portfolio', label: 'Holdings', icon: PieChart },
  { to: '/options/^NSEI', label: 'F&O Chain', icon: Activity },
  { to: '/chart/^NSEI', label: 'Charts', icon: CandlestickChart },
  { to: '/backtest', label: 'Backtest', icon: FlaskConical },
  { to: '/scanner', label: 'Scanner', icon: Search },
  { to: '/alerts', label: 'Alerts', icon: Bell },
]

export default function NavBar() {
  const { user, logout } = useAuth()
  const { theme, toggleTheme } = useTheme()
  const [menuOpen, setMenuOpen] = useState(false)
  const [watchlistOpen, setWatchlistOpen] = useState(false)

  return (
    <nav className="navbar">
      {/* Top Row: Brand, Tickers, Search, Profile */}
      <div style={{ display: 'flex', alignItems: 'center', height: '60px', padding: '0 24px', borderBottom: '1px solid var(--color-border)' }}>
        <div className="navbar-brand" style={{ flexShrink: 0, marginRight: 24 }}>
          <TrendingUp size={22} />
          AI<span>Stock</span>
        </div>

        {user && <LiveTicker />}
        
        <button className="nav-menu-button" onClick={() => setMenuOpen(!menuOpen)} aria-label="Toggle navigation">
          {menuOpen ? <X size={20} /> : <Menu size={20} />}
        </button>

        {user && (
          <div className="nav-actions">
            <StockSearchBox width={250} placeholder="Search symbol or company..." />
            {user.subscription_tier === 'FREE' ? (
              <NavLink to="/pricing" style={{ 
                flexShrink: 0,
                background: 'var(--primary-color)', 
                color: 'white', 
                padding: '6px 12px', 
                borderRadius: '20px', 
                textDecoration: 'none',
                fontSize: '0.85rem',
                fontWeight: 'bold',
                display: 'flex',
                alignItems: 'center',
                gap: '5px',
                whiteSpace: 'nowrap'
              }}>
                <Crown size={14} /> Upgrade
              </NavLink>
            ) : (
              <span style={{ flexShrink: 0, whiteSpace: 'nowrap', color: 'var(--success-color)', fontWeight: 'bold', fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: '5px' }}>
                <Crown size={14} /> PRO
              </span>
            )}
            
            <div style={{ display: 'flex', alignItems: 'center', gap: '15px', marginLeft: '10px', flexShrink: 0 }}>
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
                  background: 'transparent', border: 'none', color: 'var(--color-text-primary)', cursor: 'pointer',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '6px', borderRadius: '50%'
                }}
              >
                <MoreHorizontal size={20} />
              </button>

              <span className="hide-on-mobile" style={{ flexShrink: 0, whiteSpace: 'nowrap', fontSize: '0.9rem', color: 'var(--color-text-secondary)' }}>{user.name}</span>
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
          </div>
        )}
      </div>

      {/* Bottom Row: Navigation Links */}
      <div style={{ display: 'flex', alignItems: 'center', height: '50px', padding: '0 24px', overflowX: 'auto', borderBottom: '1px solid var(--color-border)' }}>
        <div className={`nav-links${menuOpen ? ' is-open' : ''}`} style={{ flex: 1, minWidth: 0 }}>
          {links.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) => `navbar-link${isActive ? ' active' : ''}`}
              onClick={() => setMenuOpen(false)}
            >
              <Icon size={15} style={{ marginRight: 4, verticalAlign: 'middle' }} />
              {label}
            </NavLink>
          ))}
        </div>
      </div>
      
      <WatchlistSidebar isOpen={watchlistOpen} onClose={() => setWatchlistOpen(false)} />
    </nav>
  )
}
