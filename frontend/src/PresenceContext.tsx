import React, { createContext, useContext, useState } from 'react'
import { usePresence, LiveUserSession } from './hooks/usePresence'
import { useAuth } from './AuthContext'

interface PresenceContextType {
  liveCount: number
  liveUsers: LiveUserSession[]
  fetchLiveUsers: () => Promise<void>
  loadingUsers: boolean
  isModalOpen: boolean
  setIsModalOpen: (open: boolean) => void
}

const PresenceContext = createContext<PresenceContextType>({
  liveCount: 1,
  liveUsers: [],
  fetchLiveUsers: async () => {},
  loadingUsers: false,
  isModalOpen: false,
  setIsModalOpen: () => {},
})

export function PresenceProvider({ children }: { children: React.ReactNode }) {
  const { user } = useAuth()
  const { liveCount, liveUsers, fetchLiveUsers, loadingUsers } = usePresence(user)
  const [isModalOpen, setIsModalOpen] = useState(false)

  return (
    <PresenceContext.Provider
      value={{
        liveCount,
        liveUsers,
        fetchLiveUsers,
        loadingUsers,
        isModalOpen,
        setIsModalOpen,
      }}
    >
      {children}
    </PresenceContext.Provider>
  )
}

export function usePresenceContext() {
  return useContext(PresenceContext)
}
