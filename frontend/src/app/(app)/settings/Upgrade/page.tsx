// frontend/src/app/(app)/settings/upgrade/page.tsx

'use client'

import { useEffect, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { motion } from 'framer-motion'
import { Loader2, Sparkles, Shield, Check, ArrowLeft } from 'lucide-react'
import { api } from '@/lib/api'

export default function UpgradePage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const plan = searchParams.get('plan') as 'forge' | 'identity' | null
  
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const plans = {
    forge: {
      name: 'The Forge',
      price: { monthly: 9, annual: 90 },
      features: ['Unlimited AI coaching', 'Daily task generation', 'Progress tracking', 'Priority support'],
      color: 'text-[#F59E0B]',
      bg: 'bg-[#F59E0B]/10',
      icon: Sparkles
    },
    identity: {
      name: 'The Identity',
      price: { monthly: 29, annual: 290 },
      features: ['Everything in Forge', 'Weekly 1-on-1 coaching', 'Custom goal frameworks', 'Identity transformation', 'Direct coach access'],
      color: 'text-[#d0ff59]',
      bg: 'bg-[#d0ff59]/10',
      icon: Shield
    }
  }

  const selectedPlan = plan && plans[plan] ? plans[plan] : plans.forge

  const handleCheckout = async (billingCycle: 'monthly' | 'annual') => {
    setLoading(true)
    setError('')
    try {
      // FIX: Use createCheckout, not createCheckoutSession
      const response = await api.billing.createCheckout({
        plan: plan || 'forge',
        billing_cycle: billingCycle
      })
      window.location.href = response.url
    } catch (err: any) {
      setError(err.detail || 'Failed to start checkout')
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-[#0A0908]">
      <div className="max-w-2xl mx-auto px-6 py-12">
        
        <button 
          onClick={() => router.back()} 
          className="flex items-center gap-2 text-[#5C524A] hover:text-[#C4BBB5] mb-8 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to Settings
        </button>

        <motion.div 
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="bg-[#141210] border border-white/5 rounded-2xl p-8"
        >
          <div className={`w-16 h-16 rounded-2xl ${selectedPlan.bg} flex items-center justify-center mb-6`}>
            <selectedPlan.icon className={`w-8 h-8 ${selectedPlan.color}`} />
          </div>

          <h1 className="font-display text-3xl text-[#F5F1ED] mb-2">
            Upgrade to {selectedPlan.name}
          </h1>
          <p className="text-[#7A6E65] mb-8">
            Choose your billing cycle
          </p>

          {error && (
            <div className="mb-6 p-4 bg-red-950/40 border border-red-900/30 rounded-xl text-red-400 text-sm">
              {error}
            </div>
          )}

          <div className="space-y-4 mb-8">
            {selectedPlan.features.map((feature, i) => (
              <div key={i} className="flex items-center gap-3 text-[#C4BBB5]">
                <div className="w-5 h-5 rounded-full bg-green-950/30 flex items-center justify-center">
                  <Check className="w-3 h-3 text-green-400" />
                </div>
                {feature}
              </div>
            ))}
          </div>

          <div className="grid grid-cols-2 gap-4">
            <button
              onClick={() => handleCheckout('monthly')}
              disabled={loading}
              className="p-6 bg-[#0A0908] border border-white/10 rounded-xl hover:border-[#F59E0B]/50 transition-all text-left"
            >
              <p className="text-[#5C524A] text-sm mb-1">Monthly</p>
              <p className="text-2xl font-display text-[#F5F1ED]">${selectedPlan.price.monthly}</p>
              <p className="text-[#3D3630] text-xs mt-1">per month</p>
            </button>

            <button
              onClick={() => handleCheckout('annual')}
              disabled={loading}
              className="p-6 bg-[#0A0908] border border-[#F59E0B]/30 rounded-xl hover:border-[#F59E0B] transition-all text-left relative overflow-hidden"
            >
              <div className="absolute top-2 right-2 px-2 py-0.5 bg-[#F59E0B]/20 text-[#F59E0B] text-xs rounded-full">
                Save 17%
              </div>
              <p className="text-[#5C524A] text-sm mb-1">Annual</p>
              <p className="text-2xl font-display text-[#F5F1ED]">${selectedPlan.price.annual}</p>
              <p className="text-[#3D3630] text-xs mt-1">per year</p>
            </button>
          </div>

          {loading && (
            <div className="mt-6 flex items-center justify-center gap-2 text-[#F59E0B]">
              <Loader2 className="w-4 h-4 animate-spin" />
              <span className="text-sm">Redirecting to checkout...</span>
            </div>
          )}
        </motion.div>
      </div>
    </div>
  )
}