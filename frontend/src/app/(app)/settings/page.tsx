'use client'

import { useState } from 'react'
import { useAuthStore } from '@/stores/auth'
import { useRouter } from 'next/navigation'

export default function SettingsPage() {
  const { user, clearAuth } = useAuthStore()
  const router = useRouter()
  const [showConfirm, setShowConfirm] = useState(false)

  const handleLogout = () => {
    clearAuth()
    router.replace('/login')
  }

  return (
    <div className="max-w-lg mx-auto px-6 py-10">
      <h1 className="text-[#E8E2DC] text-xl font-semibold mb-8">Settings</h1>

      {/* Account */}
      <section className="mb-8">
        <p className="text-[#5C524A] text-xs uppercase tracking-widest mb-3">Account</p>
        <div className="bg-[#111009] border border-white/5 rounded-2xl p-5 space-y-4">
          <div>
            <p className="text-[#5C524A] text-xs mb-1">Name</p>
            <p className="text-[#C4BBB5] text-sm">{user?.display_name || '—'}</p>
          </div>
          <div>
            <p className="text-[#5C524A] text-xs mb-1">Email</p>
            <p className="text-[#C4BBB5] text-sm">{user?.email}</p>
          </div>
        </div>
      </section>

      {/* Danger zone */}
      <section>
        <p className="text-[#5C524A] text-xs uppercase tracking-widest mb-3">Session</p>
        <div className="bg-[#111009] border border-white/5 rounded-2xl p-5">
          {!showConfirm ? (
            <button
              onClick={() => setShowConfirm(true)}
              className="text-sm text-[#C4BBB5] hover:text-red-400 transition-colors"
            >
              Sign out
            </button>
          ) : (
            <div className="space-y-3">
              <p className="text-[#C4BBB5] text-sm">Are you sure you want to sign out?</p>
              <div className="flex gap-3">
                <button
                  onClick={handleLogout}
                  className="px-4 py-2 bg-red-500/10 border border-red-500/20 text-red-400 text-sm rounded-xl hover:bg-red-500/20 transition-all"
                >
                  Yes, sign out
                </button>
                <button
                  onClick={() => setShowConfirm(false)}
                  className="px-4 py-2 text-[#5C524A] text-sm hover:text-[#C4BBB5] transition-colors"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      </section>
    </div>
  )
}
