import React, { useState } from 'react'
import { ShieldCheck, KeyRound, X } from 'lucide-react'
import { adminApi, setAdminStepUpToken } from '../services/api'

interface AdminStepUpModalProps {
  open: boolean
  title?: string
  onCancel: () => void
  onVerified: () => void
}

export default function AdminStepUpModal({
  open,
  title = 'Authenticator Step-Up Verification',
  onCancel,
  onVerified,
}: AdminStepUpModalProps) {
  const [code, setCode] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  if (!open) return null

  const handleVerify = async (e: React.FormEvent) => {
    e.preventDefault()
    const clean = code.trim()
    if (!clean) return
    setLoading(true)
    setError('')
    try {
      const res = await adminApi.stepUpMfa(clean)
      const tok = res.data?.stepup_token
      const exp = Number(res.data?.expires_in || 600)
      if (tok) {
        setAdminStepUpToken(tok, exp)
      }
      setCode('')
      onVerified()
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Invalid authenticator or recovery code.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0, 0, 0, 0.72)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 16,
        zIndex: 1100,
      }}
    >
      <div
        className="card"
        style={{
          width: '100%',
          maxWidth: 400,
          padding: 22,
          border: '1px solid var(--color-border-light)',
          position: 'relative',
        }}
      >
        <button
          type="button"
          onClick={onCancel}
          aria-label="Close verification dialog"
          style={{
            position: 'absolute',
            top: 14,
            right: 14,
            background: 'transparent',
            border: 'none',
            color: 'var(--color-text-muted)',
            cursor: 'pointer',
          }}
        >
          <X size={18} />
        </button>

        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
          <div
            style={{
              width: 36,
              height: 36,
              borderRadius: 8,
              background: 'rgba(59, 130, 246, 0.14)',
              color: 'var(--color-accent-blue)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
            }}
          >
            <ShieldCheck size={20} />
          </div>
          <div>
            <div style={{ fontWeight: 700, fontSize: 15 }}>{title}</div>
            <div style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>
              Confirm your 6-digit Authenticator or backup code (valid for 10 min)
            </div>
          </div>
        </div>

        {error && (
          <div
            style={{
              padding: '8px 10px',
              marginBottom: 12,
              borderRadius: 6,
              fontSize: 12.5,
              border: '1px solid rgba(239, 68, 68, 0.4)',
              background: 'rgba(239, 68, 68, 0.12)',
              color: '#f87171',
            }}
          >
            {error}
          </div>
        )}

        <form onSubmit={handleVerify} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <KeyRound size={16} style={{ color: 'var(--color-text-muted)', flexShrink: 0 }} />
            <input
              type="text"
              className="input mono"
              placeholder="6-digit code or XXXX-XXXX"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              autoFocus
              required
            />
          </div>
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
            <button type="button" className="btn btn-secondary" onClick={onCancel}>
              Cancel
            </button>
            <button type="submit" className="btn btn-primary" disabled={loading || !code.trim()}>
              {loading ? 'Verifying...' : 'Verify & Continue'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
