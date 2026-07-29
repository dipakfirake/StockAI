import { useEffect, useState } from 'react'
import { alertsApi } from '../services/api'
import { Bell, PlusCircle, Trash2, BellOff } from 'lucide-react'

const CONDITION_TYPES = [
  { value: 'PRICE_ABOVE', label: 'Price Above' },
  { value: 'PRICE_BELOW', label: 'Price Below' },
  { value: 'RSI_ABOVE', label: 'RSI Above' },
  { value: 'RSI_BELOW', label: 'RSI Below' },
  { value: 'MACD_CROSS_UP', label: 'MACD Cross Up' },
  { value: 'MACD_CROSS_DOWN', label: 'MACD Cross Down' },
]

export default function AlertsPage() {
  const [alerts, setAlerts] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ symbol: '', condition_type: 'PRICE_ABOVE', condition_value: '', message: '' })
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => { loadAlerts() }, [])

  async function loadAlerts() {
    try {
      const res = await alertsApi.list()
      setAlerts(res.data.alerts || [])
    } finally { setLoading(false) }
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    setSubmitting(true)
    try {
      await alertsApi.create({
        symbol: form.symbol.toUpperCase(),
        condition_type: form.condition_type,
        condition_value: parseFloat(form.condition_value),
        message: form.message || undefined,
      })
      setShowForm(false)
      setForm({ symbol: '', condition_type: 'PRICE_ABOVE', condition_value: '', message: '' })
      await loadAlerts()
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Failed to create alert')
    } finally { setSubmitting(false) }
  }

  async function handleDelete(id: string) {
    if (!confirm('Delete this alert?')) return
    await alertsApi.delete(id)
    await loadAlerts()
  }

  async function handleDeactivate(id: string) {
    await alertsApi.deactivate(id)
    await loadAlerts()
  }

  return (
    <div>
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h1 className="page-title">Alerts</h1>
          <p className="page-subtitle">Price, RSI, MACD alerts with de-duplication and quiet hours</p>
        </div>
        <button className="btn btn-primary" onClick={() => setShowForm(!showForm)}>
          <PlusCircle size={15} /> New Alert
        </button>
      </div>

      {/* Create Alert Form */}
      {showForm && (
        <div className="card" style={{ marginBottom: 20 }}>
          <div className="card-title" style={{ marginBottom: 16 }}>Create New Alert</div>
          <form onSubmit={handleCreate} style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 12 }}>
            <div>
              <label style={{ fontSize: 12, color: 'var(--color-text-muted)', marginBottom: 4, display: 'block' }}>Symbol</label>
              <input className="input" placeholder="RELIANCE.NS" required value={form.symbol} onChange={e => setForm({ ...form, symbol: e.target.value })} />
            </div>
            <div>
              <label style={{ fontSize: 12, color: 'var(--color-text-muted)', marginBottom: 4, display: 'block' }}>Condition</label>
              <select className="input" value={form.condition_type} onChange={e => setForm({ ...form, condition_type: e.target.value })}>
                {CONDITION_TYPES.map(c => <option key={c.value} value={c.value}>{c.label}</option>)}
              </select>
            </div>
            <div>
              <label style={{ fontSize: 12, color: 'var(--color-text-muted)', marginBottom: 4, display: 'block' }}>Value</label>
              <input className="input" type="number" step="any" required placeholder="e.g. 2850" value={form.condition_value} onChange={e => setForm({ ...form, condition_value: e.target.value })} />
            </div>
            <div>
              <label style={{ fontSize: 12, color: 'var(--color-text-muted)', marginBottom: 4, display: 'block' }}>Custom Message (optional)</label>
              <input className="input" placeholder="Optional note…" value={form.message} onChange={e => setForm({ ...form, message: e.target.value })} />
            </div>
            <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end' }}>
              <button type="submit" className="btn btn-primary" disabled={submitting}>{submitting ? 'Creating…' : 'Create Alert'}</button>
              <button type="button" className="btn btn-ghost" onClick={() => setShowForm(false)}>Cancel</button>
            </div>
          </form>
          <div style={{ marginTop: 12, fontSize: 12, color: 'var(--color-text-muted)' }}>
            ℹ️ Alerts are de-duplicated (4-hour cooldown). No alerts outside market hours (09:15–15:30 IST).
          </div>
        </div>
      )}

      {/* Alerts Table */}
      <div className="card">
        {loading && <div className="loading">Loading alerts…</div>}
        {!loading && alerts.length === 0 && (
          <div className="empty-state">
            <Bell size={32} style={{ marginBottom: 8, opacity: 0.3 }} />
            <div>No alerts configured yet. Create your first alert above.</div>
          </div>
        )}
        {alerts.length > 0 && (
          <table className="table">
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Condition</th>
                <th>Value</th>
                <th>Status</th>
                <th>Last Triggered</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {alerts.map(a => (
                <tr key={a.alert_id}>
                  <td><span className="mono" style={{ fontWeight: 600 }}>{a.symbol}</span></td>
                  <td style={{ color: 'var(--color-text-secondary)' }}>{CONDITION_TYPES.find(c => c.value === a.condition_type)?.label || a.condition_type}</td>
                  <td className="mono">{a.condition_value}</td>
                  <td>
                    <span style={{ color: a.is_active ? 'var(--color-bullish)' : 'var(--color-text-muted)', fontSize: 13 }}>
                      {a.is_active ? '● Active' : '○ Inactive'}
                    </span>
                  </td>
                  <td style={{ color: 'var(--color-text-muted)', fontSize: 12 }}>
                    {a.triggered_at ? new Date(a.triggered_at).toLocaleString('en-IN') : 'Never'}
                  </td>
                  <td>
                    <div style={{ display: 'flex', gap: 6 }}>
                      {a.is_active && <button className="btn btn-ghost" style={{ padding: '4px 10px', fontSize: 12 }} onClick={() => handleDeactivate(a.alert_id)}><BellOff size={13} /></button>}
                      <button className="btn btn-danger" style={{ padding: '4px 10px', fontSize: 12 }} onClick={() => handleDelete(a.alert_id)}><Trash2 size={13} /></button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
