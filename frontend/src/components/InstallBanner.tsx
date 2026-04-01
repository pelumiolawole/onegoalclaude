'use client'

import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'

const STORAGE_KEY = 'ogp_install_banner'
const MAX_WEEKS = 4

interface BannerState {
  dismissedAt: number   // timestamp of last dismissal
  showCount: number     // how many times it's been shown total
}

function getStoredState(): BannerState | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

function shouldShowBanner(): boolean {
  const state = getStoredState()

  // Never shown before — show it
  if (!state) return true

  // Shown 4+ times — never again
  if (state.showCount >= MAX_WEEKS) return false

  // Check if a full week has passed since last dismissal
  const oneWeek = 7 * 24 * 60 * 60 * 1000
  const now = Date.now()
  return now - state.dismissedAt >= oneWeek
}

function recordDismissal() {
  const state = getStoredState()
  const next: BannerState = {
    dismissedAt: Date.now(),
    showCount: (state?.showCount ?? 0) + 1,
  }
  localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
}

function detectPlatform(): 'ios' | 'android' | 'other' {
  if (typeof navigator === 'undefined') return 'other'
  const ua = navigator.userAgent
  if (/iPad|iPhone|iPod/.test(ua)) return 'ios'
  if (/Android/.test(ua)) return 'android'
  return 'other'
}

function isAlreadyInstalled(): boolean {
  if (typeof window === 'undefined') return false
  return window.matchMedia('(display-mode: standalone)').matches
}

async function requestPushPermission() {
  if (!('Notification' in window) || !('serviceWorker' in navigator)) return

  try {
    const permission = await Notification.requestPermission()
    if (permission !== 'granted') return

    const registration = await navigator.serviceWorker.ready

    // Use the existing VAPID key from the environment
    const vapidKey = process.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY
    if (!vapidKey) return

    const subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: vapidKey,
    })

    // Send to backend — uses existing /push/subscribe endpoint
    const apiUrl = process.env.NEXT_PUBLIC_API_URL
    if (!apiUrl) return

    const token = localStorage.getItem('access_token')
    await fetch(`${apiUrl}/push/subscribe`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({
        endpoint: subscription.endpoint,
        p256dh: btoa(String.fromCharCode(...new Uint8Array(subscription.getKey('p256dh')!))),
        auth: btoa(String.fromCharCode(...new Uint8Array(subscription.getKey('auth')!))),
      }),
    })
  } catch {
    // Silent fail — push is optional
  }
}

const ANDROID_STEPS = [
  { n: 1, text: 'Open this page in Chrome' },
  { n: 2, text: 'Tap the three-dot menu in the top right' },
  { n: 3, text: 'Tap "Add to Home Screen"' },
  { n: 4, text: 'Tap Add to confirm' },
]

const IOS_STEPS = [
  { n: 1, text: 'Open this page in Safari' },
  { n: 2, text: 'Tap the Share button at the bottom' },
  { n: 3, text: 'Scroll down and tap "Add to Home Screen"' },
  { n: 4, text: 'Tap Add in the top right' },
]

