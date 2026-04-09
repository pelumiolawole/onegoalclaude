// frontend/src/app/(app)/settings/page.tsx

'use client'

import { useEffect, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useAuthStore } from '@/stores/auth'
import { api } from '@/lib/api'
import { useRouter } from 'next/navigation'
import { 
  CreditCard, 
  Calendar, 
  AlertCircle, 
  CheckCircle2, 
  XCircle, 
  RefreshCw,
  Download,
  ArrowRight,
  Loader2,
  Sparkles,
  Shield
} from 'lucide-react'

// ── Types ─────────────────────────────────────────────────────────────────

interface Subscription {
  plan: 'spark' | 'forge' | 'identity' | null
  status: 'active' | 'ended' | null
  billing_cycle: 'monthly' | 'annual' | null
  current_period_end: string | null
  cancel_at_period_end: boolean
}

interface Invoice {
  id: string
  amount_due: number
  amount_paid: number
  status: 'paid' | 'open' | 'void' | 'uncollectible'
  created: number
  invoice_pdf: string | null
  description: string
}

interface ProfileData {
  avatar_url: string | null
  bio: string | null
  days_active: number
  current_streak: number
  goal_area: string | null
  display_name: string | null
  email: string
}

// ── Main Component ────────────────────────────────────────────────────────

