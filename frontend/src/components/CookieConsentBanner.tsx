import React, { useState, useEffect } from 'react'
import './CookieConsentBanner.css'

export interface CookiePreferences {
  essential: boolean
  security: boolean
  location: boolean
  timestamp: string
  version: string
}

const COOKIE_NAME = 'dpdpa_consent_v1'
const LOCAL_STORAGE_KEY = 'stockai_dpdpa_consent'

function getStoredConsent(): CookiePreferences | null {
  try {
    // 1. Check Cookie
    const match = document.cookie.match(new RegExp('(^| )' + COOKIE_NAME + '=([^;]+)'))
    if (match) {
      return JSON.parse(decodeURIComponent(match[2]))
    }
    // 2. Check LocalStorage fallback
    const local = localStorage.getItem(LOCAL_STORAGE_KEY)
    if (local) {
      return JSON.parse(local)
    }
  } catch (err) {
    console.warn('Error reading cookie consent:', err)
  }
  return null
}

function persistConsent(pref: CookiePreferences) {
  try {
    const serialized = encodeURIComponent(JSON.stringify(pref))
    // Store in cookie for 1 year, SameSite=Lax
    document.cookie = `${COOKIE_NAME}=${serialized}; max-age=${365 * 24 * 60 * 60}; path=/; SameSite=Lax`
    localStorage.setItem(LOCAL_STORAGE_KEY, JSON.stringify(pref))
  } catch (err) {
    console.error('Error persisting cookie consent:', err)
  }
}

