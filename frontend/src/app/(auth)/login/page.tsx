'use client'

import { useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { motion } from 'framer-motion'
import { api } from '@/lib/api'
import { useAuthStore } from '@/stores/auth'
import OneGoalLogo from '@/components/OneGoalLogo'

const SUPABASE_URL = 'https://guqlwplztxxiseyenbye.supabase.co'
const REDIRECT_URL = 'https://onegoalpro.app/auth/callback'

export default function LoginPage() {
  const router = useRouter()
  const setAuth = useAuthStore(s => s.setAuth)

  const [email, setEmail]       = useState('')
  const [password, setPassword] = useState('')
  const [error, setError]       = useState<string | React.ReactNode>('')
  const [loading, setLoading]   = useState(false)
  const [googleLoading, setGoogleLoading] = useState(false)
  const [showResendLink, setShowResendLink] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setShowResendLink(false)
    setLoading(true)

    try {
      const data = await api.auth.login(email, password)
      setAuth(data)

      const step = data.user.onboarding_step
      if (step === 0 || step === 1) router.push('/interview')
      else if (step === 2) router.push('/goal-setup')
      else if (step === 3) router.push('/preview')
      else if (step === 4) router.push('/activate')
      else router.push('/dashboard')
    } catch (err: any) {
      if (err.status === 403 && err.detail?.toLowerCase().includes('not verified')) {
        setShowResendLink(true)
        setError(
          <span>
            Email not verified.{' '}
            <Link
              href={`/resend-verification?email=${encodeURIComponent(email)}`}
              className="underline text-[#F59E0B] hover:text-[#FCD34D]"
            >
              Resend verification email
            </Link>
          </span>
        )
      } else {
        setError(err.detail || 'Login failed. Check your email and password.')
      }
    } finally {
      setLoading(false)
    }
  }

  function handleGoogle() {
    setGoogleLoading(true)
    const url = `${SUPABASE_URL}/auth/v1/authorize?provider=google&redirect_to=${encodeURIComponent(REDIRECT_URL)}`
    window.location.href = url
  }

  return (
    <div className="min-h-screen bg-[#0A0908] flex">

      {/* Left: Visual */}
      <div className="hidden lg:flex lg:w-1/2 relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-br from-[#1a1208] via-[#0A0908] to-[#0A0908]" />
        <div
          className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[500px] h-[500px] rounded-full opacity-20"
          style={{ background: 'radial-gradient(circle, rgba(245,158,11,0.4) 0%, transparent 70%)' }}
        />
        <div className="relative z-10 flex flex-col justify-between p-16 w-full">
          <OneGoalLogo size={30} textSize="text-2xl" />
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3, duration: 0.8 }}
            className="max-w-sm"
          >
            <blockquote className="font-display text-3xl leading-snug text-[#E8E2DC] italic">
              "You do not rise to the level of your goals. You fall to the level of your systems."
            </blockquote>
            <p className="mt-4 text-[#7A6E65] text-sm tracking-widest uppercase">— James Clear</p>
          </motion.div>
          <p className="text-[#3D3630] text-sm">One Goal. One identity. One day at a time.</p>
        </div>
      </div>

      {/* Right: Form */}
      <div className="w-full lg:w-1/2 flex items-center justify-center p-8">
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="w-full max-w-sm"
        >
          <div className="lg:hidden mb-10">
            <OneGoalLogo size={30} textSize="text-2xl" />
          </div>

          <h1 className="font-display text-3xl text-[#F5F1ED] mb-2">Welcome back</h1>
          <p className="text-[#7A6E65] mb-8">Pick up where you left off.</p>

          {error && (
            <motion.div
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0 }}
              className={`mb-6 px-4 py-3 rounded-xl text-sm ${
                showResendLink
                  ? 'bg-amber-950/40 border border-amber-900/30 text-amber-400'
                  : 'bg-red-950/40 border border-red-900/30 text-red-400'
              }`}
            >
              {error}
            </motion.div>
          )}

          {/* Google button */}
          <button
            onClick={handleGoogle}
            disabled={googleLoading || loading}
            className="w-full h-11 flex items-center justify-center gap-3 bg-white text-[#1a1a1a] rounded-xl text-sm font-medium hover:bg-gray-100 transition-colors disabled:opacity-50 mb-6"
          >
            {googleLoading ? <Spinner dark /> : <GoogleIcon />}
            Continue with Google
          </button>

          {/* Divider */}
          <div className="flex items-center gap-3 mb-6">
            <div className="flex-1 h-px bg-white/5" />
            <span className="text-[#3D3630] text-xs">or</span>
            <div className="flex-1 h-px bg-white/5" />
          </div>

          {/* Email form */}
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-[#A09690] text-sm mb-1.5">Email</label>
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
              <div className="flex items-center justify-between mb-1.5">
                <label className="text-[#A09690] text-sm">Password</label>
                <Link href="/forgot-password" className="text-[#F59E0B] hover:text-[#FCD34D] text-sm transition-colors">
                  Forgot password?
                </Link>
              </div>
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
              disabled={loading || googleLoading}
              className="btn btn-primary w-full mt-6 h-12 text-base"
            >
              {loading ? <span className="flex items-center gap-2"><Spinner /> Signing in...</span> : 'Sign in'}
            </button>
          </form>

          <p className="mt-6 text-center text-[#5C524A] text-sm">
            No account?{' '}
            <Link href="/signup" className="text-[#F59E0B] hover:text-[#FCD34D] transition-colors">Create one</Link>
          </p>
        </motion.div>
      </div>
    </div>
  )
}

function Spinner({ dark }: { dark?: boolean }) {
  return (
    <svg className={`animate-spin h-4 w-4 ${dark ? 'text-[#1a1a1a]' : 'text-current'}`} viewBox="0 0 24 24" fill="none">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  )
}

function GoogleIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24">
      <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
      <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
      <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
      <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
    </svg>
  )
}