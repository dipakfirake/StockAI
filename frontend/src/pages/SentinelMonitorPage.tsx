import React, { useState, useEffect, useRef } from 'react';
import { sentinelApi } from '../services/api';
import { Link } from 'react-router-dom';

interface SubsystemInfo {
  status: 'HEALTHY' | 'WARNING' | 'DEGRADED' | 'DOWN';
  latency_ms?: number;
  message?: string;
  checked_at: string;
  [key: string]: any;
}

interface SentinelIncident {
  id: string;
  subsystem: string;
  severity: 'CRITICAL' | 'WARNING' | 'INFO';
  title: string;
  detail: string;
  suggested_action: string;
  occurrence_count: number;
  status: 'OPEN' | 'RESOLVED';
  first_seen_at: string;
  last_seen_at: string;
}

interface HealthSummary {
  overall_status: string;
  health_score: number;
  audit_runs: number;
  open_incident_count: number;
  subsystems: Record<string, SubsystemInfo>;
  recent_incidents: SentinelIncident[];
  server_time: string;
}

export default function SentinelMonitorPage() {
  const [data, setData] = useState<HealthSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [auditing, setAuditing] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [resolveLoading, setResolveLoading] = useState<string | null>(null);
  const timerRef = useRef<any>(null);

  const fetchHealth = async (showLoading = false) => {
    if (showLoading) setLoading(true);
    try {
      const res = await sentinelApi.getStatus();
      setData(res.data);
    } catch (err) {
      console.error('Sentinel fetch error', err);
    } finally {
      if (showLoading) setLoading(false);
    }
  };

  useEffect(() => {
    fetchHealth(true);

    if (autoRefresh) {
      timerRef.current = setInterval(() => {
        fetchHealth(false);
      }, 3000);
    }

    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [autoRefresh]);

  const handleAuditNow = async () => {
    setAuditing(true);
    try {
      const res = await sentinelApi.auditNow();
      setData(res.data);
    } catch (err) {
      console.error('Deep audit error', err);
    } finally {
      setAuditing(false);
    }
  };

  const handleResolve = async (incidentId: string) => {
    setResolveLoading(incidentId);
    try {
      await sentinelApi.resolveIncident(incidentId);
      await fetchHealth(false);
    } catch (err) {
      console.error('Resolve error', err);
    } finally {
      setResolveLoading(null);
    }
  };

  const score = data?.health_score ?? 100;
  const scoreColor = score >= 90 ? '#22c55e' : score >= 70 ? '#f59e0b' : '#ef4444';

  return (
    <div style={{ maxWidth: '1240px', margin: '0 auto', padding: '30px 20px' }}>
      
      {/* Top Banner & Control Bar */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: '26px',
        flexWrap: 'wrap',
        gap: '16px'
      }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <h1 style={{ fontSize: '2rem', fontWeight: 800, margin: 0 }}>
              🛡️ Sentinel 24/7 Autonomous Watchdog
            </h1>
            <span style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              padding: '4px 10px',
              borderRadius: '20px',
              background: 'rgba(34, 197, 94, 0.15)',
              border: '1px solid #22c55e',
              color: '#4ade80',
              fontSize: '0.8rem',
              fontWeight: 700
            }}>
              <span style={{
                width: '8px',
                height: '8px',
                borderRadius: '50%',
                background: '#22c55e',
                boxShadow: '0 0 8px #22c55e',
                animation: 'pulse 1.5s infinite'
              }} />
              ACTIVE 24/7 (1-2s Loop)
            </span>
          </div>
          <p style={{ color: 'var(--text-secondary)', margin: '6px 0 0 0', fontSize: '0.95rem' }}>
            Autonomous sub-second surveillance continuously probing databases, Redis, broker tokens, Celery queues, API endpoints, and security threat vectors.
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <button
            onClick={() => setAutoRefresh(!autoRefresh)}
            style={{
              padding: '9px 14px',
              borderRadius: '8px',
              border: '1px solid var(--border-color)',
              background: autoRefresh ? 'rgba(59, 130, 246, 0.15)' : 'var(--surface-color)',
              color: autoRefresh ? '#60a5fa' : 'var(--text-secondary)',
              cursor: 'pointer',
              fontWeight: 600,
              fontSize: '0.85rem'
            }}
          >
            {autoRefresh ? '🟢 Auto-Refresh (3s)' : '⏸️ Paused'}
          </button>

          <button
            onClick={handleAuditNow}
            disabled={auditing}
            style={{
              padding: '9px 16px',
              borderRadius: '8px',
              border: 'none',
              background: 'linear-gradient(90deg, #3b82f6, #2563eb)',
              color: 'white',
              cursor: 'pointer',
              fontWeight: 700,
              fontSize: '0.88rem',
              boxShadow: '0 4px 12px rgba(37, 99, 235, 0.3)'
            }}
          >
            {auditing ? '⚡ Auditing...' : '⚡ Audit Now'}
          </button>

          <Link
            to="/admin"
            style={{
              padding: '9px 14px',
              borderRadius: '8px',
              border: '1px solid var(--border-color)',
              background: 'var(--surface-color)',
              color: 'var(--text-color)',
              textDecoration: 'none',
              fontWeight: 600,
              fontSize: '0.85rem'
            }}
          >
            👥 User Admin
          </Link>
        </div>
      </div>

      {/* Primary KPI Row */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(230px, 1fr))',
        gap: '16px',
        marginBottom: '26px'
      }}>
        {/* Health Score */}
        <div style={{
          background: 'var(--surface-color)',
          padding: '22px',
          borderRadius: '14px',
          border: `1px solid ${scoreColor}`,
          position: 'relative',
          overflow: 'hidden'
        }}>
          <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', fontWeight: 600 }}>System Health Score</div>
          <div style={{ fontSize: '2.5rem', fontWeight: 900, color: scoreColor, marginTop: '4px' }}>
            {score}%
          </div>
          <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginTop: '2px' }}>
            Status: <strong style={{ color: scoreColor }}>{data?.overall_status || 'OPERATIONAL'}</strong>
          </div>
        </div>

        {/* Audits Executed */}
        <div style={{
          background: 'var(--surface-color)',
          padding: '22px',
          borderRadius: '14px',
          border: '1px solid var(--border-color)'
        }}>
          <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', fontWeight: 600 }}>Surveillance Cycles Run</div>
          <div style={{ fontSize: '2.5rem', fontWeight: 900, color: '#60a5fa', marginTop: '4px' }}>
            {data?.audit_runs?.toLocaleString() ?? 0}
          </div>
          <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginTop: '2px' }}>
            Continuous 24/7 background inspections
          </div>
        </div>

        {/* Open Incidents */}
        <div style={{
          background: 'var(--surface-color)',
          padding: '22px',
          borderRadius: '14px',
          border: data?.open_incident_count ? '1px solid #f59e0b' : '1px solid var(--border-color)'
        }}>
          <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', fontWeight: 600 }}>Active Incident Anomaly Count</div>
          <div style={{ fontSize: '2.5rem', fontWeight: 900, color: data?.open_incident_count ? '#fbbf24' : '#4ade80', marginTop: '4px' }}>
            {data?.open_incident_count ?? 0}
          </div>
          <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginTop: '2px' }}>
            {data?.open_incident_count ? 'Requires review or remediation' : 'Zero unmitigated failures'}
          </div>
        </div>

        {/* Server Clock */}
        <div style={{
          background: 'var(--surface-color)',
          padding: '22px',
          borderRadius: '14px',
          border: '1px solid var(--border-color)'
        }}>
          <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', fontWeight: 600 }}>Sentinel Time Horizon</div>
          <div style={{ fontSize: '1.2rem', fontWeight: 700, marginTop: '8px', color: 'var(--text-color)' }}>
            {data?.server_time ? new Date(data.server_time).toLocaleTimeString() : '—'}
          </div>
          <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginTop: '4px' }}>
            {data?.server_time ? new Date(data.server_time).toLocaleDateString() : '—'}
          </div>
        </div>
      </div>

      {/* Subsystem Radar Matrix */}
      <div style={{ marginBottom: '30px' }}>
        <h2 style={{ fontSize: '1.3rem', fontWeight: 700, marginBottom: '14px' }}>
          📡 360° Subsystem Health Radar
        </h2>
        
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
          gap: '14px'
        }}>
          {Object.entries(data?.subsystems || {}).map(([key, sub]) => {
            const isHealthy = sub.status === 'HEALTHY';
            const isWarning = sub.status === 'WARNING';
            const borderCol = isHealthy ? 'rgba(34, 197, 94, 0.25)' : isWarning ? 'rgba(245, 158, 11, 0.4)' : 'rgba(239, 68, 68, 0.4)';
            const badgeBg = isHealthy ? 'rgba(34, 197, 94, 0.15)' : isWarning ? 'rgba(245, 158, 11, 0.2)' : 'rgba(239, 68, 68, 0.2)';
            const badgeText = isHealthy ? '#4ade80' : isWarning ? '#fbbf24' : '#f87171';

            return (
              <div key={key} style={{
                background: 'var(--surface-color)',
                borderRadius: '12px',
                padding: '18px',
                border: `1px solid ${borderCol}`
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                  <div style={{ fontWeight: 700, fontSize: '1rem', textTransform: 'capitalize' }}>
                    {key.replace('_', ' ')}
                  </div>
                  <span style={{
                    padding: '3px 8px',
                    borderRadius: '12px',
                    fontSize: '0.75rem',
                    fontWeight: 700,
                    background: badgeBg,
                    color: badgeText
                  }}>
                    {sub.status}
                  </span>
                </div>

                <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '8px', minHeight: '38px' }}>
                  {sub.message || 'Operational and responsive'}
                </div>

                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.78rem', color: 'var(--text-secondary)', borderTop: '1px solid var(--border-color)', paddingTop: '8px' }}>
                  <span>Latency: <strong style={{ color: 'var(--text-color)' }}>{sub.latency_ms !== undefined ? `${sub.latency_ms}ms` : 'N/A'}</strong></span>
                  <span>{new Date(sub.checked_at).toLocaleTimeString()}</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* 24/7 Incident Ledger & Bug List */}
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
          <h2 style={{ fontSize: '1.3rem', fontWeight: 700, margin: 0 }}>
            📋 Live Incident Ledger & Bug Catalog
          </h2>
          <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
            Showing {data?.recent_incidents?.length ?? 0} most recent events
          </span>
        </div>

        <div className="table-container" style={{
          background: 'var(--surface-color)',
          borderRadius: '12px',
          border: '1px solid var(--border-color)',
          overflowX: 'auto',
          WebkitOverflowScrolling: 'touch'
        }}>
          {(!data?.recent_incidents || data.recent_incidents.length === 0) ? (
            <div style={{ padding: '40px', textAlign: 'center', color: '#4ade80' }}>
              🎉 Zero active bugs or subsystem failures detected! The system is operating at 100% capacity.
            </div>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.88rem', minWidth: '800px' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border-color)', textAlign: 'left', background: 'rgba(255,255,255,0.02)' }}>
                  <th style={{ padding: '12px 16px', fontWeight: 600 }}>Severity</th>
                  <th style={{ padding: '12px 16px', fontWeight: 600 }}>Subsystem</th>
                  <th style={{ padding: '12px 16px', fontWeight: 600 }}>Incident / Bug Title</th>
                  <th style={{ padding: '12px 16px', fontWeight: 600 }}>Occurrences</th>
                  <th style={{ padding: '12px 16px', fontWeight: 600 }}>Suggested Action</th>
                  <th style={{ padding: '12px 16px', fontWeight: 600 }}>Status</th>
                  <th style={{ padding: '12px 16px', fontWeight: 600, textAlign: 'right' }}>Action</th>
                </tr>
              </thead>
              <tbody>
                {data.recent_incidents.map((inc) => {
                  const isResolved = inc.status === 'RESOLVED';
                  const sevColor = inc.severity === 'CRITICAL' ? '#ef4444' : inc.severity === 'WARNING' ? '#f59e0b' : '#3b82f6';

                  return (
                    <tr key={inc.id} style={{ borderBottom: '1px solid var(--border-color)', opacity: isResolved ? 0.6 : 1 }}>
                      <td style={{ padding: '12px 16px' }}>
                        <span style={{
                          padding: '3px 8px',
                          borderRadius: '4px',
                          fontSize: '0.72rem',
                          fontWeight: 700,
                          background: `${sevColor}22`,
                          color: sevColor
                        }}>
                          {inc.severity}
                        </span>
                      </td>
                      <td style={{ padding: '12px 16px', fontWeight: 600 }}>
                        {inc.subsystem}
                      </td>
                      <td style={{ padding: '12px 16px' }}>
                        <div style={{ fontWeight: 600, color: 'var(--text-color)' }}>{inc.title}</div>
                        <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', marginTop: '2px', maxWidth: '300px' }}>
                          {inc.detail}
                        </div>
                      </td>
                      <td style={{ padding: '12px 16px' }}>
                        <span style={{
                          padding: '2px 8px',
                          borderRadius: '10px',
                          background: 'rgba(255,255,255,0.06)',
                          fontWeight: 700,
                          fontSize: '0.8rem'
                        }}>
                          x{inc.occurrence_count}
                        </span>
                      </td>
                      <td style={{ padding: '12px 16px', fontSize: '0.8rem', color: '#60a5fa' }}>
                        {inc.suggested_action}
                      </td>
                      <td style={{ padding: '12px 16px' }}>
                        <span style={{
                          padding: '3px 8px',
                          borderRadius: '12px',
                          fontSize: '0.75rem',
                          fontWeight: 700,
                          background: isResolved ? 'rgba(34,197,94,0.15)' : 'rgba(245,158,11,0.2)',
                          color: isResolved ? '#4ade80' : '#fbbf24'
                        }}>
                          {inc.status}
                        </span>
                      </td>
                      <td style={{ padding: '12px 16px', textAlign: 'right' }}>
                        {!isResolved && (
                          <button
                            onClick={() => handleResolve(inc.id)}
                            disabled={resolveLoading === inc.id}
                            style={{
                              padding: '5px 12px',
                              background: 'rgba(34, 197, 94, 0.2)',
                              border: '1px solid #22c55e',
                              borderRadius: '6px',
                              color: '#4ade80',
                              fontSize: '0.75rem',
                              fontWeight: 700,
                              cursor: 'pointer'
                            }}
                          >
                            ✓ Resolve
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>

    </div>
  );
}