export const CookieConsentBanner: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false)
  const [showCustomize, setShowCustomize] = useState(false)
  const [preferences, setPreferences] = useState<CookiePreferences>({
    essential: true,
    security: true,
    location: false,
    timestamp: new Date().toISOString(),
    version: '2023.1'
  })

  useEffect(() => {
    const existing = getStoredConsent()
    if (!existing) {
      // First time visitor, display banner
      setIsOpen(true)
    } else {
      setPreferences(existing)
      // If user previously consented to location, we can refresh position if requested
      if (existing.location && navigator.geolocation) {
        requestGeoLocation(false)
      }
    }

    // Global listener so user can open settings from footer or profile anytime
    const handleReopen = () => {
      setIsOpen(true)
      setShowCustomize(true)
    }
    window.addEventListener('open-cookie-settings', handleReopen)
    return () => window.removeEventListener('open-cookie-settings', handleReopen)
  }, [])

  const requestGeoLocation = (promptUser = true) => {
    if (!navigator.geolocation) return
    navigator.geolocation.getCurrentPosition(
      (position) => {
        const geoData = {
          lat: position.coords.latitude,
          lon: position.coords.longitude,
          accuracy: position.coords.accuracy,
          recordedAt: new Date().toISOString()
        }
        sessionStorage.setItem('stockai_geo_telemetry', JSON.stringify(geoData))
      },
      (error) => {
        if (promptUser) {
          console.log('Location access not granted:', error.message)
        }
      },
      { timeout: 8000, maximumAge: 60000 }
    )
  }

  const handleAcceptAll = () => {
    const newPref: CookiePreferences = {
      essential: true,
      security: true,
      location: true,
      timestamp: new Date().toISOString(),
      version: '2023.1'
    }
    setPreferences(newPref)
    persistConsent(newPref)
    setIsOpen(false)
    setShowCustomize(false)
    requestGeoLocation(true)
  }

  const handleEssentialOnly = () => {
    const newPref: CookiePreferences = {
      essential: true,
      security: false,
      location: false,
      timestamp: new Date().toISOString(),
      version: '2023.1'
    }
    setPreferences(newPref)
    persistConsent(newPref)
    setIsOpen(false)
    setShowCustomize(false)
    sessionStorage.removeItem('stockai_geo_telemetry')
  }

  const handleSaveCustom = () => {
    const updatedPref: CookiePreferences = {
      ...preferences,
      essential: true, // Always required
      timestamp: new Date().toISOString()
    }
    persistConsent(updatedPref)
    setIsOpen(false)
    setShowCustomize(false)
    if (updatedPref.location) {
      requestGeoLocation(true)
    } else {
      sessionStorage.removeItem('stockai_geo_telemetry')
    }
  }

  return (
    <>
      {/* Floating Re-Open Button for DPDPA Ongoing Consent Modification */}
      {!isOpen && (
        <button
          className="cookie-revisit-badge"
          onClick={() => {
            setShowCustomize(true)
            setIsOpen(true)
          }}
          title="Review Indian DPDPA 2023 Privacy & Cookie Settings"
          aria-label="Privacy & Cookie Preferences"
        >
          <span>🛡️</span>
          <span>Privacy & Cookies</span>
        </button>
      )}

      {/* Main Consent Banner Modal/Popup */}
      {isOpen && (
        <div className="cookie-consent-overlay" role="dialog" aria-modal="true" aria-labelledby="cookie-title">
          <div className="cookie-consent-card">
            <div className="cookie-consent-header">
              <div className="cookie-consent-icon-badge">
                <span>🍪</span>
              </div>
              <div className="cookie-consent-title-wrap">
                <h3 id="cookie-title" className="cookie-consent-title">
                  Privacy & Cookie Notice
                  <span className="cookie-consent-badge-gov">DPDPA 2023 Compliant</span>
                </h3>
              </div>
            </div>

            <p className="cookie-consent-text">
              Under India's <span className="cookie-consent-legal-ref">Digital Personal Data Protection Act (DPDPA 2023)</span> and{' '}
              <span className="cookie-consent-legal-ref">IT Act 2000 (SPDI Rules)</span>, we provide transparent notice and full control over your data. We use cookies and security signals to protect financial accounts and detect unauthorized access.
            </p>

            {/* Granular Preferences Drawer */}
            {showCustomize && (
              <div className="cookie-preferences-drawer">
                {/* 1. Essential Cookies */}
                <div className="cookie-pref-item">
                  <div className="cookie-pref-info">
                    <div className="cookie-pref-name-row">
                      <span className="cookie-pref-label">Strictly Necessary Cookies</span>
                      <span className="cookie-pref-tag required">Required</span>
                    </div>
                    <p className="cookie-pref-desc">
                      Essential for authentication, CSRF security, and trade execution. Cannot be switched off.
                    </p>
                  </div>
                  <label className="cookie-toggle">
                    <input type="checkbox" checked={true} disabled aria-label="Strictly Necessary Cookies" />
                    <span className="cookie-toggle-slider"></span>
                  </label>
                </div>

                {/* 2. Security & Fraud Detection */}
                <div className="cookie-pref-item">
                  <div className="cookie-pref-info">
                    <div className="cookie-pref-name-row">
                      <span className="cookie-pref-label">Security & Fraud Detection</span>
                      <span className="cookie-pref-tag optin">Recommended</span>
                    </div>
                    <p className="cookie-pref-desc">
                      Detects impossible-travel velocity, session hijacking, and credential stuffing per CERT-In & SEBI CSCRF guidelines.
                    </p>
                  </div>
                  <label className="cookie-toggle">
                    <input
                      type="checkbox"
                      checked={preferences.security}
                      onChange={(e) => setPreferences({ ...preferences, security: e.target.checked })}
                      aria-label="Security and Fraud Detection"
                    />
                    <span className="cookie-toggle-slider"></span>
                  </label>
                </div>

                {/* 3. Precise Location (GPS) */}
                <div className="cookie-pref-item">
                  <div className="cookie-pref-info">
                    <div className="cookie-pref-name-row">
                      <span className="cookie-pref-label">Precise Location Verification</span>
                      <span className="cookie-pref-tag optin">Opt-in</span>
                    </div>
                    <p className="cookie-pref-desc">
                      Allows browser GPS verification to detect anomalous logins and protect against account takeover from unfamiliar regions.
                    </p>
                  </div>
                  <label className="cookie-toggle">
                    <input
                      type="checkbox"
                      checked={preferences.location}
                      onChange={(e) => setPreferences({ ...preferences, location: e.target.checked })}
                      aria-label="Precise Location Verification"
                    />
                    <span className="cookie-toggle-slider"></span>
                  </label>
                </div>
              </div>
            )}

            {/* Actions */}
            <div className="cookie-consent-actions">
              {showCustomize ? (
                <>
                  <button className="btn-cookie-primary" onClick={handleSaveCustom}>
                    Save Preferences
                  </button>
                  <button className="btn-cookie-secondary" onClick={handleAcceptAll}>
                    Accept All
                  </button>
                  <button className="btn-cookie-ghost" onClick={() => setShowCustomize(false)}>
                    Back
                  </button>
                </>
              ) : (
                <>
                  <button className="btn-cookie-primary" onClick={handleAcceptAll}>
                    Accept All
                  </button>
                  <button className="btn-cookie-secondary" onClick={handleEssentialOnly}>
                    Essential Only
                  </button>
                  <button className="btn-cookie-ghost" onClick={() => setShowCustomize(true)}>
                    Customize
                  </button>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  )
}

export default CookieConsentBanner
