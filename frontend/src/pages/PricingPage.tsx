import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
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
    <div className="pricing-container" style={{ padding: '40px 20px', maxWidth: '1080px', margin: '0 auto' }}>
      <div style={{ textAlign: 'center', marginBottom: '35px' }}>
        <h1 style={{ fontSize: '2.4rem', fontWeight: 800, marginBottom: '10px' }}>
          StockAI Membership Plans
        </h1>
        <p style={{ color: 'var(--text-secondary)', fontSize: '1.15rem', maxWidth: '640px', margin: '0 auto' }}>
          Select the best pathway for your research: Instant Verified Subscription or Manual Administrator Review.
        </p>
      </div>

      {error && (
        <div className="auth-alert error" style={{ marginBottom: '20px', padding: '12px 16px', borderRadius: '8px', background: 'rgba(239, 68, 68, 0.1)', border: '1px solid #ef4444', color: '#f87171' }}>
          ⚠️ {error}
        </div>
      )}

      {success && (
        <div className="auth-alert success" style={{ marginBottom: '20px', padding: '12px 16px', borderRadius: '8px', background: 'rgba(34, 197, 94, 0.1)', border: '1px solid #22c55e', color: '#4ade80' }}>
          ✅ {success}
        </div>
      )}

      {isPendingApproval && (
        <div style={{
          marginBottom: '25px',
          padding: '16px 20px',
          borderRadius: '10px',
          background: 'rgba(245, 158, 11, 0.1)',
          border: '1px solid #f59e0b',
          color: '#fbbf24',
          display: 'flex',
          alignItems: 'center',
          gap: '12px'
        }}>
          <span style={{ fontSize: '1.5rem' }}>🕒</span>
          <div>
            <strong>PRO Membership Request Under Admin Review</strong>
            <div style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', marginTop: '2px' }}>
              Your application has been received by our administrators. Your account will automatically activate once approved.
            </div>
          </div>
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '30px' }}>
        
        {/* FREE TIER CARD */}
        <div style={{ 
          background: 'var(--surface-color)', 
          borderRadius: '14px', 
          padding: '32px',
          border: '1px solid var(--border-color)',
          display: 'flex',
          flexDirection: 'column',
          boxShadow: '0 4px 20px rgba(0,0,0,0.1)'
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <h2 style={{ fontSize: '1.6rem', fontWeight: 700 }}>Free Tier</h2>
            <span style={{ fontSize: '0.8rem', padding: '4px 10px', background: 'rgba(255,255,255,0.06)', borderRadius: '20px' }}>Standard</span>
          </div>
          <div style={{ fontSize: '2.4rem', fontWeight: 800, margin: '20px 0 10px' }}>
            $0<span style={{ fontSize: '1rem', color: 'var(--text-secondary)', fontWeight: 400 }}> / month</span>
          </div>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.92rem', marginBottom: '24px' }}>
            Basic technical screener and charting for casual retail traders.
          </p>

          <ul style={{ listStyle: 'none', padding: 0, margin: '0 0 30px 0', flex: 1, fontSize: '0.95rem' }}>
            <li style={{ marginBottom: '14px' }}>✅ Live Nifty/Sensex Market Quotes</li>
            <li style={{ marginBottom: '14px' }}>✅ Technical Indicators (RSI, MACD, EMA)</li>
            <li style={{ marginBottom: '14px' }}>✅ Virtual Paper Trading Engine</li>
            <li style={{ marginBottom: '14px' }}>✅ Custom Watchlist & Holdings</li>
            <li style={{ marginBottom: '14px', color: 'var(--text-secondary)' }}>❌ LightGBM 3-Class AI Forecasts</li>
            <li style={{ marginBottom: '14px', color: 'var(--text-secondary)' }}>❌ Institutional Smart Money Hunter</li>
            <li style={{ marginBottom: '14px', color: 'var(--text-secondary)' }}>❌ Black-Scholes Greeks Engine</li>
          </ul>

          <button 
            disabled={true}
            style={{ 
              width: '100%', 
              padding: '12px', 
              background: 'var(--bg-color)', 
              border: '1px solid var(--border-color)', 
              color: 'var(--text-secondary)',
              borderRadius: '8px',
              cursor: 'not-allowed',
              fontWeight: 600
            }}
          >
            {isPro ? 'Included' : 'Current Plan'}
          </button>
        </div>

        {/* PRO TIER CARD */}
        <div style={{ 
          background: 'linear-gradient(145deg, var(--surface-color) 0%, rgba(59, 130, 246, 0.12) 100%)', 
          borderRadius: '14px', 
          padding: '32px',
          border: '2px solid #3b82f6',
          display: 'flex',
          flexDirection: 'column',
          position: 'relative',
          boxShadow: '0 8px 30px rgba(59, 130, 246, 0.15)'
        }}>
          <div style={{
            position: 'absolute',
            top: '-13px',
            right: '24px',
            background: 'linear-gradient(90deg, #3b82f6, #60a5fa)',
            color: 'white',
            padding: '4px 14px',
            borderRadius: '20px',
            fontSize: '0.8rem',
            fontWeight: 800,
            letterSpacing: '0.05em'
          }}>RECOMMENDED</div>
          
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <h2 style={{ fontSize: '1.6rem', fontWeight: 800, color: '#60a5fa' }}>StockAI PRO</h2>
            {isPro && (
              <span style={{ fontSize: '0.8rem', padding: '4px 10px', background: 'rgba(34,197,94,0.2)', color: '#4ade80', borderRadius: '20px', fontWeight: 700 }}>
                ACTIVE PRO
              </span>
            )}
          </div>

          <div style={{ fontSize: '2.4rem', fontWeight: 800, margin: '20px 0 10px' }}>
            $29<span style={{ fontSize: '1rem', color: 'var(--text-secondary)', fontWeight: 400 }}> / month (₹2,499)</span>
          </div>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.92rem', marginBottom: '24px' }}>
            Full quantitative intelligence, machine learning signals, and options analytics.
          </p>

          <ul style={{ listStyle: 'none', padding: 0, margin: '0 0 30px 0', flex: 1, fontSize: '0.95rem' }}>
            <li style={{ marginBottom: '14px' }}>✅ Everything in Free Tier</li>
            <li style={{ marginBottom: '14px', fontWeight: 600 }}>🚀 LightGBM + Attention ML Predictions</li>
            <li style={{ marginBottom: '14px', fontWeight: 600 }}>🏛️ Smart Money Concepts (SMC) Radar</li>
            <li style={{ marginBottom: '14px', fontWeight: 600 }}>📊 Institutional Options Greeks (Gamma/Delta)</li>
            <li style={{ marginBottom: '14px', fontWeight: 600 }}>⚡ Real-time Fyers WebSocket Feed</li>
            <li style={{ marginBottom: '14px', fontWeight: 600 }}>🛡️ Automated 24/7 Sentinel Watchdog</li>
          </ul>
          
          {isPro ? (
            <button 
              disabled={true}
              style={{ 
                width: '100%', 
                padding: '14px', 
                background: 'rgba(34,197,94,0.2)', 
                border: '1px solid #22c55e', 
                color: '#4ade80',
                borderRadius: '8px',
                fontWeight: 700,
                cursor: 'default'
              }}
            >
              🌟 PRO Membership Active
            </button>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {/* Pathway 1: Paid Subscription */}
              <button 
                onClick={() => setShowPayModal(true)}
                disabled={loading}
                style={{ 
                  width: '100%', 
                  padding: '13px', 
                  background: 'linear-gradient(90deg, #3b82f6, #2563eb)', 
                  border: 'none', 
                  color: 'white',
                  borderRadius: '8px',
                  cursor: 'pointer',
                  fontWeight: 700,
                  fontSize: '0.95rem',
                  boxShadow: '0 4px 14px rgba(37, 99, 235, 0.35)',
                  transition: 'transform 0.15s ease'
                }}
              >
                💳 Pay & Activate PRO ($29 / ₹2,499)
              </button>

              {/* Pathway 2: Admin Approval */}
              <button 
                onClick={() => setShowRequestModal(true)}
                disabled={loading || isPendingApproval}
                style={{ 
                  width: '100%', 
                  padding: '12px', 
                  background: isPendingApproval ? 'rgba(245, 158, 11, 0.1)' : 'transparent', 
                  border: isPendingApproval ? '1px solid #f59e0b' : '1px solid var(--border-color)', 
                  color: isPendingApproval ? '#fbbf24' : 'var(--text-color)',
                  borderRadius: '8px',
                  cursor: isPendingApproval ? 'default' : 'pointer',
                  fontWeight: 600,
                  fontSize: '0.9rem',
                }}
              >
                {isPendingApproval ? '🕒 Approval Request Pending' : '✍️ Request Admin Approval (Free Trial/Student)'}
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
            borderRadius: '16px',
            width: '100%',
            maxWidth: '480px',
            padding: '28px',
            boxShadow: '0 20px 40px rgba(0,0,0,0.4)'
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '18px' }}>
              <h3 style={{ fontSize: '1.3rem', fontWeight: 700 }}>Secure PRO Checkout</h3>
              <button 
                onClick={() => setShowPayModal(false)}
                style={{ background: 'none', border: 'none', color: 'var(--text-secondary)', fontSize: '1.4rem', cursor: 'pointer' }}
              >✕</button>
            </div>

            <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', marginBottom: '18px' }}>
              Subscription: <strong>StockAI PRO (1 Month)</strong> — Amount: <strong>$29.00 / ₹2,499</strong>
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
