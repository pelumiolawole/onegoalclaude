/**
 * stores/auth.ts
 * Global auth state — persisted to localStorage
 */
import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { api, type UserSummary, type TokenResponse } from '@/lib/api'

interface AuthState {
  user: UserSummary | null
  isAuthenticated: boolean
  isLoading: boolean

  setAuth: (data: TokenResponse) => void
  clearAuth: () => void
  refreshUser: () => Promise<void>
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      isAuthenticated: false,
      isLoading: false,

      setAuth: (data: TokenResponse) => {
        localStorage.setItem('access_token', data.access_token)
        localStorage.setItem('refresh_token', data.refresh_token)
        set({ user: data.user, isAuthenticated: true })
      },

      clearAuth: () => {
        localStorage.removeItem('access_token')
        localStorage.removeItem('refresh_token')
        set({ user: null, isAuthenticated: false })
      },

      refreshUser: async () => {
        try {
          const user = await api.auth.me()
          set({ user })
        } catch {
          get().clearAuth()
        }
      },
    }),
    {
      name: 'one-goal-auth',
      partialize: (state) => ({ user: state.user, isAuthenticated: state.isAuthenticated }),
    }
  )
)
