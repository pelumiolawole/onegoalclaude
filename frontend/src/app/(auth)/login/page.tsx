'use client'

import { useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { motion } from 'framer-motion'
import { api } from '@/lib/api'
import { useAuthStore } from '@/stores/auth'

export default function LoginPage() {
  const router = useRouter()
  const setAuth = useAuthStore(s => s.setAuth)

  const [email, setEmail]       = useState('')
  const [password, setPassword] = useState('')
  const [error, setError]       = useState('')
  const [loading, setLoading]   = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)

    try {
      const data = await api.auth.login(email, password)
      setAuth(data)

      // Route based on onboarding status
      const step = data.user.onboarding_step
      if (step < 5) {
        router.push('/onboarding')
      } else {
        router.push('/dashboard')
      }
    } catch (err: any) {
      setError(err.detail || 'Login failed. Check your email and password.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-[#0A0908] flex">

      {/* ── Left: Visual ────────────────────────────────── */}
      <div className="hidden lg:flex lg:w-1/2 relative overflow-hidden">
        {/* Ambient background */}
        <div className="absolute inset-0 bg-gradient-to-br from-[#1a1208] via-[#0A0908] to-[#0A0908]" />
        <div
          className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[500px] h-[500px] rounded-full opacity-20"
          style={{ background: 'radial-gradient(circle, rgba(245,158,11,0.4) 0%, transparent 70%)' }}
        />

        <div className="relative z-10 flex flex-col justify-between p-16 w-full">
          {/* Logo */}
          <div>
            <span className="font-display text-2xl text-[#F5F1ED]">One Goal</span>
          </div>

          {/* Quote */}
          <div className="max-w-sm">
            <motion.blockquote
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.3, duration: 0.8 }}
              className="font-display text-3xl leading-snug text-[#E8E2DC] italic"
            >
              "You do not rise to the level of your goals. You fall to the level of your systems."
            </motion.blockquote>
            <motion.p
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.7 }}
              className="mt-4 text-[#7A6E65] text-sm tracking-widest uppercase"
            >
              — James Clear
            </motion.p>
          </div>

          {/* Bottom note */}
          <p className="text-[#3D3630] text-sm">
            One Goal. One identity. One day at a time.
          </p>
        </div>
      </div>

      {/* ── Right: Form ─────────────────────────────────── */}
      <div className="w-full lg:w-1/2 flex items-center justify-center p-8">
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="w-full max-w-sm"
        >
          {/* Mobile logo */}
          <div className="lg:hidden mb-10">
            <span className="font-display text-2xl text-[#F5F1ED]">One Goal</span>
          </div>

          <h1 className="font-display text-3xl text-[#F5F1ED] mb-2">
            Welcome back
          </h1>
          <p className="text-[#7A6E65] mb-8">
            Continue your transformation.
          </p>

          {error && (
            <motion.div
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0 }}
              className="mb-6 px-4 py-3 rounded-xl bg-red-950/40 border border-red-900/30 text-red-400 text-sm"
            >
              {error}
            </motion.div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-[#A09690] text-sm mb-1.5">
                Email
              </label>
              <input
                type="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                placeholder="you@example.com"
                required
                className="input-base"
              />
            </div>

            <div>
              <label className="block text-[#A09690] text-sm mb-1.5">
                Password
              </label>
              <input
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="••••••••"
                required
                className="input-base"
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="btn btn-primary w-full mt-6 h-12 text-base"
            >
              {loading ? (
                <span className="flex items-center gap-2">
                  <Spinner /> Signing in...
                </span>
              ) : (
                'Sign in'
              )}
            </button>
          </form>

          <p className="mt-6 text-center text-[#5C524A] text-sm">
            No account?{' '}
            <Link href="/signup" className="text-[#F59E0B] hover:text-[#FCD34D] transition-colors">
              Start your journey
            </Link>
          </p>
        </motion.div>
      </div>
    </div>
  )
}

function Spinner() {
  return (
    <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  )
}
