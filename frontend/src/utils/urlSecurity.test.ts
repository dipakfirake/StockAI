import { describe, it, expect, vi, afterEach } from 'vitest'
import { sanitizeBrowserUrl } from './urlSecurity'

describe('sanitizeBrowserUrl', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('scrubs exposed query strings like ?tab=threats or ?redirect=/admin cleanly', () => {
    const replaceState = vi.fn()
    vi.stubGlobal('window', {
      location: { pathname: '/admin', search: '?tab=threats' },
      history: { replaceState },
    })

    sanitizeBrowserUrl('/admin')
    expect(replaceState).toHaveBeenCalledTimes(1)
    expect(replaceState).toHaveBeenCalledWith({}, '', '/admin')
  })

  it('does not rewrite history when route is already clean', () => {
    const replaceState = vi.fn()
    vi.stubGlobal('window', {
      location: { pathname: '/alerts', search: '' },
      history: { replaceState },
    })

    sanitizeBrowserUrl('/alerts')
    expect(replaceState).not.toHaveBeenCalled()
  })
})
