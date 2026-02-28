'use client'

import { useEffect } from 'react'
import { useRouter, usePathname } from 'next/navigation'
import Link from 'next/link'
import { motion } from 'framer-motion'
import { useAuthStore } from '@/stores/auth'

const NAV = [
  { href: '/dashboard', label: 'Today',    icon: HomeIcon },
  { href: '/coach',     label: 'Coach',    icon: CoachIcon },
  { href: '/progress',  label: 'Progress', icon: ChartIcon },
  { href: '/goal',      label: 'Goal',     icon: GoalIcon },
]

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { user, isAuthenticated } = useAuthStore()
  const router = useRouter()
  const pathname = usePathname()

  useEffect(() => {
    if (!isAuthenticated) { router.replace('/login'); return }
    if (user && user.onboarding_step < 5) {
      const step = user.onboarding_step
      if (step <= 1) router.replace('/interview')
      else if (step === 2) router.replace('/goal-setup')
      else if (step === 3) router.replace('/preview')
      else router.replace('/activate')
    }
  }, [isAuthenticated, user])

  return (
    <div className="min-h-screen bg-[#0A0908] flex">

      {/* ── Sidebar (desktop) ──────────────────────────── */}
      <aside className="hidden md:flex flex-col w-60 border-r border-white/5 p-5 shrink-0">
        <div className="mb-10 px-2">
          <span className="font-display text-xl text-[#F5F1ED]">One Goal</span>
        </div>

        <nav className="flex-1 space-y-1">
          {NAV.map(item => {
            const active = pathname === item.href || pathname.startsWith(item.href + '/')
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm transition-all ${
                  active
                    ? 'bg-[#F59E0B]/10 text-[#F59E0B] border border-[#F59E0B]/15'
                    : 'text-[#5C524A] hover:text-[#A09690] hover:bg-[#141210]'
                }`}
              >
                <item.icon size={16} />
                {item.label}
              </Link>
            )
          })}
        </nav>

        {user && (
          <div className="border-t border-white/5 pt-4">
            <Link
              href="/settings"
              className="flex items-center gap-3 px-3 py-2 rounded-xl hover:bg-[#141210] transition-all group"
            >
              <div className="w-7 h-7 rounded-full bg-[#F59E0B]/20 border border-[#F59E0B]/20 flex items-center justify-center shrink-0">
                <span className="text-[#F59E0B] text-xs font-medium">
                  {(user.display_name || user.email)[0].toUpperCase()}
                </span>
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-[#C4BBB5] text-xs truncate group-hover:text-[#E8E2DC]">
                  {user.display_name || user.email}
                </p>
                <p className="text-[#3D3630] text-xs font-mono">Settings</p>
              </div>
            </Link>
          </div>
        )}
      </aside>

      {/* ── Main ────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col min-w-0">
        <main className="flex-1 overflow-y-auto">
          <motion.div
            key={pathname}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3 }}
            className="h-full"
          >
            {children}
          </motion.div>
        </main>

        {/* ── Mobile bottom nav ───────────────────────── */}
        <nav className="md:hidden border-t border-white/5 px-2 py-2 flex justify-around bg-[#0A0908]">
          {NAV.map(item => {
            const active = pathname === item.href
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex flex-col items-center gap-1 px-4 py-2 rounded-xl transition-all ${
                  active ? 'text-[#F59E0B]' : 'text-[#3D3630]'
                }`}
              >
                <item.icon size={20} />
                <span className="text-[10px]">{item.label}</span>
              </Link>
            )
          })}
        </nav>
      </div>
    </div>
  )
}

function HomeIcon({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
      <polyline points="9 22 9 12 15 12 15 22" />
    </svg>
  )
}

function CoachIcon({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
    </svg>
  )
}

function ChartIcon({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="20" x2="18" y2="10" />
      <line x1="12" y1="20" x2="12" y2="4" />
      <line x1="6"  y1="20" x2="6"  y2="14" />
    </svg>
  )
}

function GoalIcon({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <circle cx="12" cy="12" r="6"  />
      <circle cx="12" cy="12" r="2"  />
    </svg>
  )
}
