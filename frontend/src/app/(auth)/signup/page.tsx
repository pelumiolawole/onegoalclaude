'use client'

import { useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { motion } from 'framer-motion'
import { api } from '@/lib/api'
import { useAuthStore } from '@/stores/auth'
import OneGoalLogo from '@/components/OneGoalLogo'

export default function SignupPage() {
  const router = useRouter()
  const setAuth = useAuthStore(s => s.setAuth)

  const [form, setForm] = useState({
    display_name: '',
    email: '',
    password: '',
    confirmPassword: '',
  })
  const [error, setError]   = useState('')
  const [loading, setLoading] = useState(false)
  const [showVerificationMessage, setShowVerificationMessage] = useState(false)

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
      
      // Store auth data for auto-login after verification
      setAuth(data)
      
      // Show verification message instead of redirecting
      setShowVerificationMessage(true)
      
    } catch (err: any) {
      const detail = err.detail
      if (typeof detail === 'string') {
        setError(detail)
      } else if (Array.isArray(detail)) {
        setError(detail[0]?.message || 'Signup failed.')
      } else {
        setError('Signup failed. Please try again.')
      }
    } finally {
      setLoading(false)
    }
  }

  // Show verification success message
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
            <svg 
              className="h-8 w-8 text-[#F59E0B]" 
              fill="none" 
              viewBox="0 0 24 24" 
              stroke="currentColor"
            >
              <path 
                strokeLinecap="round" 
                strokeLinejoin="round" 
                strokeWidth={2} 
                d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" 
              />
            </svg>
          </div>

          <h1 className="font-display text-3xl text-[#F5F1ED] mb-4">
            Check your email
          </h1>
          
          <p className="text-[#A09690] mb-2">
            We sent a verification link to
          </p>
          <p className="text-[#F5F1ED] font-medium mb-6">
            {form.email}
          </p>
          
          <p className="text-[#7A6E65] text-sm mb-8 leading-relaxed">
            Click the link in that email to activate your account. 
            Once verified, you&apos;ll be ready to start your interview.
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

          <p className="mt-8 text-[#3D3630] text-xs">
            Didn&apos;t receive it? Check your spam folder or click resend above.
          </p>
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

        <h1 className="font-display text-3xl text-[#F5F1ED] mb-2">
          Begin here
        </h1>
        <p className="text-[#7A6E65] mb-8">
          The interview takes about 15 minutes. That&apos;s where everything starts.
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
            disabled={loading}
            className="btn btn-primary w-full mt-6 h-12 text-base"
          >
            {loading ? 'Creating account...' : 'Create account'}
          </button>
        </form>

        <p className="mt-6 text-center text-[#5C524A] text-sm">
          Already have an account?{' '}
          <Link href="/login" className="text-[#F59E0B] hover:text-[#FCD34D] transition-colors">
            Sign in
          </Link>
        </p>

        <p className="mt-8 text-center text-[#3D3630] text-xs leading-relaxed">
          By creating an account you agree to our terms. Your data is yours
          and can be exported or deleted at any time.
        </p>
      </motion.div>
    </div>
  )
}