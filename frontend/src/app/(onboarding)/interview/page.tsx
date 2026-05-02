'use client'

import { useState, useEffect, useRef } from 'react'
import { useRouter } from 'next/navigation'
import { motion, AnimatePresence } from 'framer-motion'
import TextareaAutosize from 'react-textarea-autosize'
import { api } from '@/lib/api'
import { useAuthStore } from '@/stores/auth'
import { trackEvent } from '@/lib/posthog'

interface Message {
  role: 'user' | 'assistant'
  content: string
}

export default function InterviewPage() {
  const router = useRouter()
  const { refreshUser } = useAuthStore()

  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput]       = useState('')
  const [loading, setLoading]   = useState(false)
  const [phase, setPhase]       = useState('tension')
  const [started, setStarted]   = useState(false)
  const [preAnswer, setPreAnswer] = useState<string | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('ogp_pre_answer')
      if (saved) setPreAnswer(saved)
    }
  }, [])

  useEffect(() => {
    async function loadState() {
      try {
        const state = await api.onboarding.getInterviewState()
        if (state.messages?.length > 0) {
          setMessages(state.messages)
          setStarted(true)
          setPhase(state.current_phase)
        }
      } catch {}
    }
    loadState()
  }, [])

  useEffect(() => {
    async function saveTimezone() {
      try {
        const tz = Intl.DateTimeFormat().resolvedOptions().timeZone
        if (tz) await api.profile.saveTimezone(tz)
      } catch {}
    }
    saveTimezone()
  }, [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  async function startInterview() {
    setStarted(true)
    setLoading(true)

    // If the user answered the landing page hook, send that as their first message.
    // Clear localStorage immediately after use.
    const firstMessage = preAnswer || "I'm ready to begin."
    const hadPreAnswer = !!preAnswer
    if (preAnswer && typeof window !== 'undefined') {
      localStorage.removeItem('ogp_pre_answer')
      setPreAnswer(null)
    }

    try {
      const res = await api.onboarding.sendInterviewMessage(firstMessage)

      // Show user bubble only if they typed something real on the landing page
      if (hadPreAnswer) {
        setMessages([
          { role: 'user', content: firstMessage },
          { role: 'assistant', content: res.message },
        ])
      } else {
        setMessages([{ role: 'assistant', content: res.message }])
      }

      setPhase(res.phase)
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  async function sendMessage() {
    if (!input.trim() || loading) return
    const text = input.trim()
    setInput('')
    setLoading(true)
    const newMessages: Message[] = [...messages, { role: 'user', content: text }]
    setMessages(newMessages)

    try {
      const res = await api.onboarding.sendInterviewMessage(text)

      if ((res as any).needs_more_depth) {
        setMessages([...newMessages, { role: 'assistant', content: res.message }])
        setPhase(res.phase)
        setLoading(false)
        return
      }

      setMessages([...newMessages, { role: 'assistant', content: res.message }])
      setPhase(res.phase)

      if (res.is_complete) {
        trackEvent('interview_completed')
        await refreshUser()
        setTimeout(() => router.push('/goal-setup'), 1200)
      }
    } catch (err: any) {
      if (err?.status === 400) {
        await refreshUser()
        router.push('/dashboard')
        return
      }
      const isTimeout = err?.name === 'AbortError'
      setMessages([...newMessages, {
        role: 'assistant',
        content: isTimeout
          ? "That took a little longer than usual. If your message didn't go through, try sending it again."
          : "Something went wrong. Try sending that again."
      }])
    } finally {
      setLoading(false)
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  if (!started) {
    return (
      <div className="text-center max-w-lg mx-auto">
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6 }}>
          <div className="w-16 h-16 rounded-2xl bg-[#F59E0B]/10 border border-[#F59E0B]/20 flex items-center justify-center mx-auto mb-8">
            <span className="text-2xl">&#10022;</span>
          </div>
          <h1 className="font-display text-4xl text-[#F59E0B] mb-4">The Discovery Interview</h1>

          {preAnswer ? (
            <>
              <p className="text-[#C4BBB5] text-base leading-relaxed mb-4">
                You already told us something important.
              </p>
              <div className="bg-[#141210] border border-[#F59E0B]/15 rounded-xl px-5 py-4 mb-6 text-left">
                <p className="text-[#5C524A] text-xs uppercase tracking-widest font-mono mb-2">You said</p>
                <p className="text-[#C4BBB5] text-sm leading-relaxed italic">"{preAnswer}"</p>
              </div>
              <p className="text-[#7A6E65] text-sm mb-10">
                The interview picks up from there. Answer honestly. Take your time.
              </p>
            </>
          ) : (
            <>
              <p className="text-[#A09690] text-lg leading-relaxed mb-4">
                Before we build your strategy, we need to understand what you actually want — not the goal you think you should have, but the real one.
              </p>
              <p className="text-[#7A6E65] mb-6">This is a conversation. Answer honestly. Take your time.</p>
            </>
          )}

          <p className="text-[#3D3630] text-xs mb-10">
            Coach PO is an AI, not a human coach. Your responses are processed by AI to build your goal profile.
          </p>
          <button onClick={startInterview} className="btn btn-primary px-10 h-13 text-base">
            {preAnswer ? 'Continue the interview' : 'Begin the interview'}
          </button>
        </motion.div>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-[calc(100vh-100px)] max-w-2xl mx-auto w-full">
      <div className="flex-1 overflow-y-auto space-y-6 pb-6 pr-2">
        <AnimatePresence initial={false}>
          {messages.map((msg, i) => (
            <motion.div key={i} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35 }}
              className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              {msg.role === 'assistant' && (
                <div className="w-8 h-8 rounded-full bg-[#F59E0B]/15 border border-[#F59E0B]/20 flex items-center justify-center mr-3 mt-0.5 shrink-0">
                  <span className="text-[#F59E0B] text-xs">&#10022;</span>
                </div>
              )}
              <div className={`max-w-[85%] px-4 py-3 rounded-2xl text-[0.9375rem] leading-relaxed ${
                msg.role === 'user'
                  ? 'bg-[#F59E0B]/10 border border-[#F59E0B]/15 text-[#E8E2DC] rounded-tr-sm'
                  : 'bg-[#1E1B18] border border-white/5 text-[#C4BBB5] rounded-tl-sm'
              }`}>
                {msg.content}
              </div>
            </motion.div>
          ))}
          {loading && (
            <motion.div key="loading" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="flex justify-start">
              <div className="w-8 h-8 rounded-full bg-[#F59E0B]/15 border border-[#F59E0B]/20 flex items-center justify-center mr-3 shrink-0">
                <span className="text-[#F59E0B] text-xs">&#10022;</span>
              </div>
              <div className="bg-[#1E1B18] border border-white/5 px-4 py-3 rounded-2xl rounded-tl-sm">
                <TypingDots />
              </div>
            </motion.div>
          )}
        </AnimatePresence>
        <div ref={bottomRef} />
      </div>
      <div className="border-t border-white/5 pt-4">
        <div className="flex items-end gap-3 bg-[#141210] border border-white/7 rounded-2xl px-4 py-3 focus-within:border-[#F59E0B]/30 focus-within:shadow-[0_0_0_3px_rgba(245,158,11,0.08)] transition-all">
          <TextareaAutosize value={input} onChange={e => setInput(e.target.value)} onKeyDown={handleKeyDown}
            placeholder="Type your response..." minRows={1} maxRows={5} disabled={loading}
            className="flex-1 bg-transparent text-[#E8E2DC] placeholder:text-[#3D3630] text-[0.9375rem] leading-relaxed resize-none focus:outline-none disabled:opacity-50 font-sans" />
          <button onClick={sendMessage} disabled={!input.trim() || loading}
            className="shrink-0 w-9 h-9 rounded-xl bg-[#F59E0B] disabled:bg-[#2A2520] disabled:text-[#5C524A] text-[#0A0908] flex items-center justify-center transition-all hover:bg-[#FCD34D] disabled:cursor-not-allowed">
            <SendIcon />
          </button>
        </div>
        <p className="text-[#3D3630] text-xs text-center mt-2">Press Enter to send · Shift+Enter for new line</p>
      </div>
    </div>
  )
}

function TypingDots() {
  return (
    <div className="flex gap-1 items-center h-5">
      {[0, 1, 2].map(i => (
        <motion.div key={i} className="w-1.5 h-1.5 rounded-full bg-[#5C524A]"
          animate={{ opacity: [0.3, 1, 0.3] }} transition={{ duration: 1.2, repeat: Infinity, delay: i * 0.2 }} />
      ))}
    </div>
  )
}

function SendIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <line x1="22" y1="2" x2="11" y2="13" />
      <polygon points="22 2 15 22 11 13 2 9 22 2" />
    </svg>
  )
}