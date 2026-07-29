import { useState, useEffect } from 'react'
import { Save, AlertCircle } from 'lucide-react'

// Dummy auth usage. Need token for real calls.
import { useAuth } from '../AuthContext'

export default function SettingsPage() {
  const { token } = useAuth()
  const [settings, setSettings] = useState<Record<string, any>>({})
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    fetchSettings()
  }, [])

  async function fetchSettings() {
    setLoading(true)
    try {
      const res = await fetch('/api/settings/', {
        headers: { Authorization: `Bearer ${token}` }
      })
      if (res.ok) {
        const data = await res.json()
        setSettings(data)
      }
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  // A real implementation would also have a saveSettings endpoint 
  // that sends updated values back to the backend.

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">System Settings & Risk Management</h1>
        <p className="page-subtitle">Configure global dynamic variables for the platform</p>
      </div>

      <div className="card" style={{ maxWidth: 800 }}>
        {loading ? (
          <div className="text-center" style={{ padding: 40 }}>Loading...</div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
            <div style={{ padding: 16, backgroundColor: 'rgba(59, 130, 246, 0.1)', borderRadius: 8, borderLeft: '4px solid #3b82f6' }}>
              <AlertCircle size={18} style={{ marginBottom: -4, marginRight: 8, color: '#3b82f6' }} />
              <strong>Dynamic Settings Enabled:</strong> These values are fetched dynamically from the database, eliminating hardcoded system defaults.
            </div>

            {Object.entries(settings).map(([key, val]) => (
              <div key={key} style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                <label style={{ fontWeight: 600, fontSize: 14 }}>
                  {key.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')}
                </label>
                <input 
                  type="text"
                  className="input"
                  value={val.toString()}
                  onChange={(e) => setSettings({ ...settings, [key]: e.target.value })}
                  style={{ maxWidth: 300 }}
                />
              </div>
            ))}
            
            <button className="btn btn-primary" style={{ alignSelf: 'flex-start', marginTop: 16 }}>
              <Save size={16} /> Save Configuration
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
