'use client'

import { useState } from 'react'
import { motion } from 'framer-motion'
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

  const initials = (user?.display_name || user?.email || 'U')
    .split(' ')
    .map((w: string) => w[0])
    .slice(0, 2)
    .join('')
    .toUpperCase()

  return (
    <div className="p-6 md:p-8 max-w-2xl mx-auto">

      {/* ── Header ─────────────────────────────────────── */}
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        className="mb-8"
      >
        <p className="text-[#5C524A] text-sm mb-1">Manage your account</p>
        <h1 className="font-display text-3xl text-[#F5F1ED]">Settings</h1>
      </motion.div>

      <div className="space-y-4">

        {/* ── Profile card ───────────────────────────────── */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.05 }}
          className="bg-[#111009] border border-white/5 rounded-2xl p-6"
        >
          <p className="text-[#5C524A] text-xs uppercase tracking-widest font-mono mb-5">Profile</p>

          <div className="flex items-center gap-4 mb-6">
            <div className="w-14 h-14 rounded-2xl bg-[#F59E0B]/20 border border-[#F59E0B]/20 flex items-center justify-center shrink-0">
              <span className="text-[#F59E0B] text-lg font-semibold">{initials}</span>
            </div>
            <div>
              <p className="text-[#E8E2DC] text-base font-medium">
                {user?.display_name || 'No name set'}
              </p>
              <p className="text-[#5C524A] text-sm">{user?.email}</p>
            </div>
          </div>

          <div className="space-y-3">
            <div className="flex items-center justify-between py-3 border-t border-white/5">
              <p className="text-[#5C524A] text-sm font-mono">Name</p>
              <p className="text-[#C4BBB5] text-sm">{user?.display_name || '—'}</p>
            </div>
            <div className="flex items-center justify-between py-3 border-t border-white/5">
              <p className="text-[#5C524A] text-sm font-mono">Email</p>
              <p className="text-[#C4BBB5] text-sm">{user?.email}</p>
            </div>
            <div className="flex items-center justify-between py-3 border-t border-white/5">
              <p className="text-[#5C524A] text-sm font-mono">Account status</p>
              <span className="px-2.5 py-1 bg-[#4ADE80]/10 border border-[#4ADE80]/20 rounded-lg text-[#4ADE80] text-xs font-mono">
                Active
              </span>
            </div>
          </div>
        </motion.div>

        {/* ── App info ───────────────────────────────────── */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="bg-[#111009] border border-white/5 rounded-2xl p-6"
        >
          <p className="text-[#5C524A] text-xs uppercase tracking-widest font-mono mb-5">About</p>
          <div className="space-y-3">
            <div className="flex items-center justify-between py-3 border-t border-white/5">
              <p className="text-[#5C524A] text-sm font-mono">Product</p>
              <p className="text-[#C4BBB5] text-sm">OneGoal Pro</p>
            </div>
            <div className="flex items-center justify-between py-3 border-t border-white/5">
              <p className="text-[#5C524A] text-sm font-mono">Version</p>
              <p className="text-[#3D3630] text-sm font-mono">0.1.0 — MVP</p>
            </div>
            <div className="flex items-center justify-between py-3 border-t border-white/5">
              <p className="text-[#5C524A] text-sm font-mono">Philosophy</p>
              <p className="text-[#C4BBB5] text-sm italic">One goal. Full commitment.</p>
            </div>
          </div>
        </motion.div>

        {/* ── Session / logout ───────────────────────────── */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
          className="bg-[#111009] border border-white/5 rounded-2xl p-6"
        >
          <p className="text-[#5C524A] text-xs uppercase tracking-widest font-mono mb-5">Session</p>

          {!showConfirm ? (
            <button
              onClick={() => setShowConfirm(true)}
              className="flex items-center gap-2 text-[#5C524A] hover:text-red-400 transition-colors text-sm group"
            >
              <SignOutIcon />
              <span>Sign out</span>
            </button>
          ) : (
            <motion.div
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              className="space-y-4"
            >
              <p className="text-[#C4BBB5] text-sm">
                You'll be signed out and returned to the login page.
              </p>
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
            </motion.div>
          )}
        </motion.div>

      </div>
    </div>
  )
}

function SignOutIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
      <polyline points="16 17 21 12 16 7" />
      <line x1="21" y1="12" x2="9" y2="12" />
    </svg>
  )
}
