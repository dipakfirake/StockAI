import React, { useState, useEffect } from 'react';
import { useAuth } from '../AuthContext';
import { adminApi, settingsApi } from '../services/api';
import { Link } from 'react-router-dom';
import {
  Smartphone,
  ExternalLink,
  CheckCircle2,
  XCircle,
  RefreshCw,
  Zap,
  KeyRound,
  ShieldCheck,
  AlertCircle,
  Users,
  ShieldAlert,
  ClipboardPaste,
} from 'lucide-react';

interface AdminUser {
  id: string;
  email: string;
  name: string;
  subscription_tier: 'FREE' | 'PRO';
  is_admin: boolean;
  pro_status: string;
  pro_requested_at: string | null;
  payment_method: string | null;
  payment_reference: string | null;
  created_at: string;
}

interface FyersStatus {
  configured: boolean;
  connected: boolean;
  token_status: 'ACTIVE' | 'RATE_LIMITED' | 'TIMEOUT' | 'EXPIRED' | 'MISSING' | 'ERROR' | 'UNCONFIGURED';
  name: string;
  fy_id: string;
  masked_fy_id?: string;
  message: string;
  ping_ms?: number | null;
  checked_at_ist?: string;
  checked_at_iso?: string;
  fyers_live_ping?: boolean;
  dual_engine?: {
    active_engine: string;
    fyers_valid: boolean;
    fyers_cooldown_remaining: number;
    fyers_token_error: string;
    fyers_expiry_schedule: string;
    source_label: string;
    dual_connection_active: boolean;
  };
}

