import React from 'react'
import { AlertTriangle, RotateCcw, Home } from 'lucide-react'

interface ErrorBoundaryProps {
  children: React.ReactNode
  sectionLabel?: string
}

interface ErrorBoundaryState {
  hasError: boolean
  errorMessage: string
}

/**
 * Production React ErrorBoundary preventing single-component exceptions
 * from blanking out the entire trading application.
 */
export default class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props)
    this.state = { hasError: false, errorMessage: '' }
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return {
      hasError: true,
      errorMessage: error?.message || 'Unexpected rendering error',
    }
  }

  componentDidCatch(error: Error, info: React.ErrorInfo): void {
    console.error('[ErrorBoundary]', this.props.sectionLabel || 'App', error, info.componentStack)
  }

  handleReset = () => {
    this.setState({ hasError: false, errorMessage: '' })
  }

  render() {
    if (this.state.hasError) {
      return (
        <div
          role="alert"
          style={{
            margin: '32px auto',
            maxWidth: 520,
            padding: 24,
            borderRadius: 12,
            background: 'var(--color-bg-card)',
            border: '1px solid var(--color-border)',
            boxShadow: 'var(--shadow-card)',
            textAlign: 'center',
          }}
        >
          <div style={{ display: 'inline-flex', padding: 10, borderRadius: '50%', background: 'rgba(239, 68, 68, 0.12)', color: 'var(--color-bearish)', marginBottom: 12 }}>
            <AlertTriangle size={24} />
          </div>
          <h2 style={{ margin: '0 0 8px', fontSize: 18, fontWeight: 700, color: 'var(--color-text-primary)' }}>
            Something went wrong
          </h2>
          <p style={{ margin: '0 0 16px', fontSize: 13.5, color: 'var(--color-text-secondary)', lineHeight: 1.5 }}>
            {this.props.sectionLabel ? `${this.props.sectionLabel} encountered an unexpected error.` : 'This section encountered an unexpected error.'} Your workspace state and data remain intact.
          </p>
          {this.state.errorMessage && (
            <div
              className="mono"
              style={{
                fontSize: 11.5,
                padding: '8px 10px',
                marginBottom: 16,
                borderRadius: 6,
                background: 'var(--color-bg-secondary)',
                border: '1px solid var(--color-border)',
                color: 'var(--color-text-muted)',
                wordBreak: 'break-word',
              }}
            >
              {this.state.errorMessage}
            </div>
          )}
          <div style={{ display: 'flex', justifyContent: 'center', gap: 10, flexWrap: 'wrap' }}>
            <button type="button" className="btn btn-primary" onClick={this.handleReset}>
              <RotateCcw size={14} /> Try Again
            </button>
            <a href="/dashboard" className="btn btn-secondary" style={{ textDecoration: 'none' }}>
              <Home size={14} /> Go to Dashboard
            </a>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}
