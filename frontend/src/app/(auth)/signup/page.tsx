'use client'

import { useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { motion } from 'framer-motion'
import { api } from '@/lib/api'
import { useAuthStore } from '@/stores/auth'

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
      router.push('/onboarding')
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

  return (
    <div className="min-h-screen bg-[#0A0908] flex items-center justify-center p-8">
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="w-full max-w-sm"
      >
        <Link href="/" className="font-display text-2xl text-[#F5F1ED] block mb-10">
          One Goal
        </Link>

        <h1 className="font-display text-3xl text-[#F5F1ED] mb-2">
          Begin here
        </h1>
        <p className="text-[#7A6E65] mb-8">
          One goal. One identity. Your transformation starts now.
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
