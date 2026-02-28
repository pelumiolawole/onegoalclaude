'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { motion } from 'framer-motion'
import { api } from '@/lib/api'
import { useAuthStore } from '@/stores/auth'

export default function ActivatePage() {
  const router = useRouter()
  const { refreshUser } = useAuthStore()
  const [activating, setActivating] = useState(false)
  const [done, setDone]             = useState(false)

  async function handleActivate() {
    setActivating(true)
    try {
      await api.onboarding.activate()
      setDone(true)
      await refreshUser()
      setTimeout(() => router.push('/dashboard'), 2000)
    } catch {
      setActivating(false)
    }
  }

  if (done) {
    return (
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        className="text-center py-16"
      >
        <motion.div
          initial={{ scale: 0.5, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ type: 'spring', stiffness: 200, damping: 12 }}
          className="w-20 h-20 rounded-3xl bg-[#F59E0B] flex items-center justify-center mx-auto mb-8"
        >
          <span className="text-4xl text-[#0A0908]">✦</span>
        </motion.div>
        <motion.h1
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          className="font-display text-4xl text-[#F5F1ED] mb-4"
        >
          Your transformation begins today.
        </motion.h1>
        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.6 }}
          className="text-[#7A6E65]"
        >
          Taking you to your dashboard…
        </motion.p>
      </motion.div>
    )
  }

  return (
    <div className="max-w-lg mx-auto w-full text-center">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6 }}
      >
        {/* Pulsing symbol */}
        <motion.div
          animate={{ opacity: [0.6, 1, 0.6] }}
          transition={{ duration: 3, repeat: Infinity }}
          className="w-16 h-16 rounded-2xl bg-[#F59E0B]/15 border border-[#F59E0B]/30 flex items-center justify-center mx-auto mb-10"
        >
          <span className="text-[#F59E0B] text-3xl">✦</span>
        </motion.div>

        <h1 className="font-display text-5xl text-[#F5F1ED] mb-6 leading-tight">
          Ready to begin?
        </h1>

        <p className="text-[#A09690] text-lg leading-relaxed mb-4">
          Your strategy is set. Your first task will be ready tomorrow morning.
        </p>
        <p className="text-[#7A6E65] leading-relaxed mb-12">
          Every day: one task, one reflection, and your coach. That's the whole system.
          Small and consistent beats big and occasional every time.
        </p>

        {/* Commitments */}
        <div className="space-y-3 mb-12 text-left">
          {COMMITMENTS.map((c, i) => (
            <motion.div
              key={c}
              initial={{ opacity: 0, x: -12 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.3 + i * 0.1 }}
              className="flex items-start gap-3 px-4 py-3 bg-[#141210] border border-white/5 rounded-xl"
            >
              <span className="text-[#F59E0B] mt-0.5">✓</span>
              <span className="text-[#C4BBB5] text-sm">{c}</span>
            </motion.div>
          ))}
        </div>

        <button
          onClick={handleActivate}
          disabled={activating}
          className="btn btn-primary w-full h-14 text-lg"
        >
          {activating ? (
            <span className="flex items-center gap-2 justify-center">
              <span className="w-5 h-5 border-2 border-[#0A0908]/30 border-t-[#0A0908] rounded-full animate-spin" />
              Setting things up…
            </span>
          ) : (
            'Begin my transformation'
          )}
        </button>
      </motion.div>
    </div>
  )
}

const COMMITMENTS = [
  'One daily task — built around who you need to become, not just what you need to do',
  'Daily reflection to track what\'s working and what isn\'t',
  'A coach that knows your goal, your history, and your current objective',
  'A weekly review showing your patterns and adjusting what comes next',
]
