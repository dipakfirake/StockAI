import { useState, useEffect } from 'react'
import {
  Save,
  AlertCircle,
  Shield,
  ArrowRight,
  Sliders,
  Bot,
  Zap,
  TrendingUp,
  Cookie,
  FileSpreadsheet,
} from 'lucide-react'
import { Link } from 'react-router-dom'
import { settingsApi } from '../services/api'
import { useAuth } from '../AuthContext'

export default function SettingsPage() {
  const { user } = useAuth()
  const isAdmin = Boolean(user?.is_admin)

  const [settings, setSettings] = useState<Record<string, any>>({})
  const [loading, setLoading] = useState(false)
  const [saveSuccess, setSaveSuccess] = useState(false)

  useEffect(() => {
    fetchSettings()
  }, [])

  async function fetchSettings() {
    setLoading(true)
    try {
      const res = await settingsApi.getAll()
      setSettings(res.data || {})
    } catch (err) {
      console.error('Failed to load settings:', err)
    } finally {
      setLoading(false)
    }
  }

  async function saveSettings() {
    setLoading(true)
    setSaveSuccess(false)
    try {
      const res = await settingsApi.update(settings)
      setSettings(res.data)
      setSaveSuccess(true)
      setTimeout(() => setSaveSuccess(false), 3000)
    } catch (err) {
      console.error('Failed to save settings:', err)
    } finally {
      setLoading(false)
    }
  }

  // Filter out any broker credentials, secrets, tokens, or Fyers keys from user settings
  const isBrokerOrSensitiveKey = (key: string) => {
    const k = key.toLowerCase()
    return (
      k.includes('fyers') ||
      k.includes('token') ||
      k.includes('secret') ||
      k.includes('client_id') ||
      k.includes('broker') ||
      k.includes('api_key')
    )
  }

  const isAlgoKey = (key: string) => {
    return (
      key === 'enable_swing_algo_trading' ||
      key === 'enable_auto_trader' ||
      key === 'enable_coupled_ratchet' ||
      key === 'enable_t2_pyramiding' ||
      key === 'swing_atr_multiplier' ||
      key === 'swing_capital_per_trade' ||
      key === 'swing_max_open_positions'
    )
  }

  const visibleSettings = Object.entries(settings).filter(
    ([key]) => !isBrokerOrSensitiveKey(key) && !isAlgoKey(key)
  )

  return (
    <div style={{ maxWidth: 850, margin: '0 auto', paddingBottom: 60 }}>
      <div className="page-header" style={{ marginBottom: 24 }}>
        <h1 className="page-title" style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <Sliders size={22} style={{ color: 'var(--color-accent-blue)' }} />
          Settings &amp; Preferences
        </h1>
        <p className="page-subtitle">Risk guardrails, automated execution, and privacy controls</p>
      </div>

      {/* Admin Notice: Directing Fyers API & Token to Admin Page */}
      {isAdmin && (
        <div
          className="card"
          style={{
            padding: '16px 20px',
            marginBottom: 20,
            borderLeft: '3px solid var(--color-accent-blue)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: 14,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, minWidth: 0 }}>
            <div style={{ width: 36, height: 36, borderRadius: 8, background: 'rgba(59, 130, 246, 0.14)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--color-accent-blue)', flexShrink: 0 }}>
              <Shield size={18} />
            </div>
            <div style={{ minWidth: 0 }}>
              <div style={{ fontWeight: 600, fontSize: 15, color: 'var(--color-text-primary)' }}>
                Broker Integration &amp; Token Manager
              </div>
              <div style={{ fontSize: 13, color: 'var(--color-text-muted)' }}>
                Daily Fyers token renewal and WebSocket status live in Admin Control.
              </div>
            </div>
          </div>

          <Link
            to="/admin"
            className="btn btn-primary"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              padding: '8px 14px',
              fontSize: 13,
              textDecoration: 'none',
            }}
          >
            Open Admin <ArrowRight size={14} />
          </Link>
        </div>
      )}

      {/* Automated Algorithmic Swing Trading Card */}
      <div
        className="card"
        style={{
          padding: 20,
          marginBottom: 20,
          borderLeft: '3px solid #10b981',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 14, marginBottom: 18 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, minWidth: 0 }}>
            <div style={{ width: 40, height: 40, borderRadius: 10, background: 'rgba(16, 185, 129, 0.14)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#10b981', flexShrink: 0 }}>
              <Bot size={20} />
            </div>
            <div style={{ minWidth: 0 }}>
              <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
                <h2 style={{ margin: 0, fontSize: 17, fontWeight: 700, color: 'var(--color-text-primary)' }}>
                  Automated Swing Engine &amp; Ratchet
                </h2>
                <span
                  style={{
                    fontSize: 11,
                    padding: '2px 8px',
                    borderRadius: 4,
                    background: (settings['enable_swing_algo_trading'] === true || settings['enable_swing_algo_trading'] === 'true') ? 'rgba(16, 185, 129, 0.2)' : 'rgba(148, 163, 184, 0.16)',
                    color: (settings['enable_swing_algo_trading'] === true || settings['enable_swing_algo_trading'] === 'true') ? '#10b981' : 'var(--color-text-muted)',
                    fontWeight: 700,
                  }}
                >
                  {(settings['enable_swing_algo_trading'] === true || settings['enable_swing_algo_trading'] === 'true') ? 'ACTIVE' : 'MONITOR ONLY'}
                </span>
              </div>
              <p style={{ margin: '4px 0 0 0', fontSize: 13, color: 'var(--color-text-muted)' }}>
                Autonomous swing execution, pyramiding, and ATR profit-locking stops
              </p>
            </div>
          </div>
        </div>

        {/* Controls Grid */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          {/* Master Toggle */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12, padding: '14px', background: 'var(--color-bg-secondary)', borderRadius: 8, border: '1px solid var(--color-border)' }}>
            <div style={{ flex: '1 1 240px', minWidth: 0 }}>
              <div style={{ fontWeight: 600, fontSize: 14, color: 'var(--color-text-primary)' }}>
                Automated Swing Algo Master Switch
              </div>
              <div style={{ fontSize: 12, color: 'var(--color-text-muted)', marginTop: 2 }}>
                Executes trades automatically on verified Swing Screener entries.
              </div>
            </div>
            <label style={{ display: 'flex', alignItems: 'center', cursor: 'pointer', gap: 8, flexShrink: 0 }}>
              <input
                type="checkbox"
                checked={settings['enable_swing_algo_trading'] === true || settings['enable_swing_algo_trading'] === 'true'}
                onChange={(e) => setSettings({ ...settings, enable_swing_algo_trading: e.target.checked.toString() })}
                style={{ width: 20, height: 20, cursor: 'pointer', accentColor: '#10b981' }}
              />
              <span style={{ fontSize: 13, fontWeight: 700, color: (settings['enable_swing_algo_trading'] === true || settings['enable_swing_algo_trading'] === 'true') ? '#10b981' : 'var(--color-text-muted)' }}>
                {(settings['enable_swing_algo_trading'] === true || settings['enable_swing_algo_trading'] === 'true') ? 'ON' : 'OFF'}
              </span>
            </label>
          </div>

          {/* Coupled Ratchet Engine Toggle */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12, padding: '14px', background: 'var(--color-bg-secondary)', borderRadius: 8, border: '1px solid var(--color-border)' }}>
            <div style={{ flex: '1 1 240px', minWidth: 0 }}>
              <div style={{ fontWeight: 600, fontSize: 14, color: 'var(--color-text-primary)', display: 'flex', alignItems: 'center', gap: 6 }}>
                <Zap size={14} style={{ color: '#38bdf8', flexShrink: 0 }} />
                Coupled Ratchet Trailing Stop
              </div>
              <div style={{ fontSize: 12, color: 'var(--color-text-muted)', marginTop: 2 }}>
                Locks Tranche 1 at break-even when Target 1 hits and trails upward as Target 2 approaches.
              </div>
            </div>
            <label style={{ display: 'flex', alignItems: 'center', cursor: 'pointer', gap: 8, flexShrink: 0 }}>
              <input
                type="checkbox"
                checked={settings['enable_coupled_ratchet'] === true || settings['enable_coupled_ratchet'] === 'true' || settings['enable_coupled_ratchet'] === undefined}
                onChange={(e) => setSettings({ ...settings, enable_coupled_ratchet: e.target.checked.toString() })}
                style={{ width: 20, height: 20, cursor: 'pointer', accentColor: '#38bdf8' }}
              />
              <span style={{ fontSize: 13, fontWeight: 700, color: '#38bdf8' }}>
                {(settings['enable_coupled_ratchet'] === true || settings['enable_coupled_ratchet'] === 'true' || settings['enable_coupled_ratchet'] === undefined) ? 'ENABLED' : 'DISABLED'}
              </span>
            </label>
          </div>

          {/* Target 2 Pyramiding Mode Toggle */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12, padding: '14px', background: 'var(--color-bg-secondary)', borderRadius: 8, border: '1px solid var(--color-border)' }}>
            <div style={{ flex: '1 1 240px', minWidth: 0 }}>
              <div style={{ fontWeight: 600, fontSize: 14, color: 'var(--color-text-primary)', display: 'flex', alignItems: 'center', gap: 6 }}>
                <TrendingUp size={14} style={{ color: '#a78bfa', flexShrink: 0 }} />
                Target 2 Pyramiding
              </div>
              <div style={{ fontSize: 12, color: 'var(--color-text-muted)', marginTop: 2 }}>
                Adds Tranche 2 when an extended Target 2 projection exists; otherwise exits at Target 1.
              </div>
            </div>
            <label style={{ display: 'flex', alignItems: 'center', cursor: 'pointer', gap: 8, flexShrink: 0 }}>
              <input
                type="checkbox"
                checked={settings['enable_t2_pyramiding'] === true || settings['enable_t2_pyramiding'] === 'true' || settings['enable_t2_pyramiding'] === undefined}
                onChange={(e) => setSettings({ ...settings, enable_t2_pyramiding: e.target.checked.toString() })}
                style={{ width: 20, height: 20, cursor: 'pointer', accentColor: '#a78bfa' }}
              />
              <span style={{ fontSize: 13, fontWeight: 700, color: '#a78bfa' }}>
                {(settings['enable_t2_pyramiding'] === true || settings['enable_t2_pyramiding'] === 'true' || settings['enable_t2_pyramiding'] === undefined) ? 'ENABLED' : 'DISABLED'}
              </span>
            </label>
          </div>

          {/* ATR Volatility Multiplier Slider */}
          <div style={{ padding: '14px', background: 'var(--color-bg-secondary)', borderRadius: 8, border: '1px solid var(--color-border)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8, marginBottom: 8 }}>
              <div style={{ flex: '1 1 220px', minWidth: 0 }}>
                <div style={{ fontWeight: 600, fontSize: 14, color: 'var(--color-text-primary)' }}>
                  ATR Volatility Multiplier
                </div>
                <div style={{ fontSize: 12, color: 'var(--color-text-muted)', marginTop: 2 }}>
                  Trails protective stops at Peak − (Multiplier × ATR) to avoid early wick stop-outs.
                </div>
              </div>
              <span style={{ fontSize: 13, fontWeight: 700, color: '#38bdf8', padding: '3px 10px', background: 'rgba(56, 189, 248, 0.14)', borderRadius: 6 }} className="mono">
                {parseFloat(settings['swing_atr_multiplier'] || '1.5').toFixed(1)}x ATR
              </span>
            </div>
            <input
              type="range"
              min="1.0"
              max="3.0"
              step="0.1"
              value={parseFloat(settings['swing_atr_multiplier'] || '1.5')}
              onChange={(e) => setSettings({ ...settings, swing_atr_multiplier: e.target.value })}
              style={{ width: '100%', cursor: 'pointer', accentColor: '#38bdf8' }}
            />
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--color-text-muted)', marginTop: 4 }}>
              <span>1.0x Tight</span>
              <span>1.5x Balanced</span>
              <span>3.0x Wide</span>
            </div>
          </div>

          {/* Capital & Position Guardrails */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 220px), 1fr))', gap: 14 }}>
            <div style={{ padding: '12px 14px', background: 'var(--color-bg-secondary)', borderRadius: 8, border: '1px solid var(--color-border)' }}>
              <label style={{ display: 'block', fontWeight: 600, fontSize: 13, marginBottom: 6, color: 'var(--color-text-secondary)' }}>
                Capital per Automated Trade (₹)
              </label>
              <input
                type="number"
                className="input"
                value={settings['swing_capital_per_trade'] || '100000'}
                onChange={(e) => setSettings({ ...settings, swing_capital_per_trade: e.target.value })}
                style={{ width: '100%' }}
              />
            </div>
            <div style={{ padding: '12px 14px', background: 'var(--color-bg-secondary)', borderRadius: 8, border: '1px solid var(--color-border)' }}>
              <label style={{ display: 'block', fontWeight: 600, fontSize: 13, marginBottom: 6, color: 'var(--color-text-secondary)' }}>
                Max Open Positions
              </label>
              <input
                type="number"
                className="input"
                value={settings['swing_max_open_positions'] || '5'}
                onChange={(e) => setSettings({ ...settings, swing_max_open_positions: e.target.value })}
                style={{ width: '100%' }}
              />
            </div>
          </div>

          {/* Save Button for Algo Card */}
          <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 12, marginTop: 4 }}>
            <button
              onClick={saveSettings}
              disabled={loading}
              className="btn btn-primary"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 8,
                fontWeight: 600,
                padding: '9px 18px',
              }}
            >
              <Save size={15} /> Save Algo Configuration
            </button>
            {saveSuccess && (
              <span style={{ color: '#10b981', fontSize: 13, fontWeight: 600 }}>
                Saved
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Trading Parameters & Risk Safeguards */}
      <div className="card" style={{ marginBottom: 20 }}>
        <h2 style={{ fontSize: 17, fontWeight: 700, margin: '0 0 14px 0' }}>Trading Parameters &amp; Risk Safeguards</h2>
        {loading ? (
          <div className="text-center" style={{ padding: 32 }}>Loading preferences...</div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div style={{ padding: 12, backgroundColor: 'rgba(59, 130, 246, 0.08)', borderRadius: 8, borderLeft: '3px solid var(--color-accent-blue)', fontSize: 13 }}>
              <AlertCircle size={15} style={{ marginBottom: -3, marginRight: 8, color: 'var(--color-accent-blue)' }} />
              <strong>Risk Governance:</strong> Controls position sizing calculations, slippage assumptions, and simulated execution limits.
            </div>

            {visibleSettings.length === 0 ? (
              <div style={{ padding: 20, textAlign: 'center', color: 'var(--color-text-muted)' }}>
                No additional user parameters configured.
              </div>
            ) : (
              visibleSettings.map(([key, val]) => {
                const isBoolean = val === true || val === false || val === 'true' || val === 'false'

                return (
                  <div key={key} style={{ display: 'flex', flexDirection: 'column', gap: 4, padding: '10px 0', borderBottom: '1px solid var(--color-border)' }}>
                    <label style={{ fontWeight: 600, fontSize: 14 }}>
                      {key.split('_').map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')}
                    </label>

                    {isBoolean ? (
                      <label style={{ display: 'flex', alignItems: 'center', cursor: 'pointer', gap: 8, marginTop: 4 }}>
                        <input
                          type="checkbox"
                          checked={val === true || val === 'true'}
                          onChange={(e) => setSettings({ ...settings, [key]: e.target.checked.toString() })}
                          style={{ width: 20, height: 20, cursor: 'pointer' }}
                        />
                        <span style={{ fontSize: 13, fontWeight: 600, color: val === true || val === 'true' ? 'var(--color-bullish)' : 'var(--color-text-muted)' }}>
                          {val === true || val === 'true' ? 'ENABLED' : 'DISABLED'}
                        </span>
                      </label>
                    ) : (
                      <input
                        type="text"
                        className="input"
                        value={val.toString()}
                        onChange={(e) => setSettings({ ...settings, [key]: e.target.value })}
                        style={{ maxWidth: 300, width: '100%' }}
                      />
                    )}
                  </div>
                )
              })
            )}

            {isAdmin && visibleSettings.length > 0 && (
              <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 12, marginTop: 8 }}>
                <button onClick={saveSettings} className="btn btn-primary" style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                  <Save size={15} /> Save Configuration
                </button>
                {saveSuccess && (
                  <span style={{ color: '#10b981', fontSize: 13, fontWeight: 600 }}>
                    Saved
                  </span>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Audit Workbooks Shortcut + Privacy & Cookies */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 280px), 1fr))', gap: 16 }}>
        <div className="card" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
            <FileSpreadsheet size={18} style={{ color: 'var(--color-accent-blue)', flexShrink: 0 }} />
            <div>
              <div style={{ fontWeight: 600, fontSize: 14 }}>11-Day Swing Audits</div>
              <div style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>Download cycle Excel reports in Swing Screener</div>
            </div>
          </div>
          <Link to="/screener" className="btn btn-secondary" style={{ fontSize: 12, textDecoration: 'none' }}>
            Open Screener
          </Link>
        </div>

        <div className="card" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
            <Cookie size={18} style={{ color: 'var(--color-text-secondary)', flexShrink: 0 }} />
            <div>
              <div style={{ fontWeight: 600, fontSize: 14 }}>Privacy &amp; Cookies</div>
              <div style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>Manage analytics and preference storage</div>
            </div>
          </div>
          <button
            type="button"
            className="btn btn-secondary"
            style={{ fontSize: 12 }}
            onClick={() => window.dispatchEvent(new CustomEvent('open-cookie-settings'))}
          >
            Cookie Settings
          </button>
        </div>
      </div>
    </div>
  )
}