export default function InstallBanner() {
  const [visible, setVisible] = useState(false)
  const [platform, setPlatform] = useState<'ios' | 'android' | 'other'>('other')
  const [activeTab, setActiveTab] = useState<'android' | 'ios'>('android')
  const [pushGranted, setPushGranted] = useState(false)

  useEffect(() => {
    if (isAlreadyInstalled()) return
    if (!shouldShowBanner()) return

    const p = detectPlatform()
    setPlatform(p)
    setActiveTab(p === 'ios' ? 'ios' : 'android')
    setPushGranted(typeof Notification !== 'undefined' && Notification.permission === 'granted')

    // Small delay so dashboard loads first
    const t = setTimeout(() => setVisible(true), 1500)
    return () => clearTimeout(t)
  }, [])

  function dismiss() {
    recordDismissal()
    setVisible(false)
  }

  async function handlePushRequest() {
    await requestPushPermission()
    setPushGranted(typeof Notification !== 'undefined' && Notification.permission === 'granted')
  }

  const steps = activeTab === 'ios' ? IOS_STEPS : ANDROID_STEPS

  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          initial={{ opacity: 0, y: -12 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -12 }}
          transition={{ duration: 0.35, ease: 'easeOut' }}
          className="mx-4 mb-5 rounded-2xl border border-[#F59E0B]/20 bg-[#1A1714] overflow-hidden"
          style={{ boxShadow: '0 0 0 1px rgba(245,158,11,0.08), 0 4px 24px rgba(0,0,0,0.4)' }}
        >
          {/* Top bar */}
          <div className="flex items-start justify-between px-4 pt-4 pb-3">
            <div className="flex items-center gap-2.5">
              <div className="w-7 h-7 rounded-lg bg-[#F59E0B]/10 border border-[#F59E0B]/20 flex items-center justify-center shrink-0">
                <span className="text-[#F59E0B] text-xs">⌂</span>
              </div>
              <p className="text-[#E8E2DC] text-sm font-medium leading-snug">
                Add OneGoal Pro to your home screen
              </p>
            </div>
            <button
              onClick={dismiss}
              className="text-[#5C524A] hover:text-[#A09690] transition-colors ml-3 mt-0.5 shrink-0"
              aria-label="Dismiss"
            >
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <path d="M1 1l12 12M13 1L1 13" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
              </svg>
            </button>
          </div>

          {/* Subtitle */}
          <p className="px-4 text-[#7A6E65] text-xs leading-relaxed pb-3">
            Works like a native app — no App Store needed. One tap from your home screen and you're in.
          </p>

          {/* Platform tabs */}
          <div className="px-4 flex gap-2 pb-3">
            {(['android', 'ios'] as const).map(tab => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                  activeTab === tab
                    ? 'bg-[#F59E0B]/15 text-[#F59E0B] border border-[#F59E0B]/25'
                    : 'text-[#5C524A] border border-white/5 hover:text-[#A09690]'
                }`}
              >
                {tab === 'android' ? 'Android' : 'iPhone / iPad'}
                {platform === tab && (
                  <span className="ml-1.5 text-[10px] opacity-60">← you</span>
                )}
              </button>
            ))}
          </div>

          {/* Steps */}
          <div className="px-4 pb-3 space-y-2">
            {steps.map(step => (
              <div key={step.n} className="flex items-start gap-3">
                <span className="w-5 h-5 rounded-full bg-[#2A2520] border border-white/8 flex items-center justify-center text-[10px] text-[#F59E0B] shrink-0 mt-0.5">
                  {step.n}
                </span>
                <p className="text-[#C4BBB5] text-xs leading-relaxed">{step.text}</p>
              </div>
            ))}
          </div>

          {/* Push notification nudge */}
          {!pushGranted && (
            <div className="mx-4 mb-4 px-3 py-2.5 rounded-xl bg-[#0F0D0B] border border-white/5 flex items-center justify-between gap-3">
              <p className="text-[#7A6E65] text-xs leading-relaxed">
                Allow notifications so you don't miss your daily task.
              </p>
              <button
                onClick={handlePushRequest}
                className="shrink-0 text-xs text-[#F59E0B] font-medium hover:text-[#FCD34D] transition-colors"
              >
                Allow
              </button>
            </div>
          )}

          {pushGranted && (
            <div className="mx-4 mb-4 px-3 py-2 rounded-xl bg-[#0F0D0B] border border-white/5 flex items-center gap-2">
              <span className="text-[#22C55E] text-xs">✓</span>
              <p className="text-[#5C524A] text-xs">Notifications on</p>
            </div>
          )}

          {/* Dismiss link */}
          <div className="px-4 pb-4 text-center">
            <button
              onClick={dismiss}
              className="text-[#3D3630] text-xs hover:text-[#5C524A] transition-colors"
            >
              Dismiss — don't show this again for a week
            </button>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}