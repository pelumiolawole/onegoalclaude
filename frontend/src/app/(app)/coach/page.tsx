'use client'

import { useState, useEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import TextareaAutosize from 'react-textarea-autosize'
import { api } from '@/lib/api'
import { useAuthStore } from '@/stores/auth'

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  streaming?: boolean
}

export default function CoachPage() {
  const { user }  = useAuthStore()
  const [sessionId, setSessionId]   = useState<string | null>(null)
  const [messages,  setMessages]    = useState<Message[]>([])
  const [input,     setInput]       = useState('')
  const [streaming, setStreaming]   = useState(false)
  const [loading,   setLoading]     = useState(true)
  const bottomRef = useRef<HTMLDivElement>(null)
  const msgId     = useRef(0)

  // Load active session
  useEffect(() => {
    api.coach.getActiveSession()
      .then(res => {
        setSessionId(res.session_id)
        setMessages(res.messages.map((m: any) => ({
          id: String(msgId.current++),
          role: m.role,
          content: m.content,
        })))
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function sendMessage() {
    if (!input.trim() || streaming || !sessionId) return
    const text = input.trim()
    setInput('')
    setStreaming(true)

    // Add user message
    const userId = String(msgId.current++)
    setMessages(prev => [...prev, { id: userId, role: 'user', content: text }])

    // Add empty assistant message for streaming
    const aiId = String(msgId.current++)
    setMessages(prev => [...prev, { id: aiId, role: 'assistant', content: '', streaming: true }])

    try {
      const res = await api.coach.streamMessage(sessionId, text)
      if (!res.body) throw new Error('No stream body')

      const reader  = res.body.getReader()
      const decoder = new TextDecoder()
      let fullText  = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        const chunk = decoder.decode(value, { stream: true })
        const lines = chunk.split('\n')

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const data = line.slice(6)
          if (data === '[DONE]' || data.startsWith('[ERROR]')) break
          // Unescape newlines from SSE format
          fullText += data.replace(/\\n/g, '\n')
          setMessages(prev =>
            prev.map(m => m.id === aiId ? { ...m, content: fullText } : m)
          )
        }
      }

      // Mark streaming done
      setMessages(prev =>
        prev.map(m => m.id === aiId ? { ...m, streaming: false } : m)
      )
    } catch {
      setMessages(prev =>
        prev.map(m => m.id === aiId
          ? { ...m, content: "Something went wrong. Please try again.", streaming: false }
          : m
        )
      )
    } finally {
      setStreaming(false)
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  const name = user?.display_name?.split(' ')[0] || 'you'

  return (
    <div className="flex flex-col h-screen max-h-screen">

      {/* Header */}
      <div className="flex items-center gap-3 px-6 py-4 border-b border-white/5 shrink-0">
        <div className="w-9 h-9 rounded-xl bg-[#F59E0B]/15 border border-[#F59E0B]/20 flex items-center justify-center">
          <span className="text-[#F59E0B] text-sm">✦</span>
        </div>
        <div>
          <p className="text-[#E8E2DC] text-sm font-medium">Your Coach</p>
          <p className="text-[#3D3630] text-xs">Knows you and your goal deeply</p>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-6 py-6 space-y-5">

        {loading && (
          <div className="flex justify-center py-12">
            <div className="w-6 h-6 border-2 border-[#F59E0B]/20 border-t-[#F59E0B] rounded-full animate-spin" />
          </div>
        )}

        {/* Empty state */}
        {!loading && messages.length === 0 && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="text-center py-16 max-w-sm mx-auto"
          >
            <div className="w-14 h-14 rounded-2xl bg-[#F59E0B]/10 border border-[#F59E0B]/15 flex items-center justify-center mx-auto mb-5">
              <span className="text-[#F59E0B] text-2xl">✦</span>
            </div>
            <h2 className="font-display text-xl text-[#E8E2DC] mb-3">
              Your coach is ready
            </h2>
            <p className="text-[#5C524A] text-sm leading-relaxed mb-6">
              Ask anything about your goal, your progress, or what's holding you back.
              Your coach knows your full context.
            </p>
            <div className="space-y-2">
              {STARTERS.map(s => (
                <button
                  key={s}
                  onClick={() => setInput(s)}
                  className="w-full text-left text-sm px-4 py-2.5 rounded-xl bg-[#141210] border border-white/5 text-[#7A6E65] hover:text-[#A09690] hover:border-white/10 transition-all"
                >
                  {s}
                </button>
              ))}
            </div>
          </motion.div>
        )}

        <AnimatePresence initial={false}>
          {messages.map((msg) => (
            <motion.div
              key={msg.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3 }}
              className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              {msg.role === 'assistant' && (
                <div className="w-7 h-7 rounded-full bg-[#F59E0B]/15 border border-[#F59E0B]/20 flex items-center justify-center mr-2.5 mt-0.5 shrink-0">
                  <span className="text-[#F59E0B] text-[10px]">✦</span>
                </div>
              )}
              <div
                className={`max-w-[82%] px-4 py-3 rounded-2xl text-sm leading-relaxed ${
                  msg.role === 'user'
                    ? 'bg-[#F59E0B]/10 border border-[#F59E0B]/15 text-[#E8E2DC] rounded-tr-sm'
                    : 'bg-[#1E1B18] border border-white/5 text-[#C4BBB5] rounded-tl-sm'
                }`}
              >
                {msg.content || (msg.streaming ? <TypingDots /> : '')}
                {msg.streaming && msg.content && (
                  <motion.span
                    animate={{ opacity: [1, 0] }}
                    transition={{ duration: 0.5, repeat: Infinity }}
                    className="inline-block w-0.5 h-3.5 bg-[#F59E0B] ml-0.5 align-middle"
                  />
                )}
              </div>
            </motion.div>
          ))}
        </AnimatePresence>

        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="border-t border-white/5 p-4 shrink-0">
        <div className="flex items-end gap-3 bg-[#141210] border border-white/7 rounded-2xl px-4 py-3 focus-within:border-[#F59E0B]/30 focus-within:shadow-[0_0_0_3px_rgba(245,158,11,0.08)] transition-all max-w-3xl mx-auto">
          <TextareaAutosize
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={`What's on your mind, ${name}?`}
            minRows={1}
            maxRows={6}
            disabled={streaming || !sessionId}
            className="flex-1 bg-transparent text-[#E8E2DC] placeholder:text-[#3D3630] text-sm leading-relaxed resize-none focus:outline-none disabled:opacity-50 font-sans"
          />
          <button
            onClick={sendMessage}
            disabled={!input.trim() || streaming || !sessionId}
            className="shrink-0 w-8 h-8 rounded-xl bg-[#F59E0B] disabled:bg-[#2A2520] disabled:text-[#5C524A] text-[#0A0908] flex items-center justify-center transition-all hover:bg-[#FCD34D] disabled:cursor-not-allowed"
          >
            {streaming ? (
              <span className="w-3 h-3 border border-[#0A0908]/30 border-t-[#0A0908] rounded-full animate-spin" />
            ) : (
              <SendIcon />
            )}
          </button>
        </div>
      </div>
    </div>
  )
}

function TypingDots() {
  return (
    <span className="inline-flex gap-1 items-center h-4">
      {[0, 1, 2].map(i => (
        <motion.span
          key={i}
          className="w-1 h-1 rounded-full bg-[#5C524A] inline-block"
          animate={{ opacity: [0.3, 1, 0.3] }}
          transition={{ duration: 1.2, repeat: Infinity, delay: i * 0.2 }}
        />
      ))}
    </span>
  )
}

function SendIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <line x1="22" y1="2" x2="11" y2="13" />
      <polygon points="22 2 15 22 11 13 2 9 22 2" />
    </svg>
  )
}

const STARTERS = [
  "I've been struggling to stay consistent this week.",
  "What should I focus on right now?",
  "I'm feeling stuck and not sure why.",
]
