'use client'

import { useEffect } from 'react'
import { useRouter, usePathname } from 'next/navigation'
import Link from 'next/link'
import { motion } from 'framer-motion'
import { useAuthStore } from '@/stores/auth'
import OneGoalLogo from '@/components/OneGoalLogo'

const NAV = [
  { href: '/dashboard', label: 'Today',    icon: HomeIcon },
  { href: '/coach',     label: 'Coach',    icon: CoachIcon },
  { href: '/progress',  label: 'Progress', icon: ChartIcon },
  { href: '/goal',      label: 'Goal',     icon: GoalIcon },
  { href: '/settings',  label: 'Profile',  icon: ProfileIcon },
]

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { user, isAuthenticated, refreshUser } = useAuthStore()
  const router = useRouter()
  const pathname = usePathname()

  useEffect(() => {
    const token = localStorage.getItem('access_token')
    if (!token) {
      router.replace('/login')
      return
    }
    refreshUser()
  }, [])

  useEffect(() => {
    if (!isAuthenticated) return
    if (user && user.onboarding_step < 5) {
      const step = user.onboarding_step
      if (step === 0 || step === 1) router.replace('/interview')
      else if (step === 2) router.replace('/goal-setup')
      else if (step === 3) router.replace('/preview')
      else if (step === 4) router.replace('/activate')
    }
  }, [user?.onboarding_step])

  const displayName = user?.display_name || user?.email || ''
  const initials = displayName
    .split(' ')
    .map((w: string) => w[0])
    .slice(0, 2)
    .join('')
    .toUpperCase() || 'U'
  const avatarUrl = (user as any)?.avatar_url || null
  const bio = (user as any)?.bio || null

  return (
    <div className="min-h-screen bg-[#0A0908] flex">

      {/* Sidebar (desktop) — sticky to viewport height */}
      <aside className="hidden md:flex flex-col w-60 border-r border-white/5 p-5 shrink-0 sticky top-0 h-screen">

        {/* Logo + avatar row */}
        <div className="flex items-center justify-between mb-10 px-2">
          <OneGoalLogo size={26} textSize="text-lg" />

          {user && (
            <Link
              href="/settings"
              className="shrink-0 w-8 h-8 rounded-full overflow-hidden border border-[#F59E0B]/20 hover:border-[#F59E0B]/50 transition-all"
              title="Profile & Settings"
            >
              {avatarUrl ? (
                <img src={avatarUrl} alt={displayName} className="w-full h-full object-cover" />
              ) : (
                <div className="w-full h-full bg-[#F59E0B]/20 flex items-center justify-center">
                  <span className="text-[#F59E0B] text-xs font-medium">{initials}</span>
                </div>
              )}
            </Link>
          )}
        </div>

        {/* Nav */}
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

        {/* Bio strip at bottom of sidebar */}
        {bio && (
          <div className="border-t border-white/5 pt-4 px-2">
            <p className="text-[#3D3630] text-[10px] uppercase tracking-widest font-mono mb-1.5">
              Becoming
            </p>
            <p className="text-[#5C524A] text-xs leading-relaxed italic">
              {bio}
            </p>
          </div>
        )}
      </aside>

      {/* Main — mobile needs padding at bottom so content clears the fixed nav */}
      <div className="flex-1 flex flex-col min-w-0 min-h-screen">
        <main className="flex-1 overflow-y-auto pb-16 md:pb-0">
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

        {/* Mobile bottom nav — fixed to bottom of viewport */}
        <nav className="md:hidden fixed bottom-0 left-0 right-0 border-t border-white/5 px-2 py-2 flex justify-around bg-[#0A0908] z-50">
          {NAV.map(item => {
            const active = pathname === item.href

            if (item.href === '/settings') {
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`flex flex-col items-center gap-1 px-4 py-2 rounded-xl transition-all ${
                    active ? 'text-[#F59E0B]' : 'text-[#3D3630]'
                  }`}
                >
                  <div className={`w-5 h-5 rounded-full overflow-hidden border ${
                    active ? 'border-[#F59E0B]' : 'border-[#3D3630]'
                  }`}>
                    {avatarUrl ? (
                      <img src={avatarUrl} alt="" className="w-full h-full object-cover" />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center bg-[#F59E0B]/10">
                        <span className="text-[9px] font-medium leading-none text-[#F59E0B]">{initials[0]}</span>
                      </div>
                    )}
                  </div>
                  <span className="text-[10px]">{item.label}</span>
                </Link>
              )
            }

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

// ── Icons ─────────────────────────────────────────────────────

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

function ProfileIcon({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
      <circle cx="12" cy="7" r="4" />
    </svg>
  )
}