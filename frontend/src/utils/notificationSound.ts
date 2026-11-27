/**
 * Notification Sound Synthesizer & Desktop Push Utility.
 * Uses native Web Audio API chimes (zero external MP3 asset dependencies)
 * and standard browser Notifications API with persistent user preferences.
 */

const SOUND_PREF_KEY = 'stockai_notif_sound_enabled'
const PUSH_PREF_KEY = 'stockai_notif_push_enabled'

export function isNotifSoundEnabled(): boolean {
  try {
    const val = localStorage.getItem(SOUND_PREF_KEY)
    return val === null ? true : val === 'true'
  } catch {
    return true
  }
}

export function setNotifSoundEnabled(enabled: boolean): void {
  try {
    localStorage.setItem(SOUND_PREF_KEY, String(enabled))
    window.dispatchEvent(new CustomEvent('stockai:notif-prefs-changed'))
  } catch {
    // ignore storage limits
  }
}

export function isNotifPushEnabled(): boolean {
  try {
    return localStorage.getItem(PUSH_PREF_KEY) === 'true'
  } catch {
    return false
  }
}

export function setNotifPushEnabled(enabled: boolean): void {
  try {
    localStorage.setItem(PUSH_PREF_KEY, String(enabled))
    window.dispatchEvent(new CustomEvent('stockai:notif-prefs-changed'))
  } catch {
    // ignore storage limits
  }
}

export async function requestDesktopPushPermission(): Promise<boolean> {
  if (typeof window === 'undefined' || !('Notification' in window)) {
    return false
  }
  if (Notification.permission === 'granted') {
    setNotifPushEnabled(true)
    return true
  }
  if (Notification.permission === 'denied') {
    setNotifPushEnabled(false)
    return false
  }
  try {
    const result = await Notification.requestPermission()
    const granted = result === 'granted'
    setNotifPushEnabled(granted)
    return granted
  } catch {
    return false
  }
}

export function playNotificationChime(severity: string = 'INFO'): void {
  if (!isNotifSoundEnabled()) return
  if (typeof window === 'undefined') return
  try {
    const AudioCtx = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext
    if (!AudioCtx) return
    const ctx = new AudioCtx()
    const now = ctx.currentTime

    const sev = severity.toUpperCase()
    const notes =
      sev === 'CRITICAL'
        ? [880, 1174.66, 880, 1318.51] // Urgent security/failure cadence
        : sev === 'WARNING' || sev === 'HIGH'
        ? [659.25, 880, 1046.5] // Prominent trading/auto-sell chime
        : [587.33, 880] // Clean two-tone pleasant notification chime

    notes.forEach((freq, idx) => {
      const osc = ctx.createOscillator()
      const gain = ctx.createGain()
      osc.type = sev === 'CRITICAL' ? 'triangle' : 'sine'
      osc.frequency.setValueAtTime(freq, now + idx * 0.11)
      gain.gain.setValueAtTime(0.001, now + idx * 0.11)
      gain.gain.exponentialRampToValueAtTime(sev === 'CRITICAL' ? 0.14 : 0.1, now + idx * 0.11 + 0.02)
      gain.gain.exponentialRampToValueAtTime(0.001, now + idx * 0.11 + 0.24)
      osc.connect(gain)
      gain.connect(ctx.destination)
      osc.start(now + idx * 0.11)
      osc.stop(now + idx * 0.11 + 0.25)
    })

    window.setTimeout(() => {
      ctx.close().catch(() => undefined)
    }, notes.length * 140 + 400)
  } catch {
    // Autoplay policy may block before user interaction
  }
}

export function triggerDesktopPushNotification(opts: {
  title: string
  body: string
  severity?: string
  tag?: string
  url?: string
  playSound?: boolean
}): void {
  if (opts.playSound !== false) {
    playNotificationChime(opts.severity || 'INFO')
  }
  if (typeof window === 'undefined' || !('Notification' in window)) return
  if (!isNotifPushEnabled() || Notification.permission !== 'granted') return

  try {
    const n = new Notification(opts.title, {
      body: opts.body,
      tag: opts.tag || `stockai-${Date.now()}`,
      silent: true, // Sound handled cleanly by Web Audio chime
    })
    n.onclick = () => {
      window.focus()
      if (opts.url) {
        window.location.href = opts.url
      }
      n.close()
    }
    window.setTimeout(() => n.close(), 7500)
  } catch {
    // Ignore restricted Notification constructor environments
  }
}
