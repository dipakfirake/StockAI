import React, { useEffect, useState } from 'react'
import { usePresenceContext } from '../PresenceContext'
import { X, RefreshCw, Smartphone, Monitor, Shield, Crown, User, Globe, Activity, MapPin } from 'lucide-react'

export default function LiveUsersModal() {
  const { isModalOpen, setIsModalOpen, liveUsers, fetchLiveUsers, loadingUsers, liveCount } = usePresenceContext()
  const [autoRefresh, setAutoRefresh] = useState(false)

  // Fetch active users list on-demand when modal opens; only poll if admin explicitly toggles auto-refresh
  useEffect(() => {
    if (!isModalOpen) return

    fetchLiveUsers()

    if (!autoRefresh) return
    const interval = setInterval(() => {
      fetchLiveUsers()
    }, 5000)

    return () => clearInterval(interval)
  }, [isModalOpen, autoRefresh, fetchLiveUsers])

  if (!isModalOpen) return null

  // Calculate metrics
  const loggedInCount = liveUsers.filter((u) => u.role !== 'GUEST').length
  const guestCount = liveUsers.filter((u) => u.role === 'GUEST').length
  const mobileCount = liveUsers.filter((u) => u.device.toLowerCase().includes('mobile')).length
  const desktopCount = liveUsers.length - mobileCount

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 99999,
        background: 'rgba(0, 0, 0, 0.75)',
        backdropFilter: 'blur(8px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '16px',
        animation: 'fadeIn 0.2s ease',
      }}
      onClick={() => setIsModalOpen(false)}
    >
      <div
        style={{
          background: 'var(--color-bg-secondary, #111827)',
          border: '1px solid var(--color-border, rgba(255, 255, 255, 0.12))',
          borderRadius: '16px',
          width: '100%',
          maxWidth: '920px',
          maxHeight: '90vh',
          display: 'flex',
          flexDirection: 'column',
          boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.7)',
          overflow: 'hidden',
          color: 'var(--color-text-primary, #f9fafb)',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal Header */}
        <div
          style={{
            padding: '20px 24px',
            borderBottom: '1px solid var(--color-border, rgba(255, 255, 255, 0.1))',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            background: 'rgba(255, 255, 255, 0.02)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <span
              style={{
                position: 'relative',
                display: 'flex',
                height: '12px',
                width: '12px',
              }}
            >
              <span
                style={{
                  position: 'absolute',
                  inset: 0,
                  borderRadius: '50%',
                  backgroundColor: '#22c55e',
                  opacity: 0.75,
                  animation: 'pulse 1.8s infinite',
                }}
              />
              <span
                style={{
                  position: 'relative',
                  display: 'inline-flex',
                  borderRadius: '50%',
                  height: '100%',
                  width: '100%',
                  backgroundColor: '#22c55e',
                  boxShadow: '0 0 10px #22c55e',
                }}
              />
            </span>
            <div>
              <h2 style={{ margin: 0, fontSize: '1.25rem', fontWeight: 800, display: 'flex', alignItems: 'center', gap: '8px' }}>
                Real-Time Live Users Surveillance
                <span
                  style={{
                    fontSize: '0.72rem',
                    padding: '2px 8px',
                    borderRadius: '12px',
                    background: 'rgba(34, 197, 94, 0.15)',
                    color: '#4ade80',
                    border: '1px solid rgba(34, 197, 94, 0.3)',
                    fontWeight: 700,
                  }}
                >
                  Admin Only
                </span>
              </h2>
              <p style={{ margin: '3px 0 0 0', fontSize: '0.8rem', color: 'var(--color-text-secondary, #9ca3af)' }}>
                Pure in-memory Redis session tracking • CERT-In 2022 & DPDPA Compliant Coarse IP Geolocation
              </p>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <button
              onClick={() => setAutoRefresh(!autoRefresh)}
              style={{
                padding: '6px 12px',
                borderRadius: '8px',
                border: '1px solid var(--border-color, rgba(255,255,255,0.15))',
                background: autoRefresh ? 'rgba(59, 130, 246, 0.15)' : 'transparent',
                color: autoRefresh ? '#60a5fa' : 'var(--color-text-secondary, #9ca3af)',
                cursor: 'pointer',
                fontSize: '0.78rem',
                fontWeight: 600,
                display: 'flex',
                alignItems: 'center',
                gap: '5px',
              }}
            >
              <Activity size={13} />
              {autoRefresh ? 'Live (3.5s)' : 'Paused'}
            </button>

            <button
              onClick={fetchLiveUsers}
              disabled={loadingUsers}
              style={{
                padding: '6px 10px',
                borderRadius: '8px',
                border: '1px solid var(--border-color, rgba(255,255,255,0.15))',
                background: 'transparent',
                color: 'var(--color-text-primary, #f9fafb)',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
              }}
              title="Refresh now"
            >
              <RefreshCw size={14} className={loadingUsers ? 'spin' : ''} />
            </button>

            <button
              onClick={() => setIsModalOpen(false)}
              style={{
                padding: '6px',
                borderRadius: '8px',
                border: 'none',
                background: 'rgba(255, 255, 255, 0.08)',
                color: 'var(--color-text-primary, #f9fafb)',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
              }}
            >
              <X size={18} />
            </button>
          </div>
        </div>

        {/* Stats Cards Row */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))',
            gap: '12px',
            padding: '16px 24px',
            background: 'rgba(0, 0, 0, 0.2)',
            borderBottom: '1px solid var(--color-border, rgba(255, 255, 255, 0.08))',
          }}
        >
          <div style={{ background: 'rgba(255,255,255,0.03)', padding: '12px', borderRadius: '10px', border: '1px solid rgba(255,255,255,0.06)' }}>
            <div style={{ fontSize: '0.75rem', color: 'var(--color-text-secondary, #9ca3af)' }}>Total Live Sessions</div>
            <div style={{ fontSize: '1.4rem', fontWeight: 800, color: '#22c55e', marginTop: '2px' }}>{liveCount}</div>
          </div>
          <div style={{ background: 'rgba(255,255,255,0.03)', padding: '12px', borderRadius: '10px', border: '1px solid rgba(255,255,255,0.06)' }}>
            <div style={{ fontSize: '0.75rem', color: 'var(--color-text-secondary, #9ca3af)' }}>Logged-In Traders</div>
            <div style={{ fontSize: '1.4rem', fontWeight: 800, color: '#3b82f6', marginTop: '2px' }}>{loggedInCount}</div>
          </div>
          <div style={{ background: 'rgba(255,255,255,0.03)', padding: '12px', borderRadius: '10px', border: '1px solid rgba(255,255,255,0.06)' }}>
            <div style={{ fontSize: '0.75rem', color: 'var(--color-text-secondary, #9ca3af)' }}>Guest Visitors</div>
            <div style={{ fontSize: '1.4rem', fontWeight: 800, color: '#a855f7', marginTop: '2px' }}>{guestCount}</div>
          </div>
          <div style={{ background: 'rgba(255,255,255,0.03)', padding: '12px', borderRadius: '10px', border: '1px solid rgba(255,255,255,0.06)' }}>
            <div style={{ fontSize: '0.75rem', color: 'var(--color-text-secondary, #9ca3af)' }}>Device Breakdown</div>
            <div style={{ fontSize: '0.92rem', fontWeight: 700, marginTop: '6px', display: 'flex', gap: '10px' }}>
              <span>💻 {desktopCount}</span>
              <span>📱 {mobileCount}</span>
            </div>
          </div>
        </div>

        {/* Live Users Table / List */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '16px 24px' }}>
          {liveUsers.length === 0 ? (
            <div style={{ padding: '40px', textAlign: 'center', color: 'var(--color-text-secondary, #9ca3af)' }}>
              No active users detected.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {liveUsers.map((u) => {
                const isMobile = u.device.toLowerCase().includes('mobile')
                return (
                  <div
                    key={u.session_id}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '12px 16px',
                      borderRadius: '10px',
                      background: 'rgba(255, 255, 255, 0.03)',
                      border: '1px solid rgba(255, 255, 255, 0.06)',
                      transition: 'background 0.15s ease',
                      flexWrap: 'wrap',
                      gap: '12px',
                    }}
                  >
                    {/* User Identity */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px', minWidth: '220px' }}>
                      <div
                        style={{
                          width: '36px',
                          height: '36px',
                          borderRadius: '50%',
                          background: u.role === 'ADMIN'
                            ? 'linear-gradient(135deg, #ef4444, #b91c1c)'
                            : u.role === 'PRO'
                            ? 'linear-gradient(135deg, #10b981, #059669)'
                            : u.role === 'FREE'
                            ? 'linear-gradient(135deg, #3b82f6, #1d4ed8)'
                            : 'linear-gradient(135deg, #64748b, #475569)',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          fontWeight: 700,
                          fontSize: '0.9rem',
                          color: '#fff',
                        }}
                      >
                        {u.user_name ? u.user_name.charAt(0).toUpperCase() : 'G'}
                      </div>
                      <div>
                        <div style={{ fontWeight: 700, fontSize: '0.92rem', display: 'flex', alignItems: 'center', gap: '6px' }}>
                          {u.user_name}
                          {u.role === 'ADMIN' && (
                            <span style={{ fontSize: '0.68rem', padding: '1px 6px', borderRadius: '10px', background: 'rgba(239, 68, 68, 0.2)', color: '#f87171', border: '1px solid rgba(239, 68, 68, 0.3)' }}>
                              ADMIN
                            </span>
                          )}
                          {u.role === 'PRO' && (
                            <span style={{ fontSize: '0.68rem', padding: '1px 6px', borderRadius: '10px', background: 'rgba(34, 197, 94, 0.2)', color: '#4ade80', border: '1px solid rgba(34, 197, 94, 0.3)' }}>
                              PRO
                            </span>
                          )}
                        </div>
                        <div style={{ fontSize: '0.78rem', color: 'var(--color-text-secondary, #9ca3af)' }}>
                          {u.user_email || 'Unregistered Visitor'}
                        </div>
                      </div>
                    </div>

                    {/* Active Page / Path */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <Globe size={14} color="#60a5fa" />
                      <span
                        style={{
                          fontSize: '0.8rem',
                          fontFamily: 'monospace',
                          background: 'rgba(59, 130, 246, 0.1)',
                          border: '1px solid rgba(59, 130, 246, 0.2)',
                          padding: '3px 8px',
                          borderRadius: '6px',
                          color: '#93c5fd',
                        }}
                      >
                        {u.path || '/dashboard'}
                      </span>
                    </div>

                    {/* Location & IP (CERT-In / DPDPA Coarse GeoIP) */}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '2px', minWidth: '150px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '5px', fontSize: '0.8rem', fontWeight: 600, color: '#f1f5f9' }}>
                        <MapPin size={13} color="#f43f5e" style={{ flexShrink: 0 }} />
                        <span style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: '160px' }} title={u.location || 'Localhost / Internal Network'}>
                          {u.location || 'Localhost / Internal Network'}
                        </span>
                      </div>
                      <div style={{ fontSize: '0.72rem', fontFamily: 'monospace', color: 'var(--color-text-secondary, #9ca3af)', paddingLeft: '18px' }} title={`Client IP: ${u.ip || '127.0.0.1'}`}>
                        {u.ip || '127.0.0.1'}
                      </div>
                    </div>

                    {/* Device Icon & Label */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.82rem', color: 'var(--color-text-secondary, #9ca3af)' }}>
                      {isMobile ? <Smartphone size={15} color="#eab308" /> : <Monitor size={15} color="#38bdf8" />}
                      <span>{u.device}</span>
                    </div>

                    {/* Ping / Freshness status */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <span
                        style={{
                          width: '7px',
                          height: '7px',
                          borderRadius: '50%',
                          backgroundColor: u.last_seen_seconds_ago <= 4 ? '#22c55e' : '#eab308',
                        }}
                      />
                      <span style={{ fontSize: '0.78rem', color: 'var(--color-text-secondary, #9ca3af)', whiteSpace: 'nowrap' }}>
                        {u.last_seen_seconds_ago <= 1 ? 'Just now' : `${u.last_seen_seconds_ago}s ago`}
                      </span>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div
          style={{
            padding: '14px 24px',
            borderTop: '1px solid var(--color-border, rgba(255, 255, 255, 0.08))',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            fontSize: '0.78rem',
            color: 'var(--color-text-secondary, #9ca3af)',
            background: 'rgba(255, 255, 255, 0.01)',
          }}
        >
          <span>Auto-prunes dead mobile tabs after 12s of inactivity</span>
          <button
            onClick={() => setIsModalOpen(false)}
            style={{
              padding: '6px 16px',
              borderRadius: '6px',
              border: '1px solid var(--color-border, rgba(255, 255, 255, 0.2))',
              background: 'transparent',
              color: '#fff',
              cursor: 'pointer',
              fontWeight: 600,
            }}
          >
            Close
          </button>
        </div>
      </div>
      <style>{`
        @keyframes fadeIn {
          from { opacity: 0; transform: scale(0.97); }
          to { opacity: 1; transform: scale(1); }
        }
        .spin {
          animation: spin 1s linear infinite;
        }
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  )
}
