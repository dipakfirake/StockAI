/**
 * useLocalStorage — typed React hook for localStorage persistence.
 * Serializes/deserializes JSON automatically. Falls back to initialValue
 * if the stored value is missing, malformed, or the key is new.
 */
import { useState, useCallback } from 'react'

export function useLocalStorage<T>(key: string, initialValue: T): [T, (value: T | ((prev: T) => T)) => void] {
  const [storedValue, setStoredValue] = useState<T>(() => {
    try {
      const item = window.localStorage.getItem(key)
      return item !== null ? (JSON.parse(item) as T) : initialValue
    } catch {
      return initialValue
    }
  })

  const setValue = useCallback(
    (value: T | ((prev: T) => T)) => {
      setStoredValue(prev => {
        const next = value instanceof Function ? value(prev) : value
        try {
          window.localStorage.setItem(key, JSON.stringify(next))
        } catch {
          // Storage quota exceeded or private browsing — silently degrade
        }
        return next
      })
    },
    [key]
  )

  return [storedValue, setValue]
}
