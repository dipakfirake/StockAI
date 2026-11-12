import { useState, useEffect } from 'react'
import {
  Save,
  AlertCircle,
  Shield,
  ArrowRight,
  Sliders,
  FileSpreadsheet,
  Download,
  RefreshCw,
  History,
  ChevronDown,
  ChevronUp,
} from 'lucide-react'
import { Link } from 'react-router-dom'
import { settingsApi, swingAuditApi } from '../services/api'
import { useAuth } from '../AuthContext'

export default function SettingsPage() {
  const { user } = useAuth()
  const isAdmin = Boolean(user?.is_admin)

  const [settings, setSettings] = useState<Record<string, any>>({})
  const [loading, setLoading] = useState(false)
  const [saveSuccess, setSaveSuccess] = useState(false)

  // 11-Day Swing Audit State
  const [auditCycle, setAuditCycle] = useState<any | null>(null)
  const [auditFiles, setAuditFiles] = useState<any[]>([])
  const [showHistory, setShowHistory] = useState(false)
  const [syncingAudit, setSyncingAudit] = useState(false)
  const [auditLoading, setAuditLoading] = useState(false)

  const fetchAuditData = async () => {
    setAuditLoading(true)
    try {
      const [cycleRes, filesRes] = await Promise.all([
        swingAuditApi.getCurrentCycle(),
        swingAuditApi.listFiles(),
      ])
      setAuditCycle(cycleRes.data?.cycle || null)
      setAuditFiles(filesRes.data?.files || [])
    } catch (err) {
      console.error('Failed to load audit in settings:', err)
    } finally {
      setAuditLoading(false)
    }
  }

  const handleSyncAudit = async () => {
    setSyncingAudit(true)
    try {
      const res = await swingAuditApi.sync()
      alert(`11-Day Audit Synchronized!\nEvaluated ${res.data.updated_count || 0} stocks\nWin Rate: ${res.data.win_rate ?? 0}%\nTotal P&L: ₹${res.data.total_pnl_rupees ?? 0}`)
      await fetchAuditData()
    } catch (err: any) {
      alert(`Audit sync failed: ${err?.response?.data?.detail || err.message}`)
    } finally {
      setSyncingAudit(false)
    }
  }

  useEffect(() => {
    fetchSettings()
    fetchAuditData()
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

      {/* 11-Day Swing Trade Audit & Reports Section */}
      <div className="card" style={{ padding: 24, marginTop: 24, border: '1px solid rgba(56, 189, 248, 0.25)', background: 'linear-gradient(180deg, rgba(15, 23, 42, 0.9) 0%, rgba(30, 41, 59, 0.8) 100%)' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 16, marginBottom: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{ width: 40, height: 40, borderRadius: 8, background: 'rgba(56, 189, 248, 0.15)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#38bdf8' }}>
              <FileSpreadsheet size={22} />
            </div>
            <div>
              <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: '#f8fafc', display: 'flex', alignItems: 'center', gap: 8 }}>
                11-Day Swing Trade Audit & Excel Reports
                <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 4, background: 'rgba(56, 189, 248, 0.2)', color: '#38bdf8', fontWeight: 700 }}>
                  ACTIVE CYCLE #{auditCycle?.cycle_number || 1}
                </span>
              </h3>
              <p style={{ margin: 0, fontSize: 13, color: '#94a3b8' }}>
                Download multi-sheet institutional Excel workbooks with daily price checkpoints and P&L journals
              </p>
            </div>
          </div>

          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            <a
              href="/api/swing-audit/download-latest"
              download
              className="btn btn-primary"
              style={{ display: 'flex', alignItems: 'center', gap: 8, height: 36, textDecoration: 'none' }}
              title="Download current active 11-day cycle Excel spreadsheet"
            >
              <Download size={14} />
              <span>Download Current Excel (.xlsx)</span>
            </a>

            <button
              onClick={handleSyncAudit}
              disabled={syncingAudit}
              className="btn btn-secondary"
              style={{ display: 'flex', alignItems: 'center', gap: 6, height: 36, color: '#34d399', borderColor: 'rgba(52, 211, 153, 0.3)', background: 'rgba(52, 211, 153, 0.08)' }}
              title="Synchronize daily prices and check targets"
            >
              <RefreshCw size={14} className={syncingAudit ? 'spin' : ''} />
              <span>{syncingAudit ? 'Syncing...' : 'Sync Prices Now'}</span>
            </button>
          </div>
        </div>

        {/* Current Cycle Overview Stats */}
        {auditCycle && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 12, marginBottom: 16 }}>
            <div style={{ padding: 12, borderRadius: 6, background: 'rgba(0, 0, 0, 0.2)', border: '1px solid rgba(255, 255, 255, 0.05)' }}>
              <div style={{ fontSize: 11, color: '#94a3b8', textTransform: 'uppercase', fontWeight: 600 }}>Period</div>
              <div style={{ fontSize: 13, fontWeight: 700, color: '#f8fafc', marginTop: 2 }}>{auditCycle.from_date} to {auditCycle.to_date}</div>
            </div>
            <div style={{ padding: 12, borderRadius: 6, background: 'rgba(0, 0, 0, 0.2)', border: '1px solid rgba(255, 255, 255, 0.05)' }}>
              <div style={{ fontSize: 11, color: '#94a3b8', textTransform: 'uppercase', fontWeight: 600 }}>Win Rate</div>
              <div style={{ fontSize: 16, fontWeight: 800, color: (auditCycle.win_rate || 0) >= 50 ? '#34d399' : '#f87171', marginTop: 2 }}>{auditCycle.win_rate ?? 0}%</div>
            </div>
            <div style={{ padding: 12, borderRadius: 6, background: 'rgba(0, 0, 0, 0.2)', border: '1px solid rgba(255, 255, 255, 0.05)' }}>
              <div style={{ fontSize: 11, color: '#94a3b8', textTransform: 'uppercase', fontWeight: 600 }}>Cycle Return</div>
              <div style={{ fontSize: 16, fontWeight: 800, color: (auditCycle.total_gain_loss_pct || 0) >= 0 ? '#34d399' : '#f87171', marginTop: 2 }}>
                {(auditCycle.total_gain_loss_pct || 0) > 0 ? `+${auditCycle.total_gain_loss_pct}` : auditCycle.total_gain_loss_pct ?? 0}%
              </div>
            </div>
            <div style={{ padding: 12, borderRadius: 6, background: 'rgba(0, 0, 0, 0.2)', border: '1px solid rgba(255, 255, 255, 0.05)' }}>
              <div style={{ fontSize: 11, color: '#94a3b8', textTransform: 'uppercase', fontWeight: 600 }}>Realized P&L</div>
              <div style={{ fontSize: 16, fontWeight: 800, color: (auditCycle.total_pnl_rupees || 0) >= 0 ? '#34d399' : '#f87171', marginTop: 2 }}>
                ₹{(auditCycle.total_pnl_rupees || 0).toLocaleString('en-IN')}
              </div>
            </div>
          </div>
        )}

        {/* Historical Archive Toggle */}
        <div style={{ borderTop: '1px solid rgba(255, 255, 255, 0.08)', paddingTop: 14 }}>
          <button
            onClick={() => setShowHistory(!showHistory)}
            className="btn btn-ghost"
            style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: '#a78bfa', padding: '6px 12px' }}
          >
            <History size={15} />
            <span>{showHistory ? 'Hide Previous Audit Spreadsheets' : `View & Download Previous Audit Spreadsheets (${auditFiles.length} available)`}</span>
            {showHistory ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>

          {showHistory && (
            <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 8 }}>
              {auditFiles.length === 0 ? (
                <div style={{ padding: 16, fontSize: 13, color: '#94a3b8', textAlign: 'center' }}>
                  No archived spreadsheets found on the server.
                </div>
              ) : (
                auditFiles.map((file, idx) => (
                  <div
                    key={idx}
                    style={{
                      padding: '10px 14px',
                      background: 'rgba(0, 0, 0, 0.25)',
                      border: '1px solid rgba(255, 255, 255, 0.05)',
                      borderRadius: 6,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      flexWrap: 'wrap',
                      gap: 12,
                    }}
                  >
                    <div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span style={{ fontWeight: 700, fontSize: 13, color: '#f8fafc' }}>
                          Cycle #{file.cycle_number > 0 ? file.cycle_number : 'Archive'}
                        </span>
                        <span style={{ fontSize: 10, padding: '1px 6px', borderRadius: 4, background: file.status === 'ACTIVE' ? 'rgba(52, 211, 153, 0.2)' : 'rgba(148, 163, 184, 0.2)', color: file.status === 'ACTIVE' ? '#34d399' : '#94a3b8', textTransform: 'uppercase', fontWeight: 600 }}>
                          {file.status}
                        </span>
                        <span style={{ fontSize: 12, color: '#94a3b8' }}>
                          {file.from_date} to {file.to_date}
                        </span>
                      </div>
                      <div style={{ fontSize: 11, color: '#64748b', marginTop: 2, display: 'flex', gap: 10 }}>
                        <span>Trades: <strong style={{ color: '#e2e8f0' }}>{file.total_trades}</strong></span>
                        <span>Win Rate: <strong style={{ color: file.win_rate >= 50 ? '#34d399' : '#f87171' }}>{file.win_rate}%</strong></span>
                        <span>P&L: <strong style={{ color: file.total_pnl_rupees >= 0 ? '#34d399' : '#f87171' }}>₹{file.total_pnl_rupees.toLocaleString('en-IN')}</strong></span>
                      </div>
                    </div>

                    <a
                      href={swingAuditApi.downloadFileUrl(file.filename)}
                      download
                      className="btn btn-secondary"
                      style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: 6,
                        height: 28,
                        fontSize: 11,
                        color: '#38bdf8',
                        borderColor: 'rgba(56, 189, 248, 0.3)',
                        background: 'rgba(56, 189, 248, 0.08)',
                        textDecoration: 'none',
                      }}
                    >
                      <Download size={12} />
                      <span>Download .xlsx</span>
                    </a>
                  </div>
                ))
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
