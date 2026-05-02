'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { motion } from 'framer-motion'
import { api } from '@/lib/api'
import { useAuthStore } from '@/stores/auth'
import OneGoalLogo from '@/components/OneGoalLogo'

const SUPABASE_URL = 'https://guqlwplztxxiseyenbye.supabase.co'
const REDIRECT_URL = 'https://onegoalpro.app/auth/callback'

export default function SignupPage() {
  const router = useRouter()
  const setAuth = useAuthStore(s => s.setAuth)

  const [preAnswer, setPreAnswer] = useState<string | null>(null)
  const [form, setForm] = useState({
    display_name: '',
    email: '',
    password: '',
    confirmPassword: '',
  })
  const [error, setError]           = useState('')
  const [loading, setLoading]       = useState(false)
  const [googleLoading, setGoogleLoading] = useState(false)
  const [showVerificationMessage, setShowVerificationMessage] = useState(false)

  useEffect(() => {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('ogp_pre_answer')
      if (saved) setPreAnswer(saved)
    }
  }, [])

  function update(field: string, value: string) {
    setForm(f => ({ ...f, [field]: value }))
    setError('')
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')

    if (form.password !== form.confirmPassword) {
      setError('Passwords do not match.')
      return
    }
    if (form.password.length < 8) {
      setError('Password must be at least 8 characters.')
      return
    }

    setLoading(true)
    try {
      const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone
      const data = await api.auth.signup({
        email: form.email,
        password: form.password,
        display_name: form.display_name || undefined,
        timezone,
      })
      setAuth(data)
      setShowVerificationMessage(true)
    } catch (err: any) {
      const detail = err.detail
      if (typeof detail === 'string') setError(detail)
      else if (Array.isArray(detail)) setError(detail[0]?.message || 'Signup failed.')
      else setError('Signup failed. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  function handleGoogle() {
    setGoogleLoading(true)
    const url = `${SUPABASE_URL}/auth/v1/authorize?provider=google&redirect_to=${encodeURIComponent(REDIRECT_URL)}`
    window.location.href = url
  }

  if (showVerificationMessage) {
    return (
      <div className="min-h-screen bg-[#0A0908] flex items-center justify-center p-8">
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.5 }}
          className="w-full max-w-sm text-center"
        >
          <Link href="/" className="block mb-10">
            <OneGoalLogo size={30} textSize="text-2xl" />
          </Link>
          <div className="mx-auto flex items-center justify-center h-16 w-16 rounded-full bg-amber-950/40 border border-amber-900/30 mb-6">
            <svg className="h-8 w-8 text-[#F59E0B]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
            </svg>
          </div>
          <h1 className="font-display text-3xl text-[#F5F1ED] mb-4">Check your email</h1>
          <p className="text-[#A09690] mb-2">We sent a verification link to</p>
          <p className="text-[#F5F1ED] font-medium mb-6">{form.email}</p>
          <p className="text-[#7A6E65] text-sm mb-8 leading-relaxed">
            Click the link in that email to activate your account. Once verified, you&apos;ll be ready to start your interview.
          </p>
          <div className="space-y-3">
            <button
              onClick={() => router.push('/resend-verification?email=' + encodeURIComponent(form.email))}
              className="block w-full py-3 px-4 rounded-xl bg-[#F59E0B] text-[#0A0908] font-medium hover:bg-[#FCD34D] transition-colors"
            >
              Resend verification email
            </button>
            <button
              onClick={() => router.push('/login')}
              className="block w-full py-3 px-4 rounded-xl border border-[#3D3630] text-[#A09690] hover:text-[#F5F1ED] hover:border-[#5C524A] transition-colors"
            >
              I already verified — go to login
            </button>
          </div>
          <p className="mt-8 text-[#3D3630] text-xs">Didn&apos;t receive it? Check your spam folder or click resend above.</p>
        </motion.div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-[#0A0908] flex items-center justify-center p-8">
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="w-full max-w-sm"
      >
        <Link href="/" className="block mb-10">
          <OneGoalLogo size={30} textSize="text-2xl" />
        </Link>

        {/* Pre-answer echo — shows what they typed on the landing page */}
        {preAnswer ? (
          <motion.div
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4 }}
            className="mb-8 p-4 rounded-xl bg-[#F59E0B]/6 border border-[#F59E0B]/15"
          >
            <p className="text-[#5C524A] text-xs uppercase tracking-widest font-mono mb-2">You said</p>
            <p className="text-[#C4BBB5] text-sm leading-relaxed italic">"{preAnswer}"</p>
            <p className="text-[#5C524A] text-xs mt-2">
              The interview starts here. Create your account to continue.
            </p>
          </motion.div>
        ) : (
          <>
            <h1 className="font-display text-3xl text-[#F5F1ED] mb-2">Begin here</h1>
            <p className="text-[#7A6E65] mb-8">The interview takes about 15 minutes. That&apos;s where everything starts.</p>
          </>
        )}

        {error && (
          <motion.div
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            className="mb-6 px-4 py-3 rounded-xl bg-red-950/40 border border-red-900/30 text-red-400 text-sm"
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

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-[#A09690] text-sm mb-1.5">
              Your name <span className="text-[#5C524A]">(optional)</span>
            </label>
            <input
              type="text"
              value={form.display_name}
              onChange={e => update('display_name', e.target.value)}
              placeholder="What should we call you?"
              className="input-base"
            />
          </div>
          <div>
            <label className="block text-[#A09690] text-sm mb-1.5">Email</label>
            <input
              type="email"
              value={form.email}
              onChange={e => update('email', e.target.value)}
              placeholder="you@example.com"
              required
              className="input-base"
            />
          </div>
          <div>
            <label className="block text-[#A09690] text-sm mb-1.5">Password</label>
            <input
              type="password"
              value={form.password}
              onChange={e => update('password', e.target.value)}
              placeholder="At least 8 characters"
              required
              className="input-base"
            />
          </div>
          <div>
            <label className="block text-[#A09690] text-sm mb-1.5">Confirm password</label>
            <input
              type="password"
              value={form.confirmPassword}
              onChange={e => update('confirmPassword', e.target.value)}
              placeholder="Same password again"
              required
              className="input-base"
            />
          </div>

          <button
            type="submit"
            disabled={loading || googleLoading}
            className="btn btn-primary w-full mt-6 h-12 text-base"
          >
            {loading ? 'Creating account...' : 'Create account'}
          </button>
        </form>

        <p className="mt-6 text-center text-[#5C524A] text-sm">
          Already have an account?{' '}
          <Link href="/login" className="text-[#F59E0B] hover:text-[#FCD34D] transition-colors">Sign in</Link>
        </p>
        <p className="mt-8 text-center text-[#3D3630] text-xs leading-relaxed">
          By creating an account you agree to our{' '}
          <Link href="/terms" className="underline hover:text-[#7A6E65] transition-colors">
            Terms of Service
          </Link>
          {' '}and{' '}
          <Link href="/privacy" className="underline hover:text-[#7A6E65] transition-colors">
            Privacy Policy
          </Link>
          . Your data is yours and can be exported or deleted at any time.
        </p>
      </motion.div>
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