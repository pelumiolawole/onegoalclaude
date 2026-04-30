'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { motion, AnimatePresence } from 'framer-motion'

interface Task {
  id: string
  identity_focus: string
  title: string
  description: string
  execution_guidance?: string | null
  guidance?: string | null
  time_estimate_minutes: number
  difficulty: number
  status: 'pending' | 'completed' | 'skipped'
  reflection_submitted: boolean
}

interface Props {
  task: Task
  onComplete: () => Promise<void>
  onSkip: (reason: string) => Promise<void>
  onReflect: () => void
}

export default function TaskCard({ task, onComplete, onSkip, onReflect }: Props) {
  const router = useRouter()
  const [expanded,   setExpanded]   = useState(false)
  const [completing, setCompleting] = useState(false)
  const [skipMode,   setSkipMode]   = useState(false)
  const [skipReason, setSkipReason] = useState('')
  const [skipping,   setSkipping]   = useState(false)

  const isCompleted = task.status === 'completed'
  const isSkipped   = task.status === 'skipped'

  // Prefer the new guidance field, fall back to execution_guidance
  const guidanceText = task.guidance || task.execution_guidance || null

  async function handleComplete() {
    setCompleting(true)
    try { await onComplete() } finally { setCompleting(false) }
  }

  async function handleSkip() {
    if (!skipReason.trim()) return
    setSkipping(true)
    try {
      await onSkip(skipReason)
    } finally {
      setSkipping(false)
      setSkipMode(false)
    }
  }

  return (
    <div className={`rounded-2xl border transition-all duration-300 overflow-hidden ${
      isCompleted
        ? 'bg-[#0F1A0F] border-[#22C55E]/20'
        : isSkipped
        ? 'bg-[#141210] border-white/5 opacity-60'
        : 'bg-[#141210] border-[#F59E0B]/15'
    }`}>

      {/* ── Identity Focus ──────────────────────────── */}
      <div className={`px-5 py-3 border-b ${isCompleted ? 'border-[#22C55E]/10' : 'border-white/5'}`}>
        <p className={`text-xs uppercase tracking-widest font-mono ${isCompleted ? 'text-[#22C55E]/70' : 'text-[#F59E0B]/70'}`}>
          Today you are
        </p>
        <p className={`text-sm mt-0.5 italic ${isCompleted ? 'text-[#4ADE80]/80' : 'text-[#C4BBB5]'}`}>
          {task.identity_focus}
        </p>
      </div>

      {/* ── Task Body ───────────────────────────────── */}
      <div className="p-5">
        <div className="flex items-start justify-between gap-4 mb-3">
          <h2 className={`font-display text-xl leading-snug ${isCompleted ? 'text-[#4ADE80]' : 'text-[#F5F1ED]'}`}>
            {task.title}
          </h2>
          <div className="flex items-center gap-2 shrink-0">
            <span className="text-[#3D3630] text-xs font-mono">
              {task.time_estimate_minutes}m
            </span>
            <DifficultyDots level={task.difficulty} />
          </div>
        </div>

        <p className="text-[#7A6E65] text-sm leading-relaxed mb-4">
          {task.description}
        </p>

        {/* How to do this — toggle */}
        <button
          onClick={() => setExpanded(e => !e)}
          className="text-[#5C524A] text-xs flex items-center gap-1 hover:text-[#A09690] transition-colors mb-4"
        >
          <span>{expanded ? '↑' : '↓'}</span>
          {expanded ? 'Hide guidance' : 'How to do this'}
        </button>

        <AnimatePresence>
          {expanded && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.25 }}
              className="overflow-hidden"
            >
              {guidanceText ? (
                // Tappable — routes to coach with task context
                <button
                  onClick={() => router.push('/coach')}
                  className="w-full text-left group mb-4"
                >
                  <div className="bg-[#1E1B18] rounded-xl p-4 border border-white/5 group-hover:border-[#F59E0B]/20 transition-colors">
                    <p className="text-[#A09690] text-sm leading-relaxed group-hover:text-[#C4BBB5] transition-colors">
                      {guidanceText}
                    </p>
                    <p className="text-[#F59E0B]/50 text-xs mt-3 group-hover:text-[#F59E0B]/80 transition-colors">
                      Tap to discuss with your coach ✦
                    </p>
                  </div>
                </button>
              ) : (
                // No guidance yet (pre-migration task) — non-tappable fallback
                <div className="bg-[#1E1B18] rounded-xl p-4 border border-white/5 mb-4">
                  <p className="text-[#5C524A] text-sm leading-relaxed italic">
                    Guidance will appear on your next task.
                  </p>
                </div>
              )}
            </motion.div>
          )}
        </AnimatePresence>

        {/* ── Actions ──────────────────────────────── */}
        {!isCompleted && !isSkipped && !skipMode && (
          <div className="flex gap-3">
            <button
              onClick={handleComplete}
              disabled={completing}
              className="btn btn-primary flex-1 h-11"
            >
              {completing ? 'Marking done…' : 'Mark complete'}
            </button>
            <button
              onClick={() => setSkipMode(true)}
              className="btn btn-ghost h-11 px-4"
            >
              Skip
            </button>
          </div>
        )}

        {/* Skip form */}
        <AnimatePresence>
          {skipMode && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              className="overflow-hidden"
            >
              <div className="space-y-3">
                <input
                  value={skipReason}
                  onChange={e => setSkipReason(e.target.value)}
                  placeholder="What got in the way?"
                  className="input-base text-sm"
                  autoFocus
                />
                <div className="flex gap-2">
                  <button
                    onClick={handleSkip}
                    disabled={!skipReason.trim() || skipping}
                    className="btn btn-ghost flex-1 h-10 text-sm"
                  >
                    {skipping ? 'Skipping…' : 'Skip today'}
                  </button>
                  <button
                    onClick={() => setSkipMode(false)}
                    className="btn btn-ghost h-10 text-sm px-4"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Completed state */}
        {isCompleted && (
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-[#22C55E] text-sm">✓ Completed</span>
            </div>
            {!task.reflection_submitted ? (
              <button
                onClick={onReflect}
                className="btn btn-ghost h-9 text-sm px-4 border-[#F59E0B]/20 text-[#F59E0B] hover:bg-[#F59E0B]/10"
              >
                Reflect ✦
              </button>
            ) : (
              <span className="text-[#3D3630] text-xs">Reflected ✓</span>
            )}
          </div>
        )}

        {isSkipped && (
          <p className="text-[#5C524A] text-sm">Skipped today. Tomorrow is new.</p>
        )}
      </div>
    </div>
  )
}

function DifficultyDots({ level }: { level: number }) {
  const filled = Math.round((level / 10) * 5)
  return (
    <div className="flex gap-0.5">
      {[...Array(5)].map((_, i) => (
        <div
          key={i}
          className={`w-1.5 h-1.5 rounded-full ${i < filled ? 'bg-[#F59E0B]' : 'bg-[#2A2520]'}`}
        />
      ))}
    </div>
  )
}