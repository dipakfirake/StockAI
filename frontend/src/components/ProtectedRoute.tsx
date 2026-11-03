import { ReactNode } from 'react';
import { Navigate, useLocation, Link } from 'react-router-dom';
import { useAuth } from '../AuthContext';
import { ShieldAlert } from 'lucide-react';

interface ProtectedRouteProps {
  children: ReactNode;
  adminOnly?: boolean;
}

export default function ProtectedRoute({ children, adminOnly = false }: ProtectedRouteProps) {
  const { user, loading } = useAuth();
  const location = useLocation();

  // If loading and there is NO cached user, show a smooth dark-mode spinner
  if (loading && !localStorage.getItem('auth_user_cache')) {
    return (
      <div style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: '60vh',
        gap: '16px',
        color: 'var(--color-text-secondary, #94a3b8)'
      }}>
        <div style={{
          width: '36px',
          height: '36px',
          border: '3px solid rgba(59, 130, 246, 0.2)',
          borderTop: '3px solid #3b82f6',
          borderRadius: '50%',
          animation: 'spin 1s linear infinite'
        }} />
        <span style={{ fontSize: '0.9rem', fontWeight: 500 }}>Authenticating session...</span>
        <style>{`
          @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
          }
        `}</style>
      </div>
    );
  }

  // If neither memory user nor localStorage auth token exists, redirect to login
  if (!user && !localStorage.getItem('auth_token')) {
    const returnUrl = location.pathname !== '/login' ? location.pathname : '/dashboard';
    return <Navigate to={`/login?redirect=${encodeURIComponent(returnUrl)}`} replace />;
  }

  // Enforce Administrator Privilege Check if route is marked adminOnly
  if (adminOnly && !user?.is_admin) {
    return (
      <div style={{ maxWidth: '600px', margin: '80px auto', textAlign: 'center', padding: '30px' }}>
        <div style={{
          width: 64,
          height: 64,
          margin: '0 auto 16px',
          borderRadius: '50%',
          background: 'rgba(239, 68, 68, 0.15)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: '#ef4444'
        }}>
          <ShieldAlert size={36} />
        </div>
        <h2 style={{ color: '#ef4444', fontSize: 24, fontWeight: 800, margin: '0 0 12px 0' }}>
          Administrator Access Required
        </h2>
        <p style={{ color: 'var(--color-text-secondary, #94a3b8)', fontSize: '0.95rem', lineHeight: 1.6, margin: '0 0 24px 0' }}>
          This area contains privileged system telemetry, cybersecurity operations, and administrative controls restricted strictly to verified platform administrators.
        </p>
        <Link
          to="/dashboard"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 8,
            background: 'rgba(59, 130, 246, 0.15)',
            border: '1px solid rgba(59, 130, 246, 0.3)',
            color: '#60a5fa',
            padding: '10px 20px',
            borderRadius: 8,
            fontWeight: 600,
            textDecoration: 'none'
          }}
        >
          Return to Dashboard
        </Link>
      </div>
    );
  }

  return <>{children}</>;
}
