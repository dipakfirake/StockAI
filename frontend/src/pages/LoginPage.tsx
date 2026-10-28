import { useState, useEffect, useRef } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '../AuthContext'
import { authApi } from '../services/api'
import { Mail, ShieldCheck, ArrowLeft, RefreshCw, Clock, CheckCircle2, Circle } from 'lucide-react'
import {
  validateEmail,
  evaluatePasswordStrength,
  sanitizeDisplayName,
  validateOtpCode,
  formatTimeRemaining
} from '../utils/validators'
import './Auth.css'

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (config: any) => void
          renderButton: (parent: HTMLElement | null, options: any) => void
          prompt: () => void
        }
      }
    }
  }
}

export default function LoginPage() {
  const [isLogin, setIsLogin] = useState(true)
  const [regStep, setRegStep] = useState<'FORM' | 'OTP'>('FORM')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [otp, setOtp] = useState('')
  const [error, setError] = useState('')
  const [successMsg, setSuccessMsg] = useState('')
  const [loading, setLoading] = useState(false)
  const [otpCountdown, setOtpCountdown] = useState(0)
  const [otpExpiresIn, setOtpExpiresIn] = useState(300)
  const [googleClientId, setGoogleClientId] = useState<string | null>(null)
  
  const googleBtnRef = useRef<HTMLDivElement>(null)
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const redirectTarget = searchParams.get('redirect') || '/dashboard'
  const { login } = useAuth()

  // 1. Fetch public Google Client ID configuration
  useEffect(() => {
    let isMounted = true
    authApi.getConfig()
      .then((res) => {
        if (isMounted && res.data?.google_client_id) {
          setGoogleClientId(res.data.google_client_id)
        }
      })
      .catch(() => {})
    return () => { isMounted = false }
  }, [])

  // 2. Load Google Identity Services SDK script dynamically
  useEffect(() => {
    if (!googleClientId) return

    const existingScript = document.getElementById('google-gsi-script')
    if (!existingScript) {
      const script = document.createElement('script')
      script.id = 'google-gsi-script'
      script.src = 'https://accounts.google.com/gsi/client'
      script.async = true
      script.defer = true
      script.onload = () => initGoogleBtn()
      document.body.appendChild(script)
    } else {
      initGoogleBtn()
    }

    function initGoogleBtn() {
      if (window.google && googleBtnRef.current) {
        try {
          window.google.accounts.id.initialize({
            client_id: googleClientId,
            callback: handleGoogleCredentialResponse,
            auto_select: false,
          })
          window.google.accounts.id.renderButton(googleBtnRef.current, {
            theme: 'filled_black',
            size: 'large',
            width: 336,
            text: isLogin ? 'signin_with' : 'signup_with',
            shape: 'rectangular',
          })
        } catch (e) {
          console.warn('Google Identity button init notice:', e)
        }
      }
    }
  }, [googleClientId, isLogin, regStep])

  // Handle Google OAuth Token Response
  const handleGoogleCredentialResponse = async (response: any) => {
    if (!response?.credential) return
    setError('')
    setSuccessMsg('')
    setLoading(true)

    try {
      const res = await authApi.googleAuth(response.credential)
      await login(res.data.access_token, res.data.user)
      navigate(redirectTarget)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Google sign-in failed. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  // 3. Countdown timer for OTP resend cooldown (60s)
  useEffect(() => {
    if (otpCountdown <= 0) return
    const timer = setInterval(() => {
      setOtpCountdown((prev) => prev - 1)
    }, 1000)
    return () => clearInterval(timer)
  }, [otpCountdown])

  // 4. Strict 5-minute (300s) OTP Expiration Countdown Timer
  useEffect(() => {
    if (regStep !== 'OTP' || otpExpiresIn <= 0) return
    const timer = setInterval(() => {
      setOtpExpiresIn((prev) => Math.max(0, prev - 1))
    }, 1000)
    return () => clearInterval(timer)
  }, [regStep, otpExpiresIn])

  // Real-time evaluation of input credentials
  const emailVal = validateEmail(email)
  const nameVal = sanitizeDisplayName(name)
  const pwdCriteria = evaluatePasswordStrength(password)

  // Form Submit handler
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setSuccessMsg('')

    if (!isLogin) {
      if (!nameVal.isValid) {
        setError(nameVal.error || 'Please enter a valid full name.')
        return
      }
      if (!emailVal.isValid) {
        setError(emailVal.error || 'Please enter a valid email address.')
        return
      }
      if (!pwdCriteria.isStrong) {
        setError('Password must meet all complexity requirements before continuing.')
        return
      }
    }

    setLoading(true)

    try {
      if (isLogin) {
        // --- LOGIN FLOW ---
        const res = await authApi.login(email.trim(), password)
        await login(res.data.access_token, res.data.user)
        navigate(redirectTarget)
      } else {
        // --- REGISTRATION STEP 1: SEND OTP ---
        const res = await authApi.sendRegistrationOtp({
          email: email.trim(),
          name: nameVal.sanitized,
          password
        })
        setRegStep('OTP')
        setOtpCountdown(res.data?.cooldown_seconds || 60)
        setOtpExpiresIn(res.data?.expires_in || 300)
        setSuccessMsg(res.data?.message || `Verification code sent to ${email}`)
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || 'An error occurred. Please check your credentials.')
    } finally {
      setLoading(false)
    }
  }

  // OTP Verification Submit handler
  const handleVerifyOtp = async (e: React.FormEvent) => {
    e.preventDefault()

    if (otpExpiresIn <= 0) {
      setError('Verification code has expired. Please click "Resend verification code" below.')
      return
    }

    if (!validateOtpCode(otp)) {
      setError('Please enter the full 6-digit numeric verification code.')
      return
    }

    setError('')
    setSuccessMsg('')
    setLoading(true)

    try {
      const res = await authApi.verifyRegistrationOtp({ email: email.trim(), otp: otp.trim() })
      setSuccessMsg('Email successfully verified! Redirecting to your dashboard...')
      await login(res.data.access_token, res.data.user)
      setTimeout(() => navigate(redirectTarget), 400)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Invalid or expired verification code. Please check and retry.')
    } finally {
      setLoading(false)
    }
  }

  // Resend OTP handler
  const handleResendOtp = async () => {
    if (otpCountdown > 0) return
    setError('')
    setSuccessMsg('')
    setLoading(true)

    try {
      const res = await authApi.sendRegistrationOtp({
        email: email.trim(),
        name: nameVal.sanitized,
        password
      })
      setOtpCountdown(res.data?.cooldown_seconds || 60)
      setOtpExpiresIn(res.data?.expires_in || 300)
      setSuccessMsg(`A fresh verification code was sent to ${email}`)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to resend code. Please wait a moment.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="auth-container">
      <div className="auth-card">
        <h2>
          {isLogin
            ? 'Login to AI Stock Research'
            : regStep === 'OTP'
            ? 'Verify Your Email'
            : 'Create an Account'}
        </h2>

        {/* Status Alerts */}
        {error && <div className="auth-alert error">{error}</div>}
        {successMsg && <div className="auth-alert success">{successMsg}</div>}

        {/* =========================================================================
            REGISTRATION STEP 2: 6-DIGIT EMAIL OTP FORM
           ========================================================================= */}
        {!isLogin && regStep === 'OTP' ? (
          <form onSubmit={handleVerifyOtp} className="auth-form">
            <div className="otp-header">
              <Mail size={32} color="#38bdf8" style={{ marginBottom: 6 }} />
              <p>
                We sent a 6-digit confirmation code to{' '}
                <span className="otp-target-email">{email}</span>.
                Enter it below to complete registration.
              </p>
              <div className="otp-expiry-container">
                <span className={`otp-expiry-badge ${otpExpiresIn <= 0 ? 'expired' : otpExpiresIn <= 60 ? 'warning' : ''}`}>
                  <Clock size={13} />
                  {otpExpiresIn <= 0 ? (
                    'Verification code expired'
                  ) : (
                    `Code expires in ${formatTimeRemaining(otpExpiresIn)}`
                  )}
                </span>
              </div>
            </div>

            {otpExpiresIn <= 0 && (
              <div className="auth-alert error" style={{ fontSize: '0.8rem', marginTop: 10 }}>
                ⚠️ Verification code has expired. Please click "Resend verification code" below to request a new code.
              </div>
            )}

            <div className="form-group">
              <label>Verification Code</label>
              <input
                type="text"
                maxLength={6}
                value={otp}
                onChange={(e) => setOtp(e.target.value.replace(/\D/g, ''))}
                placeholder="123456"
                className="otp-input-field"
                autoFocus
                disabled={otpExpiresIn <= 0}
                required
              />
            </div>

            <button
              type="submit"
              disabled={loading || otp.length < 6 || otpExpiresIn <= 0}
              className="auth-button"
            >
              {loading
                ? 'Verifying Code...'
                : otpExpiresIn <= 0
                ? 'Code Expired — Resend Below'
                : 'Verify & Complete Registration'}
            </button>

            <div className="otp-actions">
              <button
                type="button"
                onClick={handleResendOtp}
                disabled={otpCountdown > 0 || loading}
                className="otp-resend-btn"
              >
                {otpCountdown > 0 ? (
                  `Resend code in ${otpCountdown}s`
                ) : (
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                    <RefreshCw size={13} /> Resend verification code
                  </span>
                )}
              </button>

              <button
                type="button"
                onClick={() => { setRegStep('FORM'); setError(''); setSuccessMsg(''); }}
                className="otp-back-btn"
              >
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                  <ArrowLeft size={13} /> Edit credentials
                </span>
              </button>
            </div>
          </form>
        ) : (
          /* =========================================================================
             STANDARD LOGIN / REGISTRATION FORM
             ========================================================================= */
          <>
            {/* Google OAuth Button */}
            <div className="auth-google-wrapper">
              <div ref={googleBtnRef} id="google-btn-container" style={{ minHeight: 40 }} />
              
              {!googleClientId && (
                <button
                  type="button"
                  className="auth-google-custom-btn"
                  onClick={() => setError('Google Sign-In ready: configure GOOGLE_CLIENT_ID in your environment or settings to activate.')}
                >
                  <svg width="18" height="18" viewBox="0 0 24 24">
                    <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
                    <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
                    <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z" />
                    <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z" />
                  </svg>
                  {isLogin ? 'Sign in with Google' : 'Sign up with Google'}
                </button>
              )}
            </div>

            <div className="auth-divider">
              <span>or with email</span>
            </div>

            <form onSubmit={handleSubmit} className="auth-form">
              {!isLogin && (
                <div className="form-group">
                  <label>Full Name</label>
                  <input
                    type="text"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="Enter your name"
                    required
                  />
                  {name.length > 0 && !nameVal.isValid && (
                    <div className="field-hint-error">{nameVal.error}</div>
                  )}
                </div>
              )}

              <div className="form-group">
                <label>Email Address</label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="name@example.com"
                  required
                />
                {!isLogin && email.length > 3 && !emailVal.isValid && (
                  <div className="field-hint-error">{emailVal.error}</div>
                )}
              </div>

              <div className="form-group">
                <label>Password</label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Minimum 8 characters"
                  required
                />
                {!isLogin && password.length > 0 && (
                  <div className="password-checklist">
                    <div className={`checklist-item ${pwdCriteria.hasMinLength ? 'valid' : ''}`}>
                      {pwdCriteria.hasMinLength ? <CheckCircle2 size={13} /> : <Circle size={13} />}
                      <span>8 to 128 characters</span>
                    </div>
                    <div className={`checklist-item ${pwdCriteria.hasLetter ? 'valid' : ''}`}>
                      {pwdCriteria.hasLetter ? <CheckCircle2 size={13} /> : <Circle size={13} />}
                      <span>At least 1 letter (a-z, A-Z)</span>
                    </div>
                    <div className={`checklist-item ${pwdCriteria.hasDigitOrSpecial ? 'valid' : ''}`}>
                      {pwdCriteria.hasDigitOrSpecial ? <CheckCircle2 size={13} /> : <Circle size={13} />}
                      <span>At least 1 number or special character</span>
                    </div>
                  </div>
                )}
              </div>

              <button
                type="submit"
                disabled={loading || (!isLogin && (!nameVal.isValid || !emailVal.isValid || !pwdCriteria.isStrong))}
                className="auth-button"
              >
                {loading
                  ? 'Processing...'
                  : isLogin
                  ? 'Sign In'
                  : 'Send Verification Code'}
              </button>
            </form>
          </>
        )}

        {/* Toggle between Login and Register */}
        <p className="auth-toggle">
          {isLogin ? "Don't have an account? " : 'Already have an account? '}
          <span
            onClick={() => {
              setIsLogin(!isLogin)
              setRegStep('FORM')
              setError('')
              setSuccessMsg('')
            }}
          >
            {isLogin ? 'Register with verified email' : 'Sign in here'}
          </span>
        </p>

        {/* Trust badge */}
        <div style={{ marginTop: '1.2rem', textAlign: 'center', fontSize: '0.75rem', color: 'var(--color-text-muted)', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5 }}>
          <ShieldCheck size={14} color="#10b981" />
          <span>Real-time Anti-Bot & Email Authenticity Protected</span>
        </div>
      </div>
    </div>
  )
}
