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
  const [done, setDone] = useState(false)
  const [commitmentStatement, setCommitmentStatement] = useState('')

  async function handleActivate() {
    if (activating) return
    setActivating(true)
    try {
      await api.onboarding.activate({ commitment_statement: commitmentStatement })
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

  const isReady = commitmentStatement.trim().length >= 30

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
          Before you begin.
        </h1>

        <p className="text-[#A09690] text-lg leading-relaxed mb-12">
          You've found your goal. The work starts here — not with tasks or streaks, but with a decision.
        </p>

        <textarea
          value={commitmentStatement}
          onChange={(e) => setCommitmentStatement(e.target.value)}
          placeholder="In your own words, write why this goal matters to you right now."
          rows={5}
          className="w-full bg-[#141210] border border-white/10 rounded-2xl px-5 py-4 text-[#F5F1ED] placeholder:text-[#3D3630] text-base leading-relaxed resize-none focus:outline-none focus:border-[#F59E0B]/40 mb-8"
        />

        <button
          onClick={handleActivate}
          disabled={!isReady || activating}
          className={`w-full h-14 text-lg rounded-2xl font-semibold transition-all ${
            isReady && !activating
              ? 'bg-[#F59E0B] text-[#0A0908] hover:bg-[#D97706]'
              : 'bg-[#1E1B18] text-[#3D3630] cursor-not-allowed'
          }`}
        >
          {activating ? (
            <span className="flex items-center gap-2 justify-center">
              <span className="w-5 h-5 border-2 border-[#3D3630]/30 border-t-[#3D3630] rounded-full animate-spin" />
              Setting things up…
            </span>
          ) : (
            "I'm ready. Begin."
          )}
        </button>
      </motion.div>
    </div>
  )
}