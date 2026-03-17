'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { motion, AnimatePresence } from 'framer-motion'
import TextareaAutosize from 'react-textarea-autosize'
import { api } from '@/lib/api'

type Stage = 'input' | 'clarifying' | 'processing' | 'done'

export default function GoalPage() {
  const router = useRouter()

  const [stage, setStage]                   = useState<Stage>('input')
  const [rawGoal, setRawGoal]               = useState('')
  const [clarifyingQs, setClarifyingQs]     = useState<string[]>([])
  const [clarifyAnswers, setClarifyAnswers] = useState('')
  const [error, setError]                   = useState('')

  async function handleSubmit() {
    if (!rawGoal.trim()) return
    setError('')
    setStage('processing')

    try {
      const res = await api.onboarding.submitGoal(rawGoal.trim())

      if (res.needs_clarification) {
        setClarifyingQs(res.clarifying_questions)
        setStage('clarifying')
      } else {
        setStage('done')
        setTimeout(() => router.push('/preview'), 800)
      }
    } catch (err: any) {
      const detail = typeof err.detail === 'object' ? err.detail?.message : err.detail
      setError(detail || 'Something went wrong. Please try again.')
      setStage('input')
    }
  }

  async function handleClarify() {
    if (!clarifyAnswers.trim()) return
    setStage('processing')

    try {
      await api.onboarding.clarifyGoal(rawGoal, clarifyAnswers)
      setStage('done')
      setTimeout(() => router.push('/preview'), 800)
    } catch (err: any) {
      const detail = typeof err.detail === 'object' ? err.detail?.message : err.detail
      setError(detail || 'Something went wrong.')
      setStage('clarifying')
    }
  }

  return (
    <div className="max-w-xl mx-auto w-full">
      <AnimatePresence mode="wait">

        {/* Goal Input */}
        {(stage === 'input' || stage === 'processing') && (
          <motion.div
            key="input"
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -16 }}
            transition={{ duration: 0.4 }}
          >
            <h1 className="font-display text-4xl text-[#F5F1ED] mb-3">
              Define your One Goal
            </h1>
            <p className="text-[#7A6E65] mb-8 leading-relaxed">
              The single outcome that matters most to you right now. Write it in
              plain language — rough is fine. The AI will work with what you give it.
            </p>

            {error && (
              <div className="mb-5 px-4 py-3 rounded-xl bg-red-950/40 border border-red-900/30 text-red-400 text-sm">
                {error}
              </div>
            )}

            <div className="bg-[#141210] border border-white/7 rounded-2xl p-1 focus-within:border-[#F59E0B]/30 focus-within:shadow-[0_0_0_3px_rgba(245,158,11,0.08)] transition-all mb-6">
              <TextareaAutosize
                value={rawGoal}
                onChange={e => setRawGoal(e.target.value)}
                placeholder="e.g. Build a product that generates $10k MRR, Get to a place where I feel strong and energetic every day, Write and publish a book about my experience..."
                minRows={4}
                className="w-full bg-transparent text-[#E8E2DC] placeholder:text-[#3D3630] text-base leading-relaxed resize-none focus:outline-none px-4 py-3 font-sans"
              />
            </div>

            <div className="flex items-center gap-4">
              <button
                onClick={handleSubmit}
                disabled={!rawGoal.trim() || stage === 'processing'}
                className="btn btn-primary px-8 h-12"
              >
                {stage === 'processing' ? (
                  <span className="flex items-center gap-2">
                    <span className="w-4 h-4 border-2 border-[#0A0908]/30 border-t-[#0A0908] rounded-full animate-spin" />
                    Analyzing...
                  </span>
                ) : (
                  'Build my strategy'
                )}
              </button>
              <p className="text-[#5C524A] text-sm">Takes about 20 seconds</p>
            </div>

            {/* Examples */}
            <div className="mt-10 border-t border-white/5 pt-8">
              <p className="text-[#5C524A] text-xs uppercase tracking-widest mb-4">
                Real examples from past users
              </p>
              <div className="space-y-3">
                {EXAMPLES.map(ex => (
                  <button
                    key={ex}
                    onClick={() => setRawGoal(ex)}
                    className="w-full text-left px-4 py-3 rounded-xl bg-[#141210] border border-white/5 text-[#7A6E65] text-sm hover:border-white/10 hover:text-[#A09690] transition-all"
                  >
                    &ldquo;{ex}&rdquo;
                  </button>
                ))}
              </div>
            </div>
          </motion.div>
        )}

        {/* Clarifying Questions */}
        {stage === 'clarifying' && (
          <motion.div
            key="clarify"
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -16 }}
            transition={{ duration: 0.4 }}
          >
            <h1 className="font-display text-3xl text-[#F5F1ED] mb-3">
              A few quick questions
            </h1>
            <p className="text-[#7A6E65] mb-8">
              The AI needs more to go on before it can build your strategy.
            </p>

            <div className="space-y-4 mb-8">
              {clarifyingQs.map((q, i) => (
                <div
                  key={i}
                  className="px-4 py-3 rounded-xl bg-[#1E1B18] border border-white/5 text-[#C4BBB5] text-sm"
                >
                  <span className="text-[#F59E0B] font-mono text-xs mr-2">{i + 1}.</span>
                  {q}
                </div>
              ))}
            </div>

            <div className="bg-[#141210] border border-white/7 rounded-2xl p-1 focus-within:border-[#F59E0B]/30 focus-within:shadow-[0_0_0_3px_rgba(245,158,11,0.08)] transition-all mb-6">
              <TextareaAutosize
                value={clarifyAnswers}
                onChange={e => setClarifyAnswers(e.target.value)}
                placeholder="Answer the questions above — one at a time or all together..."
                minRows={4}
                className="w-full bg-transparent text-[#E8E2DC] placeholder:text-[#3D3630] text-base leading-relaxed resize-none focus:outline-none px-4 py-3 font-sans"
              />
            </div>

            <button
              onClick={handleClarify}
              disabled={!clarifyAnswers.trim()}
              className="btn btn-primary px-8 h-12"
            >
              Continue
            </button>
          </motion.div>
        )}

        {/* Done */}
        {stage === 'done' && (
          <motion.div
            key="done"
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="text-center py-16"
          >
            <motion.div
              animate={{ scale: [1, 1.1, 1] }}
              transition={{ duration: 0.6 }}
              className="w-16 h-16 rounded-2xl bg-[#F59E0B]/20 flex items-center justify-center mx-auto mb-6"
            >
              <span className="text-3xl">&#10022;</span>
            </motion.div>
            <h2 className="font-display text-2xl text-[#F5F1ED]">
              Strategy built. Reviewing now...
            </h2>
          </motion.div>
        )}

      </AnimatePresence>
    </div>
  )
}

const EXAMPLES = [
  'Ship a SaaS product that generates real revenue within a year',
  'Get to a place where I feel strong and have energy every day',
  'Build the discipline to do deep work every morning without fighting myself',
]