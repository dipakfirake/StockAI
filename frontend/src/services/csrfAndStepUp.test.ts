import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import api, { setAdminStepUpToken, getAdminStepUpToken } from './api'

describe('Security Request Interceptors: Double-Submit CSRF & Admin Step-Up Token', () => {
  const cookieStore = { cookie: '' }
  const lsMap = new Map<string, string>()

  beforeEach(() => {
    setAdminStepUpToken(null)
    cookieStore.cookie = ''
    lsMap.clear()
    vi.stubGlobal('document', cookieStore)
    vi.stubGlobal('localStorage', {
      getItem: (k: string) => lsMap.get(k) ?? null,
      setItem: (k: string, v: string) => {
        lsMap.set(k, String(v))
      },
      removeItem: (k: string) => {
        lsMap.delete(k)
      },
      clear: () => {
        lsMap.clear()
      },
    })
  })

  afterEach(() => {
    setAdminStepUpToken(null)
    vi.unstubAllGlobals()
  })

  it('enables withCredentials for HttpOnly session cookie transport', () => {
    expect(api.defaults.withCredentials).toBe(true)
  })

  it('injects X-CSRF-Token from cookie on unsafe HTTP methods without touching localStorage auth_token', async () => {
    cookieStore.cookie = 'stockai_csrf_token=csrf_demo_token_abc123'
    localStorage.setItem('auth_token', 'should_never_be_used')

    const handlers = (api.interceptors.request as any).handlers || []
    const reqFulfilled = handlers[0]?.fulfilled
    expect(typeof reqFulfilled).toBe('function')

    const postConfig = await reqFulfilled({
      method: 'post',
      url: '/admin/broadcast-notice',
      headers: {},
    })

    expect(postConfig.headers['X-CSRF-Token']).toBe('csrf_demo_token_abc123')
    expect(postConfig.headers.Authorization).toBeUndefined()
  })

  it('skips X-CSRF-Token on safe GET requests', async () => {
    cookieStore.cookie = 'stockai_csrf_token=csrf_demo_token_xyz'
    const handlers = (api.interceptors.request as any).handlers || []
    const reqFulfilled = handlers[0]?.fulfilled

    const getConfig = await reqFulfilled({
      method: 'get',
      url: '/auth/me',
      headers: {},
    })
    expect(getConfig.headers['X-CSRF-Token']).toBeUndefined()
  })

  it('stores short-lived Admin Step-Up Token in memory only and attaches X-Admin-StepUp-Token', async () => {
    setAdminStepUpToken('stepup_jwt_valid_123', 600)
    expect(getAdminStepUpToken()).toBe('stepup_jwt_valid_123')
    expect(localStorage.getItem('stepup_jwt_valid_123')).toBeNull()

    const handlers = (api.interceptors.request as any).handlers || []
    const reqFulfilled = handlers[0]?.fulfilled
    const config = await reqFulfilled({
      method: 'post',
      url: '/admin/users/123/set-admin',
      headers: {},
    })
    expect(config.headers['X-Admin-StepUp-Token']).toBe('stepup_jwt_valid_123')

    setAdminStepUpToken(null)
    expect(getAdminStepUpToken()).toBeNull()
  })
})