export default function SettingsPage() {
  const router = useRouter()
  const { user, logout, clearAuth, refreshUser } = useAuthStore()
  
  // Billing state
  const [subscription, setSubscription] = useState<Subscription | null>(null)
  const [invoices, setInvoices] = useState<Invoice[]>([])
  const [billingLoading, setBillingLoading] = useState(true)
  const [actionLoading, setActionLoading] = useState(false)
  const [billingError, setBillingError] = useState('')

  // Profile state
  const [profile, setProfile] = useState<ProfileData | null>(null)
  const [profileLoading, setProfileLoading] = useState(true)
  const [avatarUploading, setAvatarUploading] = useState(false)
  const [avatarPreview, setAvatarPreview] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [shareLoading, setShareLoading] = useState(false)
  const [shareMessage, setShareMessage] = useState<string | null>(null)
  const [shareUrl, setShareUrl] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const [showSharePanel, setShowSharePanel] = useState(false)
  const [showLogoutConfirm, setShowLogoutConfirm] = useState(false)

  useEffect(() => {
    loadBillingData()
    loadProfileData()
  }, [])

  const loadBillingData = async () => {
    try {
      setBillingLoading(true)
      const [subData, invoiceData] = await Promise.all([
        api.billing.getSubscription(),
        api.billing.getInvoices().catch(() => ({ invoices: [] }))
      ])
      setSubscription(subData as Subscription)
      setInvoices(invoiceData.invoices || [])
    } catch (err: any) {
      setBillingError('Failed to load subscription data')
      console.error('Billing load error:', err)
    } finally {
      setBillingLoading(false)
    }
  }

  const loadProfileData = async () => {
    try {
      const data = await api.profile.get()
      setProfile(data)
      setAvatarPreview(data.avatar_url)
    } catch (err) {
      console.error('Profile load error:', err)
    } finally {
      setProfileLoading(false)
    }
  }

  async function handleAvatarChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    const localUrl = URL.createObjectURL(file)
    setAvatarPreview(localUrl)
    setAvatarUploading(true)
    try {
      const { avatar_url } = await api.profile.uploadAvatar(file)
      setAvatarPreview(avatar_url)
      await refreshUser()
    } catch {
      setAvatarPreview(profile?.avatar_url ?? null)
    } finally {
      setAvatarUploading(false)
    }
  }

  async function handleInvite() {
    setShowSharePanel(true)
    if (shareMessage) return
    setShareLoading(true)
    try {
      const data = await api.profile.generateShareMessage()
      setShareMessage(data.message)
      setShareUrl(data.share_url)
    } catch {
      setShareMessage("I'm using OneGoal Pro to commit to one goal — no excuses. Join me.")
      setShareUrl('https://onegoalpro.vercel.app')
    } finally {
      setShareLoading(false)
    }
  }

  async function handleNativeShare() {
    const text = `${shareMessage}\n\n${shareUrl}`
    if (navigator.share) {
      try { await navigator.share({ text }) } catch {}
    } else {
      handleCopy()
    }
  }

  async function handleCopy() {
    await navigator.clipboard.writeText(`${shareMessage}\n\n${shareUrl}`)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const handleCancel = async () => {
    if (!confirm('Are you sure? You\'ll keep access until the end of your billing period.')) return
    setActionLoading(true)
    try {
      await api.billing.cancelSubscription()
      await loadBillingData()
    } catch (err: any) {
      setBillingError(err.detail || 'Failed to cancel subscription')
    } finally {
      setActionLoading(false)
    }
  }

  const handleResume = async () => {
    setActionLoading(true)
    try {
      await api.billing.resumeSubscription()
      await loadBillingData()
    } catch (err: any) {
      setBillingError(err.detail || 'Failed to resume subscription')
    } finally {
      setActionLoading(false)
    }
  }

  const handleUpgrade = () => {
    router.push('/settings/upgrade')
  }

  function handleLogout() {
    clearAuth()
    router.replace('/login')
  }

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return 'N/A'
    return new Date(dateStr).toLocaleDateString('en-US', {
      month: 'long',
      day: 'numeric',
      year: 'numeric'
    })
  }

  const formatCurrency = (cents: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD'
    }).format(cents / 100)
  }

  const getPlanDisplay = (plan: string | null) => {
    switch (plan) {
      case 'forge': return { name: 'The Forge', color: 'text-[#F59E0B]', bg: 'bg-[#F59E0B]/10', icon: Sparkles }
      case 'identity': return { name: 'The Identity', color: 'text-[#d0ff59]', bg: 'bg-[#d0ff59]/10', icon: Shield }
      default: return { name: 'The Spark', color: 'text-[#A09690]', bg: 'bg-[#A09690]/10', icon: CheckCircle2 }
    }
  }

  const getStatusBadge = (status: string | null, cancelAtPeriodEnd: boolean) => {
    const isActive = status === 'active' && !cancelAtPeriodEnd
    return {
      className: isActive
        ? 'bg-green-950/30 text-green-400 border-green-900/30'
        : 'bg-gray-500/20 text-gray-400 border-gray-500/30',
      label: isActive ? 'Active' : 'Ended'
    }
  }

  const planInfo = getPlanDisplay(subscription?.plan ?? null)
  const displayName = user?.display_name || profile?.display_name || ''
  const email = user?.email || profile?.email || ''
  const initials = (displayName || email).split(' ').map((w: string) => w[0]).slice(0, 2).join('').toUpperCase() || 'U'

  if (billingLoading && profileLoading) {
    return (
      <div className="min-h-screen bg-[#0A0908] flex items-center justify-center">
        <Loader2 className="w-8 h-8 text-[#F59E0B] animate-spin" />
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-[#0A0908]">
      <div className="max-w-4xl mx-auto px-6 py-12 pb-24 md:pb-8">
        
        {/* Header */}
        <div className="mb-10">
          <h1 className="font-display text-3xl text-[#F5F1ED] mb-2">Settings</h1>
          <p className="text-[#7A6E65]">Manage your account and subscription</p>
        </div>

        {/* Error Alert */}
        <AnimatePresence>
          {billingError && (
            <motion.div
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className="mb-6 p-4 bg-red-950/40 border border-red-900/30 rounded-xl text-red-400 text-sm flex items-center gap-3"
            >
              <AlertCircle className="w-5 h-5 shrink-0" />
              {billingError}
              <button onClick={() => setBillingError('')} className="ml-auto hover:text-red-300">✕</button>
            </motion.div>
          )}
        </AnimatePresence>

        <div className="space-y-6">

          {/* ── Profile Section ───────────────────────────────────── */}
          <section className="bg-[#141210] border border-white/5 rounded-2xl p-6">
            <div className="flex items-center gap-3 mb-6">
              <div className="w-5 h-5 text-[#F59E0B]">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
              </div>
              <h2 className="text-lg font-medium text-[#F5F1ED]">Profile</h2>
            </div>

            <div className="flex items-center gap-4 mb-6">
              <div className="relative w-16 h-16 rounded-2xl cursor-pointer group shrink-0" onClick={() => fileInputRef.current?.click()}>
                {avatarPreview ? (
                  <img src={avatarPreview} alt="Avatar" className="w-full h-full rounded-2xl object-cover" />
                ) : (
                  <div className="w-full h-full rounded-2xl bg-[#F59E0B]/20 border border-[#F59E0B]/20 flex items-center justify-center">
                    <span className="text-[#F59E0B] text-lg font-semibold">{initials}</span>
                  </div>
                )}
                <div className="absolute inset-0 rounded-2xl bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                  {avatarUploading ? <Spinner /> : <CameraIcon />}
                </div>
              </div>
              <input ref={fileInputRef} type="file" accept="image/jpeg,image/png,image/webp" className="hidden" onChange={handleAvatarChange} />

              <div>
                <p className="text-[#E8E2DC] text-base font-medium">{displayName || 'No name set'}</p>
                <p className="text-[#5C524A] text-sm">{email}</p>
                <p className="text-[#3D3630] text-xs mt-0.5">Click photo to change</p>
              </div>
            </div>

            <div className="border-t border-white/5 pt-5 mb-5">
              <p className="text-[#5C524A] text-xs uppercase tracking-widest font-mono mb-3">Who you're becoming</p>
              {profile?.bio
                ? <p className="text-[#C4BBB5] text-sm leading-relaxed italic">{profile.bio}</p>
                : <p className="text-[#3D3630] text-sm">{profileLoading ? 'Writing your identity statement…' : 'Complete a goal to unlock your identity statement.'}</p>
              }
            </div>

            {!profileLoading && profile && (
              <div className="grid grid-cols-2 gap-3 border-t border-white/5 pt-5">
                <div className="bg-[#0A0908] rounded-xl p-3">
                  <p className="text-[#3D3630] text-xs font-mono mb-1">Days active</p>
                  <p className="text-[#C4BBB5] text-xl font-display">{profile.days_active}</p>
                </div>
                <div className="bg-[#0A0908] rounded-xl p-3">
                  <p className="text-[#3D3630] text-xs font-mono mb-1">Current streak</p>
                  <p className="text-[#F59E0B] text-xl font-display">{profile.current_streak}d</p>
                </div>
              </div>
            )}
          </section>

          {/* ── Subscription Section ──────────────────────────────── */}
          <section className="bg-[#141210] border border-white/5 rounded-2xl p-6">
            <div className="flex items-center gap-3 mb-6">
              <CreditCard className="w-5 h-5 text-[#F59E0B]" />
              <h2 className="text-lg font-medium text-[#F5F1ED]">Subscription</h2>
            </div>

            {subscription?.plan && subscription.plan !== 'spark' ? (
              <div className="space-y-6">
                <div className="flex items-center justify-between p-4 bg-[#0A0908] rounded-xl border border-white/5">
                  <div className="flex items-center gap-4">
                    <div className={`w-12 h-12 rounded-xl ${planInfo.bg} flex items-center justify-center`}>
                      <planInfo.icon className={`w-6 h-6 ${planInfo.color}`} />
                    </div>
                    <div>
                      <h3 className={`font-display text-xl ${planInfo.color}`}>
                        {planInfo.name}
                      </h3>
                      <p className="text-sm text-[#5C524A] capitalize">
                        {subscription.billing_cycle || 'Monthly'} plan
                      </p>
                    </div>
                  </div>
                  {(() => {
                    const badge = getStatusBadge(subscription.status, subscription.cancel_at_period_end)
                    return (
                      <span className={`px-3 py-1.5 rounded-full text-xs font-medium border ${badge.className}`}>
                        {badge.label}
                      </span>
                    )
                  })()}
                </div>

                <div className="flex items-center gap-3 text-sm text-[#7A6E65]">
                  <Calendar className="w-4 h-4" />
                  {subscription.status === 'active' && !subscription.cancel_at_period_end ? (
                    <span>Renews on {formatDate(subscription.current_period_end)}</span>
                  ) : (
                    <span>Access until {formatDate(subscription.current_period_end)}</span>
                  )}
                </div>

                <div className="flex flex-wrap gap-3 pt-4 border-t border-white/5">
                  {subscription.status === 'active' && !subscription.cancel_at_period_end && (
                    <>
                      {subscription.plan !== 'identity' && (
                        <button
                          onClick={handleUpgrade}
                          className="flex items-center gap-2 px-4 py-2 bg-[#F59E0B]/10 border border-[#F59E0B]/20 text-[#F59E0B] font-medium rounded-lg hover:bg-[#F59E0B]/20 transition-colors text-sm"
                        >
                          <Sparkles className="w-4 h-4" />
                          Upgrade
                        </button>
                      )}
                      <button
                        onClick={handleCancel}
                        disabled={actionLoading}
                        className="flex items-center gap-2 px-4 py-2 bg-white/5 text-[#C4BBB5] border border-white/10 rounded-lg hover:bg-white/10 transition-colors text-sm disabled:opacity-50"
                      >
                        {actionLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <XCircle className="w-4 h-4" />}
                        Cancel Subscription
                      </button>
                    </>
                  )}

                  {(subscription.status === 'ended' || subscription.cancel_at_period_end) && (
                    <button
                      onClick={handleResume}
                      disabled={actionLoading}
                      className="flex items-center gap-2 px-4 py-2 bg-[#F59E0B] text-black font-medium rounded-lg hover:bg-[#F59E0B]/90 transition-colors text-sm disabled:opacity-50"
                    >
                      {actionLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
                      Resume Subscription
                    </button>
                  )}
                </div>
              </div>
            ) : (
              <div className="text-center py-8">
                <p className="text-[#7A6E65] mb-4">You're on The Spark (Free)</p>
                <button
                  onClick={handleUpgrade}
                  className="inline-flex items-center gap-2 px-6 py-3 bg-[#F59E0B] text-black font-medium rounded-xl hover:bg-[#F59E0B]/90 transition-colors"
                >
                  <Sparkles className="w-5 h-5" />
                  Upgrade
                  <ArrowRight className="w-4 h-4" />
                </button>
              </div>
            )}
          </section>

          {/* ── Billing History ─────────────────────────────────── */}
          {invoices.length > 0 && (
            <section className="bg-[#141210] border border-white/5 rounded-2xl p-6">
              <div className="flex items-center gap-3 mb-6">
                <Download className="w-5 h-5 text-[#F59E0B]" />
                <h2 className="text-lg font-medium text-[#F5F1ED]">Billing History</h2>
              </div>

              <div className="space-y-3">
                {invoices.map((invoice) => (
                  <div
                    key={invoice.id}
                    className="flex items-center justify-between p-4 bg-[#0A0908] rounded-xl border border-white/5 hover:border-white/10 transition-colors"
                  >
                    <div className="flex items-center gap-4">
                      <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${
                        invoice.status === 'paid' 
                          ? 'bg-green-950/30 text-green-400' 
                          : 'bg-amber-950/30 text-amber-400'
                      }`}>
                        {invoice.status === 'paid' ? <CheckCircle2 className="w-5 h-5" /> : <AlertCircle className="w-5 h-5" />}
                      </div>
                      <div>
                        <p className="text-[#C4BBB5] font-medium">{invoice.description}</p>
                        <p className="text-sm text-[#5C524A]">
                          {new Date(invoice.created * 1000).toLocaleDateString()}
                        </p>
                      </div>
                    </div>
                    
                    <div className="flex items-center gap-4">
                      <span className={`font-medium ${
                        invoice.status === 'paid' ? 'text-green-400' : 'text-amber-400'
                      }`}>
                        {formatCurrency(invoice.amount_paid || invoice.amount_due)}
                      </span>
                      {invoice.invoice_pdf && (
                        <a
                          href={invoice.invoice_pdf}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="p-2 hover:bg-white/5 rounded-lg transition-colors text-[#7A6E65] hover:text-[#C4BBB5]"
                          title="Download PDF"
                        >
                          <Download className="w-4 h-4" />
                        </a>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* ── Invite Section ───────────────────────────────────── */}
          <section className="bg-[#141210] border border-white/5 rounded-2xl p-6">
            <div className="flex items-center gap-3 mb-6">
              <div className="w-5 h-5 text-[#F59E0B]">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/></svg>
              </div>
              <h2 className="text-lg font-medium text-[#F5F1ED]">Invite</h2>
            </div>
            
            <p className="text-[#5C524A] text-sm mb-5">Share your transformation. Invite someone who needs this.</p>

            <button onClick={handleInvite} className="flex items-center gap-2 px-4 py-2.5 bg-[#F59E0B]/10 border border-[#F59E0B]/20 rounded-xl text-[#F59E0B] text-sm hover:bg-[#F59E0B]/20 transition-all">
              <ShareIcon />
              Invite a friend
            </button>

            <AnimatePresence>
              {showSharePanel && (
                <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }} transition={{ duration: 0.25 }} className="overflow-hidden">
                  <div className="mt-5 border-t border-white/5 pt-5 space-y-4">
                    <div className="bg-[#0A0908] rounded-xl p-4">
                      {shareLoading
                        ? <div className="flex items-center gap-2 text-[#5C524A] text-sm"><Spinner small />Writing your message...</div>
                        : <p className="text-[#C4BBB5] text-sm leading-relaxed">{shareMessage}</p>
                      }
                    </div>
                    {shareUrl && <p className="text-[#3D3630] text-xs font-mono px-1">{shareUrl}</p>}
                    {!shareLoading && (
                      <div className="flex gap-3 items-center">
                        <button onClick={handleNativeShare} className="flex items-center gap-2 px-4 py-2.5 bg-[#F59E0B] text-[#0A0908] text-sm font-medium rounded-xl hover:bg-[#F59E0B]/90 transition-all">
                          <ShareIcon dark />Share
                        </button>
                        <button onClick={handleCopy} className="flex items-center gap-2 px-4 py-2.5 bg-white/5 border border-white/10 text-[#C4BBB5] text-sm rounded-xl hover:bg-white/10 transition-all">
                          {copied ? <CheckIcon /> : <CopyIcon />}
                          {copied ? 'Copied!' : 'Copy'}
                        </button>
                        <button onClick={() => setShowSharePanel(false)} className="ml-auto text-[#3D3630] hover:text-[#5C524A] text-sm transition-colors">Close</button>
                      </div>
                    )}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </section>

          {/* ── About ───────────────────────────────────────────── */}
          <section className="bg-[#141210] border border-white/5 rounded-2xl p-6">
            <div className="flex items-center gap-3 mb-6">
              <div className="w-5 h-5 text-[#F59E0B]">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
              </div>
              <h2 className="text-lg font-medium text-[#F5F1ED]">About</h2>
            </div>
            
            <div className="space-y-0">
              <div className="flex items-center justify-between py-3 border-b border-white/5">
                <p className="text-[#5C524A] text-sm font-mono">Product</p>
                <p className="text-[#C4BBB5] text-sm">OneGoal Pro</p>
              </div>
              <div className="flex items-center justify-between py-3 border-b border-white/5">
                <p className="text-[#5C524A] text-sm font-mono">Version</p>
                <p className="text-[#3D3630] text-sm font-mono">0.1.0 — MVP</p>
              </div>
              <div className="flex items-center justify-between py-3">
                <p className="text-[#5C524A] text-sm font-mono">Philosophy</p>
                <p className="text-[#C4BBB5] text-sm italic">One goal. Full commitment.</p>
              </div>
            </div>
          </section>

          {/* ── Session / Sign Out ──────────────────────────────── */}
          <section className="bg-[#141210] border border-white/5 rounded-2xl p-6">
            <div className="flex items-center gap-3 mb-6">
              <div className="w-5 h-5 text-red-400">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
              </div>
              <h2 className="text-lg font-medium text-[#F5F1ED]">Session</h2>
            </div>

            {!showLogoutConfirm ? (
              <button 
                onClick={() => setShowLogoutConfirm(true)} 
                className="flex items-center gap-2 text-[#5C524A] hover:text-red-400 transition-colors text-sm"
              >
                <SignOutIcon />Sign out
              </button>
            ) : (
              <motion.div initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} className="space-y-4">
                <p className="text-[#C4BBB5] text-sm">You'll be signed out and returned to the login page.</p>
                <div className="flex gap-3">
                  <button 
                    onClick={handleLogout} 
                    className="px-4 py-2 bg-red-500/10 border border-red-500/20 text-red-400 text-sm rounded-xl hover:bg-red-500/20 transition-all"
                  >
                    Yes, sign out
                  </button>
                  <button 
                    onClick={() => setShowLogoutConfirm(false)} 
                    className="px-4 py-2 text-[#5C524A] text-sm hover:text-[#C4BBB5] transition-colors"
                  >
                    Cancel
                  </button>
                </div>
              </motion.div>
            )}
          </section>

        </div>
      </div>
    </div>
  )
}

// ── Icons & Helpers ───────────────────────────────────────────────────────

function Spinner({ small }: { small?: boolean }) {
  return <div className={`${small ? 'w-3 h-3' : 'w-4 h-4'} border border-current border-t-transparent rounded-full animate-spin opacity-60`} />
}

function CameraIcon() {
  return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/></svg>
}

function ShareIcon({ dark }: { dark?: boolean }) {
  return <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={dark ? '#0A0908' : 'currentColor'} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/></svg>
}

function CopyIcon() {
  return <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
}

function CheckIcon() {
  return <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#4ADE80" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
}

function SignOutIcon() {
  return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
}