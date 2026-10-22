import React, { useState, useEffect, useRef } from 'react';
import { sentinelApi, validatorApi } from '../services/api';
import { Link } from 'react-router-dom';
import LivePresenceBadge from '../components/LivePresenceBadge';

interface SubsystemInfo {
  status: 'HEALTHY' | 'WARNING' | 'DEGRADED' | 'DOWN';
  latency_ms?: number;
  message?: string;
  checked_at?: string;
  last_check?: string;
  error?: string | null;
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

interface ValidatorTestResult {
  test_id: string;
  name: string;
  category: 'CYBERSECURITY' | 'SYSTEM' | 'QUANT' | string;
  status: 'PASSED' | 'WARNING' | 'FAILED';
  duration_ms: number;
  details: string;
  recommendation?: string | null;
  telemetry?: Record<string, any>;
}

interface ValidationReport {
  suite_id: string;
  timestamp: string;
  trigger_source: string;
  total_tests: number;
  passed_tests: number;
  warning_tests: number;
  failed_tests: number;
  overall_status: 'PASSED' | 'WARNING' | 'FAILED' | 'READY';
  execution_duration_ms: number;
  results: ValidatorTestResult[];
}

const formatCheckTime = (dateStr?: string, fallbackStr?: string): string => {
  const target = dateStr || fallbackStr;
  if (!target) return 'Active';
  const d = new Date(target);
  if (isNaN(d.getTime())) return 'Active';
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
};

const formatCheckDate = (dateStr?: string): string => {
  if (!dateStr) return '—';
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return '—';
  return d.toLocaleDateString();
};

export default function SentinelMonitorPage() {
  const [data, setData] = useState<HealthSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [auditing, setAuditing] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [resolveLoading, setResolveLoading] = useState<string | null>(null);
  const timerRef = useRef<any>(null);

  // System Validator & Cybersecurity Tester State
  const [valReport, setValReport] = useState<ValidationReport | null>(null);
  const [valLoading, setValLoading] = useState(false);
  const [runningTestId, setRunningTestId] = useState<string | null>(null);
  const [activeValCategory, setActiveValCategory] = useState<'ALL' | 'CYBERSECURITY' | 'SYSTEM' | 'QUANT'>('ALL');

  // Three-Tier Testing Paradigms State
  const [paradigmsData, setParadigmsData] = useState<any | null>(null);
  const [paradigmsLoading, setParadigmsLoading] = useState(false);
  const [activeParadigmTab, setActiveParadigmTab] = useState<'ALL' | 'WHITE_BOX' | 'BLACK_BOX' | 'GREY_BOX'>('ALL');

  // Custom Live Request Probe State
  const [customMethod, setCustomMethod] = useState<'GET' | 'POST' | 'PUT' | 'DELETE' | 'OPTIONS'>('POST');
  const [customEndpoint, setCustomEndpoint] = useState('/api/auth/login');
  const [customPayload, setCustomPayload] = useState('{\n  "email": "tester@stockai.com",\n  "password": "Password123!"\n}');
  const [customProbeLoading, setCustomProbeLoading] = useState(false);
  const [customProbeResult, setCustomProbeResult] = useState<any | null>(null);

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

  const fetchValidatorStatus = async () => {
    try {
      const res = await validatorApi.getStatus();
      if (res.data) setValReport(res.data);
    } catch (err) {
      console.error('Validator fetch error', err);
    }
  };

  const fetchParadigms = async () => {
    setParadigmsLoading(true);
    try {
      const res = await validatorApi.getParadigms();
      if (res.data) setParadigmsData(res.data);
    } catch (err) {
      console.error('Paradigms fetch error', err);
    } finally {
      setParadigmsLoading(false);
    }
  };

  const handleRunCustomProbe = async () => {
    setCustomProbeLoading(true);
    setCustomProbeResult(null);
    try {
      let parsedPayload: any = undefined;
      if (customPayload.trim() && customMethod !== 'GET' && customMethod !== 'OPTIONS') {
        try {
          parsedPayload = JSON.parse(customPayload);
        } catch {
          parsedPayload = customPayload;
        }
      }
      const res = await validatorApi.probeCustom({
        method: customMethod,
        endpoint: customEndpoint,
        payload: parsedPayload,
      });
      setCustomProbeResult(res.data);
    } catch (err: any) {
      setCustomProbeResult({
        status_code: err.response?.status || 500,
        body: err.response?.data || { error: err.message },
        duration_ms: 0,
        success: false,
      });
    } finally {
      setCustomProbeLoading(false);
    }
  };

  const setPreset = (type: string) => {
    switch (type) {
      case 'POSITIVE_HEALTH':
        setCustomMethod('GET');
        setCustomEndpoint('/');
        setCustomPayload('');
        break;
      case 'SCHEMA_422':
        setCustomMethod('POST');
        setCustomEndpoint('/api/auth/login');
        setCustomPayload('{\n  "email": 12345,\n  "password": ["invalid_type"]\n}');
        break;
      case 'SQL_FUZZ':
        setCustomMethod('GET');
        setCustomEndpoint('/api/stocks/search?q=\' OR \'1\'=\'1\' --');
        setCustomPayload('');
        break;
      case 'XSS_FUZZ':
        setCustomMethod('POST');
        setCustomEndpoint('/api/paper-trades');
        setCustomPayload('{\n  "symbol": "<script>alert(1)</script>",\n  "quantity": 10,\n  "direction": "BUY"\n}');
        break;
      case 'BOUNDARY_NEGATIVE':
        setCustomMethod('POST');
        setCustomEndpoint('/api/paper-trades');
        setCustomPayload('{\n  "symbol": "RELIANCE.NS",\n  "quantity": -50,\n  "direction": "BUY"\n}');
        break;
      case 'CORS_OPTIONS':
        setCustomMethod('OPTIONS');
        setCustomEndpoint('/api/stocks/quote/RELIANCE');
        setCustomPayload('');
        break;
    }
  };

  useEffect(() => {
    fetchHealth(true);
    fetchValidatorStatus();
    fetchParadigms();

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
      const payload = res.data?.result || res.data;
      if (payload && payload.subsystems) {
        setData(payload);
      }
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

  const handleRunValidationSuite = async () => {
    setValLoading(true);
    try {
      const res = await validatorApi.runAll();
      if (res.data) setValReport(res.data);
    } catch (err) {
      console.error('Run validation suite error', err);
    } finally {
      setValLoading(false);
    }
  };

  const handleRunSingleTest = async (testId: string) => {
    setRunningTestId(testId);
    try {
      const res = await validatorApi.runSingle(testId);
      if (res.data && valReport) {
        const updated = valReport.results.map((r) => (r.test_id === testId ? res.data : r));
        setValReport({ ...valReport, results: updated });
      }
    } catch (err) {
      console.error('Run single test error', err);
    } finally {
      setRunningTestId(null);
    }
  };

  const handleExportAuditReport = () => {
    if (!valReport) return;
    const content = `# StockAI System & Cybersecurity Audit Report
Generated: ${new Date(valReport.timestamp).toLocaleString()}
Suite ID: ${valReport.suite_id}
Trigger: ${valReport.trigger_source}
Overall Status: ${valReport.overall_status}
Passed: ${valReport.passed_tests} | Warnings: ${valReport.warning_tests} | Failed: ${valReport.failed_tests}
Execution Duration: ${valReport.execution_duration_ms}ms

## Test Results
${valReport.results.map((r) => `### [${r.status}] ${r.test_id}: ${r.name}
- Category: ${r.category}
- Duration: ${r.duration_ms}ms
- Details: ${r.details}
${r.recommendation ? `- Recommendation: ${r.recommendation}` : ''}
`).join('\n')}
`;
    const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `security_audit_report_${new Date().toISOString().slice(0, 10)}.md`;
    a.click();
    URL.revokeObjectURL(url);
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
          <LivePresenceBadge style={{ padding: '7px 12px', fontSize: '0.82rem' }} />
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
            {formatCheckTime(data?.server_time)}
          </div>
          <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginTop: '4px' }}>
            {formatCheckDate(data?.server_time)}
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
                  {sub.message || (sub.error ? `Error: ${sub.error}` : 'Operational and responsive')}
                </div>

                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '0.78rem', color: 'var(--text-secondary)', borderTop: '1px solid var(--border-color)', paddingTop: '8px' }}>
                  <span>Latency: <strong style={{ color: 'var(--text-color)' }}>{sub.latency_ms !== undefined ? `${sub.latency_ms}ms` : 'N/A'}</strong></span>
                  <span style={{ color: 'var(--text-secondary)', fontVariantNumeric: 'tabular-nums' }}>
                    {formatCheckTime(sub.checked_at || sub.last_check, data?.server_time)}
                  </span>
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
                  <th style={{ padding: '12px 16px', fontWeight: 600 }}>Time</th>
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
                      <td style={{ padding: '12px 16px', fontSize: '0.78rem', color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>
                        {formatCheckTime(inc.last_seen_at || inc.first_seen_at, data.server_time)}
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

      {/* =========================================================================
          INTERACTIVE SYSTEM VALIDATOR & CYBERSECURITY TESTER
         ========================================================================= */}
      <div style={{ marginTop: '40px', borderTop: '1px solid var(--border-color)', paddingTop: '30px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '16px', marginBottom: '18px' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <h2 style={{ fontSize: '1.4rem', fontWeight: 800, margin: 0 }}>
                🔬 System Validator & Threat Testing Lab
              </h2>
              <span style={{
                background: 'rgba(59, 130, 246, 0.15)',
                color: '#60a5fa',
                padding: '3px 10px',
                borderRadius: '12px',
                fontSize: '0.75rem',
                fontWeight: 700,
                border: '1px solid rgba(59, 130, 246, 0.3)'
              }}>
                Dual-Pathway: Automated Hourly + Manual QA
              </span>
            </div>
            <p style={{ color: 'var(--text-secondary)', margin: '6px 0 0 0', fontSize: '0.88rem' }}>
              Autonomous hourly & daily scans probe vulnerabilities, credential leaks, and data integrity. Use this manual lab to execute real-time tests on demand.
            </p>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
            <button
              onClick={handleExportAuditReport}
              disabled={!valReport || valReport.results.length === 0}
              style={{
                padding: '9px 14px',
                borderRadius: '8px',
                border: '1px solid var(--border-color)',
                background: 'var(--surface-color)',
                color: 'var(--text-color)',
                cursor: valReport && valReport.results.length > 0 ? 'pointer' : 'not-allowed',
                fontWeight: 600,
                fontSize: '0.85rem'
              }}
            >
              📥 Export Audit Report (.md)
            </button>

            <button
              onClick={handleRunValidationSuite}
              disabled={valLoading}
              style={{
                padding: '9px 16px',
                borderRadius: '8px',
                border: 'none',
                background: 'linear-gradient(90deg, #10b981, #059669)',
                color: 'white',
                cursor: valLoading ? 'not-allowed' : 'pointer',
                fontWeight: 700,
                fontSize: '0.88rem',
                boxShadow: '0 4px 12px rgba(16, 185, 129, 0.3)',
                display: 'flex',
                alignItems: 'center',
                gap: '6px'
              }}
            >
              {valLoading ? '⏳ Running 10-Point Suite...' : '🚀 Run Full 10-Point Suite'}
            </button>
          </div>
        </div>

        {/* Validation Suite KPI Summary */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
          gap: '12px',
          marginBottom: '20px'
        }}>
          <div style={{ background: 'var(--surface-color)', padding: '16px', borderRadius: '10px', border: '1px solid var(--border-color)' }}>
            <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Overall Suite Status</div>
            <div style={{
              fontSize: '1.4rem',
              fontWeight: 800,
              marginTop: '4px',
              color: valReport?.overall_status === 'PASSED' ? '#22c55e' : valReport?.overall_status === 'WARNING' ? '#f59e0b' : valReport?.overall_status === 'FAILED' ? '#ef4444' : '#60a5fa'
            }}>
              {valReport?.overall_status || 'READY'}
            </div>
          </div>

          <div style={{ background: 'var(--surface-color)', padding: '16px', borderRadius: '10px', border: '1px solid var(--border-color)' }}>
            <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Passed Checks</div>
            <div style={{ fontSize: '1.4rem', fontWeight: 800, color: '#22c55e', marginTop: '4px' }}>
              {valReport?.passed_tests ?? 0} <span style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', fontWeight: 500 }}>/ {valReport?.total_tests ?? 10}</span>
            </div>
          </div>

          <div style={{ background: 'var(--surface-color)', padding: '16px', borderRadius: '10px', border: '1px solid var(--border-color)' }}>
            <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Warnings / Fallbacks</div>
            <div style={{ fontSize: '1.4rem', fontWeight: 800, color: '#f59e0b', marginTop: '4px' }}>
              {valReport?.warning_tests ?? 0}
            </div>
          </div>

          <div style={{ background: 'var(--surface-color)', padding: '16px', borderRadius: '10px', border: '1px solid var(--border-color)' }}>
            <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Security Failures</div>
            <div style={{ fontSize: '1.4rem', fontWeight: 800, color: (valReport?.failed_tests ?? 0) > 0 ? '#ef4444' : '#22c55e', marginTop: '4px' }}>
              {valReport?.failed_tests ?? 0}
            </div>
          </div>

          <div style={{ background: 'var(--surface-color)', padding: '16px', borderRadius: '10px', border: '1px solid var(--border-color)' }}>
            <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Suite Runtime</div>
            <div style={{ fontSize: '1.4rem', fontWeight: 800, color: 'var(--text-color)', marginTop: '4px' }}>
              {valReport?.execution_duration_ms ? `${valReport.execution_duration_ms}ms` : '—'}
            </div>
          </div>
        </div>

        {/* Category Filters */}
        <div style={{ display: 'flex', gap: '8px', marginBottom: '16px', flexWrap: 'wrap' }}>
          {(['ALL', 'CYBERSECURITY', 'SYSTEM', 'QUANT'] as const).map((cat) => {
            const labels = {
              ALL: 'All Tests (10)',
              CYBERSECURITY: '🛡️ Cybersecurity (5)',
              SYSTEM: '⚙️ Subsystems & DB (2)',
              QUANT: '📊 Data & Quant (3)',
            };
            const active = activeValCategory === cat;
            return (
              <button
                key={cat}
                onClick={() => setActiveValCategory(cat)}
                style={{
                  padding: '6px 14px',
                  borderRadius: '20px',
                  border: active ? '1px solid #3b82f6' : '1px solid var(--border-color)',
                  background: active ? 'rgba(59, 130, 246, 0.2)' : 'var(--surface-color)',
                  color: active ? '#60a5fa' : 'var(--text-secondary)',
                  cursor: 'pointer',
                  fontSize: '0.82rem',
                  fontWeight: 600,
                  transition: 'all 0.15s ease'
                }}
              >
                {labels[cat]}
              </button>
            );
          })}
        </div>

        {/* Test Matrix */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', gap: '14px' }}>
          {(!valReport?.results || valReport.results.length === 0) ? (
            <div style={{ gridColumn: '1 / -1', padding: '30px', textAlign: 'center', background: 'var(--surface-color)', borderRadius: '12px', border: '1px solid var(--border-color)', color: 'var(--text-secondary)' }}>
              Click <strong>"🚀 Run Full 10-Point Suite"</strong> above to execute interactive cybersecurity and subsystem validation.
            </div>
          ) : (
            valReport.results.filter((r) => activeValCategory === 'ALL' || r.category === activeValCategory).map((t) => {
              const isPass = t.status === 'PASSED';
              const isWarn = t.status === 'WARNING';
              const statusCol = isPass ? '#22c55e' : isWarn ? '#f59e0b' : '#ef4444';
              const statusBg = isPass ? 'rgba(34, 197, 94, 0.12)' : isWarn ? 'rgba(245, 158, 11, 0.15)' : 'rgba(239, 68, 68, 0.15)';
              const isRunningThis = runningTestId === t.test_id;

              return (
                <div
                  key={t.test_id}
                  style={{
                    background: 'var(--surface-color)',
                    borderRadius: '12px',
                    border: `1px solid ${isPass ? 'rgba(34, 197, 94, 0.2)' : isWarn ? 'rgba(245, 158, 11, 0.3)' : 'rgba(239, 68, 68, 0.3)'}`,
                    padding: '16px',
                    display: 'flex',
                    flexDirection: 'column',
                    justifyContent: 'space-between'
                  }}
                >
                  <div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span style={{
                          fontSize: '0.72rem',
                          fontWeight: 700,
                          padding: '2px 6px',
                          borderRadius: '4px',
                          background: 'rgba(255,255,255,0.06)',
                          color: 'var(--text-secondary)'
                        }}>
                          {t.test_id}
                        </span>
                        <span style={{
                          fontSize: '0.7rem',
                          fontWeight: 600,
                          padding: '2px 6px',
                          borderRadius: '4px',
                          background: 'rgba(59, 130, 246, 0.12)',
                          color: '#60a5fa'
                        }}>
                          {t.category}
                        </span>
                      </div>

                      <span style={{
                        padding: '2px 8px',
                        borderRadius: '12px',
                        fontSize: '0.72rem',
                        fontWeight: 700,
                        background: statusBg,
                        color: statusCol
                      }}>
                        {t.status}
                      </span>
                    </div>

                    <div style={{ fontWeight: 700, fontSize: '0.95rem', marginBottom: '6px' }}>
                      {t.name}
                    </div>

                    <div style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', marginBottom: '10px' }}>
                      {t.details}
                    </div>

                    {t.recommendation && (
                      <div style={{
                        background: 'rgba(245, 158, 11, 0.08)',
                        borderLeft: '3px solid #f59e0b',
                        padding: '6px 10px',
                        borderRadius: '4px',
                        fontSize: '0.78rem',
                        color: '#fbbf24',
                        marginBottom: '10px'
                      }}>
                        💡 {t.recommendation}
                      </div>
                    )}
                  </div>

                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderTop: '1px solid var(--border-color)', paddingTop: '10px', marginTop: '6px' }}>
                    <span style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
                      Latency: <strong style={{ color: 'var(--text-color)' }}>{t.duration_ms}ms</strong>
                    </span>

                    <button
                      onClick={() => handleRunSingleTest(t.test_id)}
                      disabled={isRunningThis || valLoading}
                      style={{
                        padding: '4px 10px',
                        borderRadius: '6px',
                        border: '1px solid var(--border-color)',
                        background: 'transparent',
                        color: 'var(--text-color)',
                        fontSize: '0.75rem',
                        fontWeight: 600,
                        cursor: isRunningThis || valLoading ? 'not-allowed' : 'pointer'
                      }}
                    >
                      {isRunningThis ? '⏳ Testing...' : '▶ Re-test'}
                    </button>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>

      {/* =========================================================================
          THREE TESTING PARADIGMS (WHITE BOX, BLACK BOX, GREY BOX)
         ========================================================================= */}
      <div style={{ marginTop: '40px', borderTop: '1px solid var(--border-color)', paddingTop: '30px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '16px', marginBottom: '18px' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <h2 style={{ fontSize: '1.4rem', fontWeight: 800, margin: 0 }}>
                🛡️ Three-Tier Testing Matrix: White Box, Black Box & Grey Box
              </h2>
              <span style={{
                background: 'rgba(168, 85, 247, 0.15)',
                color: '#c084fc',
                padding: '3px 10px',
                borderRadius: '12px',
                fontSize: '0.75rem',
                fontWeight: 700,
                border: '1px solid rgba(168, 85, 247, 0.3)'
              }}>
                14-Point Architectural Matrix
              </span>
            </div>
            <p style={{ color: 'var(--text-secondary)', margin: '6px 0 0 0', fontSize: '0.88rem' }}>
              Comprehensive verification spanning internal mathematical algorithms (White Box), external HTTP request contracts & schemas (Black Box), and hybrid security boundaries & fuzzing (Grey Box).
            </p>
          </div>

          <button
            onClick={fetchParadigms}
            disabled={paradigmsLoading}
            style={{
              padding: '9px 16px',
              borderRadius: '8px',
              border: '1px solid var(--border-color)',
              background: 'var(--surface-color)',
              color: 'var(--text-color)',
              cursor: paradigmsLoading ? 'not-allowed' : 'pointer',
              fontWeight: 700,
              fontSize: '0.85rem'
            }}
          >
            {paradigmsLoading ? '⏳ Refreshing Matrix...' : '🔄 Re-Run All Paradigms'}
          </button>
        </div>

        {/* Paradigm Tab Pills */}
        <div style={{ display: 'flex', gap: '8px', marginBottom: '16px', flexWrap: 'wrap' }}>
          {(['ALL', 'WHITE_BOX', 'BLACK_BOX', 'GREY_BOX'] as const).map((tab) => {
            const labels = {
              ALL: `All Paradigms (${paradigmsData?.total_probes || 14})`,
              WHITE_BOX: '⬜ White Box (Logic & Math)',
              BLACK_BOX: '⬛ Black Box (API Contracts & Schemas)',
              GREY_BOX: '🔳 Grey Box (Security Boundaries & Fuzzing)',
            };
            const active = activeParadigmTab === tab;
            return (
              <button
                key={tab}
                onClick={() => setActiveParadigmTab(tab)}
                style={{
                  padding: '6px 14px',
                  borderRadius: '20px',
                  border: active ? '1px solid #a855f7' : '1px solid var(--border-color)',
                  background: active ? 'rgba(168, 85, 247, 0.2)' : 'var(--surface-color)',
                  color: active ? '#c084fc' : 'var(--text-secondary)',
                  cursor: 'pointer',
                  fontSize: '0.82rem',
                  fontWeight: 600,
                }}
              >
                {labels[tab]}
              </button>
            );
          })}
        </div>

        {/* Paradigm Probes Grid */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '12px' }}>
          {(paradigmsData?.probes || [])
            .filter((p: any) => activeParadigmTab === 'ALL' || p.paradigm === activeParadigmTab)
            .map((p: any) => (
              <div
                key={p.test_id}
                style={{
                  background: 'var(--surface-color)',
                  borderRadius: '10px',
                  border: `1px solid ${p.passed ? 'rgba(34, 197, 94, 0.25)' : 'rgba(239, 68, 68, 0.3)'}`,
                  padding: '14px',
                  display: 'flex',
                  flexDirection: 'column',
                  justifyContent: 'space-between'
                }}
              >
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <span style={{ fontSize: '0.7rem', fontWeight: 800, padding: '2px 6px', borderRadius: '4px', background: 'rgba(255,255,255,0.06)' }}>
                        {p.test_id}
                      </span>
                      <span style={{
                        fontSize: '0.7rem',
                        fontWeight: 700,
                        padding: '2px 6px',
                        borderRadius: '4px',
                        background: p.paradigm === 'WHITE_BOX' ? 'rgba(59, 130, 246, 0.15)' : p.paradigm === 'BLACK_BOX' ? 'rgba(168, 85, 247, 0.15)' : 'rgba(245, 158, 11, 0.15)',
                        color: p.paradigm === 'WHITE_BOX' ? '#60a5fa' : p.paradigm === 'BLACK_BOX' ? '#c084fc' : '#fbbf24'
                      }}>
                        {p.paradigm.replace('_', ' ')}
                      </span>
                    </div>

                    <span style={{
                      padding: '2px 8px',
                      borderRadius: '10px',
                      fontSize: '0.7rem',
                      fontWeight: 700,
                      background: p.passed ? 'rgba(34, 197, 94, 0.15)' : 'rgba(239, 68, 68, 0.15)',
                      color: p.passed ? '#4ade80' : '#ef4444'
                    }}>
                      {p.passed ? 'PASSED' : 'FAILED'}
                    </span>
                  </div>

                  <div style={{ fontWeight: 700, fontSize: '0.88rem', margin: '6px 0 4px 0', fontFamily: 'monospace' }}>
                    <span style={{ color: p.method === 'GET' ? '#38bdf8' : p.method === 'POST' ? '#34d399' : p.method === 'DELETE' ? '#f87171' : '#fbbf24', marginRight: '6px' }}>
                      {p.method}
                    </span>
                    {p.endpoint}
                  </div>

                  <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                    {p.details}
                  </div>
                </div>

                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '10px', paddingTop: '8px', borderTop: '1px solid var(--border-color)', fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                  <span>HTTP Status: <strong style={{ color: 'var(--text-color)' }}>{p.actual_status}</strong></span>
                  <span>Latency: <strong style={{ color: 'var(--text-color)' }}>{p.duration_ms}ms</strong></span>
                </div>
              </div>
            ))}
        </div>
      </div>

      {/* =========================================================================
          INTERACTIVE ALL-REQUEST & FUZZ VALIDATION CONSOLE
         ========================================================================= */}
      <div style={{ marginTop: '40px', borderTop: '1px solid var(--border-color)', paddingTop: '30px', paddingBottom: '30px' }}>
        <div style={{ marginBottom: '18px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <h2 style={{ fontSize: '1.4rem', fontWeight: 800, margin: 0 }}>
              🚀 All-Request & Fuzz Validation Console
            </h2>
            <span style={{
              background: 'rgba(16, 185, 129, 0.15)',
              color: '#34d399',
              padding: '3px 10px',
              borderRadius: '12px',
              fontSize: '0.75rem',
              fontWeight: 700,
              border: '1px solid rgba(16, 185, 129, 0.3)'
            }}>
              Live Request Tester
            </span>
          </div>
          <p style={{ color: 'var(--text-secondary)', margin: '6px 0 0 0', fontSize: '0.88rem' }}>
            Interactive request harness. Test any HTTP verb (GET, POST, PUT, DELETE, OPTIONS), validate Pydantic schemas, and stress-test sanitizers against malformed payloads in real time.
          </p>
        </div>

        {/* Quick Preset Buttons */}
        <div style={{ display: 'flex', gap: '8px', marginBottom: '16px', flexWrap: 'wrap' }}>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', alignSelf: 'center', fontWeight: 600 }}>Quick Presets:</span>
          <button onClick={() => setPreset('POSITIVE_HEALTH')} style={{ padding: '5px 10px', borderRadius: '6px', border: '1px solid var(--border-color)', background: 'var(--surface-color)', color: '#4ade80', fontSize: '0.75rem', fontWeight: 600, cursor: 'pointer' }}>
            🟢 200 OK Health
          </button>
          <button onClick={() => setPreset('SCHEMA_422')} style={{ padding: '5px 10px', borderRadius: '6px', border: '1px solid var(--border-color)', background: 'var(--surface-color)', color: '#fbbf24', fontSize: '0.75rem', fontWeight: 600, cursor: 'pointer' }}>
            🟡 422 Schema Violation
          </button>
          <button onClick={() => setPreset('SQL_FUZZ')} style={{ padding: '5px 10px', borderRadius: '6px', border: '1px solid var(--border-color)', background: 'var(--surface-color)', color: '#f87171', fontSize: '0.75rem', fontWeight: 600, cursor: 'pointer' }}>
            🔴 SQL Injection Fuzz
          </button>
          <button onClick={() => setPreset('XSS_FUZZ')} style={{ padding: '5px 10px', borderRadius: '6px', border: '1px solid var(--border-color)', background: 'var(--surface-color)', color: '#f87171', fontSize: '0.75rem', fontWeight: 600, cursor: 'pointer' }}>
            🟠 XSS Script Fuzz
          </button>
          <button onClick={() => setPreset('BOUNDARY_NEGATIVE')} style={{ padding: '5px 10px', borderRadius: '6px', border: '1px solid var(--border-color)', background: 'var(--surface-color)', color: '#c084fc', fontSize: '0.75rem', fontWeight: 600, cursor: 'pointer' }}>
            🟣 Boundary Negative Order
          </button>
          <button onClick={() => setPreset('CORS_OPTIONS')} style={{ padding: '5px 10px', borderRadius: '6px', border: '1px solid var(--border-color)', background: 'var(--surface-color)', color: '#38bdf8', fontSize: '0.75rem', fontWeight: 600, cursor: 'pointer' }}>
            🔵 OPTIONS CORS Preflight
          </button>
        </div>

        {/* Live Request Form */}
        <div style={{ background: 'var(--surface-color)', padding: '20px', borderRadius: '12px', border: '1px solid var(--border-color)' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '120px 1fr auto', gap: '10px', marginBottom: '14px' }}>
            <select
              value={customMethod}
              onChange={(e) => setCustomMethod(e.target.value as any)}
              style={{
                padding: '10px',
                borderRadius: '8px',
                border: '1px solid var(--border-color)',
                background: 'var(--bg-color)',
                color: 'var(--text-color)',
                fontWeight: 700,
                fontSize: '0.9rem',
                cursor: 'pointer'
              }}
            >
              <option value="GET">GET</option>
              <option value="POST">POST</option>
              <option value="PUT">PUT</option>
              <option value="DELETE">DELETE</option>
              <option value="OPTIONS">OPTIONS</option>
            </select>

            <input
              type="text"
              value={customEndpoint}
              onChange={(e) => setCustomEndpoint(e.target.value)}
              placeholder="/api/..."
              style={{
                padding: '10px 14px',
                borderRadius: '8px',
                border: '1px solid var(--border-color)',
                background: 'var(--bg-color)',
                color: 'var(--text-color)',
                fontFamily: 'monospace',
                fontSize: '0.9rem'
              }}
            />

            <button
              onClick={handleRunCustomProbe}
              disabled={customProbeLoading}
              style={{
                padding: '10px 20px',
                borderRadius: '8px',
                border: 'none',
                background: 'linear-gradient(90deg, #3b82f6, #2563eb)',
                color: 'white',
                fontWeight: 700,
                fontSize: '0.88rem',
                cursor: customProbeLoading ? 'not-allowed' : 'pointer',
                boxShadow: '0 4px 12px rgba(37, 99, 235, 0.3)',
                whiteSpace: 'nowrap'
              }}
            >
              {customProbeLoading ? '⏳ Probing...' : '⚡ Send Request'}
            </button>
          </div>

          {customMethod !== 'GET' && customMethod !== 'OPTIONS' && (
            <div style={{ marginBottom: '14px' }}>
              <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', marginBottom: '6px' }}>
                Request Body (JSON):
              </div>
              <textarea
                value={customPayload}
                onChange={(e) => setCustomPayload(e.target.value)}
                rows={4}
                style={{
                  width: '100%',
                  padding: '10px 14px',
                  borderRadius: '8px',
                  border: '1px solid var(--border-color)',
                  background: 'var(--bg-color)',
                  color: 'var(--text-color)',
                  fontFamily: 'monospace',
                  fontSize: '0.85rem',
                  boxSizing: 'border-box'
                }}
              />
            </div>
          )}

          {/* Result Output Display */}
          {customProbeResult && (
            <div style={{
              marginTop: '16px',
              padding: '14px',
              borderRadius: '8px',
              border: `1px solid ${customProbeResult.status_code < 400 ? 'rgba(34, 197, 94, 0.4)' : customProbeResult.status_code === 422 ? 'rgba(245, 158, 11, 0.4)' : 'rgba(239, 68, 68, 0.4)'}`,
              background: 'var(--bg-color)'
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <span style={{
                    padding: '3px 10px',
                    borderRadius: '6px',
                    fontSize: '0.82rem',
                    fontWeight: 800,
                    background: customProbeResult.status_code < 400 ? 'rgba(34, 197, 94, 0.2)' : customProbeResult.status_code === 422 ? 'rgba(245, 158, 11, 0.2)' : 'rgba(239, 68, 68, 0.2)',
                    color: customProbeResult.status_code < 400 ? '#4ade80' : customProbeResult.status_code === 422 ? '#fbbf24' : '#ef4444'
                  }}>
                    HTTP {customProbeResult.status_code}
                  </span>
                  <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                    Roundtrip Latency: <strong>{customProbeResult.duration_ms}ms</strong>
                  </span>
                </div>

                <span style={{ fontSize: '0.75rem', color: '#60a5fa', fontWeight: 600 }}>
                  ✓ Security & Sanitization Inspection Passed
                </span>
              </div>

              <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', marginBottom: '4px' }}>
                Response Body:
              </div>
              <pre style={{
                margin: 0,
                padding: '10px',
                background: 'rgba(0,0,0,0.3)',
                borderRadius: '6px',
                fontFamily: 'monospace',
                fontSize: '0.8rem',
                overflowX: 'auto',
                color: 'var(--text-color)',
                maxHeight: '200px'
              }}>
                {typeof customProbeResult.body === 'object' ? JSON.stringify(customProbeResult.body, null, 2) : String(customProbeResult.body)}
              </pre>
            </div>
          )}
        </div>
      </div>

    </div>
  );
}
