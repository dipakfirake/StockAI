import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Check, X, Clock, CreditCard, Shield } from 'lucide-react';
import { useAuth } from '../AuthContext';
import { subscriptionApi } from '../services/api';
import './Auth.css';

export default function PricingPage() {
  const { user, reloadUser } = useAuth();
  const navigate = useNavigate();
  
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  
  // Pathway 1: Payment Checkout Modal state
  const [showPayModal, setShowPayModal] = useState(false);
  const [payMethod, setPayMethod] = useState<'UPI' | 'CARD' | 'NETBANKING'>('UPI');
  const [payRef, setPayRef] = useState('');
  
  // Pathway 2: Admin Request state
  const [showRequestModal, setShowRequestModal] = useState(false);
  const [requestNote, setRequestNote] = useState('');
  const [proStatus, setProStatus] = useState<string>(user?.pro_status || 'NONE');

  useEffect(() => {
    if (user) {
      subscriptionApi.getStatus().then(res => {
        if (res.data?.pro_status) {
          setProStatus(res.data.pro_status);
        }
      }).catch(() => {});
    }
  }, [user]);

  // Pathway 1: Submit Payment Checkout
  const handlePaymentSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!user) {
      navigate('/login');
      return;
    }
    if (!payRef.trim()) {
      setError('Please enter a valid Transaction / Reference ID.');
      return;
    }

    setLoading(true);
    setError('');
    setSuccess('');

    try {
      const res = await subscriptionApi.checkout({
        payment_method: payMethod,
        payment_reference: payRef.trim(),
        amount: 29.0,
      });
      setSuccess(res.data.message || 'Payment verified! Upgraded to PRO.');
      setShowPayModal(false);
      setPayRef('');
      await reloadUser();
      setProStatus('ACTIVE');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Payment verification failed.');
    } finally {
      setLoading(false);
    }
  };

  // Pathway 2: Submit Admin Approval Request
  const handleAdminRequestSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!user) {
      navigate('/login');
      return;
    }

    setLoading(true);
    setError('');
    setSuccess('');

    try {
      const res = await subscriptionApi.requestPro(requestNote.trim());
      setSuccess(res.data.message || 'Request submitted to administrator!');
      setShowRequestModal(false);
      setRequestNote('');
      await reloadUser();
      setProStatus('REQUESTED');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to submit admin request.');
    } finally {
      setLoading(false);
    }
  };

  const isPro = user?.subscription_tier === 'PRO';
  const isPendingApproval = proStatus === 'REQUESTED' && !isPro;

  return (
    <div className="pricing-container" style={{ padding: '24px 12px', maxWidth: '980px', margin: '0 auto' }}>
      <div style={{ textAlign: 'center', marginBottom: '28px' }}>
        <h1 style={{ fontSize: 'clamp(1.6rem, 3.5vw, 2.2rem)', fontWeight: 700, marginBottom: '8px' }}>
          Membership Plans
        </h1>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.98rem', maxWidth: '580px', margin: '0 auto' }}>
          Choose between Standard research tools or PRO quantitative signals and options analytics.
        </p>
      </div>

      {error && (
        <div className="auth-alert error" style={{ marginBottom: '18px', padding: '12px 16px', borderRadius: '8px', background: 'rgba(239, 68, 68, 0.1)', border: '1px solid #ef4444', color: '#f87171' }}>
          {error}
        </div>
      )}

      {success && (
        <div className="auth-alert success" style={{ marginBottom: '18px', padding: '12px 16px', borderRadius: '8px', background: 'rgba(16, 185, 129, 0.1)', border: '1px solid #10b981', color: '#34d399' }}>
          {success}
        </div>
      )}

      {isPendingApproval && (
        <div style={{
          marginBottom: '22px',
          padding: '14px 18px',
          borderRadius: '10px',
          background: 'rgba(245, 158, 11, 0.1)',
          border: '1px solid rgba(245, 158, 11, 0.5)',
          color: '#fbbf24',
          display: 'flex',
          alignItems: 'center',
          gap: '12px'
        }}>
          <Clock size={20} style={{ flexShrink: 0 }} />
          <div>
            <strong>PRO Membership Under Admin Review</strong>
            <div style={{ fontSize: '0.88rem', color: 'var(--text-secondary)', marginTop: '2px' }}>
              Your application has been received. Your account activates automatically once approved.
            </div>
          </div>
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 280px), 1fr))', gap: '20px' }}>

        {/* FREE TIER CARD */}
        <div className="card" style={{
          borderRadius: '12px',
          padding: 'clamp(18px, 4vw, 28px)',
          display: 'flex',
          flexDirection: 'column',
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <h2 style={{ fontSize: '1.35rem', fontWeight: 700, margin: 0 }}>Standard</h2>
            <span style={{ fontSize: '0.75rem', padding: '3px 10px', background: 'var(--color-bg-secondary)', border: '1px solid var(--border-color)', borderRadius: '14px' }}>Free</span>
          </div>
          <div className="mono" style={{ fontSize: '2.1rem', fontWeight: 700, margin: '18px 0 8px' }}>
            ₹0<span style={{ fontSize: '0.95rem', color: 'var(--text-secondary)', fontWeight: 400 }}> / month</span>
          </div>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', marginBottom: '20px' }}>
            Core technical screener, charting, and paper portfolio tracking.
          </p>

          <ul style={{ listStyle: 'none', padding: 0, margin: '0 0 24px 0', flex: 1, fontSize: '0.9rem', display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <li style={{ display: 'flex', alignItems: 'center', gap: 10 }}><Check size={16} color="#10b981" /> Live NSE &amp; BSE Market Quotes</li>
            <li style={{ display: 'flex', alignItems: 'center', gap: 10 }}><Check size={16} color="#10b981" /> RSI, MACD &amp; EMA Chart Overlays</li>
            <li style={{ display: 'flex', alignItems: 'center', gap: 10 }}><Check size={16} color="#10b981" /> Paper Trading &amp; Portfolio Ledger</li>
            <li style={{ display: 'flex', alignItems: 'center', gap: 10 }}><Check size={16} color="#10b981" /> Custom Watchlist &amp; Price Alerts</li>
            <li style={{ display: 'flex', alignItems: 'center', gap: 10, color: 'var(--color-text-muted)' }}><X size={16} /> ML Ensemble Signal Forecasts</li>
            <li style={{ display: 'flex', alignItems: 'center', gap: 10, color: 'var(--color-text-muted)' }}><X size={16} /> Smart Money Concepts Radar</li>
            <li style={{ display: 'flex', alignItems: 'center', gap: 10, color: 'var(--color-text-muted)' }}><X size={16} /> Options Chain &amp; Greeks Engine</li>
          </ul>

          <button
            disabled={true}
            className="btn btn-secondary"
            style={{ width: '100%', cursor: 'not-allowed', opacity: 0.7 }}
          >
            {isPro ? 'Included' : 'Current Plan'}
          </button>
        </div>

        {/* PRO TIER CARD */}
        <div className="card" style={{
          borderRadius: '12px',
          padding: 'clamp(18px, 4vw, 28px)',
          border: '1.5px solid var(--color-accent-blue)',
          display: 'flex',
          flexDirection: 'column',
          position: 'relative',
        }}>
          <div style={{
            position: 'absolute',
            top: '-12px',
            right: '20px',
            background: 'var(--color-accent-blue)',
            color: 'white',
            padding: '3px 12px',
            borderRadius: '14px',
            fontSize: '0.72rem',
            fontWeight: 700,
            letterSpacing: '0.05em'
          }}>RECOMMENDED</div>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <h2 style={{ fontSize: '1.35rem', fontWeight: 700, color: 'var(--color-accent-blue)', margin: 0 }}>StockAI PRO</h2>
            {isPro && (
              <span style={{ fontSize: '0.75rem', padding: '3px 10px', background: 'rgba(16,185,129,0.18)', color: '#10b981', borderRadius: '14px', fontWeight: 700 }}>
                ACTIVE
              </span>
            )}
          </div>

          <div className="mono" style={{ fontSize: '2.1rem', fontWeight: 700, margin: '18px 0 8px' }}>
            ₹2,499<span style={{ fontSize: '0.95rem', color: 'var(--text-secondary)', fontWeight: 400 }}> / month</span>
          </div>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', marginBottom: '20px' }}>
            Full quantitative screener, ML signals, strategy backtesting, and options Greeks.
          </p>

          <ul style={{ listStyle: 'none', padding: 0, margin: '0 0 24px 0', flex: 1, fontSize: '0.9rem', display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <li style={{ display: 'flex', alignItems: 'center', gap: 10 }}><Check size={16} color="#10b981" /> Everything in Standard Plan</li>
            <li style={{ display: 'flex', alignItems: 'center', gap: 10, fontWeight: 600 }}><Check size={16} color="#10b981" /> Multi-Factor AI &amp; ML Forecasts</li>
            <li style={{ display: 'flex', alignItems: 'center', gap: 10, fontWeight: 600 }}><Check size={16} color="#10b981" /> Smart Money Liquidity Scanner</li>
            <li style={{ display: 'flex', alignItems: 'center', gap: 10, fontWeight: 600 }}><Check size={16} color="#10b981" /> Options Chain &amp; Greeks Analytics</li>
            <li style={{ display: 'flex', alignItems: 'center', gap: 10, fontWeight: 600 }}><Check size={16} color="#10b981" /> Real-Time Streaming Market Feed</li>
            <li style={{ display: 'flex', alignItems: 'center', gap: 10, fontWeight: 600 }}><Check size={16} color="#10b981" /> Automated Risk &amp; Target Alerts</li>
          </ul>

          {isPro ? (
            <button
              disabled={true}
              className="btn"
              style={{
                width: '100%',
                background: 'rgba(16,185,129,0.16)',
                border: '1px solid #10b981',
                color: '#10b981',
                cursor: 'default'
              }}
            >
              PRO Membership Active
            </button>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              <button
                onClick={() => setShowPayModal(true)}
                disabled={loading}
                className="btn btn-primary"
                style={{ width: '100%', padding: '12px', fontWeight: 700 }}
              >
                <CreditCard size={16} /> Subscribe — ₹2,499 / month
              </button>

              <button
                onClick={() => setShowRequestModal(true)}
                disabled={loading || isPendingApproval}
                className="btn btn-secondary"
                style={{
                  width: '100%',
                  borderColor: isPendingApproval ? '#f59e0b' : undefined,
                  color: isPendingApproval ? '#fbbf24' : undefined,
                }}
              >
                <Shield size={15} /> {isPendingApproval ? 'Approval Request Pending' : 'Request Admin Access'}
              </button>
            </div>
          )}
        </div>

      </div>

      {/* MODAL 1: Verified Payment Checkout */}
      {showPayModal && (
        <div style={{
          position: 'fixed',
          top: 0, left: 0, right: 0, bottom: 0,
          background: 'rgba(0,0,0,0.7)',
          backdropFilter: 'blur(4px)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1000,
          padding: '20px'
        }}>
          <div style={{
            background: 'var(--surface-color)',
            border: '1px solid var(--border-color)',
            borderRadius: '14px',
            width: '100%',
            maxWidth: '460px',
            padding: '24px',
            boxShadow: '0 20px 40px rgba(0,0,0,0.4)'
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <h3 style={{ fontSize: '1.2rem', fontWeight: 700, margin: 0 }}>PRO Checkout</h3>
              <button
                onClick={() => setShowPayModal(false)}
                style={{ background: 'none', border: 'none', color: 'var(--text-secondary)', fontSize: '1.2rem', cursor: 'pointer' }}
              >✕</button>
            </div>

            <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', marginBottom: '16px' }}>
              Plan: <strong>StockAI PRO Monthly</strong> · Amount: <strong className="mono">₹2,499</strong>
            </p>

            <form onSubmit={handlePaymentSubmit}>
              <div style={{ marginBottom: '14px' }}>
                <label style={{ display: 'block', fontSize: '0.85rem', marginBottom: '6px', fontWeight: 600 }}>Payment Method</label>
                <div style={{ display: 'flex', gap: '8px' }}>
                  {(['UPI', 'CARD', 'NETBANKING'] as const).map(method => (
                    <button
                      key={method}
                      type="button"
                      onClick={() => setPayMethod(method)}
                      style={{
                        flex: 1,
                        padding: '10px 8px',
                        borderRadius: '8px',
                        border: payMethod === method ? '2px solid #3b82f6' : '1px solid var(--border-color)',
                        background: payMethod === method ? 'rgba(59, 130, 246, 0.15)' : 'var(--bg-color)',
                        color: payMethod === method ? '#60a5fa' : 'var(--text-secondary)',
                        fontWeight: 600,
                        fontSize: '0.85rem',
                        cursor: 'pointer'
                      }}
                    >
                      {method}
                    </button>
                  ))}
                </div>
              </div>

              {payMethod === 'UPI' && (
                <div style={{
                  padding: '12px',
                  borderRadius: '8px',
                  background: 'var(--bg-color)',
                  border: '1px dashed var(--border-color)',
                  marginBottom: '16px',
                  textAlign: 'center',
                  fontSize: '0.88rem'
                }}>
                  <div style={{ fontWeight: 600, color: '#60a5fa' }}>UPI VPA: stockai@upi</div>
                  <div style={{ color: 'var(--text-secondary)', fontSize: '0.8rem', marginTop: '4px' }}>
                    Pay via GPay, PhonePe, or Paytm and enter the 12-digit UTR/Ref below.
                  </div>
                </div>
              )}

              <div style={{ marginBottom: '20px' }}>
                <label style={{ display: 'block', fontSize: '0.85rem', marginBottom: '6px', fontWeight: 600 }}>
                  Transaction / UTR Reference ID <span style={{ color: '#ef4444' }}>*</span>
                </label>
                <input
                  type="text"
                  placeholder="e.g. UPI-20261013-889922 or CHK-44910"
                  value={payRef}
                  onChange={(e) => setPayRef(e.target.value)}
                  required
                  style={{
                    width: '100%',
                    padding: '11px 14px',
                    borderRadius: '8px',
                    border: '1px solid var(--border-color)',
                    background: 'var(--bg-color)',
                    color: 'var(--text-color)',
                    fontSize: '0.95rem'
                  }}
                />
              </div>

              <div style={{ display: 'flex', gap: '10px' }}>
                <button
                  type="button"
                  onClick={() => setShowPayModal(false)}
                  style={{
                    flex: 1,
                    padding: '11px',
                    background: 'var(--bg-color)',
                    border: '1px solid var(--border-color)',
                    borderRadius: '8px',
                    color: 'var(--text-color)',
                    cursor: 'pointer',
                    fontWeight: 600
                  }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={loading}
                  style={{
                    flex: 2,
                    padding: '11px',
                    background: '#3b82f6',
                    border: 'none',
                    borderRadius: '8px',
                    color: 'white',
                    cursor: 'pointer',
                    fontWeight: 700
                  }}
                >
                  {loading ? 'Verifying...' : 'Verify & Activate PRO'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MODAL 2: Request Admin Approval */}
      {showRequestModal && (
        <div style={{
          position: 'fixed',
          top: 0, left: 0, right: 0, bottom: 0,
          background: 'rgba(0,0,0,0.7)',
          backdropFilter: 'blur(4px)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1000,
          padding: '20px'
        }}>
          <div style={{
            background: 'var(--surface-color)',
            border: '1px solid var(--border-color)',
            borderRadius: '16px',
            width: '100%',
            maxWidth: '480px',
            padding: '28px',
            boxShadow: '0 20px 40px rgba(0,0,0,0.4)'
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '18px' }}>
              <h3 style={{ fontSize: '1.3rem', fontWeight: 700 }}>Request Administrator Approval</h3>
              <button 
                onClick={() => setShowRequestModal(false)}
                style={{ background: 'none', border: 'none', color: 'var(--text-secondary)', fontSize: '1.4rem', cursor: 'pointer' }}
              >✕</button>
            </div>

            <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', marginBottom: '18px' }}>
              Institutional accounts, research analysts, and students can request free PRO access directly from the system administrator.
            </p>

            <form onSubmit={handleAdminRequestSubmit}>
              <div style={{ marginBottom: '20px' }}>
                <label style={{ display: 'block', fontSize: '0.85rem', marginBottom: '6px', fontWeight: 600 }}>
                  Reason / Purpose (Optional)
                </label>
                <textarea
                  rows={3}
                  placeholder="e.g. Academic stock analysis research, algorithmic testing pilot..."
                  value={requestNote}
                  onChange={(e) => setRequestNote(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '10px 14px',
                    borderRadius: '8px',
                    border: '1px solid var(--border-color)',
                    background: 'var(--bg-color)',
                    color: 'var(--text-color)',
                    fontSize: '0.9rem',
                    resize: 'vertical'
                  }}
                />
              </div>

              <div style={{ display: 'flex', gap: '10px' }}>
                <button
                  type="button"
                  onClick={() => setShowRequestModal(false)}
                  style={{
                    flex: 1,
                    padding: '11px',
                    background: 'var(--bg-color)',
                    border: '1px solid var(--border-color)',
                    borderRadius: '8px',
                    color: 'var(--text-color)',
                    cursor: 'pointer',
                    fontWeight: 600
                  }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={loading}
                  style={{
                    flex: 2,
                    padding: '11px',
                    background: '#f59e0b',
                    border: 'none',
                    borderRadius: '8px',
                    color: '#000',
                    cursor: 'pointer',
                    fontWeight: 700
                  }}
                >
                  {loading ? 'Submitting...' : 'Submit to Admin'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

    </div>
  );
}
