'use client'

import { useEffect, useState, Suspense } from 'react'
import { useSearchParams } from 'next/navigation'
import Link from 'next/link'
import { CheckCircle, ArrowRight, Loader2 } from 'lucide-react'
import { api } from '@/lib/api'

// Loading fallback component
function SuccessLoading() {
  return (
    <div className="min-h-screen bg-[#0a0a0a] flex items-center justify-center">
      <div className="text-center">
        <Loader2 className="w-8 h-8 text-[#d0ff59] animate-spin mx-auto mb-4" />
        <p className="text-white/60">Verifying your subscription...</p>
      </div>
    </div>
  )
}

// Main content component that uses useSearchParams
function SuccessContent() {
  const searchParams = useSearchParams()
  const sessionId = searchParams.get('session_id')
  const [subscription, setSubscription] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!sessionId) {
      setError('No session ID found')
      setLoading(false)
      return
    }

    const verifySession = async () => {
      try {
        const response = await api.post('/billing/verify-session', {
          session_id: sessionId
        })
        setSubscription(response.data)
      } catch (err) {
        setError('Failed to verify subscription')
      } finally {
        setLoading(false)
      }
    }

    verifySession()
  }, [sessionId])

  if (loading) {
    return (
      <div className="min-h-screen bg-[#0a0a0a] flex items-center justify-center">
        <div className="text-center">
          <Loader2 className="w-8 h-8 text-[#d0ff59] animate-spin mx-auto mb-4" />
          <p className="text-white/60">Verifying your subscription...</p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="min-h-screen bg-[#0a0a0a] flex items-center justify-center p-4">
        <div className="max-w-md w-full bg-white/5 border border-white/10 rounded-2xl p-8 text-center">
          <div className="w-16 h-16 bg-red-500/20 rounded-full flex items-center justify-center mx-auto mb-4">
            <span className="text-red-400 text-2xl">✕</span>
          </div>
          <h1 className="text-2xl font-bold text-white mb-2">Something went wrong</h1>
          <p className="text-white/60 mb-6">{error}</p>
          <Link
            href="/settings"
            className="inline-flex items-center gap-2 px-6 py-3 bg-[#d0ff59] text-black font-medium rounded-xl hover:bg-[#d0ff59]/90 transition-colors"
          >
            Go to Settings
            <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      </div>
    )
  }

  const currentPlan = subscription?.plan === 'forge' 
    ? { name: 'The Forge', description: 'You now have unlimited access to the AI Coach and advanced features.' }
    : { name: 'The Identity', description: 'You now have full access including priority support and re-interview capability.' }

  return (
    <div className="min-h-screen bg-[#0a0a0a] flex items-center justify-center p-4">
      <div className="max-w-md w-full bg-white/5 border border-white/10 rounded-2xl p-8 text-center">
        {/* Success Icon */}
        <div className="w-16 h-16 bg-[#d0ff59]/20 rounded-full flex items-center justify-center mx-auto mb-4">
          <CheckCircle className="w-8 h-8 text-[#d0ff59]" />
        </div>

        <h1 className="text-2xl font-bold text-white mb-2">
          Welcome to {currentPlan.name}!
        </h1>
        <p className="text-white/60 mb-6">{currentPlan.description}</p>

        <div className="bg-white/5 rounded-xl p-4 mb-6 text-left">
          <h3 className="text-sm font-medium text-white/80 mb-2">What's included:</h3>
          <ul className="space-y-2 text-sm text-white/60">
            {subscription?.plan === 'forge' && (
              <>
                <li className="flex items-center gap-2">
                  <span className="text-[#d0ff59]">✓</span> Unlimited AI coach messages
                </li>
                <li className="flex items-center gap-2">
                  <span className="text-[#d0ff59]">✓</span> Weekly progress reviews
                </li>
                <li className="flex items-center gap-2">
                  <span className="text-[#d0ff59]">✓</span> Advanced analytics
                </li>
              </>
            )}
            {subscription?.plan === 'identity' && (
              <>
                <li className="flex items-center gap-2">
                  <span className="text-[#d0ff59]">✓</span> Everything in Forge
                </li>
                <li className="flex items-center gap-2">
                  <span className="text-[#d0ff59]">✓</span> Priority support
                </li>
                <li className="flex items-center gap-2">
                  <span className="text-[#d0ff59]">✓</span> Re-interview capability
                </li>
              </>
            )}
          </ul>
        </div>

        {subscription?.current_period_end && (
          <p className="text-sm text-white/40 mb-6">
            Your subscription renews on {new Date(subscription.current_period_end).toLocaleDateString()}
          </p>
        )}

        <div className="flex flex-col gap-3">
          <Link
            href="/dashboard"
            className="inline-flex items-center justify-center gap-2 px-6 py-3 bg-[#d0ff59] text-black font-medium rounded-xl hover:bg-[#d0ff59]/90 transition-colors"
          >
            Go to Dashboard
            <ArrowRight className="w-4 h-4" />
          </Link>
          <Link
            href="/settings"
            className="inline-flex items-center justify-center gap-2 px-6 py-3 bg-white/10 text-white font-medium rounded-xl hover:bg-white/20 transition-colors"
          >
            Manage Subscription
          </Link>
        </div>
      </div>
    </div>
  )
}

// Main page component with Suspense boundary
export default function SuccessPage() {
  return (
    <Suspense fallback={<SuccessLoading />}>
      <SuccessContent />
    </Suspense>
  )
}