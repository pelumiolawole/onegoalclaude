'use client'

import { useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { motion, useScroll, useTransform, useInView, AnimatePresence } from 'framer-motion'
import { useAuthStore } from '@/stores/auth'
import OneGoalLogo from '@/components/OneGoalLogo'

// ── Fade-in-on-scroll wrapper ──────────────────────────────────
function Reveal({
  children,
  delay = 0,
  className = '',
}: {
  children: React.ReactNode
  delay?: number
  className?: string
}) {
  const ref = useRef(null)
  const inView = useInView(ref, { once: true, margin: '-80px' })
  return (
    <motion.div
      ref={ref}
      initial={{ opacity: 0, y: 32 }}
      animate={inView ? { opacity: 1, y: 0 } : {}}
      transition={{ duration: 0.65, delay, ease: [0.22, 1, 0.36, 1] }}
      className={className}
    >
      {children}
    </motion.div>
  )
}

// ── Floating orb ───────────────────────────────────────────────
function FloatingOrb({
  size, top, left, delay, duration, opacity,
}: {
  size: number; top: string; left: string; delay: number; duration: number; opacity: number
}) {
  return (
    <motion.div
      className="absolute rounded-full pointer-events-none"
      style={{
        width: size, height: size, top, left, opacity,
        background: 'radial-gradient(circle, rgba(245,158,11,0.4) 0%, transparent 70%)',
      }}
      animate={{ y: [0, -20, 0], scale: [1, 1.05, 1] }}
      transition={{ duration, delay, repeat: Infinity, ease: 'easeInOut' }}
    />
  )
}

// ── Demo Interview Preview ─────────────────────────────────────
const DEMO_MESSAGES = [
  { role: 'ai', text: "Two years is a long time to be circling something. What's actually in the way — resources, or something else?" },
  { role: 'user', text: "Honestly? I keep refining instead of shipping. I know what to do. I just don't do it." },
  { role: 'ai', text: "That gap between knowing and doing is the only thing worth talking about. What does the version of you who ships look like day to day?" },
  { role: 'user', text: "They make decisions faster. They don't wait to feel ready. They care less about looking stupid." },
  { role: 'ai', text: "So the goal isn't to build a business. It's to stop being someone who waits for permission. Let's make that concrete." },
]

function DemoPreview() {
  const [visibleCount, setVisibleCount] = useState(0)
  const ref = useRef(null)
  const inView = useInView(ref, { once: true, margin: '-100px' })

  useEffect(() => {
    if (!inView) return
    const interval = setInterval(() => {
      setVisibleCount(c => {
        if (c >= DEMO_MESSAGES.length) { clearInterval(interval); return c }
        return c + 1
      })
    }, 1200)
    return () => clearInterval(interval)
  }, [inView])

  return (
    <div
      ref={ref}
      className="relative rounded-2xl border border-white/8 bg-[#0D0B09] overflow-hidden"
      style={{ boxShadow: '0 0 60px rgba(245,158,11,0.06)' }}
    >
      {/* Mock header */}
      <div className="flex items-center gap-2 px-5 py-3 border-b border-white/5 bg-[#141210]">
        <div className="flex gap-1.5">
          <div className="w-2.5 h-2.5 rounded-full bg-[#FF5F57]" />
          <div className="w-2.5 h-2.5 rounded-full bg-[#FEBC2E]" />
          <div className="w-2.5 h-2.5 rounded-full bg-[#28C840]" />
        </div>
        <span className="text-[#3D3630] text-xs ml-2 font-mono">The Discovery Interview</span>
        <div className="ml-auto flex items-center gap-1.5">
          <div className="w-1.5 h-1.5 rounded-full bg-[#4ADE80] animate-pulse" />
          <span className="text-[#3D3630] text-xs">Live AI</span>
        </div>
      </div>

      {/* Messages */}
      <div className="p-5 space-y-4 min-h-[320px]">
        <AnimatePresence>
          {DEMO_MESSAGES.slice(0, visibleCount).map((msg, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
              className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-[80%] px-4 py-3 rounded-2xl text-sm leading-relaxed ${
                  msg.role === 'ai'
                    ? 'bg-[#1E1B18] text-[#C4BBB5] rounded-tl-sm'
                    : 'bg-[#F59E0B]/15 border border-[#F59E0B]/20 text-[#F5F1ED] rounded-tr-sm'
                }`}
              >
                {msg.text}
              </div>
            </motion.div>
          ))}
        </AnimatePresence>

        {/* Typing indicator */}
        {visibleCount > 0 && visibleCount < DEMO_MESSAGES.length && DEMO_MESSAGES[visibleCount].role === 'ai' && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="flex gap-1 px-4 py-3 bg-[#1E1B18] rounded-2xl rounded-tl-sm w-fit"
          >
            {[0, 1, 2].map(i => (
              <motion.div
                key={i}
                className="w-1.5 h-1.5 rounded-full bg-[#5C524A]"
                animate={{ y: [0, -4, 0] }}
                transition={{ duration: 0.6, delay: i * 0.15, repeat: Infinity }}
              />
            ))}
          </motion.div>
        )}
      </div>

      {/* Overlay fade at bottom */}
      <div className="absolute bottom-0 left-0 right-0 h-16 bg-gradient-to-t from-[#0D0B09] to-transparent pointer-events-none" />
    </div>
  )
}

// ── Main Page ──────────────────────────────────────────────────
export default function LandingPage() {
  const { isAuthenticated, user } = useAuthStore()
  const router = useRouter()
  const [billing, setBilling] = useState<'monthly' | 'annual'>('monthly')
  const { scrollY } = useScroll()
  const heroParallax = useTransform(scrollY, [0, 500], [0, -80])
  const heroOpacity = useTransform(scrollY, [0, 300], [1, 0.3])

  useEffect(() => {
    if (!isAuthenticated || !user) return
    const step = user.onboarding_step
    if (step <= 1) router.replace('/interview')
    else if (step === 2) router.replace('/goal-setup')
    else if (step === 3) router.replace('/preview')
    else if (step === 4) router.replace('/activate')
    else router.replace('/dashboard')
  }, [isAuthenticated, user])

  const PLANS = {
    monthly: [
      {
        name: 'The Spark',
        tagline: 'Start here. Prove it works.',
        price: '$0',
        period: 'forever',
        features: [
          'AI Discovery Interview',
          'One Goal definition',
          '1 daily identity task',
          'Basic progress tracking',
          '7-day streak tracking',
          'Coach PO — 5 messages/day',
        ],
        cta: 'Start Free',
        highlight: false,
      },
      {
        name: 'The Forge',
        tagline: 'For people who are serious.',
        price: '$4.99',
        period: '/month',
        features: [
          'Everything in The Spark',
          'Coach PO with full memory — unlimited',
          'Weekly review every Monday',
          'Full transformation score breakdown',
          'Reflection insights',
          'Goal history and archive',
        ],
        cta: 'Go deeper',
        highlight: true,
      },
      {
        name: 'The Identity',
        tagline: 'For people committed to becoming.',
        price: '$10.99',
        period: '/month',
        features: [
          'Everything in The Forge',
          'Re-interview when your goal evolves',
          'Behavioural pattern summary',
          'Priority task generation',
          'Early feature access',
          'Priority support',
        ],
        cta: 'Commit fully',
        highlight: false,
      },
    ],
    annual: [
      {
        name: 'The Spark',
        tagline: 'Start here. Prove it works.',
        price: '$0',
        period: 'forever',
        features: [
          'AI Discovery Interview',
          'One Goal definition',
          '1 daily identity task',
          'Basic progress tracking',
          '7-day streak tracking',
          'Coach PO — 5 messages/day',
        ],
        cta: 'Start Free',
        highlight: false,
      },
      {
        name: 'The Forge',
        tagline: 'For people who are serious.',
        price: '$4.99',
        period: '/month',
        annualPrice: '$47.88',
        savings: 'Save 20%',
        features: [
          'Everything in The Spark',
          'Coach PO with full memory — unlimited',
          'Weekly review every Monday',
          'Full transformation score breakdown',
          'Reflection insights',
          'Goal history and archive',
        ],
        cta: 'Go deeper',
        highlight: true,
      },
      {
        name: 'The Identity',
        tagline: 'For people committed to becoming.',
        price: '$10.99',
        period: '/month',
        annualPrice: '$107.88',
        savings: 'Save 18%',
        features: [
          'Everything in The Forge',
          'Re-interview when your goal evolves',
          'Behavioural pattern summary',
          'Priority task generation',
          'Early feature access',
          'Priority support',
        ],
        cta: 'Commit fully',
        highlight: false,
      },
    ],
  }

  const activePlans = PLANS[billing]

  return (
    <div className="min-h-screen bg-[#0A0908] text-[#F5F1ED] overflow-x-hidden">

      {/* ── Nav ───────────────────────────────────────────── */}
      <motion.nav
        initial={{ opacity: 0, y: -16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="fixed top-0 left-0 right-0 z-50 flex items-center justify-between px-6 py-4 border-b border-white/5 bg-[#0A0908]/80 backdrop-blur-md"
      >
        <OneGoalLogo size={26} textSize="text-lg" />
        <div className="flex items-center gap-4">
          <Link href="/login" className="text-sm text-[#7A6E65] hover:text-[#F5F1ED] transition-colors">
            Sign in
          </Link>
          <Link
            href="/signup"
            className="text-sm px-4 py-2 rounded-xl bg-[#F59E0B] text-[#0A0908] font-medium hover:bg-[#D97706] transition-all hover:scale-[1.02] active:scale-[0.98]"
          >
            Start the interview
          </Link>
        </div>
      </motion.nav>

      {/* ── Hero ──────────────────────────────────────────── */}
      <section className="relative min-h-screen flex flex-col items-center justify-center px-6 pt-24 pb-16 text-center overflow-hidden">
        <FloatingOrb size={600} top="20%" left="50%" delay={0} duration={8} opacity={0.07} />
        <FloatingOrb size={300} top="60%" left="15%" delay={2} duration={10} opacity={0.05} />
        <FloatingOrb size={200} top="30%" left="75%" delay={4} duration={7} opacity={0.06} />

        <div
          className="absolute inset-0 pointer-events-none opacity-[0.03]"
          style={{
            backgroundImage: 'linear-gradient(rgba(245,158,11,0.5) 1px, transparent 1px), linear-gradient(90deg, rgba(245,158,11,0.5) 1px, transparent 1px)',
            backgroundSize: '60px 60px',
          }}
        />

        <motion.div
          style={{ y: heroParallax, opacity: heroOpacity }}
          className="relative z-10 max-w-4xl mx-auto"
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.6, delay: 0.1 }}
            className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full border border-[#F59E0B]/20 bg-[#F59E0B]/5 text-[#F59E0B] text-xs tracking-widest uppercase mb-8"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-[#F59E0B] animate-pulse" />
            Identity-Based Goal System
          </motion.div>

          <motion.h1
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.2, ease: [0.22, 1, 0.36, 1] }}
            className="font-display text-5xl md:text-7xl lg:text-8xl leading-[1.05] text-[#F5F1ED] mb-4"
          >
            One Goal.{' '}
            <br className="hidden md:block" />
            <span className="text-[#F59E0B] italic">No Excuses.</span>
          </motion.h1>

          <motion.p
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.4 }}
            className="text-[#7A6E65] text-lg md:text-xl max-w-2xl mx-auto mb-10 leading-relaxed"
          >
            You don't have a focus problem. You have an identity problem.
            OneGoal Pro finds your one goal, then coaches you toward the person who achieves it.
          </motion.p>

          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.55 }}
            className="flex flex-col sm:flex-row items-center justify-center gap-4"
          >
            <Link
              href="/signup"
              className="group w-full sm:w-auto px-8 py-4 rounded-2xl bg-[#F59E0B] text-[#0A0908] font-semibold text-base hover:bg-[#D97706] transition-all hover:scale-[1.03] active:scale-[0.98] flex items-center justify-center gap-2"
            >
              Start the interview
              <motion.span
                animate={{ x: [0, 4, 0] }}
                transition={{ duration: 1.5, repeat: Infinity }}
              >→</motion.span>
            </Link>
            <Link
              href="/login"
              className="w-full sm:w-auto px-8 py-4 rounded-2xl border border-white/10 text-[#A09690] text-base hover:border-white/25 hover:text-[#F5F1ED] transition-all"
            >
              Sign in
            </Link>
          </motion.div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, delay: 0.75 }}
          className="relative z-10 mt-20 grid grid-cols-3 gap-8 max-w-lg mx-auto"
        >
          {[
            { value: 'One Goal', label: 'Not ten half-finished ones' },
            { value: 'Daily', label: 'Tasks built for who you\'re becoming' },
            { value: 'Most people', label: 'Never commit to one thing fully' },
          ].map((stat) => (
            <div key={stat.label} className="text-center">
              <div className="font-display text-base md:text-lg text-[#F59E0B] mb-1">{stat.value}</div>
              <div className="text-xs text-[#5C524A] uppercase tracking-wider">{stat.label}</div>
            </div>
          ))}
        </motion.div>

        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 1.2 }}
          className="absolute bottom-8 left-1/2 -translate-x-1/2 flex flex-col items-center gap-2"
        >
          <span className="text-[#3D3630] text-xs tracking-widest uppercase">Scroll</span>
          <motion.div
            animate={{ y: [0, 6, 0] }}
            transition={{ duration: 1.5, repeat: Infinity }}
            className="w-px h-8 bg-gradient-to-b from-[#F59E0B]/30 to-transparent"
          />
        </motion.div>
      </section>

      {/* ── Live Demo ─────────────────────────────────────── */}
      <section className="px-6 py-24 max-w-5xl mx-auto">
        <div className="grid md:grid-cols-2 gap-12 items-center">
          <Reveal>
            <p className="text-[#F59E0B] text-xs tracking-widest uppercase mb-4">See It In Action</p>
            <h2 className="font-display text-4xl md:text-5xl text-[#F5F1ED] mb-6">
              This is not<br />
              <span className="italic text-[#7A6E65]">an onboarding form.</span>
            </h2>
            <p className="text-[#5C524A] leading-relaxed mb-6">
              The Discovery Interview is a real conversation. The AI asks hard questions,
              pushes back on vague answers, and builds a picture of who you actually are —
              not who you think you want to be. Everything else runs on that.
            </p>
            <p className="text-[#5C524A] leading-relaxed mb-6">
              There is a difference between knowing and doing. Most apps never go near it.
              This one starts there.  The interview takes 10-15 minutes. You only do it once.
            </p>
            <Link
              href="/signup"
              className="inline-flex items-center gap-2 text-[#F59E0B] text-sm hover:gap-3 transition-all"
            >
              Start your interview <span>→</span>
            </Link>
          </Reveal>

          <Reveal delay={0.15}>
            <DemoPreview />
          </Reveal>
        </div>
      </section>

      {/* ── How It Works ──────────────────────────────────── */}
      <section className="px-6 py-24 bg-[#0D0B09]">
        <div className="max-w-5xl mx-auto">
          <Reveal className="text-center mb-16">
            <p className="text-[#F59E0B] text-xs tracking-widest uppercase mb-4">The Process</p>
            <h2 className="font-display text-4xl md:text-5xl text-[#F5F1ED]">
              Built around{' '}
              <span className="italic">who you're becoming</span>
            </h2>
          </Reveal>

          <div className="grid md:grid-cols-3 gap-6">
            {[
              {
                step: '01',
                title: 'The Discovery Interview',
                description: 'A real AI conversation about your life, not a form. It asks uncomfortable questions, challenges your answers, and builds a profile of who you actually are right now.',
                icon: '◎',
                delay: 0,
              },
              {
                step: '02',
                title: 'Your One Goal',
                description: 'From the interview, the AI identifies one goal worth pursuing — and maps the identity gap between who you are and who you need to be to reach it.',
                icon: '◈',
                delay: 0.1,
              },
              {
                step: '03',
                title: 'Daily Identity Actions',
                description: 'Every morning, one task. Not a generic to-do — something calibrated to your goal, your current week, and the specific trait you\'re trying to build.',
                icon: '◆',
                delay: 0.2,
              },
            ].map((item) => (
              <Reveal key={item.step} delay={item.delay}>
                <motion.div
                  whileHover={{ y: -4, borderColor: 'rgba(245,158,11,0.3)' }}
                  transition={{ duration: 0.2 }}
                  className="relative p-6 rounded-2xl border border-white/5 bg-[#141210] cursor-default h-full"
                >
                  <div className="text-[#F59E0B]/15 font-display text-6xl absolute top-4 right-5 select-none">
                    {item.step}
                  </div>
                  <div className="text-[#F59E0B] text-2xl mb-4">{item.icon}</div>
                  <h3 className="font-display text-xl text-[#F5F1ED] mb-3">{item.title}</h3>
                  <p className="text-[#5C524A] text-sm leading-relaxed">{item.description}</p>
                </motion.div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* ── Features ──────────────────────────────────────── */}
      <section className="px-6 py-24">
        <div className="max-w-5xl mx-auto">
          <Reveal className="text-center mb-16">
            <p className="text-[#F59E0B] text-xs tracking-widest uppercase mb-4">What It Does</p>
            <h2 className="font-display text-4xl md:text-5xl text-[#F5F1ED]">
              Three things that{' '}
              <span className="italic text-[#7A6E65]">actually change you.</span>
            </h2>
          </Reveal>

          <div className="grid md:grid-cols-3 gap-6">
            {[
              {
                title: 'The interview finds your real goal',
                description: 'Not the goal you think you want. The one you have been avoiding. The AI interview asks uncomfortable questions, pushes back on vague answers, and builds a picture of who you actually are.',
                delay: 0,
              },
              {
                title: 'One task every morning',
                description: 'Calibrated to your goal and the specific identity trait you are building that week. Not a to-do list. An identity action.',
                delay: 0.1,
              },
              {
                title: 'A coach that remembers everything',
                description: 'Knows your goal, your history, your patterns. Calls you out when you are reframing avoidance as strategy. Does not let you off the hook.',
                delay: 0.2,
              },
            ].map((feature) => (
              <Reveal key={feature.title} delay={feature.delay}>
                <motion.div
                  whileHover={{ y: -4, borderColor: 'rgba(245,158,11,0.3)' }}
                  transition={{ duration: 0.2 }}
                  className="p-7 rounded-2xl border border-white/5 bg-[#141210] cursor-default h-full flex flex-col"
                >
                  <h3 className="font-display text-xl text-[#F5F1ED] mb-4 leading-snug">{feature.title}</h3>
                  <p className="text-[#5C524A] text-sm leading-relaxed flex-1">{feature.description}</p>
                </motion.div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* ── Social Proof ──────────────────────────────────── */}
      <section className="px-6 py-24 bg-[#0D0B09]">
        <div className="max-w-3xl mx-auto text-center">
          <Reveal>
            <p className="text-[#F59E0B] text-xs tracking-widest uppercase mb-8">Early Users</p>
            <h2 className="font-display text-4xl md:text-5xl text-[#F5F1ED] mb-10">
              What happened when they{' '}
              <span className="italic">committed to one thing.</span>
            </h2>

            <motion.div
              whileHover={{ borderColor: 'rgba(245,158,11,0.2)' }}
              transition={{ duration: 0.3 }}
              className="p-10 rounded-2xl border border-white/8 bg-[#141210]"
            >
              <div className="text-5xl font-display text-[#F59E0B] mb-6">11</div>
              <p className="text-[#C4BBB5] text-lg leading-relaxed mb-6">
                people have committed to one goal.
              </p>
              <div className="w-px h-8 bg-[#F59E0B]/20 mx-auto mb-6" />
              <p className="text-[#7A6E65] text-base leading-relaxed mb-4">
                The first paid subscriber signed up within 72 hours of launch.
              </p>
              <p className="text-[#5C524A] text-sm leading-relaxed italic">
                Most apps collect goals. This one changes who you are while you pursue them.
              </p>
            </motion.div>

            <p className="text-[#3D3630] text-xs mt-8">
              Real quotes from named users coming as the product grows.
              We won't fake them.
            </p>
          </Reveal>
        </div>
      </section>

      {/* ── Pricing ───────────────────────────────────────── */}
      <section className="px-6 py-24">
        <div className="max-w-5xl mx-auto">
          <Reveal className="text-center mb-12">
            <p className="text-[#F59E0B] text-xs tracking-widest uppercase mb-4">Pricing</p>
            <h2 className="font-display text-4xl md:text-5xl text-[#F5F1ED] mb-6">
              Choose your level of{' '}
              <span className="italic text-[#F59E0B]">commitment</span>
            </h2>

            <div className="inline-flex items-center gap-1 p-1 rounded-xl border border-white/10 bg-[#141210]">
              <button
                onClick={() => setBilling('monthly')}
                className={`px-5 py-2 rounded-lg text-sm font-medium transition-all ${
                  billing === 'monthly'
                    ? 'bg-[#F59E0B] text-[#0A0908]'
                    : 'text-[#5C524A] hover:text-[#A09690]'
                }`}
              >
                Monthly
              </button>
              <button
                onClick={() => setBilling('annual')}
                className={`px-5 py-2 rounded-lg text-sm font-medium transition-all flex items-center gap-2 ${
                  billing === 'annual'
                    ? 'bg-[#F59E0B] text-[#0A0908]'
                    : 'text-[#5C524A] hover:text-[#A09690]'
                }`}
              >
                Annual
                <span className={`text-xs px-1.5 py-0.5 rounded-md ${billing === 'annual' ? 'bg-[#0A0908]/20' : 'bg-[#F59E0B]/10 text-[#F59E0B]'}`}>
                  Save up to 20% on paid plans
                </span>
              </button>
            </div>
          </Reveal>

          <div className="grid md:grid-cols-3 gap-6">
            <AnimatePresence mode="wait">
              {activePlans.map((plan, i) => (
                <motion.div
                  key={`${billing}-${plan.name}`}
                  initial={{ opacity: 0, y: 16 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -8 }}
                  transition={{ duration: 0.35, delay: i * 0.07 }}
                  className={`relative p-6 rounded-2xl border flex flex-col ${
                    plan.highlight
                      ? 'border-[#F59E0B]/35 bg-[#141210]'
                      : 'border-white/5 bg-[#141210]'
                  }`}
                >
                  {plan.highlight && (
                    <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-4 py-1 rounded-full bg-[#F59E0B] text-[#0A0908] text-xs font-semibold whitespace-nowrap">
                      Most Popular
                    </div>
                  )}
                  {'savings' in plan && plan.savings && (
                    <div className="absolute -top-3 right-4 px-3 py-1 rounded-full bg-[#4ADE80]/20 border border-[#4ADE80]/30 text-[#4ADE80] text-xs font-medium">
                      {plan.savings}
                    </div>
                  )}

                  <div className="mb-6">
                    <h3 className="font-display text-xl text-[#F5F1ED] mb-1">{plan.name}</h3>
                    <p className="text-[#5C524A] text-sm mb-4">{plan.tagline}</p>

                    <div className="flex items-baseline gap-1">
                      <span className="font-mono text-4xl font-bold text-[#F5F1ED] tracking-tight">{plan.price}</span>
                      <span className="text-[#5C524A] text-sm">{plan.period}</span>
                    </div>

                    {'annualPrice' in plan && plan.annualPrice && (
                      <p className="mt-2 text-sm text-[#7A6E65]">
                        Billed as {plan.annualPrice}/year
                      </p>
                    )}
                  </div>

                  <ul className="space-y-3 mb-8 flex-1">
                    {plan.features.map((f) => (
                      <li key={f} className="flex items-start gap-2 text-sm">
                        <span className="text-[#F59E0B] mt-0.5 shrink-0">✓</span>
                        <span className="text-[#7A6E65]">{f}</span>
                      </li>
                    ))}
                  </ul>

                  <Link
                    href="/signup"
                    className={`w-full py-3 rounded-xl text-sm font-medium text-center transition-all hover:scale-[1.02] active:scale-[0.98] ${
                      plan.highlight
                        ? 'bg-[#F59E0B] text-[#0A0908] hover:bg-[#D97706]'
                        : 'border border-white/10 text-[#A09690] hover:border-white/25 hover:text-[#F5F1ED]'
                    }`}
                  >
                    {plan.cta}
                  </Link>
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
          <p className="text-center text-[#3D3630] text-xs mt-8">
            All plans include a 14-day money-back guarantee. No questions asked.
          </p>
        </div>
      </section>

      {/* ── FAQ ───────────────────────────────────────────── */}
      <section className="px-6 py-24 bg-[#0D0B09]">
        <div className="max-w-3xl mx-auto">
          <Reveal className="text-center mb-16">
            <p className="text-[#F59E0B] text-xs tracking-widest uppercase mb-4">FAQ</p>
            <h2 className="font-display text-4xl text-[#F5F1ED]">Common questions.</h2>
          </Reveal>
          <FAQList />
        </div>
      </section>

      {/* ── Final CTA ─────────────────────────────────────── */}
      <section className="px-6 py-32 text-center relative overflow-hidden">
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <motion.div
            animate={{ scale: [1, 1.1, 1], opacity: [0.04, 0.07, 0.04] }}
            transition={{ duration: 6, repeat: Infinity }}
            className="w-[700px] h-[700px] rounded-full"
            style={{ background: 'radial-gradient(circle, rgba(245,158,11,1) 0%, transparent 70%)' }}
          />
        </div>
        <Reveal className="relative z-10 max-w-2xl mx-auto">
          <h2 className="font-display text-4xl md:text-6xl text-[#F5F1ED] mb-6">
            The person you want to be{' '}
            <span className="italic text-[#F59E0B]">is one goal away.</span>
          </h2>
          <p className="text-[#5C524A] mb-10 text-lg">Stop managing tasks. Start becoming.</p>
          <Link
            href="/signup"
            className="inline-flex items-center gap-3 px-10 py-4 rounded-2xl bg-[#F59E0B] text-[#0A0908] font-semibold text-base hover:bg-[#D97706] transition-all hover:scale-[1.03] active:scale-[0.98]"
          >
            Start the interview
            <motion.span animate={{ x: [0, 5, 0] }} transition={{ duration: 1.5, repeat: Infinity }}>
              →
            </motion.span>
          </Link>
        </Reveal>
      </section>

      {/* ── Footer ────────────────────────────────────────── */}
      <footer className="px-6 py-10 border-t border-white/5">
        <div className="max-w-5xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4">
          <OneGoalLogo size={22} textSize="text-lg" />
          <p className="text-[#3D3630] text-xs text-center">Stop managing tasks. Start becoming.</p>
          <div className="flex gap-6 text-xs text-[#3D3630]">
            <Link href="/login" className="hover:text-[#7A6E65] transition-colors">Sign in</Link>
            <Link href="/signup" className="hover:text-[#7A6E65] transition-colors">Start the interview</Link>
            <Link href="/privacy" className="hover:text-[#7A6E65] transition-colors">Privacy</Link>
            <Link href="/terms" className="hover:text-[#7A6E65] transition-colors">Terms</Link>
          </div>
        </div>
        <div className="max-w-5xl mx-auto mt-6 pt-6 border-t border-white/5 text-center">
          <p className="text-[#3D3630] text-xs">
            One Goal Pro Ltd &middot; Company No. 17127527 &middot; Registered in England and Wales &middot; 5 Brayford Square, London, E1 0SG
          </p>
        </div>
      </footer>
    </div>
  )
}

// ── FAQ Accordion ──────────────────────────────────────────────
const FAQS = [
  { q: 'Why only ONE goal? That seems limiting.', a: 'Because most people fail by spreading thin, not by focusing too hard. One goal means one thing gets your full attention. The discipline of choosing is half the work.' },
  { q: 'What is the Discovery Interview?', a: 'A conversation with the AI that takes 10–20 minutes. It asks about your life, your gaps, your history with goals, and what keeps getting in the way. Your answers build the profile everything else runs on.' },
  { q: 'How is this different from other productivity apps?', a: 'Most apps track tasks. This one tracks who you\'re becoming. The goal isn\'t to get more done — it\'s to close the gap between who you are and who you need to be.' },
  { q: 'Can I change my goal?', a: 'On The Identity plan you can re-interview and reset anytime. On other plans, the AI Coach can help you refine your goal as your thinking sharpens.' },
  { q: 'Is there a refund policy?', a: 'Yes. All paid plans come with a 14-day money-back guarantee.' },
]

function FAQList() {
  const [open, setOpen] = useState<number | null>(null)
  return (
    <div className="space-y-3">
      {FAQS.map((faq, i) => (
        <Reveal key={i} delay={i * 0.05}>
          <div className="border border-white/5 rounded-2xl bg-[#141210] overflow-hidden">
            <button
              onClick={() => setOpen(open === i ? null : i)}
              className="w-full flex items-center justify-between px-6 py-4 text-left text-[#C4BBB5] hover:text-[#F5F1ED] transition-colors text-sm font-medium"
            >
              {faq.q}
              <motion.span
                animate={{ rotate: open === i ? 45 : 0 }}
                transition={{ duration: 0.2 }}
                className="text-[#F59E0B] shrink-0 ml-4 text-lg leading-none"
              >
                +
              </motion.span>
            </button>
            <AnimatePresence>
              {open === i && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: 'auto', opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
                  className="overflow-hidden"
                >
                  <div className="px-6 pb-5 text-[#5C524A] text-sm leading-relaxed border-t border-white/5 pt-4">
                    {faq.a}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </Reveal>
      ))}
    </div>
  )
}