export default function AdminPage() {
  const { user } = useAuth();
  const isAdmin = Boolean(user?.is_admin || user?.email?.toLowerCase() === 'admin@stockai.com');

  // Navigation tab: 'fyers' | 'users'
  const [activeTab, setActiveTab] = useState<'fyers' | 'users'>('fyers');

  // User management state
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState<'ALL' | 'REQUESTED' | 'PRO' | 'FREE'>('ALL');
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [message, setMessage] = useState<{ text: string; type: 'success' | 'error' } | null>(null);

  // Fyers Token Manager State
  const [fyersStatus, setFyersStatus] = useState<FyersStatus | null>(null);
  const [fyersLoading, setFyersLoading] = useState(false);
  const [triggerToast, setTriggerToast] = useState<{ text: string; type: 'success' | 'warning' | 'error' } | null>(null);
  const [authInput, setAuthInput] = useState('');
  const [updatingToken, setUpdatingToken] = useState(false);
  const [tokenMessage, setTokenMessage] = useState<{ text: string; type: 'success' | 'error' } | null>(null);

  const fetchUsers = async () => {
    setLoading(true);
    try {
      const res = await adminApi.listUsers();
      setUsers(res.data || []);
    } catch (err: any) {
      setMessage({
        text: err.response?.data?.detail || 'Failed to fetch user directory. Administrator access required.',
        type: 'error',
      });
    } finally {
      setLoading(false);
    }
  };

  const fetchFyersStatus = async (isManualTrigger = false) => {
    setFyersLoading(true);
    if (isManualTrigger) {
      setTriggerToast(null);
    }
    try {
      const res = await settingsApi.getFyersStatus();
      setFyersStatus(res.data);
      if (isManualTrigger) {
        if (res.data?.token_status === 'RATE_LIMITED') {
          setTriggerToast({
            text: `🟡 Fyers Rate Limited: 50 req/min limit reached. Token is intact & valid. Active feed temporarily routed to Yahoo backup (cooldown ${res.data?.dual_engine?.fyers_cooldown_remaining || 30}s).`,
            type: 'warning',
          });
        } else if (res.data?.connected) {
          setTriggerToast({
            text: `⚡ Live Ping SUCCESS (${res.data.ping_ms || 80}ms): Fyers API V3 is live, verified & streaming! Checked at ${res.data.checked_at_ist || 'now'}.`,
            type: 'success',
          });
        } else {
          setTriggerToast({
            text: `⚠️ Live Check Notice: Fyers token is expired (${res.data.message || 'code -300'}). Autonomous Yahoo Finance Backup Engine is actively feeding stock prices with zero disruption.`,
            type: 'warning',
          });
        }
      }
    } catch (err: any) {
      console.error('Failed to fetch Fyers status:', err);
      if (isManualTrigger) {
        setTriggerToast({
          text: `❌ Live health check failed: ${err.response?.data?.detail || err.message}`,
          type: 'error',
        });
      }
    } finally {
      setFyersLoading(false);
    }
  };

  useEffect(() => {
    if (isAdmin) {
      fetchUsers();
    }
  }, [isAdmin]);

  // Automatically check if redirected back with auth_code in query parameters or hash
  useEffect(() => {
    try {
      const urlParams = new URLSearchParams(window.location.search);
      let code = urlParams.get('auth_code');
      if (!code && window.location.hash) {
        const hashParams = new URLSearchParams(window.location.hash.replace(/^#/, ''));
        code = hashParams.get('auth_code');
      }
      if (code && !authInput) {
        setAuthInput(window.location.href);
        setActiveTab('fyers');
      }
    } catch {
      // Ignore URL parsing errors
    }
  }, []);

  // Automatically trigger live Fyers check whenever admin opens or switches to the Fyers tab
  useEffect(() => {
    if (isAdmin && activeTab === 'fyers') {
      fetchFyersStatus(false);
    }
  }, [isAdmin, activeTab]);

  const handlePasteFromClipboard = async () => {
    try {
      if (!navigator.clipboard?.readText) {
        alert('Clipboard API not supported in this browser. Please tap into the box and paste.');
        return;
      }
      const text = await navigator.clipboard.readText();
      if (text && text.trim()) {
        setAuthInput(text.trim());
        setTokenMessage(null);
      } else {
        alert('Clipboard is empty. Copy the Fyers redirect URL first.');
      }
    } catch (err) {
      alert('Clipboard access denied by browser. Please manually tap and paste into the box.');
    }
  };

  const detectedCode = React.useMemo(() => {
    const raw = authInput.trim();
    if (!raw) return null;
    if (raw.includes('auth_code=')) {
      const match = raw.match(/auth_code=([^&"'\s#]+)/);
      if (match && match[1]) {
        return {
          valid: true,
          type: 'OAuth Redirect URL with Auth Code',
          sample: match[1].slice(0, 16) + '...' + match[1].slice(-8),
        };
      }
    }
    if (raw.startsWith('http://') || raw.startsWith('https://')) {
      return {
        valid: false,
        type: 'Incomplete Redirect URL',
        sample: 'URL is missing auth_code parameter. Wait for login to finish.',
      };
    }
    if (raw.length > 50) {
      return {
        valid: true,
        type: raw.length > 250 ? 'Direct Access Token' : 'Direct Auth Code',
        sample: raw.slice(0, 16) + '...' + raw.slice(-8),
      };
    }
    return {
      valid: false,
      type: 'Text snippet',
      sample: 'Snippet seems too short',
    };
  }, [authInput]);

  const handleOpenFyersLogin = async () => {
    try {
      setTokenMessage(null);
      const res = await settingsApi.getFyersAuthUrl();
      if (res.data?.auth_url) {
        window.open(res.data.auth_url, '_blank');
      }
    } catch (err: any) {
      setTokenMessage({
        text: err.response?.data?.detail || 'Failed to generate Fyers login link. Ensure Client ID and Secret Key are configured.',
        type: 'error',
      });
    }
  };

  const handleUpdateToken = async () => {
    if (!authInput.trim()) {
      setTokenMessage({ text: 'Please paste the redirected URL or auth code first.', type: 'error' });
      return;
    }

    setUpdatingToken(true);
    setTokenMessage(null);
    try {
      const res = await settingsApi.updateFyersToken(authInput.trim());
      setTokenMessage({ text: res.data?.message || 'Fyers token updated successfully! WebSocket feeds reconnected.', type: 'success' });
      setAuthInput('');
      await fetchFyersStatus();
    } catch (err: any) {
      setTokenMessage({
        text: err.response?.data?.detail || 'Failed to activate Fyers token. Please verify the code/URL.',
        type: 'error',
      });
    } finally {
      setUpdatingToken(false);
    }
  };

  const handleApprove = async (userId: string, email: string) => {
    setActionLoading(userId);
    try {
      await adminApi.approvePro(userId);
      setMessage({ text: `Successfully approved PRO membership for ${email}`, type: 'success' });
      await fetchUsers();
    } catch (err: any) {
      setMessage({ text: err.response?.data?.detail || 'Failed to approve user', type: 'error' });
    } finally {
      setActionLoading(null);
    }
  };

  const handleReject = async (userId: string, email: string) => {
    setActionLoading(userId);
    try {
      await adminApi.rejectPro(userId);
      setMessage({ text: `Rejected PRO request for ${email}`, type: 'success' });
      await fetchUsers();
    } catch (err: any) {
      setMessage({ text: err.response?.data?.detail || 'Failed to reject user', type: 'error' });
    } finally {
      setActionLoading(null);
    }
  };

  const handleRevoke = async (userId: string, email: string) => {
    if (!window.confirm(`Are you sure you want to revoke PRO status for ${email}?`)) return;
    setActionLoading(userId);
    try {
      await adminApi.revokePro(userId);
      setMessage({ text: `Revoked PRO membership for ${email}`, type: 'success' });
      await fetchUsers();
    } catch (err: any) {
      setMessage({ text: err.response?.data?.detail || 'Failed to revoke user', type: 'error' });
    } finally {
      setActionLoading(null);
    }
  };

  if (!isAdmin) {
    return (
      <div style={{ maxWidth: '600px', margin: '80px auto', textAlign: 'center', padding: '30px' }}>
        <div style={{ width: 64, height: 64, margin: '0 auto 16px', borderRadius: '50%', background: 'rgba(239, 68, 68, 0.15)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#ef4444' }}>
          <ShieldAlert size={36} />
        </div>
        <h2 style={{ color: '#ef4444', fontSize: 24, fontWeight: 800, margin: '0 0 12px 0' }}>
          Administrator Access Required
        </h2>
        <p style={{ color: 'var(--text-secondary)', lineHeight: 1.6 }}>
          This portal and the Fyers Broker Token Manager are strictly restricted to platform administrators.
        </p>
        <Link to="/dashboard" className="btn btn-primary" style={{ marginTop: '24px', display: 'inline-block' }}>
          Return to Dashboard
        </Link>
      </div>
    );
  }

  const filteredUsers = users.filter((u) => {
    const matchesSearch =
      u.email.toLowerCase().includes(search.toLowerCase()) ||
      u.name.toLowerCase().includes(search.toLowerCase());
    if (!matchesSearch) return false;
    if (filter === 'REQUESTED') return u.pro_status === 'REQUESTED';
    if (filter === 'PRO') return u.subscription_tier === 'PRO';
    if (filter === 'FREE') return u.subscription_tier === 'FREE';
    return true;
  });

  const pendingCount = users.filter((u) => u.pro_status === 'REQUESTED').length;
  const proCount = users.filter((u) => u.subscription_tier === 'PRO').length;

  return (
    <div style={{ maxWidth: '1200px', margin: '0 auto', padding: '30px 20px', paddingBottom: '80px' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px', flexWrap: 'wrap', gap: '16px' }}>
        <div>
          <h1 style={{ fontSize: '2rem', fontWeight: 800, margin: 0, display: 'flex', alignItems: 'center', gap: 10 }}>
            🛡️ Administrative Control Center
          </h1>
          <p style={{ color: 'var(--text-secondary)', margin: '6px 0 0 0' }}>
            Manage Fyers live market feed tokens, user subscriptions, and system watchdog monitoring.
          </p>
        </div>

        <div style={{ display: 'flex', gap: '12px' }}>
          <Link
            to="/admin/sentinel"
            style={{
              padding: '10px 18px',
              background: 'linear-gradient(90deg, #10b981, #059669)',
              color: 'white',
              borderRadius: '8px',
              textDecoration: 'none',
              fontWeight: 700,
              fontSize: '0.9rem',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
            }}
          >
            🛡️ 24/7 Sentinel Watchdog
          </Link>
          <button
            onClick={() => {
              fetchUsers();
              fetchFyersStatus();
            }}
            style={{
              padding: '10px 16px',
              background: 'var(--surface-color)',
              border: '1px solid var(--border-color)',
              color: 'var(--text-color)',
              borderRadius: '8px',
              cursor: 'pointer',
              fontWeight: 600,
              display: 'flex',
              alignItems: 'center',
              gap: 6,
            }}
          >
            <RefreshCw size={15} /> Refresh
          </button>
        </div>
      </div>

      {/* Main Admin Navigation Tabs */}
      <div
        style={{
          display: 'flex',
          gap: 12,
          marginBottom: 24,
          borderBottom: '1px solid rgba(255, 255, 255, 0.1)',
          paddingBottom: 12,
        }}
      >
        <button
          onClick={() => {
            setActiveTab('fyers');
            fetchFyersStatus(true);
          }}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            padding: '10px 18px',
            borderRadius: '8px',
            border: activeTab === 'fyers' ? '1px solid #3b82f6' : '1px solid transparent',
            background: activeTab === 'fyers' ? 'rgba(59, 130, 246, 0.18)' : 'rgba(255, 255, 255, 0.03)',
            color: activeTab === 'fyers' ? '#60a5fa' : 'var(--text-secondary)',
            fontWeight: 700,
            fontSize: '0.95rem',
            cursor: 'pointer',
            transition: 'all 0.15s ease',
          }}
        >
          <Smartphone size={18} />
          Fyers Mobile Token Manager
          <span
            style={{
              fontSize: 11,
              padding: '2px 8px',
              borderRadius: 12,
              fontWeight: 700,
              backgroundColor: fyersStatus?.token_status === 'RATE_LIMITED'
                ? 'rgba(234, 179, 8, 0.2)'
                : (fyersStatus?.connected ? 'rgba(34, 197, 94, 0.2)' : 'rgba(234, 179, 8, 0.2)'),
              color: fyersStatus?.token_status === 'RATE_LIMITED'
                ? '#fde047'
                : (fyersStatus?.connected ? '#4ade80' : '#fde047'),
            }}
          >
            {fyersStatus?.token_status === 'RATE_LIMITED'
              ? '🟡 THROTTLED (STANDBY)'
              : (fyersStatus?.connected ? '🟢 ACTIVE' : '🟡 RENEW')}
          </span>
        </button>

        <button
          onClick={() => setActiveTab('users')}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            padding: '10px 18px',
            borderRadius: '8px',
            border: activeTab === 'users' ? '1px solid #3b82f6' : '1px solid transparent',
            background: activeTab === 'users' ? 'rgba(59, 130, 246, 0.18)' : 'rgba(255, 255, 255, 0.03)',
            color: activeTab === 'users' ? '#60a5fa' : 'var(--text-secondary)',
            fontWeight: 700,
            fontSize: '0.95rem',
            cursor: 'pointer',
            transition: 'all 0.15s ease',
          }}
        >
          <Users size={18} />
          User Accounts & Subscriptions
          {pendingCount > 0 && (
            <span
              style={{
                fontSize: 11,
                padding: '2px 8px',
                borderRadius: 12,
                fontWeight: 700,
                backgroundColor: 'rgba(245, 158, 11, 0.2)',
                color: '#fbbf24',
              }}
            >
              {pendingCount} Pending
            </span>
          )}
        </button>
      </div>

      {/* =========================================================================
          TAB 1: 📱 FYERS MOBILE TOKEN MANAGER (ADMIN ONLY)
         ========================================================================= */}
      {activeTab === 'fyers' && (
        <div
          className="card"
          style={{
            marginBottom: 32,
            border: '1px solid rgba(59, 130, 246, 0.35)',
            background: 'linear-gradient(180deg, rgba(30, 41, 59, 0.7) 0%, rgba(15, 23, 42, 0.85) 100%)',
            boxShadow: '0 8px 32px rgba(0, 0, 0, 0.3)',
            padding: 24,
            borderRadius: 12,
          }}
        >
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              flexWrap: 'wrap',
              gap: 12,
              borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
              paddingBottom: 16,
              marginBottom: 20,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <div
                style={{
                  width: 44,
                  height: 44,
                  borderRadius: 10,
                  background: 'rgba(59, 130, 246, 0.15)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: '#60a5fa',
                }}
              >
                <Smartphone size={24} />
              </div>
              <div>
                <h2 style={{ fontSize: 20, fontWeight: 800, margin: 0, display: 'flex', alignItems: 'center', gap: 10 }}>
                  Fyers Mobile Token Manager
                  <span
                    style={{
                      fontSize: 11,
                      background: 'rgba(59, 130, 246, 0.2)',
                      color: '#93c5fd',
                      padding: '3px 10px',
                      borderRadius: 12,
                      fontWeight: 700,
                    }}
                  >
                    100% Mobile Ready
                  </span>
                </h2>
                <p style={{ margin: 0, fontSize: 13, color: 'var(--color-text-muted)' }}>
                  Update daily broker token directly from your phone in 15 seconds (no laptop, .bat files, scp, or ssh needed)
                </p>
              </div>
            </div>

            <button
              type="button"
              onClick={() => fetchFyersStatus(true)}
              disabled={fyersLoading}
              style={{
                fontSize: 13,
                padding: '9px 18px',
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                fontWeight: 700,
                borderRadius: 8,
                border: 'none',
                background: fyersStatus?.connected
                  ? 'linear-gradient(135deg, #10b981, #059669)'
                  : 'linear-gradient(135deg, #3b82f6, #1d4ed8)',
                color: 'white',
                cursor: fyersLoading ? 'not-allowed' : 'pointer',
                boxShadow: '0 4px 14px rgba(0, 0, 0, 0.25)',
                transition: 'all 0.2s ease',
              }}
            >
              <Zap size={15} className={fyersLoading ? 'spin' : ''} />
              {fyersLoading ? 'Pinging Fyers V3 Servers...' : '⚡ Trigger Live Fyers API Check'}
            </button>
          </div>

          {/* Trigger Toast Alert Notification */}
          {triggerToast && (
            <div
              style={{
                padding: '12px 16px',
                borderRadius: 8,
                marginBottom: 18,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: 12,
                background:
                  triggerToast.type === 'success'
                    ? 'rgba(34, 197, 94, 0.15)'
                    : triggerToast.type === 'warning'
                    ? 'rgba(234, 179, 8, 0.15)'
                    : 'rgba(239, 68, 68, 0.15)',
                border: `1px solid ${
                  triggerToast.type === 'success'
                    ? '#22c55e'
                    : triggerToast.type === 'warning'
                    ? '#eab308'
                    : '#ef4444'
                }`,
                color:
                  triggerToast.type === 'success'
                    ? '#4ade80'
                    : triggerToast.type === 'warning'
                    ? '#fde047'
                    : '#f87171',
                fontSize: 13,
                fontWeight: 600,
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                {triggerToast.type === 'success' && <CheckCircle2 size={18} />}
                {triggerToast.type === 'warning' && <AlertCircle size={18} />}
                {triggerToast.type === 'error' && <XCircle size={18} />}
                <span>{triggerToast.text}</span>
              </div>
              <button
                type="button"
                onClick={() => setTriggerToast(null)}
                style={{ background: 'transparent', border: 'none', color: 'inherit', cursor: 'pointer', padding: 4, fontSize: 14 }}
              >
                ✕
              </button>
            </div>
          )}

          {/* Live Diagnostic & Telemetry Grid */}
          {(() => {
            const isRateLimited = fyersStatus?.token_status === 'RATE_LIMITED';
            const isConnected = Boolean(fyersStatus?.connected);
            const cooldownSec = fyersStatus?.dual_engine?.fyers_cooldown_remaining || 0;

            return (
              <>
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
                    gap: 14,
                    marginBottom: 20,
                  }}
                >
                  {/* Card 1: Fyers API Connection */}
                  <div style={{ background: 'rgba(255, 255, 255, 0.04)', borderRadius: 8, padding: '14px 16px', border: '1px solid rgba(255, 255, 255, 0.08)' }}>
                    <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6 }}>
                      Fyers API V3 Live State
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 15, fontWeight: 800, color: isRateLimited ? '#fbbf24' : (isConnected ? '#4ade80' : '#fde047') }}>
                      <span style={{ width: 10, height: 10, borderRadius: '50%', background: isRateLimited ? '#f59e0b' : (isConnected ? '#22c55e' : '#eab308'), display: 'inline-block', boxShadow: isRateLimited ? '0 0 10px #f59e0b' : (isConnected ? '0 0 10px #22c55e' : '0 0 10px #eab308') }} />
                      {isRateLimited ? 'RATE-LIMITED (COOLDOWN)' : (isConnected ? 'LIVE & ACTIVE' : 'EXPIRED (06:00 AM)')}
                    </div>
                    <div style={{ fontSize: 12, color: 'var(--color-text-muted)', marginTop: 4 }}>
                      {isRateLimited ? `Resuming Fyers in ${cooldownSec}s` : (fyersStatus?.name ? `Trader: ${fyersStatus.name}` : 'Awaiting daily renewal')}
                    </div>
                  </div>

                  {/* Card 2: Broker Ping Latency */}
                  <div style={{ background: 'rgba(255, 255, 255, 0.04)', borderRadius: 8, padding: '14px 16px', border: '1px solid rgba(255, 255, 255, 0.08)' }}>
                    <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6 }}>
                      Direct Broker Ping
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 16, fontWeight: 800, color: '#60a5fa' }}>
                      <Zap size={16} />
                      {fyersStatus?.ping_ms != null ? `${fyersStatus.ping_ms} ms` : (fyersLoading ? 'Measuring...' : 'Standby')}
                    </div>
                    <div style={{ fontSize: 12, color: 'var(--color-text-muted)', marginTop: 4 }}>
                      {isRateLimited ? 'Throttled by Fyers (50 req/min cap)' : (isConnected ? 'Ultra-low WebSocket push latency' : 'Yahoo backup poller active')}
                    </div>
                  </div>

                  {/* Card 3: Active Market Engine */}
                  <div style={{ background: 'rgba(255, 255, 255, 0.04)', borderRadius: 8, padding: '14px 16px', border: '1px solid rgba(255, 255, 255, 0.08)' }}>
                    <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6 }}>
                      Active Market Feed
                    </div>
                    <div style={{ fontSize: 14, fontWeight: 800, color: (isConnected && !isRateLimited) ? '#4ade80' : '#fbbf24' }}>
                      {isRateLimited ? 'Backup: Yahoo Finance (Throttled)' : (isConnected ? 'Primary: Fyers WebSocket' : 'Backup: Yahoo Finance')}
                    </div>
                    <div style={{ fontSize: 12, color: 'var(--color-text-muted)', marginTop: 4 }}>
                      {isRateLimited ? `Hot-swaps to Fyers in ${cooldownSec}s` : (isConnected ? 'Real-time (<100ms push stream)' : 'Live ticker (smooth 3s polling)')}
                    </div>
                  </div>

                  {/* Card 4: Last Verified Live */}
                  <div style={{ background: 'rgba(255, 255, 255, 0.04)', borderRadius: 8, padding: '14px 16px', border: '1px solid rgba(255, 255, 255, 0.08)' }}>
                    <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6 }}>
                      Last Live Health Check
                    </div>
                    <div style={{ fontSize: 14, fontWeight: 700, color: '#e2e8f0' }}>
                      {fyersStatus?.checked_at_ist || 'Auto-checked on mount'}
                    </div>
                    <div style={{ fontSize: 12, color: 'var(--color-text-muted)', marginTop: 4 }}>
                      Auto-triggers when viewing tab
                    </div>
                  </div>
                </div>

                {/* Connection Status Badge Banner */}
                <div
                  style={{
                    padding: '14px 18px',
                    borderRadius: 8,
                    marginBottom: 20,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    flexWrap: 'wrap',
                    gap: 12,
                    backgroundColor: isRateLimited
                      ? 'rgba(234, 179, 8, 0.12)'
                      : (isConnected ? 'rgba(34, 197, 94, 0.12)' : 'rgba(234, 179, 8, 0.12)'),
                    border: `1px solid ${isRateLimited ? 'rgba(234, 179, 8, 0.3)' : (isConnected ? 'rgba(34, 197, 94, 0.3)' : 'rgba(234, 179, 8, 0.3)')}`,
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                    {isConnected && !isRateLimited ? (
                      <CheckCircle2 size={26} style={{ color: '#22c55e', flexShrink: 0 }} />
                    ) : (
                      <XCircle size={26} style={{ color: '#eab308', flexShrink: 0 }} />
                    )}
                    <div>
                      <div style={{ fontWeight: 800, fontSize: 15, color: isRateLimited ? '#fbbf24' : (isConnected ? '#4ade80' : '#fde047') }}>
                        {isRateLimited
                          ? `🟡 Dual Engine Active: Fyers Rate-Limited (Yahoo Backup Feeding Smoothly)`
                          : (isConnected
                            ? `🟢 Dual Engine Active: Primary Fyers WebSocket Stream (<100ms Push)`
                            : `🟡 Dual Engine Active: Yahoo Finance Backup Engine (Live 3s Poller)`)}
                      </div>
                      <div style={{ fontSize: 13, color: 'var(--color-text-muted)', marginTop: 3 }}>
                        {isRateLimited
                          ? `Fyers Standard Plan limit (50 req/min) reached. Your Fyers token is 100% VALID & INTACT. Yahoo Finance backup is streaming uninterrupted and will automatically resume Fyers in ${cooldownSec}s.`
                          : (isConnected
                            ? `Trader: ${fyersStatus?.name || 'Dipak Firake'} (${fyersStatus?.masked_fy_id || fyersStatus?.fy_id || ''}) • Real-time tick stream active (expires daily at 06:00 AM IST)`
                            : `Fyers token expired at 06:00 AM IST. Stock prices are live and actively updating via Yahoo Finance backup without interruption. Renew token whenever convenient.`)}
                      </div>
                    </div>
                  </div>

                  <div style={{ fontSize: 12, color: 'var(--color-text-muted)', display: 'flex', alignItems: 'center', gap: 6 }}>
                    <ShieldCheck size={16} style={{ color: '#60a5fa' }} />
                    Autonomous Dual Failover
                  </div>
                </div>
              </>
            );
          })()}

          {/* Dual-Engine Architecture Notice */}
          <div
            style={{
              padding: '12px 16px',
              borderRadius: 8,
              marginBottom: 20,
              background: 'rgba(59, 130, 246, 0.08)',
              border: '1px solid rgba(59, 130, 246, 0.2)',
              fontSize: 12,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              flexWrap: 'wrap',
              gap: 10,
              color: '#93c5fd',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Zap size={15} style={{ color: '#3b82f6' }} />
              <span>
                <strong>Dual-Connection Cycle:</strong> Tokens expire at <strong>06:00 AM IST</strong> daily. If unrenewed, the system automatically runs on Yahoo Finance backup so prices never freeze. Activating a new token hot-swaps to Fyers immediately.
              </span>
            </div>
            <span style={{ fontWeight: 700, color: fyersStatus?.connected ? '#4ade80' : '#fbbf24' }}>
              Engine: {fyersStatus?.connected ? 'PRIMARY (FYERS)' : 'BACKUP (YAHOO)'}
            </span>
          </div>

          {/* Step-by-Step Mobile Renewal Process */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {/* Step 1 */}
            <div style={{ background: 'rgba(255, 255, 255, 0.03)', padding: 16, borderRadius: 8, border: '1px solid rgba(255, 255, 255, 0.06)' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
                <div>
                  <div style={{ fontWeight: 700, fontSize: 15, display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ width: 22, height: 22, borderRadius: '50%', background: '#3b82f6', color: 'white', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: 12, fontWeight: 700 }}>
                      1
                    </span>
                    Step 1: Open Fyers Mobile Login
                  </div>
                  <div style={{ fontSize: 13, color: 'var(--color-text-muted)', marginTop: 4 }}>
                    Opens the official Fyers authentication page. Log in with your Client ID, PIN & 2FA OTP.
                  </div>
                </div>

                <button
                  type="button"
                  onClick={handleOpenFyersLogin}
                  className="btn btn-primary"
                  style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px 18px', fontSize: 14, fontWeight: 600 }}
                >
                  <KeyRound size={16} />
                  Open Fyers Login
                  <ExternalLink size={15} />
                </button>
              </div>
            </div>

            {/* Step 2 & 3 */}
            <div style={{ background: 'rgba(255, 255, 255, 0.03)', padding: 16, borderRadius: 8, border: '1px solid rgba(255, 255, 255, 0.06)' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 10, marginBottom: 8 }}>
                <div style={{ fontWeight: 700, fontSize: 15, display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ width: 22, height: 22, borderRadius: '50%', background: '#3b82f6', color: 'white', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: 12, fontWeight: 700 }}>
                    2
                  </span>
                  Step 2 & 3: Paste Redirected URL & Activate Token
                </div>

                <button
                  type="button"
                  onClick={handlePasteFromClipboard}
                  className="btn btn-secondary"
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 6,
                    padding: '6px 12px',
                    fontSize: 12,
                    fontWeight: 700,
                    background: 'rgba(59, 130, 246, 0.15)',
                    border: '1px solid rgba(59, 130, 246, 0.35)',
                    color: '#60a5fa',
                    cursor: 'pointer',
                    borderRadius: 6,
                  }}
                  title="Reads the copied URL directly from your phone clipboard with 1 tap"
                >
                  <ClipboardPaste size={15} />
                  📋 Paste from Clipboard (1-Tap)
                </button>
              </div>

              <div style={{ fontSize: 13, color: 'var(--color-text-muted)', marginBottom: 8 }}>
                After logging in, copy the full redirected URL (or auth_code) from your mobile browser address bar and paste it below.
              </div>
              <div style={{ fontSize: 12, color: '#fde047', marginBottom: 14, background: 'rgba(234, 179, 8, 0.1)', padding: '6px 10px', borderRadius: 6, border: '1px solid rgba(234, 179, 8, 0.2)' }}>
                ⚡ <strong>Important:</strong> Fyers auth codes expire in <strong>2-3 minutes</strong> and can only be redeemed <strong>ONCE</strong>. If you used the code in another app or more than 2 minutes have passed, please click <strong>Step 1</strong> to generate a fresh link.
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                <textarea
                  className="input"
                  rows={2}
                  value={authInput}
                  onChange={(e) => setAuthInput(e.target.value)}
                  placeholder="Paste https://trade.fyers.in/api-login/redirect-uri/index.html?s=ok&auth_code=... or tap 'Paste from Clipboard' above"
                  style={{
                    width: '100%',
                    fontFamily: 'monospace',
                    fontSize: 12,
                    resize: 'vertical',
                    padding: 12,
                    borderRadius: 6,
                    border: '1px solid rgba(255, 255, 255, 0.15)',
                  }}
                />

                {/* Real-time Code / URL Inspector */}
                {detectedCode && (
                  <div
                    style={{
                      padding: '8px 12px',
                      borderRadius: 6,
                      fontSize: 12,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      flexWrap: 'wrap',
                      gap: 8,
                      background: detectedCode.valid ? 'rgba(34, 197, 94, 0.1)' : 'rgba(239, 68, 68, 0.1)',
                      border: `1px solid ${detectedCode.valid ? 'rgba(34, 197, 94, 0.25)' : 'rgba(239, 68, 68, 0.25)'}`,
                      color: detectedCode.valid ? '#4ade80' : '#f87171',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      {detectedCode.valid ? <CheckCircle2 size={14} /> : <AlertCircle size={14} />}
                      <span><strong>Format Detected:</strong> {detectedCode.type}</span>
                    </div>
                    <span style={{ fontFamily: 'monospace', fontSize: 11, opacity: 0.9 }}>{detectedCode.sample}</span>
                  </div>
                )}

                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
                  <button
                    type="button"
                    onClick={() => setAuthInput('')}
                    className="btn btn-secondary"
                    style={{ fontSize: 12, padding: '8px 14px' }}
                    disabled={!authInput}
                  >
                    Clear Box
                  </button>

                  <button
                    type="button"
                    onClick={handleUpdateToken}
                    disabled={updatingToken || !authInput.trim()}
                    className="btn btn-primary"
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 8,
                      padding: '10px 22px',
                      fontSize: 14,
                      fontWeight: 700,
                      background: 'linear-gradient(90deg, #10b981, #059669)',
                      border: 'none',
                    }}
                  >
                    <Zap size={16} />
                    {updatingToken ? 'Validating with Fyers...' : '🚀 Activate Token Now'}
                  </button>
                </div>
              </div>
            </div>

            {/* Notification Feedback Banner */}
            {tokenMessage && (
              <div
                style={{
                  padding: '12px 16px',
                  borderRadius: 6,
                  fontSize: 13,
                  fontWeight: 600,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 10,
                  backgroundColor: tokenMessage.type === 'success' ? 'rgba(34, 197, 94, 0.15)' : 'rgba(239, 68, 68, 0.15)',
                  color: tokenMessage.type === 'success' ? '#4ade80' : '#f87171',
                  border: `1px solid ${tokenMessage.type === 'success' ? 'rgba(34, 197, 94, 0.3)' : 'rgba(239, 68, 68, 0.3)'}`,
                }}
              >
                {tokenMessage.type === 'success' ? <CheckCircle2 size={18} /> : <AlertCircle size={18} />}
                {tokenMessage.text}
              </div>
            )}
          </div>
        </div>
      )}

      {/* =========================================================================
          TAB 2: 👥 USER DIRECTORY & PRO MEMBERSHIPS
         ========================================================================= */}
      {activeTab === 'users' && (
        <>
          {/* Metrics Row */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '16px', marginBottom: '24px' }}>
            <div style={{ background: 'var(--surface-color)', padding: '20px', borderRadius: '12px', border: '1px solid var(--border-color)' }}>
              <div style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>Total Accounts</div>
              <div style={{ fontSize: '1.8rem', fontWeight: 800, marginTop: '4px' }}>{users.length}</div>
            </div>
            <div style={{ background: 'var(--surface-color)', padding: '20px', borderRadius: '12px', border: '1px solid rgba(59, 130, 246, 0.3)' }}>
              <div style={{ color: '#60a5fa', fontSize: '0.85rem' }}>Active PRO Subscribers</div>
              <div style={{ fontSize: '1.8rem', fontWeight: 800, marginTop: '4px', color: '#60a5fa' }}>{proCount}</div>
            </div>
            <div style={{ background: 'var(--surface-color)', padding: '20px', borderRadius: '12px', border: '1px solid rgba(245, 158, 11, 0.3)' }}>
              <div style={{ color: '#fbbf24', fontSize: '0.85rem' }}>Pending Approval Requests</div>
              <div style={{ fontSize: '1.8rem', fontWeight: 800, marginTop: '4px', color: '#fbbf24' }}>{pendingCount}</div>
            </div>
          </div>

          {message && (
            <div
              style={{
                padding: '12px 18px',
                borderRadius: '8px',
                marginBottom: '20px',
                background: message.type === 'success' ? 'rgba(34, 197, 94, 0.1)' : 'rgba(239, 68, 68, 0.1)',
                border: message.type === 'success' ? '1px solid #22c55e' : '1px solid #ef4444',
                color: message.type === 'success' ? '#4ade80' : '#f87171',
                fontWeight: 600,
              }}
            >
              {message.text}
            </div>
          )}

          {/* Search and Filters */}
          <div style={{ display: 'flex', gap: '12px', marginBottom: '18px', flexWrap: 'wrap' }}>
            <input
              type="text"
              placeholder="Search by email or name..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              style={{
                flex: '1 1 280px',
                padding: '10px 14px',
                borderRadius: '8px',
                border: '1px solid var(--border-color)',
                background: 'var(--surface-color)',
                color: 'var(--text-color)',
                fontSize: '0.9rem',
              }}
            />

            <div style={{ display: 'flex', gap: '6px' }}>
              {(['ALL', 'REQUESTED', 'PRO', 'FREE'] as const).map((tab) => (
                <button
                  key={tab}
                  onClick={() => setFilter(tab)}
                  style={{
                    padding: '8px 14px',
                    borderRadius: '8px',
                    border: filter === tab ? '1px solid #3b82f6' : '1px solid var(--border-color)',
                    background: filter === tab ? 'rgba(59, 130, 246, 0.15)' : 'var(--surface-color)',
                    color: filter === tab ? '#60a5fa' : 'var(--text-secondary)',
                    fontWeight: 600,
                    fontSize: '0.85rem',
                    cursor: 'pointer',
                  }}
                >
                  {tab === 'REQUESTED' ? `Requests (${pendingCount})` : tab}
                </button>
              ))}
            </div>
          </div>

          {/* User Directory Table */}
          <div
            className="table-container"
            style={{
              background: 'var(--surface-color)',
              borderRadius: '12px',
              border: '1px solid var(--border-color)',
              overflowX: 'auto',
            }}
          >
            {loading ? (
              <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-secondary)' }}>
                Loading user directory...
              </div>
            ) : filteredUsers.length === 0 ? (
              <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-secondary)' }}>
                No users found matching current filters.
              </div>
            ) : (
              <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.9rem' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border-color)', color: 'var(--text-secondary)', fontSize: '0.8rem' }}>
                    <th style={{ padding: '14px 18px' }}>USER</th>
                    <th style={{ padding: '14px 18px' }}>TIER</th>
                    <th style={{ padding: '14px 18px' }}>PRO STATUS</th>
                    <th style={{ padding: '14px 18px' }}>PAYMENT DETAILS</th>
                    <th style={{ padding: '14px 18px', textAlign: 'right' }}>ACTIONS</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredUsers.map((u) => {
                    const isProUser = u.subscription_tier === 'PRO';
                    const isRequested = u.pro_status === 'REQUESTED';
                    const isUserAdmin = u.is_admin;

                    return (
                      <tr key={u.id} style={{ borderBottom: '1px solid var(--border-color)' }}>
                        <td style={{ padding: '14px 18px' }}>
                          <div style={{ fontWeight: 600, display: 'flex', alignItems: 'center', gap: '8px' }}>
                            {u.name || 'Unnamed Trader'}
                            {isUserAdmin && (
                              <span style={{ fontSize: '0.7rem', padding: '2px 6px', background: '#3b82f6', color: 'white', borderRadius: '4px', fontWeight: 700 }}>
                                ADMIN
                              </span>
                            )}
                          </div>
                          <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginTop: '2px' }}>{u.email}</div>
                        </td>
                        <td style={{ padding: '14px 18px' }}>
                          <span
                            style={{
                              padding: '4px 8px',
                              borderRadius: '6px',
                              fontSize: '0.75rem',
                              fontWeight: 700,
                              background: isProUser ? 'rgba(59, 130, 246, 0.15)' : 'rgba(255, 255, 255, 0.05)',
                              color: isProUser ? '#60a5fa' : 'var(--text-secondary)',
                              border: isProUser ? '1px solid #3b82f6' : '1px solid var(--border-color)',
                            }}
                          >
                            {u.subscription_tier}
                          </span>
                        </td>
                        <td style={{ padding: '14px 18px' }}>
                          <span
                            style={{
                              padding: '4px 8px',
                              borderRadius: '6px',
                              fontSize: '0.75rem',
                              fontWeight: 600,
                              background:
                                u.pro_status === 'ACTIVE'
                                  ? 'rgba(34, 197, 94, 0.15)'
                                  : u.pro_status === 'REQUESTED'
                                  ? 'rgba(245, 158, 11, 0.15)'
                                  : 'transparent',
                              color:
                                u.pro_status === 'ACTIVE'
                                  ? '#4ade80'
                                  : u.pro_status === 'REQUESTED'
                                  ? '#fbbf24'
                                  : 'var(--text-secondary)',
                            }}
                          >
                            {u.pro_status}
                          </span>
                        </td>
                        <td style={{ padding: '14px 18px', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                          {u.payment_reference ? (
                            <div>
                              <div><strong>Ref:</strong> {u.payment_reference}</div>
                              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>via {u.payment_method || 'UPI'}</div>
                            </div>
                          ) : (
                            '—'
                          )}
                        </td>
                        <td style={{ padding: '14px 18px', textAlign: 'right' }}>
                          <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
                            {isRequested && (
                              <>
                                <button
                                  onClick={() => handleApprove(u.id, u.email)}
                                  disabled={actionLoading === u.id}
                                  style={{
                                    padding: '6px 12px',
                                    background: '#22c55e',
                                    border: 'none',
                                    borderRadius: '6px',
                                    color: 'white',
                                    fontSize: '0.8rem',
                                    fontWeight: 700,
                                    cursor: 'pointer',
                                  }}
                                >
                                  ✓ Approve
                                </button>
                                <button
                                  onClick={() => handleReject(u.id, u.email)}
                                  disabled={actionLoading === u.id}
                                  style={{
                                    padding: '6px 12px',
                                    background: 'rgba(239, 68, 68, 0.2)',
                                    border: '1px solid #ef4444',
                                    borderRadius: '6px',
                                    color: '#f87171',
                                    fontSize: '0.8rem',
                                    fontWeight: 600,
                                    cursor: 'pointer',
                                  }}
                                >
                                  ✕ Reject
                                </button>
                              </>
                            )}

                            {!isProUser && !isRequested && (
                              <button
                                onClick={() => handleApprove(u.id, u.email)}
                                disabled={actionLoading === u.id}
                                style={{
                                  padding: '6px 12px',
                                  background: 'rgba(59, 130, 246, 0.15)',
                                  border: '1px solid #3b82f6',
                                  borderRadius: '6px',
                                  color: '#60a5fa',
                                  fontSize: '0.8rem',
                                  fontWeight: 600,
                                  cursor: 'pointer',
                                }}
                              >
                                Grant PRO
                              </button>
                            )}

                            {isProUser && !isUserAdmin && (
                              <button
                                onClick={() => handleRevoke(u.id, u.email)}
                                disabled={actionLoading === u.id}
                                style={{
                                  padding: '6px 12px',
                                  background: 'rgba(239, 68, 68, 0.1)',
                                  border: '1px solid rgba(239, 68, 68, 0.4)',
                                  borderRadius: '6px',
                                  color: '#f87171',
                                  fontSize: '0.8rem',
                                  fontWeight: 600,
                                  cursor: 'pointer',
                                }}
                              >
                                Revoke PRO
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}
    </div>
  );
}
