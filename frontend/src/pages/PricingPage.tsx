import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../AuthContext';
import { authApi } from '../services/api';
import './Auth.css';

export default function PricingPage() {
  const { user, upgradeToPro } = useAuth();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleUpgrade = async () => {
    if (!user) {
      navigate('/login');
      return;
    }
    
    setLoading(true);
    setError('');
    
    try {
      await authApi.upgrade();
      upgradeToPro();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to upgrade');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="pricing-container" style={{ padding: '40px 20px', maxWidth: '1000px', margin: '0 auto' }}>
      <div style={{ textAlign: 'center', marginBottom: '40px' }}>
        <h1 style={{ fontSize: '2.5rem', marginBottom: '10px' }}>Upgrade to PRO</h1>
        <p style={{ color: 'var(--text-secondary)', fontSize: '1.2rem' }}>
          Unlock the full power of our AI Stock Research platform.
        </p>
      </div>

      {error && (
        <div className="auth-alert error" style={{ marginBottom: '20px' }}>
          {error}
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '30px' }}>
        
        {/* FREE TIER */}
        <div style={{ 
          background: 'var(--surface-color)', 
          borderRadius: '12px', 
          padding: '30px',
          border: '1px solid var(--border-color)',
          display: 'flex',
          flexDirection: 'column'
        }}>
          <h2>Free</h2>
          <div style={{ fontSize: '2rem', fontWeight: 'bold', margin: '20px 0' }}>$0<span style={{ fontSize: '1rem', color: 'var(--text-secondary)' }}>/month</span></div>
          <ul style={{ listStyle: 'none', padding: 0, margin: '0 0 30px 0', flex: 1 }}>
            <li style={{ marginBottom: '15px' }}>✅ Live OHLCV Charts</li>
            <li style={{ marginBottom: '15px' }}>✅ Technical Indicators</li>
            <li style={{ marginBottom: '15px' }}>✅ Paper Trading</li>
            <li style={{ marginBottom: '15px' }}>✅ Watchlist & Portfolio</li>
            <li style={{ marginBottom: '15px', color: 'var(--text-secondary)' }}>❌ AI Probability Score</li>
            <li style={{ marginBottom: '15px', color: 'var(--text-secondary)' }}>❌ NLP News Sentiment</li>
            <li style={{ marginBottom: '15px', color: 'var(--text-secondary)' }}>❌ Strategy Backtesting</li>
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
              cursor: 'not-allowed'
            }}
          >
            {user?.subscription_tier === 'FREE' ? 'Current Plan' : 'Free Tier'}
          </button>
        </div>

        {/* PRO TIER */}
        <div style={{ 
          background: 'linear-gradient(145deg, var(--surface-color) 0%, rgba(33, 150, 243, 0.1) 100%)', 
          borderRadius: '12px', 
          padding: '30px',
          border: '2px solid var(--primary-color)',
          display: 'flex',
          flexDirection: 'column',
          position: 'relative'
        }}>
          <div style={{
            position: 'absolute',
            top: '-15px',
            right: '20px',
            background: 'var(--primary-color)',
            color: 'white',
            padding: '5px 15px',
            borderRadius: '20px',
            fontSize: '0.85rem',
            fontWeight: 'bold'
          }}>RECOMMENDED</div>
          
          <h2>PRO</h2>
          <div style={{ fontSize: '2rem', fontWeight: 'bold', margin: '20px 0' }}>$29<span style={{ fontSize: '1rem', color: 'var(--text-secondary)' }}>/month</span></div>
          <ul style={{ listStyle: 'none', padding: 0, margin: '0 0 30px 0', flex: 1 }}>
            <li style={{ marginBottom: '15px' }}>✅ Everything in Free</li>
            <li style={{ marginBottom: '15px', fontWeight: 'bold' }}>🚀 LightGBM AI Predictions</li>
            <li style={{ marginBottom: '15px', fontWeight: 'bold' }}>📰 Real-time NLP Sentiment</li>
            <li style={{ marginBottom: '15px', fontWeight: 'bold' }}>📈 Unlimited Backtesting</li>
            <li style={{ marginBottom: '15px', fontWeight: 'bold' }}>💡 SHAP Feature Explanations</li>
          </ul>
          
          <button 
            onClick={handleUpgrade}
            disabled={loading || user?.subscription_tier === 'PRO'}
            style={{ 
              width: '100%', 
              padding: '12px', 
              background: user?.subscription_tier === 'PRO' ? 'var(--success-color)' : 'var(--primary-color)', 
              border: 'none', 
              color: 'white',
              borderRadius: '8px',
              cursor: user?.subscription_tier === 'PRO' ? 'default' : 'pointer',
              fontWeight: 'bold',
              transition: 'all 0.3s'
            }}
          >
            {loading ? 'Processing...' : user?.subscription_tier === 'PRO' ? 'You are PRO' : 'Upgrade to PRO'}
          </button>
        </div>

      </div>
    </div>
  );
}
