import { Link, useNavigate } from 'react-router-dom'
import { ShieldCheck, FileText, ArrowLeft } from 'lucide-react'

interface LegalPageProps {
  mode: 'privacy' | 'terms'
}

export default function LegalPage({ mode }: LegalPageProps) {
  const navigate = useNavigate()
  const isPrivacy = mode === 'privacy'

  return (
    <div style={{ maxWidth: 820, margin: '0 auto', padding: '20px 12px 48px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 10, marginBottom: 20 }}>
        <button
          type="button"
          className="btn btn-secondary"
          onClick={() => navigate(-1)}
          style={{ fontSize: 12.5, padding: '6px 12px' }}
        >
          <ArrowLeft size={14} /> Back
        </button>

        <div style={{ display: 'flex', gap: 8 }}>
          <Link
            to="/privacy"
            className={`btn ${isPrivacy ? 'btn-primary' : 'btn-secondary'}`}
            style={{ fontSize: 12.5, textDecoration: 'none' }}
          >
            <ShieldCheck size={14} /> Privacy Policy
          </Link>
          <Link
            to="/terms"
            className={`btn ${!isPrivacy ? 'btn-primary' : 'btn-secondary'}`}
            style={{ fontSize: 12.5, textDecoration: 'none' }}
          >
            <FileText size={14} /> Terms of Use
          </Link>
        </div>
      </div>

      <div className="card" style={{ padding: 24, display: 'flex', flexDirection: 'column', gap: 18 }}>
        {isPrivacy ? (
          <>
            <div>
              <h1 className="page-title" style={{ marginBottom: 6 }}>Privacy Policy (DPDPA 2023 Notice)</h1>
              <p style={{ margin: 0, fontSize: 13, color: 'var(--color-text-muted)' }}>
                Effective Date: November 2026 · StockAI Research Platform
              </p>
            </div>

            <section>
              <h2 style={{ fontSize: 15, fontWeight: 700, marginBottom: 6 }}>1. Data We Process</h2>
              <p style={{ margin: 0, fontSize: 13.5, color: 'var(--color-text-secondary)', lineHeight: 1.6 }}>
                We collect only account identity fields required for authentication (name, email, hashed credentials or Google ID verification), user-configured watchlists, price alerts, paper-trading records, and security telemetry (IP timestamps and consent preferences) to safeguard accounts.
              </p>
            </section>

            <section>
              <h2 style={{ fontSize: 15, fontWeight: 700, marginBottom: 6 }}>2. Security &amp; Encryption Controls</h2>
              <p style={{ margin: 0, fontSize: 13.5, color: 'var(--color-text-secondary)', lineHeight: 1.6 }}>
                Authentication sessions use HttpOnly SameSite cookies paired with CSRF verification. Administrator credentials and optional authenticator secrets are encrypted at rest, and sensitive broker credentials are never returned to standard users or exposed in client code.
              </p>
            </section>

            <section>
              <h2 style={{ fontSize: 15, fontWeight: 700, marginBottom: 6 }}>3. Your Rights (Access, Export &amp; Erasure)</h2>
              <p style={{ margin: 0, fontSize: 13.5, color: 'var(--color-text-secondary)', lineHeight: 1.6 }}>
                Under India&apos;s Digital Personal Data Protection Act (DPDPA 2023), you may export a machine-readable JSON copy of your account records or permanently delete your account and personal records anytime from{' '}
                <Link to="/settings" style={{ fontWeight: 600 }}>Settings</Link>.
              </p>
            </section>

            <section style={{ display: 'flex', gap: 10, flexWrap: 'wrap', paddingTop: 6 }}>
              <button
                type="button"
                className="btn btn-secondary"
                style={{ fontSize: 12.5 }}
                onClick={() => window.dispatchEvent(new CustomEvent('open-cookie-settings'))}
              >
                Manage Cookie Preferences
              </button>
              <Link to="/settings" className="btn btn-primary" style={{ fontSize: 12.5, textDecoration: 'none' }}>
                Export or Delete Account Data
              </Link>
            </section>
          </>
        ) : (
          <>
            <div>
              <h1 className="page-title" style={{ marginBottom: 6 }}>Terms of Service &amp; Research Disclaimer</h1>
              <p style={{ margin: 0, fontSize: 13, color: 'var(--color-text-muted)' }}>
                Effective Date: November 2026 · StockAI Research Platform
              </p>
            </div>

            <section>
              <h2 style={{ fontSize: 15, fontWeight: 700, marginBottom: 6 }}>1. Educational Research &amp; Simulation Only</h2>
              <p style={{ margin: 0, fontSize: 13.5, color: 'var(--color-text-secondary)', lineHeight: 1.6 }}>
                StockAI is an independent quantitative analysis, technical charting, and virtual paper-trading platform for Indian NSE/BSE equities. It is not a SEBI-registered investment adviser or stock broker, and never places real-money exchange orders.
              </p>
            </section>

            <section>
              <h2 style={{ fontSize: 15, fontWeight: 700, marginBottom: 6 }}>2. Forecasts &amp; Market Data Latency</h2>
              <p style={{ margin: 0, fontSize: 13.5, color: 'var(--color-text-secondary)', lineHeight: 1.6 }}>
                All indicators, ML scores, Best Buy levels, Stop Loss estimates, and GTT bracket simulations carry inherent statistical uncertainty. Market quotes follow exchange hours (09:15–15:30 IST, Mon–Fri) and upstream feed availability.
              </p>
            </section>

            <section>
              <h2 style={{ fontSize: 15, fontWeight: 700, marginBottom: 6 }}>3. Acceptable Usage &amp; Quotas</h2>
              <p style={{ margin: 0, fontSize: 13.5, color: 'var(--color-text-secondary)', lineHeight: 1.6 }}>
                Automated scraping, rate-limit circumvention, prompt-injection probing, and credential sharing are prohibited. Plan rate limits and daily AI query quotas protect service stability for all users.
              </p>
            </section>
          </>
        )}
      </div>
    </div>
  )
}
