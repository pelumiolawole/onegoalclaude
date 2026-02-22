'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { motion } from 'framer-motion'
import { useAuthStore } from '@/stores/auth'

const STEPS = [
  { label: 'Discovery' },
  { label: 'Your Goal' },
  { label: 'Strategy' },
  { label: 'Activate' },
]

export default function OnboardingLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const { user, isAuthenticated } = useAuthStore()
  const router = useRouter()

  useEffect(() => {
    if (!isAuthenticated) router.replace('/login')
    if (user?.onboarding_step === 5) router.replace('/dashboard')
  }, [isAuthenticated, user])

  const currentStep = Math.max(0, (user?.onboarding_step ?? 1) - 1)

  return (
    <div className="min-h-screen bg-[#0A0908] flex flex-col">
      {/* Header */}
      <header className="flex items-center justify-between px-8 py-6 border-b border-white/5">
        <span className="font-display text-xl text-[#F5F1ED]">One Goal</span>

        {/* Step indicators — desktop */}
        <div className="hidden sm:flex items-center gap-2">
          {STEPS.map((step, i) => (
            <div key={step.label} className="flex items-center gap-2">
              <div className="flex items-center gap-1.5">
                <div
                  className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-mono transition-all duration-300 ${
                    i < currentStep
                      ? 'bg-[#F59E0B] text-[#0A0908]'
                      : i === currentStep
                      ? 'bg-[#F59E0B]/20 text-[#F59E0B] border border-[#F59E0B]/40'
                      : 'bg-[#1E1B18] text-[#3D3630] border border-white/5'
                  }`}
                >
                  {i < currentStep ? '✓' : i + 1}
                </div>
                <span
                  className={`text-xs transition-colors ${
                    i <= currentStep ? 'text-[#A09690]' : 'text-[#3D3630]'
                  }`}
                >
                  {step.label}
                </span>
              </div>
              {i < STEPS.length - 1 && (
                <div className={`w-8 h-px ${i < currentStep ? 'bg-[#F59E0B]/40' : 'bg-white/5'}`} />
              )}
            </div>
          ))}
        </div>

        {/* Mobile: step X of Y */}
        <span className="sm:hidden text-[#5C524A] text-sm">
          Step {currentStep + 1} of {STEPS.length}
        </span>
      </header>

      {/* Content */}
      <main className="flex-1 flex items-center justify-center p-6">
        <motion.div
          key={currentStep}
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          className="w-full max-w-2xl"
        >
          {children}
        </motion.div>
      </main>
    </div>
  )
}
