import { useState, useEffect } from 'react'
import {
  Save,
  AlertCircle,
  Shield,
  ArrowRight,
  Sliders,
  KeyRound,
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

  const visibleSettings = Object.entries(settings).filter(([key]) => !isBrokerOrSensitiveKey(key))

  return (
    <div style={{ maxWidth: 850, margin: '0 auto', paddingBottom: 60 }}>
      <div className="page-header" style={{ marginBottom: 24 }}>
        <h1 className="page-title" style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <Sliders size={24} style={{ color: '#3b82f6' }} />
          Platform & Trading Preferences
        </h1>
        <p className="page-subtitle">Configure risk controls, default order execution parameters, and platform preferences</p>
      </div>

      {/* Admin Notice: Directing Fyers API & Token to Admin Page */}
      {isAdmin && (
        <div
          style={{
            padding: '16px 20px',
            marginBottom: 24,
            borderRadius: 10,
            background: 'linear-gradient(135deg, rgba(30, 41, 59, 0.9) 0%, rgba(15, 23, 42, 0.9) 100%)',
            border: '1px solid rgba(59, 130, 246, 0.3)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: 16,
            boxShadow: '0 4px 16px rgba(0,0,0,0.2)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{ width: 36, height: 36, borderRadius: 8, background: 'rgba(59, 130, 246, 0.2)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#60a5fa' }}>
              <Shield size={20} />
            </div>
            <div>
              <div style={{ fontWeight: 700, fontSize: 15, color: '#f8fafc' }}>
                Fyers Broker Integration & Mobile Token Manager
              </div>
              <div style={{ fontSize: 13, color: '#94a3b8' }}>
                Daily Fyers token renewal and live WebSocket streams are restricted to the Admin Control Center.
              </div>
            </div>
          </div>

          <Link
            to="/admin"
            className="btn btn-primary"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 8,
              padding: '8px 16px',
              fontSize: 13,
              textDecoration: 'none',
              fontWeight: 600,
            }}
          >
            Open Admin Control <ArrowRight size={15} />
          </Link>
        </div>
      )}

      {/* =========================================================================
          ⚙️ User & Trading Preferences Card
         ========================================================================= */}
      <div className="card">
        <h2 style={{ fontSize: 18, fontWeight: 700, margin: '0 0 16px 0' }}>Trading Parameters & Risk Safeguards</h2>
        {loading ? (
          <div className="text-center" style={{ padding: 40 }}>Loading preferences...</div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
            <div style={{ padding: 14, backgroundColor: 'rgba(59, 130, 246, 0.1)', borderRadius: 8, borderLeft: '4px solid #3b82f6', fontSize: 13 }}>
              <AlertCircle size={16} style={{ marginBottom: -3, marginRight: 8, color: '#3b82f6' }} />
              <strong>Risk Governance:</strong> These thresholds govern position sizing calculations, slippage assumptions, and simulated execution.
            </div>

            {visibleSettings.length === 0 ? (
              <div style={{ padding: 20, textAlign: 'center', color: 'var(--color-text-muted)' }}>
                No configurable user parameters at this time.
              </div>
            ) : (
              visibleSettings.map(([key, val]) => {
                const isBoolean = val === true || val === false || val === 'true' || val === 'false'

                return (
                  <div key={key} style={{ display: 'flex', flexDirection: 'column', gap: 4, padding: '12px 0', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
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
                        <span style={{ fontSize: 14, color: val === true || val === 'true' ? 'var(--color-bullish)' : 'var(--color-text-muted)' }}>
                          {val === true || val === 'true' ? 'ENABLED' : 'DISABLED'}
                        </span>
                      </label>
                    ) : (
                      <input
                        type="text"
                        className="input"
                        value={val.toString()}
                        onChange={(e) => setSettings({ ...settings, [key]: e.target.value })}
                        style={{ maxWidth: 300 }}
                      />
                    )}
                  </div>
                )
              })
            )}

            {isAdmin && visibleSettings.length > 0 && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 12 }}>
                <button onClick={saveSettings} className="btn btn-primary" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <Save size={16} /> Save Configuration
                </button>
                {saveSuccess && (
                  <span style={{ color: '#4ade80', fontSize: 13, fontWeight: 600 }}>
                    ✓ Settings saved successfully!
                  </span>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {/* =========================================================================
          🔐 Google OAuth 2.0 Web Client ID (Admin Only)
         ========================================================================= */}
      {isAdmin && (
        <div className="card" style={{ marginTop: 24, border: '1px solid rgba(59, 130, 246, 0.3)' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16, flexWrap: 'wrap', gap: 10 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <div style={{ width: 38, height: 38, borderRadius: 10, background: 'rgba(59, 130, 246, 0.15)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <KeyRound size={20} style={{ color: '#60a5fa' }} />
              </div>
              <div>
                <h2 style={{ fontSize: 17, fontWeight: 700, margin: 0, color: '#f8fafc' }}>
                  Google 1-Click OAuth2 Configuration
                </h2>
                <p style={{ margin: '2px 0 0', fontSize: 12, color: '#94a3b8' }}>
                  Enables 1-click Google Sign-In and instant registration on the login screen
                </p>
              </div>
            </div>
            {settings['google_client_id'] ? (
              <span style={{ fontSize: 11, fontWeight: 700, color: '#34d399', background: 'rgba(16, 185, 129, 0.15)', padding: '5px 12px', borderRadius: 6, border: '1px solid rgba(16, 185, 129, 0.3)' }}>
                ✓ GOOGLE SIGN-IN ACTIVE
              </span>
            ) : (
              <span style={{ fontSize: 11, fontWeight: 700, color: '#fbbf24', background: 'rgba(245, 158, 11, 0.15)', padding: '5px 12px', borderRadius: 6, border: '1px solid rgba(245, 158, 11, 0.3)' }}>
                ⚠️ UNCONFIGURED
              </span>
            )}
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <label style={{ fontSize: 13, fontWeight: 600, color: '#e2e8f0' }}>
              Google OAuth Client ID
            </label>
            <input
              type="text"
              className="input"
              placeholder="e.g. 123456789012-abcdefghijklmnopqrstuvwxyz.apps.googleusercontent.com"
              value={settings['google_client_id'] || ''}
              onChange={(e) => setSettings({ ...settings, google_client_id: e.target.value.trim() })}
              style={{ width: '100%', fontFamily: 'monospace', fontSize: 13, padding: '10px 14px' }}
            />
            <p style={{ fontSize: 12, color: '#64748b', margin: 0, lineHeight: 1.5 }}>
              Paste the <strong>Client ID</strong> generated from Google Cloud Console. Click <strong>Save Google Client ID</strong> to activate it across all devices immediately without restarting any containers.
            </p>

            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 8 }}>
              <button
                onClick={saveSettings}
                className="btn btn-primary"
                disabled={loading}
                style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px 18px', fontWeight: 600 }}
              >
                <Save size={16} /> Save Google Client ID
              </button>
              {saveSuccess && (
                <span style={{ color: '#4ade80', fontSize: 13, fontWeight: 600 }}>
                  ✓ Google Client ID saved successfully!
                </span>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
