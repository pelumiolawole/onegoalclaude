'use client'

import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import TextareaAutosize from 'react-textarea-autosize'
import { api } from '@/lib/api'

interface Props {
  taskId: string
  taskTitle: string
  onClose: () => void
  onDone: () => void
}

type Stage = 'loading' | 'answering' | 'submitting' | 'feedback'

interface Question {
  question: string
  question_type: string
}

export default function ReflectionModal({ taskId, taskTitle, onClose, onDone }: Props) {
  const [stage,     setStage]     = useState<Stage>('loading')
  const [questions, setQuestions] = useState<Question[]>([])
  const [answers,   setAnswers]   = useState<string[]>([])
  const [feedback,  setFeedback]  = useState('')
  const [sentiment, setSentiment] = useState('')

  useEffect(() => {
    api.reflections.getQuestions(taskId)
      .then(res => {
        setQuestions(res.questions)
        setAnswers(res.questions.map(() => ''))
        setStage('answering')
      })
      .catch(onClose)
  }, [taskId])

  async function handleSubmit() {
    const filled = questions.every((_, i) => answers[i]?.trim())
    if (!filled) return

    setStage('submitting')
    try {
      const res = await api.reflections.submit(
        taskId,
        questions.map((q, i) => ({
          question: q.question,
          answer: answers[i],
          question_type: q.question_type,
        }))
      )
      setFeedback(res.ai_feedback)
      setSentiment(res.sentiment)
      setStage('feedback')
    } catch {
      setStage('answering')
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4"
      onClick={e => e.target === e.currentTarget && onClose()}
    >
      <motion.div
        initial={{ y: 40, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        exit={{ y: 40, opacity: 0 }}
        transition={{ type: 'spring', stiffness: 300, damping: 30 }}
        className="bg-[#141210] border border-white/7 rounded-3xl w-full max-w-lg max-h-[90vh] overflow-y-auto"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-5 border-b border-white/5">
          <div>
            <p className="text-[#5C524A] text-xs uppercase tracking-widest font-mono">Reflect</p>
            <p className="text-[#E8E2DC] text-sm mt-0.5 line-clamp-1">{taskTitle}</p>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-xl bg-[#1E1B18] flex items-center justify-center text-[#5C524A] hover:text-[#A09690] transition-colors"
          >
            ✕
          </button>
        </div>

        <div className="p-6">

          {/* Loading */}
          {stage === 'loading' && (
            <div className="py-12 flex flex-col items-center gap-3">
              <div className="w-8 h-8 border-2 border-[#F59E0B]/20 border-t-[#F59E0B] rounded-full animate-spin" />
              <p className="text-[#5C524A] text-sm">Preparing your reflection questions…</p>
            </div>
          )}

          {/* Questions */}
          {stage === 'answering' && (
            <div className="space-y-6">
              {questions.map((q, i) => (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.1 }}
                >
                  <label className="block text-[#C4BBB5] text-sm mb-2 leading-relaxed">
                    {q.question}
                  </label>
                  <TextareaAutosize
                    value={answers[i]}
                    onChange={e => {
                      const next = [...answers]
                      next[i] = e.target.value
                      setAnswers(next)
                    }}
                    minRows={2}
                    placeholder="Take your time…"
                    className="input-base text-sm leading-relaxed resize-none"
                  />
                </motion.div>
              ))}

              <button
                onClick={handleSubmit}
                disabled={!questions.every((_, i) => answers[i]?.trim())}
                className="btn btn-primary w-full h-11"
              >
                Submit reflection
              </button>
            </div>
          )}

          {/* Submitting */}
          {stage === 'submitting' && (
            <div className="py-12 flex flex-col items-center gap-3">
              <div className="w-8 h-8 border-2 border-[#F59E0B]/20 border-t-[#F59E0B] rounded-full animate-spin" />
              <p className="text-[#5C524A] text-sm">Analyzing your reflection…</p>
            </div>
          )}

          {/* AI Feedback */}
          {stage === 'feedback' && (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className="space-y-5"
            >
              <div className="flex items-center gap-2 mb-4">
                <div className="w-7 h-7 rounded-full bg-[#F59E0B]/15 border border-[#F59E0B]/20 flex items-center justify-center">
                  <span className="text-[#F59E0B] text-xs">✦</span>
                </div>
                <p className="text-[#5C524A] text-xs uppercase tracking-widest font-mono">
                  From your coach
                </p>
              </div>

              <p className="text-[#C4BBB5] leading-relaxed text-[0.9375rem]">
                {feedback}
              </p>

              {sentiment && (
                <div className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-mono border ${sentimentStyle(sentiment)}`}>
                  {sentimentEmoji(sentiment)} {sentiment}
                </div>
              )}

              <button
                onClick={onDone}
                className="btn btn-primary w-full h-11 mt-4"
              >
                Done
              </button>
            </motion.div>
          )}
        </div>
      </motion.div>
    </motion.div>
  )
}

function sentimentStyle(s: string) {
  const map: Record<string, string> = {
    positive:    'bg-green-950/30 border-green-900/30 text-green-400',
    breakthrough:'bg-amber-950/30 border-amber-900/30 text-amber-400',
    neutral:     'bg-slate-900/30 border-slate-800/30 text-slate-400',
    resistant:   'bg-orange-950/30 border-orange-900/30 text-orange-400',
    struggling:  'bg-red-950/30 border-red-900/30 text-red-400',
  }
  return map[s] || map.neutral
}

function sentimentEmoji(s: string) {
  const map: Record<string, string> = {
    positive: '↑', breakthrough: '✦', neutral: '→', resistant: '↕', struggling: '↓',
  }
  return map[s] || '→'
}
