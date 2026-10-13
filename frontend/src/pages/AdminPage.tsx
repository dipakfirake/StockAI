import React, { useState, useEffect } from 'react';
import { useAuth } from '../AuthContext';
import { adminApi } from '../services/api';
import { Link } from 'react-router-dom';

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

export default function AdminPage() {
  const { user } = useAuth();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState<'ALL' | 'REQUESTED' | 'PRO' | 'FREE'>('ALL');
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [message, setMessage] = useState<{ text: string; type: 'success' | 'error' } | null>(null);

  const fetchUsers = async () => {
    setLoading(true);
    try {
      const res = await adminApi.listUsers();
      setUsers(res.data || []);
    } catch (err: any) {
      setMessage({
        text: err.response?.data?.detail || 'Failed to fetch user directory. Administrator access required.',
        type: 'error'
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchUsers();
  }, []);

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

  const filteredUsers = users.filter(u => {
    const matchesSearch = u.email.toLowerCase().includes(search.toLowerCase()) || 
                          u.name.toLowerCase().includes(search.toLowerCase());
    if (!matchesSearch) return false;
    if (filter === 'REQUESTED') return u.pro_status === 'REQUESTED';
    if (filter === 'PRO') return u.subscription_tier === 'PRO';
    if (filter === 'FREE') return u.subscription_tier === 'FREE';
    return true;
  });

  const pendingCount = users.filter(u => u.pro_status === 'REQUESTED').length;
  const proCount = users.filter(u => u.subscription_tier === 'PRO').length;

  return (
    <div style={{ maxWidth: '1200px', margin: '0 auto', padding: '30px 20px' }}>
      
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px', flexWrap: 'wrap', gap: '16px' }}>
        <div>
          <h1 style={{ fontSize: '2rem', fontWeight: 800, margin: 0 }}>
            🛡️ Administrative Control Center
          </h1>
          <p style={{ color: 'var(--text-secondary)', margin: '6px 0 0 0' }}>
            Manage user subscription entitlements, review pending PRO upgrade requests, and monitor system health.
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
              gap: '6px'
            }}
          >
            🛡️ 24/7 Sentinel Watchdog
          </Link>
          <button
            onClick={fetchUsers}
            style={{
              padding: '10px 16px',
              background: 'var(--surface-color)',
              border: '1px solid var(--border-color)',
              color: 'var(--text-color)',
              borderRadius: '8px',
              cursor: 'pointer',
              fontWeight: 600
            }}
          >
            🔄 Refresh
          </button>
        </div>
      </div>

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
        <div style={{
          padding: '12px 18px',
          borderRadius: '8px',
          marginBottom: '20px',
          background: message.type === 'success' ? 'rgba(34, 197, 94, 0.1)' : 'rgba(239, 68, 68, 0.1)',
          border: message.type === 'success' ? '1px solid #22c55e' : '1px solid #ef4444',
          color: message.type === 'success' ? '#4ade80' : '#f87171',
          fontWeight: 600
        }}>
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
            fontSize: '0.9rem'
          }}
        />

        <div style={{ display: 'flex', gap: '6px' }}>
          {(['ALL', 'REQUESTED', 'PRO', 'FREE'] as const).map(tab => (
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
                cursor: 'pointer'
              }}
            >
              {tab === 'REQUESTED' ? `Requests (${pendingCount})` : tab}
            </button>
          ))}
        </div>
      </div>

      {/* User Directory Table */}
      <div className="table-container" style={{
        background: 'var(--surface-color)',
        borderRadius: '12px',
        border: '1px solid var(--border-color)',
        overflowX: 'auto',
        WebkitOverflowScrolling: 'touch'
      }}>
        {loading ? (
          <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-secondary)' }}>
            Loading user directory...
          </div>
        ) : filteredUsers.length === 0 ? (
          <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-secondary)' }}>
            No users match the selected query.
          </div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.9rem', minWidth: '700px' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border-color)', textAlign: 'left', background: 'rgba(255,255,255,0.02)' }}>
                <th style={{ padding: '14px 18px', fontWeight: 600 }}>User</th>
                <th style={{ padding: '14px 18px', fontWeight: 600 }}>Role</th>
                <th style={{ padding: '14px 18px', fontWeight: 600 }}>Tier</th>
                <th style={{ padding: '14px 18px', fontWeight: 600 }}>PRO Status</th>
                <th style={{ padding: '14px 18px', fontWeight: 600 }}>Payment / Ref</th>
                <th style={{ padding: '14px 18px', fontWeight: 600, textAlign: 'right' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredUsers.map((u) => {
                const isUserAdmin = u.is_admin || u.email.toLowerCase() === 'admin@stockai.com';
                const isRequested = u.pro_status === 'REQUESTED';
                const isProUser = u.subscription_tier === 'PRO';

                return (
                  <tr key={u.id} style={{ borderBottom: '1px solid var(--border-color)' }}>
                    <td style={{ padding: '14px 18px' }}>
                      <div style={{ fontWeight: 600 }}>{u.name}</div>
                      <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>{u.email}</div>
                    </td>
                    <td style={{ padding: '14px 18px' }}>
                      <span style={{
                        padding: '3px 8px',
                        borderRadius: '4px',
                        fontSize: '0.75rem',
                        fontWeight: 700,
                        background: isUserAdmin ? 'rgba(239, 68, 68, 0.15)' : 'rgba(255,255,255,0.05)',
                        color: isUserAdmin ? '#f87171' : 'var(--text-secondary)'
                      }}>
                        {isUserAdmin ? 'ADMIN' : 'USER'}
                      </span>
                    </td>
                    <td style={{ padding: '14px 18px' }}>
                      <span style={{
                        padding: '3px 8px',
                        borderRadius: '4px',
                        fontSize: '0.75rem',
                        fontWeight: 700,
                        background: isProUser ? 'rgba(34, 197, 94, 0.15)' : 'rgba(255,255,255,0.05)',
                        color: isProUser ? '#4ade80' : 'var(--text-secondary)'
                      }}>
                        {u.subscription_tier}
                      </span>
                    </td>
                    <td style={{ padding: '14px 18px' }}>
                      <span style={{
                        padding: '4px 10px',
                        borderRadius: '12px',
                        fontSize: '0.8rem',
                        fontWeight: 600,
                        background: isRequested ? 'rgba(245, 158, 11, 0.2)' : 'rgba(255,255,255,0.04)',
                        color: isRequested ? '#fbbf24' : 'var(--text-secondary)'
                      }}>
                        {u.pro_status}
                      </span>
                    </td>
                    <td style={{ padding: '14px 18px', fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
                      {u.payment_reference ? (
                        <div>
                          <div>{u.payment_method || 'REF'}</div>
                          <code style={{ fontSize: '0.75rem', color: '#60a5fa' }}>{u.payment_reference}</code>
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
                                cursor: 'pointer'
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
                                cursor: 'pointer'
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
                              cursor: 'pointer'
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
                              cursor: 'pointer'
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

    </div>
  );
}
