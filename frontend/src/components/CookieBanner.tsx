'use client'

import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'

const COOKIE_KEY = 'ogp_cookie_consent'

export default function CookieBanner() {
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    try {
      const stored = localStorage.getItem(COOKIE_KEY)
      if (!stored) setVisible(true)
    } catch {
      // localStorage unavailable — don't show
    }
  }, [])

  function accept() {
    try { localStorage.setItem(COOKIE_KEY, 'accepted') } catch {}
    setVisible(false)
  }

  function decline() {
    try { localStorage.setItem(COOKIE_KEY, 'declined') } catch {}
    setVisible(false)
  }

  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 16 }}
          transition={{ duration: 0.3, ease: 'easeOut' }}
          className="fixed bottom-20 md:bottom-6 left-4 right-4 md:left-auto md:right-6 md:max-w-sm z-50"
        >
          <div
            className="rounded-2xl border border-white/8 bg-[#1A1714] px-5 py-4"
            style={{ boxShadow: '0 8px 32px rgba(0,0,0,0.5), 0 0 0 1px rgba(255,255,255,0.04)' }}
          >
            <p className="text-[#E8E2DC] text-sm font-medium mb-1">This site uses cookies</p>
            <p className="text-[#5C524A] text-xs leading-relaxed mb-4">
              We use essential cookies to keep you logged in and remember your preferences. No tracking or advertising cookies.{' '}
              <a
                href="/privacy"
                className="text-[#7A6E65] underline underline-offset-2 hover:text-[#A09690] transition-colors"
              >
                Privacy policy
              </a>
              {' '}·{' '}
              <a
                href="/terms"
                className="text-[#7A6E65] underline underline-offset-2 hover:text-[#A09690] transition-colors"
              >
                Terms
              </a>
            </p>
            <div className="flex gap-2">
              <button
                onClick={accept}
                className="flex-1 h-9 rounded-xl bg-[#F59E0B] text-[#0A0908] text-sm font-medium hover:bg-[#FCD34D] transition-colors"
              >
                Accept
              </button>
              <button
                onClick={decline}
                className="flex-1 h-9 rounded-xl border border-white/8 text-[#5C524A] text-sm hover:text-[#A09690] hover:border-white/15 transition-all"
              >
                Decline
              </button>
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
