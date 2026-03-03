'use client'

import { useState, useEffect, useRef } from 'react'
import { useRouter } from 'next/navigation'
import { motion, AnimatePresence } from 'framer-motion'
import TextareaAutosize from 'react-textarea-autosize'
import { api } from '@/lib/api'
import { useAuthStore } from '@/stores/auth'

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
  const [phase, setPhase]       = useState('intro')
  const [started, setStarted]   = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  // Load existing state on mount
  useEffect(() => {
    async function loadState() {
      try {
        const state = await api.onboarding.getInterviewState()
        if (state.messages?.length > 0) {
          setMessages(state.messages)
          setStarted(true)
          setPhase(state.current_phase)
          
          // If resuming in timezone phase, auto-detect and offer
          if (state.current_phase === 'timezone') {
            offerTimezoneDetection()
          }
        }
      } catch {}
    }
    loadState()
  }, [])

  // Scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  // NEW: Auto-detect timezone and offer to user
  function offerTimezoneDetection() {
    const detectedTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone
    
    // Format for display (e.g., "Africa/Lagos" → "Lagos (West Africa)")
    const displayName = formatTimezone(detectedTimezone)
    
    // Add a system message offering the detected timezone
    const offerMessage: Message = {
      role: 'assistant',
      content: `We detected you're in ${displayName}. Is this correct?`
    }
    
    setMessages(prev => [...prev, offerMessage])
    
    // Store the detected value temporarily
    setInput(detectedTimezone)
  }

  // NEW: Format timezone for display
  function formatTimezone(timezone: string): string {
    try {
      const now = new Date()
      const formatter = new Intl.DateTimeFormat('en-US', {
        timeZone: timezone,
        timeZoneName: 'short'
      })
      const parts = formatter.formatToParts(now)
      const offset = parts.find(p => p.type === 'timeZoneName')?.value || ''
      
      // Extract city/region from timezone string
      const city = timezone.split('/').pop()?.replace(/_/g, ' ') || timezone
      
      return `${city} (${offset})`
    } catch {
      return timezone
    }
  }

  // NEW: Handle timezone confirmation
  async function confirmTimezone(confirmed: boolean) {
    if (confirmed) {
      // User confirmed detected timezone
      const detectedTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone
      await sendTimezoneResponse(detectedTimezone)
    } else {
      // User wants to manually enter
      setInput('')
      const manualMessage: Message = {
        role: 'assistant',
        content: 'No problem. What timezone are you in? (e.g., "Lagos", "London", "New York")'
      }
      setMessages(prev => [...prev, manualMessage])
    }
  }

  // NEW: Send timezone response to backend
  async function sendTimezoneResponse(timezone: string) {
    setLoading(true)
    
    const newMessages: Message[] = [...messages, { role: 'user', content: timezone }]
    setMessages(newMessages)

    try {
      const res = await api.onboarding.sendInterviewMessage(timezone)
      setMessages([...newMessages, { role: 'assistant', content: res.message }])
      setPhase(res.phase)

      if (res.is_complete) {
        await refreshUser()
        setTimeout(() => router.push('/goal-setup'), 1200)
      }
    } catch (err) {
      setMessages([
        ...newMessages,
        { role: 'assistant', content: "Something went wrong. Try sending that again." },
      ])
    } finally {
      setLoading(false)
    }
  }

  async function startInterview() {
    setStarted(true)
    setLoading(true)
    try {
      const res = await api.onboarding.sendInterviewMessage(
        "I'm ready to begin."
      )
      setMessages([{ role: 'assistant', content: res.message }])
      setPhase(res.phase)
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  // MODIFIED: Handle send with timezone phase logic
  async function sendMessage() {
    if (!input.trim() || loading) return
    
    // If in timezone phase and we haven't confirmed yet, handle differently
    if (phase === 'timezone' && messages[messages.length - 1]?.content?.includes('detected')) {
      // This is a response to the timezone confirmation
      const response = input.trim().toLowerCase()
      if (response === 'yes' || response === 'y' || response === 'correct') {
        await confirmTimezone(true)
      } else {
        await confirmTimezone(false)
      }
      return
    }

    const text = input.trim()
    setInput('')
    setLoading(true)

    const newMessages: Message[] = [...messages, { role: 'user', content: text }]
    setMessages(newMessages)

    try {
      const res = await api.onboarding.sendInterviewMessage(text)
      setMessages([...newMessages, { role: 'assistant', content: res.message }])
      setPhase(res.phase)

      // NEW: If we just entered timezone phase, offer auto-detection
      if (res.phase === 'timezone' && phase !== 'timezone') {
        offerTimezoneDetection()
      }

      if (res.is_complete) {
        await refreshUser()
        setTimeout(() => router.push('/goal-setup'), 1200)
      }
    } catch (err) {
      setMessages([
        ...newMessages,
        { role: 'assistant', content: "Something went wrong on my end. Try sending that again." },
      ])
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

  // ── Welcome screen ────────────────────────────────────────
  if (!started) {
    return (
      <div className="text-center max-w-lg mx-auto">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
        >
          <div className="w-16 h-16 rounded-2xl bg-[#F59E0B]/10 border border-[#F59E0B]/20 flex items-center justify-center mx-auto mb-8">
            <span className="text-2xl">✦</span>
          </div>

          <h1 className="font-display text-4xl text-[#F59E1ED] mb-4">
            The Discovery Interview
          </h1>
          <p className="text-[#A09690] text-lg leading-relaxed mb-4">
            Before we build your strategy, the AI needs to understand you —
            your situation, what you actually want, and what's been getting in the way.
          </p>
          <p className="text-[#7A6E65] mb-10">
            This is a conversation. Take your time with it.
          </p>

          <button
            onClick={startInterview}
            className="btn btn-primary px-10 h-13 text-base"
          >
            Begin the interview
          </button>
        </motion.div>
      </div>
    )
  }

  // ── Chat UI ───────────────────────────────────────────────
  return (
    <div className="flex flex-col h-[calc(100vh-100px)] max-w-2xl mx-auto w-full">

      {/* Messages */}
      <div className="flex-1 overflow-y-auto space-y-6 pb-6 pr-2">
        <AnimatePresence initial={false}>
          {messages.map((msg, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.35 }}
              className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              {msg.role === 'assistant' && (
                <div className="w-8 h-8 rounded-full bg-[#F59E0B]/15 border border-[#F59E0B]/20 flex items-center justify-center mr-3 mt-0.5 shrink-0">
                  <span className="text-[#F59E0B] text-xs">✦</span>
                </div>
              )}
              <div
                className={`max-w-[85%] px-4 py-3 rounded-2xl text-[0.9375rem] leading-relaxed ${
                  msg.role === 'user'
                    ? 'bg-[#F59E0B]/10 border border-[#F59E0B]/15 text-[#E8E2DC] rounded-tr-sm'
                    : 'bg-[#1E1B18] border border-white/5 text-[#C4BBB5] rounded-tl-sm'
                }`}
              >
                {msg.content}
              </div>
            </motion.div>
          ))}

          {/* Loading dots */}
          {loading && (
            <motion.div
              key="loading"
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex justify-start"
            >
              <div className="w-8 h-8 rounded-full bg-[#F59E0B]/15 border border-[#F59E0B]/20 flex items-center justify-center mr-3 shrink-0">
                <span className="text-[#F59E0B] text-xs">✦</span>
              </div>
              <div className="bg-[#1E1B18] border border-white/5 px-4 py-3 rounded-2xl rounded-tl-sm">
                <TypingDots />
              </div>
            </motion.div>
          )}
        </AnimatePresence>
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="border-t border-white/5 pt-4">
        <div className="flex items-end gap-3 bg-[#141210] border border-white/7 rounded-2xl px-4 py-3 focus-within:border-[#F59E0B]/30 focus-within:shadow-[0_0_0_3px_rgba(245,158,11,0.08)] transition-all">
          <TextareaAutosize
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={phase === 'timezone' && messages[messages.length - 1]?.content?.includes('detected') 
              ? "Type 'yes' to confirm or 'no' to enter manually..." 
              : "Type your response…"}
            minRows={1}
            maxRows={5}
            disabled={loading}
            className="flex-1 bg-transparent text-[#E8E2DC] placeholder:text-[#3D3630] text-[0.9375rem] leading-relaxed resize-none focus:outline-none disabled:opacity-50 font-sans"
          />
          <button
            onClick={sendMessage}
            disabled={!input.trim() || loading}
            className="shrink-0 w-9 h-9 rounded-xl bg-[#F59E0B] disabled:bg-[#2A2520] disabled:text-[#5C524A] text-[#0A0908] flex items-center justify-center transition-all hover:bg-[#FCD34D] disabled:cursor-not-allowed"
          >
            <SendIcon />
          </button>
        </div>
        <p className="text-[#3D3630] text-xs text-center mt-2">
          Press Enter to send · Shift+Enter for new line
        </p>
      </div>
    </div>
  )
}

function TypingDots() {
  return (
    <div className="flex gap-1 items-center h-5">
      {[0, 1, 2].map(i => (
        <motion.div
          key={i}
          className="w-1.5 h-1.5 rounded-full bg-[#5C524A]"
          animate={{ opacity: [0.3, 1, 0.3] }}
          transition={{ duration: 1.2, repeat: Infinity, delay: i * 0.2 }}
        />
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