import { NavLink } from 'react-router-dom'
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
  LogOut
} from 'lucide-react'
import { useAuth } from '../AuthContext'
import StockSearchBox from './StockSearchBox'

const links = [
  { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/chart', label: 'Charts', icon: CandlestickChart },
  { to: '/heatmap', label: 'Heatmap', icon: PieChart },
  { to: '/options', label: 'Options', icon: Search },
  { to: '/scanner', label: 'Scanner', icon: Search },
  { to: '/alerts', label: 'Alerts', icon: Bell },
  { to: '/paper-trading', label: 'Paper Trade', icon: Briefcase },
  { to: '/backtest', label: 'Backtest', icon: FlaskConical },
  { to: '/portfolio', label: 'Portfolio', icon: PieChart },
  { to: '/settings', label: 'Settings', icon: LogOut },
]

export default function NavBar() {
  const { user, logout } = useAuth()

  return (
    <nav className="navbar" style={{ display: 'flex', alignItems: 'center' }}>
      <div className="navbar-brand" style={{ flexShrink: 0 }}>
        <TrendingUp size={22} />
        AI<span>Stock</span>
      </div>
      
      <div style={{ display: 'flex', flex: 1 }}>
        {links.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) => `navbar-link${isActive ? ' active' : ''}`}
          >
            <Icon size={15} style={{ marginRight: 4, verticalAlign: 'middle' }} />
            {label}
          </NavLink>
        ))}
      </div>

      {user && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '15px' }}>
          <StockSearchBox width={250} placeholder="Search symbol or company..." />
          {user.subscription_tier === 'FREE' ? (
            <NavLink to="/pricing" style={{ 
              background: 'var(--primary-color)', 
              color: 'white', 
              padding: '6px 12px', 
              borderRadius: '20px', 
              textDecoration: 'none',
              fontSize: '0.85rem',
              fontWeight: 'bold',
              display: 'flex',
              alignItems: 'center',
              gap: '5px'
            }}>
              <Crown size={14} /> Upgrade
            </NavLink>
          ) : (
            <span style={{ color: 'var(--success-color)', fontWeight: 'bold', fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: '5px' }}>
              <Crown size={14} /> PRO
            </span>
          )}
          
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <span style={{ fontSize: '0.9rem', color: 'var(--text-secondary)' }}>{user.name}</span>
            <button onClick={logout} style={{ background: 'transparent', border: 'none', color: 'var(--text-secondary)', cursor: 'pointer' }}>
              <LogOut size={18} />
            </button>
          </div>
        </div>
      )}
    </nav>
  )
}
