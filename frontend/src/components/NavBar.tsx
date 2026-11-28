import { NavLink, useLocation, useNavigate } from 'react-router-dom'
import { useEffect, useRef, useState } from 'react'
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
  LogIn,
  Menu,
  X,
  Sun,
  Moon,
  Activity,
  Settings,
  Target,
  Radar,
  Shield,
  ChevronDown,
  Grid,
  Star,
} from 'lucide-react'
import { useAuth } from '../AuthContext'
import { useTheme } from '../ThemeContext'
import { adminApi, notificationsApi } from '../services/api'
import { triggerDesktopPushNotification } from '../utils/notificationSound'
import StockSearchBox from './StockSearchBox'
import LiveTicker from './LiveTicker'
import WatchlistSidebar from './WatchlistSidebar'
import NotificationBell from './NotificationBell'

export default function NavBar() {
  const navigate = useNavigate()
  const location = useLocation()
  const { user, loading: authLoading, logout } = useAuth()
  const { theme, toggleTheme } = useTheme()
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const [watchlistOpen, setWatchlistOpen] = useState(false)
  const [toolsOpen, setToolsOpen] = useState(false)
  const [userUnseenCount, setUserUnseenCount] = useState(0)
  const [adminUnseenCount, setAdminUnseenCount] = useState(0)
  const prevAdminUnseenRef = useRef<number | null>(null)
  const toolsRef = useRef<HTMLDivElement>(null)

  const isAdmin = Boolean(user?.is_admin)

  useEffect(() => {
    setToolsOpen(false)
    setMobileMenuOpen(false)
  }, [location.pathname])

  useEffect(() => {
    function handleOutside(e: MouseEvent) {
      if (toolsRef.current && !toolsRef.current.contains(e.target as Node)) {
        setToolsOpen(false)
      }
    }
    document.addEventListener('mousedown', handleOutside)
    return () => document.removeEventListener('mousedown', handleOutside)
  }, [])

  useEffect(() => {
    if (!user) {
      setUserUnseenCount(0)
      setAdminUnseenCount(0)
      return
    }
    const loadUserBadge = async () => {
      try {
        const res = await notificationsApi.list({ limit: 5 })
        setUserUnseenCount(Number(res.data?.unseen_count ?? 0))
      } catch {
        // ignore
      }
    }
    loadUserBadge()
    const uTimer = window.setInterval(loadUserBadge, 30000)
    window.addEventListener('stockai:notifications-updated', loadUserBadge)

    let aTimer: number | null = null
    const loadAdminBadge = async () => {
      if (!isAdmin) return
      try {
        const res = await adminApi.getAlertsHub({ limit: 5 })
        const nextUnseen = Number(res.data?.unseen_count ?? 0)
        if (
          prevAdminUnseenRef.current !== null &&
          nextUnseen > prevAdminUnseenRef.current &&
          Array.isArray(res.data?.alerts) &&
          res.data.alerts.length > 0
        ) {
          const newest = res.data.alerts.find((a: any) => !a.is_seen) || res.data.alerts[0]
          triggerDesktopPushNotification({
            title: `🚨 [ADMIN] ${newest.title}`,
            body: (newest.detail || '').slice(0, 140),
            severity: newest.severity || 'CRITICAL',
            tag: `admin-poll-${newest.id}`,
            url: '/admin?tab=threats',
          })
        }
        prevAdminUnseenRef.current = nextUnseen
        setAdminUnseenCount(nextUnseen)
      } catch {
        // ignore
      }
    }
    if (isAdmin) {
      loadAdminBadge()
      aTimer = window.setInterval(loadAdminBadge, 30000)
      window.addEventListener('stockai:admin-alerts-updated', loadAdminBadge)
    }

    return () => {
      window.clearInterval(uTimer)
      window.removeEventListener('stockai:notifications-updated', loadUserBadge)
      if (aTimer !== null) window.clearInterval(aTimer)
      if (isAdmin) window.removeEventListener('stockai:admin-alerts-updated', loadAdminBadge)
    }
  }, [user, isAdmin])

  const primaryLinks = [
    { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
    { to: '/screener', label: 'Screener', icon: Radar },
    { to: '/paper-trading', label: 'Orders', icon: Briefcase },
    { to: '/portfolio', label: 'Holdings', icon: PieChart },
    { to: '/chart', label: 'Charts', icon: CandlestickChart },
    { to: '/options', label: 'F&O', icon: Activity },
    { to: '/alerts', label: 'Alerts', icon: Bell },
  ]

  const toolLinks = [
    { to: '/scanner', label: 'Technical Scanner', icon: Search },
    { to: '/smc-watchlist', label: 'SMC Liquidity Zones', icon: Target },
    { to: '/heatmap', label: 'Market Heatmap', icon: Grid },
    { to: '/backtest', label: 'Strategy Backtest', icon: FlaskConical },
  ]

  const systemLinks = [
    { to: '/settings', label: 'Settings', icon: Settings },
    ...(isAdmin ? [{ to: '/admin', label: 'Admin', icon: Shield }] : []),
  ]

  const isToolsActive = toolLinks.some((t) => location.pathname.startsWith(t.to))
  const isPro = user?.subscription_tier === 'PRO'

  return (
    <nav className="navbar">
      {/* =========================================================================
          DESKTOP VIEW (Screens > 768px): Dual-Row Header
         ========================================================================= */}
      <div className="navbar-desktop-row" style={{ display: 'flex', alignItems: 'center', height: '60px', padding: '0 20px', borderBottom: '1px solid var(--color-border)', width: '100%', boxSizing: 'border-box', gap: '12px' }}>
        <NavLink to="/dashboard" className="navbar-brand" style={{ flexShrink: 0, marginRight: 8, textDecoration: 'none', cursor: 'pointer' }}>
          <TrendingUp size={21} />
          Stock<span>AI</span>
        </NavLink>

        {user && <LiveTicker />}

        {!user && authLoading && (
          <div style={{ marginLeft: 'auto', opacity: 0.45, fontSize: '0.78rem', color: 'var(--color-text-secondary)', display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#3b82f6', display: 'inline-block', animation: 'pulse 1.4s ease-in-out infinite' }} />
            Connecting…
          </div>
        )}

        {user ? (
          <div className="nav-actions" style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '10px', flexShrink: 0 }}>
            <StockSearchBox width={235} placeholder="Search symbol..." />

            {!isPro ? (
              <NavLink to="/pricing" style={{
                flexShrink: 0,
                background: 'var(--color-accent-blue)',
                color: 'white',
                padding: '6px 12px',
                borderRadius: '18px',
                textDecoration: 'none',
                fontSize: '0.8rem',
                fontWeight: 600,
                display: 'flex',
                alignItems: 'center',
                gap: '5px',
                whiteSpace: 'nowrap'
              }}>
                <Crown size={13} /> Upgrade PRO
              </NavLink>
            ) : (
              <span style={{
                flexShrink: 0,
                whiteSpace: 'nowrap',
                color: '#10b981',
                background: 'rgba(16, 185, 129, 0.14)',
                border: '1px solid rgba(16, 185, 129, 0.25)',
                padding: '4px 10px',
                borderRadius: '16px',
                fontWeight: 700,
                fontSize: '0.75rem',
                display: 'flex',
                alignItems: 'center',
                gap: '4px'
              }}>
                <Crown size={12} /> PRO
              </span>
            )}

            <button
              onClick={toggleTheme}
              aria-label="Toggle Theme"
              title="Toggle Theme"
              style={{
                flexShrink: 0,
                background: 'transparent', border: 'none', color: 'var(--color-text-primary)', cursor: 'pointer',
                display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '7px', borderRadius: '50%'
              }}
            >
              {theme === 'dark' ? <Sun size={17} /> : <Moon size={17} />}
            </button>

            <NotificationBell />

            <button
              onClick={() => setWatchlistOpen(true)}
              aria-label="Open Watchlist"
              title="Watchlist"
              style={{
                flexShrink: 0,
                background: 'transparent', border: '1px solid var(--color-border)', color: 'var(--color-text-primary)', cursor: 'pointer',
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '5px', padding: '6px 10px', borderRadius: '6px', fontSize: '0.8rem', fontWeight: 600, whiteSpace: 'nowrap'
              }}
            >
              <Star size={14} /> Watchlist
            </button>

            <span style={{ flexShrink: 0, whiteSpace: 'nowrap', fontSize: '0.82rem', color: 'var(--color-text-secondary)', maxWidth: '130px', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {user.name}
            </span>

            <button
              onClick={() => { logout(); navigate('/login'); }}
              aria-label="Logout"
              title="Sign Out"
              style={{
                flexShrink: 0,
                background: 'rgba(239, 68, 68, 0.1)',
                border: '1px solid rgba(239, 68, 68, 0.25)',
                color: '#ef4444',
                cursor: 'pointer',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                padding: '7px', borderRadius: '6px'
              }}
            >
              <LogOut size={15} />
            </button>
          </div>
        ) : (
          <div className="nav-actions" style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '12px' }}>
            <button
              onClick={toggleTheme}
              aria-label="Toggle Theme"
              title="Toggle Theme"
              style={{
                flexShrink: 0,
                background: 'transparent', border: 'none', color: 'var(--color-text-primary)', cursor: 'pointer',
                display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '6px', borderRadius: '50%'
              }}
            >
              {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
            </button>
            <NavLink
              to="/login"
              style={{
                flexShrink: 0,
                background: 'var(--color-accent-blue)',
                color: 'white',
                padding: '6px 16px',
                borderRadius: '8px',
                textDecoration: 'none',
                fontSize: '0.84rem',
                fontWeight: 600,
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
              }}
            >
              <LogIn size={15} /> Sign In
            </NavLink>
          </div>
        )}
      </div>

      {/* Desktop Bottom Row: Consolidated Navigation (Fits cleanly on 1024px–1440px+ without overflow) */}
      <div className="navbar-desktop-row" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', height: '48px', padding: '0 20px', borderBottom: '1px solid var(--color-border)', width: '100%', boxSizing: 'border-box' }}>
        <div style={{ display: 'flex', gap: '4px', alignItems: 'center', flexWrap: 'nowrap' }}>
          {primaryLinks.map(({ to, label, icon: Icon }) => {
            const linkBadge = to === '/alerts' ? userUnseenCount : 0
            return (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) => `navbar-link${isActive ? ' active' : ''}`}
                style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', position: 'relative' }}
              >
                <Icon size={14} />
                <span>{label}</span>
                {linkBadge > 0 && (
                  <span
                    style={{
                      minWidth: 16,
                      height: 16,
                      padding: '0 5px',
                      borderRadius: 999,
                      background: '#ef4444',
                      color: '#ffffff',
                      fontSize: 10,
                      fontWeight: 700,
                      display: 'inline-flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      lineHeight: 1,
                    }}
                  >
                    {linkBadge > 99 ? '99+' : linkBadge}
                  </span>
                )}
              </NavLink>
            )
          })}

          {/* Consolidated Tools Dropdown */}
          <div ref={toolsRef} style={{ position: 'relative' }}>
            <button
              type="button"
              onClick={() => setToolsOpen((o) => !o)}
              className={`navbar-link${isToolsActive ? ' active' : ''}`}
              style={{
                background: isToolsActive ? 'var(--color-bg-card)' : 'transparent',
                border: 'none',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '5px',
              }}
              aria-expanded={toolsOpen}
            >
              <Grid size={14} />
              <span>Tools</span>
              <ChevronDown size={13} style={{ transform: toolsOpen ? 'rotate(180deg)' : 'none', transition: 'transform 0.15s' }} />
            </button>

            {toolsOpen && (
              <div
                style={{
                  position: 'absolute',
                  top: 'calc(100% + 6px)',
                  left: 0,
                  minWidth: '210px',
                  background: 'var(--color-bg-secondary)',
                  border: '1px solid var(--color-border-light)',
                  borderRadius: '10px',
                  boxShadow: '0 14px 30px rgba(0, 0, 0, 0.45)',
                  padding: '6px',
                  zIndex: 1200,
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '2px',
                }}
              >
                {toolLinks.map(({ to, label, icon: Icon }) => (
                  <NavLink
                    key={to}
                    to={to}
                    onClick={() => setToolsOpen(false)}
                    className={({ isActive }) => `navbar-link${isActive ? ' active' : ''}`}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '9px',
                      padding: '8px 10px',
                      borderRadius: '6px',
                      width: '100%',
                    }}
                  >
                    <Icon size={14} />
                    <span>{label}</span>
                  </NavLink>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Right System Controls */}
        <div style={{ display: 'flex', gap: '4px', alignItems: 'center' }}>
          {systemLinks.map(({ to, label, icon: Icon }) => {
            const linkBadge = to === '/admin' ? adminUnseenCount : 0
            return (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) => `navbar-link${isActive ? ' active' : ''}`}
                style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}
              >
                <Icon size={14} />
                <span>{label}</span>
                {linkBadge > 0 && (
                  <span
                    style={{
                      minWidth: 16,
                      height: 16,
                      padding: '0 5px',
                      borderRadius: 999,
                      background: '#ef4444',
                      color: '#ffffff',
                      fontSize: 10,
                      fontWeight: 700,
                      display: 'inline-flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      lineHeight: 1,
                    }}
                  >
                    {linkBadge > 99 ? '99+' : linkBadge}
                  </span>
                )}
              </NavLink>
            )
          })}
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
        padding: '0 12px',
        width: '100%',
        boxSizing: 'border-box',
        borderBottom: '1px solid var(--color-border)',
        background: 'var(--color-bg-secondary)'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <button
            className="nav-menu-button"
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            aria-label="Toggle navigation menu"
            style={{
              background: 'transparent',
              border: 'none',
              color: 'var(--color-text-primary)',
              cursor: 'pointer',
              minWidth: 36,
              minHeight: 36,
              padding: '6px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center'
            }}
          >
            {mobileMenuOpen ? <X size={21} /> : <Menu size={21} />}
          </button>

          <NavLink to="/dashboard" style={{ display: 'flex', alignItems: 'center', gap: '6px', textDecoration: 'none', color: 'inherit', padding: '4px 0' }}>
            <TrendingUp size={19} color="var(--color-accent-blue)" />
            <span style={{ fontWeight: 800, fontSize: '1.05rem' }}>Stock<span style={{ color: 'var(--color-accent-blue)' }}>AI</span></span>
          </NavLink>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          {user && !isPro && (
            <NavLink to="/pricing" style={{
              background: 'var(--color-accent-blue)',
              color: 'white',
              padding: '5px 10px',
              borderRadius: '14px',
              fontSize: '0.72rem',
              fontWeight: 700,
              textDecoration: 'none',
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
              minHeight: 28,
            }}>
              <Crown size={12} /> PRO
            </NavLink>
          )}

          {user && isPro && (
            <span style={{
              background: 'rgba(16, 185, 129, 0.16)',
              color: '#10b981',
              border: '1px solid rgba(16, 185, 129, 0.25)',
              padding: '3px 8px',
              borderRadius: '12px',
              fontSize: '0.7rem',
              fontWeight: 700
            }}>
              PRO
            </span>
          )}

          <button
            onClick={toggleTheme}
            aria-label="Toggle theme"
            title="Toggle theme"
            style={{
              background: 'transparent',
              border: 'none',
              color: 'var(--color-text-primary)',
              cursor: 'pointer',
              minWidth: 36,
              minHeight: 36,
              padding: '6px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center'
            }}
          >
            {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
          </button>

          {user && <NotificationBell compact={true} />}

          {user && (
            <button
              onClick={() => setWatchlistOpen(true)}
              aria-label="Open Watchlist"
              title="Watchlist"
              style={{
                background: 'var(--color-bg-card)',
                border: '1px solid var(--color-border)',
                color: 'var(--color-text-primary)',
                borderRadius: '8px',
                minWidth: 36,
                minHeight: 36,
                padding: '6px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                cursor: 'pointer'
              }}
            >
              <Star size={16} />
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
          background: 'rgba(0,0,0,0.65)',
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
              padding: '14px',
              maxHeight: '85vh',
              overflowY: 'auto',
              boxShadow: '0 10px 25px rgba(0,0,0,0.5)'
            }}
            onClick={(e) => e.stopPropagation()}
          >
            {user && (
              <div style={{ marginBottom: '12px' }}>
                <StockSearchBox width="100%" placeholder="Search symbol..." />
              </div>
            )}

            {[
              { group: 'Trading', items: primaryLinks },
              { group: 'Analysis Tools', items: toolLinks },
              { group: 'Account', items: systemLinks },
            ].map((section) => (
              <div key={section.group} style={{ marginBottom: '10px' }}>
                <div style={{ fontSize: '10px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.6px', color: 'var(--color-text-muted)', padding: '4px 10px' }}>
                  {section.group}
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
                  {section.items.map(({ to, label, icon: Icon }) => {
                    const linkBadge =
                      to === '/alerts' ? userUnseenCount : to === '/admin' ? adminUnseenCount : 0
                    return (
                      <NavLink
                        key={to}
                        to={to}
                        onClick={() => setMobileMenuOpen(false)}
                        className={({ isActive }) => `navbar-link${isActive ? ' active' : ''}`}
                        style={{
                          padding: '9px 12px',
                          borderRadius: '8px',
                          fontSize: '0.9rem',
                          fontWeight: 600,
                          display: 'flex',
                          alignItems: 'center',
                          gap: '10px',
                          minHeight: 38,
                        }}
                      >
                        <Icon size={16} color="var(--color-accent-blue)" />
                        <span style={{ flex: 1 }}>{label}</span>
                        {linkBadge > 0 && (
                          <span
                            style={{
                              minWidth: 20,
                              height: 20,
                              padding: '0 6px',
                              borderRadius: 999,
                              background: '#ef4444',
                              color: '#ffffff',
                              fontSize: 11,
                              fontWeight: 700,
                              display: 'inline-flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                            }}
                          >
                            {linkBadge > 99 ? '99+' : linkBadge}
                          </span>
                        )}
                      </NavLink>
                    )
                  })}
                </div>
              </div>
            ))}

            {user && (
              <div style={{ marginTop: '12px', paddingTop: '12px', borderTop: '1px solid var(--color-border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10 }}>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontWeight: 700, fontSize: '0.88rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{user.name}</div>
                  <div style={{ fontSize: '0.76rem', color: 'var(--color-text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{user.email}</div>
                </div>
                <button
                  onClick={() => { setMobileMenuOpen(false); logout(); navigate('/login'); }}
                  className="btn btn-danger"
                  style={{
                    padding: '7px 12px',
                    fontSize: '0.82rem',
                    flexShrink: 0,
                  }}
                >
                  <LogOut size={14} /> Logout
                </button>
              </div>
            )}

            {!user && (
              <div style={{ marginTop: '12px', paddingTop: '12px', borderTop: '1px solid var(--color-border)' }}>
                <NavLink
                  to="/login"
                  onClick={() => setMobileMenuOpen(false)}
                  className="btn btn-primary"
                  style={{ width: '100%' }}
                >
                  <LogIn size={16} /> Sign In / Create Account
                </NavLink>
              </div>
            )}
          </div>
        </div>
      )}

      <WatchlistSidebar isOpen={watchlistOpen} onClose={() => setWatchlistOpen(false)} />
    </nav>
  )
}
