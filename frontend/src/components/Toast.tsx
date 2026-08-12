import { useEffect, useState, useCallback } from 'react'
import { CheckCircle, XCircle, AlertTriangle, Info, X } from 'lucide-react'

export type ToastType = 'success' | 'error' | 'warning' | 'info'

export interface Toast {
  id: string
  type: ToastType
  title: string
  message?: string
  duration?: number
}

// Global singleton store — accessible outside React
type Listener = (toasts: Toast[]) => void
let _toasts: Toast[] = []
const _listeners: Set<Listener> = new Set()

function notifyListeners() {
  _listeners.forEach(fn => fn([..._toasts]))
}

export const toast = {
  show(type: ToastType, title: string, message?: string, duration = 4000) {
    const id = `toast-${Date.now()}-${Math.random()}`
    _toasts = [..._toasts, { id, type, title, message, duration }]
    notifyListeners()
    if (duration > 0) {
      setTimeout(() => toast.dismiss(id), duration)
    }
    return id
  },
  success: (title: string, message?: string) => toast.show('success', title, message),
  error: (title: string, message?: string) => toast.show('error', title, message, 6000),
  warning: (title: string, message?: string) => toast.show('warning', title, message, 5000),
  info: (title: string, message?: string) => toast.show('info', title, message),
  dismiss(id: string) {
    _toasts = _toasts.filter(t => t.id !== id)
    notifyListeners()
  },
}

const iconMap = {
  success: <CheckCircle size={18} />,
  error: <XCircle size={18} />,
  warning: <AlertTriangle size={18} />,
  info: <Info size={18} />,
}

const colorMap = {
  success: { border: '#10b981', bg: 'rgba(16,185,129,0.1)', icon: '#10b981' },
  error: { border: '#ef4444', bg: 'rgba(239,68,68,0.1)', icon: '#ef4444' },
  warning: { border: '#f59e0b', bg: 'rgba(245,158,11,0.1)', icon: '#f59e0b' },
  info: { border: '#3b82f6', bg: 'rgba(59,130,246,0.1)', icon: '#3b82f6' },
}

export function ToastContainer() {
  const [toasts, setToasts] = useState<Toast[]>([])

  useEffect(() => {
    const listener: Listener = updated => setToasts(updated)
    _listeners.add(listener)
    return () => { _listeners.delete(listener) }
  }, [])

  if (toasts.length === 0) return null

  return (
    <div style={{
      position: 'fixed',
      bottom: 24,
      right: 24,
      zIndex: 9999,
      display: 'flex',
      flexDirection: 'column',
      gap: 10,
      maxWidth: 360,
      pointerEvents: 'none',
    }}>
      {toasts.map((t) => {
        const colors = colorMap[t.type]
        return (
          <div
            key={t.id}
            className="toast-item"
            style={{
              background: 'var(--color-bg-card)',
              border: `1px solid ${colors.border}`,
              borderLeft: `4px solid ${colors.border}`,
              borderRadius: 10,
              padding: '12px 16px',
              boxShadow: `0 8px 32px rgba(0,0,0,0.3), 0 0 0 1px ${colors.border}22`,
              display: 'flex',
              gap: 10,
              alignItems: 'flex-start',
              pointerEvents: 'all',
              animation: 'toastSlideIn 0.3s cubic-bezier(0.34, 1.56, 0.64, 1)',
            }}
          >
            <span style={{ color: colors.icon, flexShrink: 0, marginTop: 1 }}>
              {iconMap[t.type]}
            </span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontWeight: 600, fontSize: 13, color: 'var(--color-text-primary)' }}>
                {t.title}
              </div>
              {t.message && (
                <div style={{ fontSize: 12, color: 'var(--color-text-secondary)', marginTop: 3, lineHeight: 1.4 }}>
                  {t.message}
                </div>
              )}
            </div>
            <button
              onClick={() => toast.dismiss(t.id)}
              style={{
                background: 'none', border: 'none', cursor: 'pointer',
                color: 'var(--color-text-muted)', padding: 2, flexShrink: 0,
                display: 'flex', alignItems: 'center',
              }}
            >
              <X size={14} />
            </button>
          </div>
        )
      })}
    </div>
  )
}
