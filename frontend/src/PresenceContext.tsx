import React, { createContext, useContext } from 'react'
import { usePresence } from './hooks/usePresence'

interface PresenceContextType {
  liveCount: number
}

const PresenceContext = createContext<PresenceContextType>({ liveCount: 1 })

export function PresenceProvider({ children }: { children: React.ReactNode }) {
  const presence = usePresence()
  return (
    <PresenceContext.Provider value={presence}>
      {children}
    </PresenceContext.Provider>
  )
}

export function usePresenceContext() {
  return useContext(PresenceContext)
}
