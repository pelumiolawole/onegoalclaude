'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { motion, AnimatePresence } from 'framer-motion'
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
import { api } from '@/lib/api'
import { useAuthStore } from '@/stores/auth'

// ── Types ─────────────────────────────────────────────────────────────────

interface Subscription {
  plan: 'spark' | 'forge' | 'identity' | null
  status: 'active' | 'canceling' | 'past_due' | 'unpaid' | 'canceled' | null
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

// ── Main Component ────────────────────────────────────────────────────────

export default function SettingsPage() {
  const router = useRouter()
  const { user, logout } = useAuthStore()
  
  const [subscription, setSubscription] = useState<Subscription | null>(null)
  const [invoices, setInvoices] = useState<Invoice[]>([])
  const [loading, setLoading] = useState(true)
  const [actionLoading, setActionLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    loadBillingData()
  }, [])

  const loadBillingData = async () => {
    try {
      setLoading(true)
      const [subData, invoiceData] = await Promise.all([
        api.billing.getSubscription(),
        api.billing.getInvoices().catch(() => ({ invoices: [] })) // Graceful fallback
      ])
      setSubscription(subData)
      setInvoices(invoiceData.invoices || [])
    } catch (err: any) {
      setError('Failed to load subscription data')
      console.error('Billing load error:', err)
    } finally {
      setLoading(false)
    }
  }

  const handleCancel = async () => {
    if (!confirm('Are you sure? You\'ll keep access until the end of your billing period.')) return
    
    setActionLoading(true)
    try {
      await api.billing.cancelSubscription()
      await loadBillingData() // Refresh to show updated status
    } catch (err: any) {
      setError(err.detail || 'Failed to cancel subscription')
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
      setError(err.detail || 'Failed to resume subscription')
    } finally {
      setActionLoading(false)
    }
  }

  const handleUpgrade = (plan: 'forge' | 'identity') => {
    router.push(`/settings/upgrade?plan=${plan}`)
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

  const planInfo = getPlanDisplay(subscription?.plan)

  if (loading) {
    return (
      <div className="min-h-screen bg-[#0A0908] flex items-center justify-center">
        <Loader2 className="w-8 h-8 text-[#F59E0B] animate-spin" />
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-[#0A0908]">
      <div className="max-w-4xl mx-auto px-6 py-12">
        
        {/* Header */}
        <div className="mb-10">
          <h1 className="font-display text-3xl text-[#F5F1ED] mb-2">Settings</h1>
          <p className="text-[#7A6E65]">Manage your account and subscription</p>
        </div>

        {/* Error Alert */}
        <AnimatePresence>
          {error && (
            <motion.div
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className="mb-6 p-4 bg-red-950/40 border border-red-900/30 rounded-xl text-red-400 text-sm flex items-center gap-3"
            >
              <AlertCircle className="w-5 h-5 shrink-0" />
              {error}
              <button onClick={() => setError('')} className="ml-auto hover:text-red-300">✕</button>
            </motion.div>
          )}
        </AnimatePresence>

        <div className="space-y-6">
          
          {/* ── Subscription Card ───────────────────────────────── */}
          <section className="bg-[#141210] border border-white/5 rounded-2xl p-6">
            <div className="flex items-center gap-3 mb-6">
              <CreditCard className="w-5 h-5 text-[#F59E0B]" />
              <h2 className="text-lg font-medium text-[#F5F1ED]">Subscription</h2>
            </div>

            {subscription?.plan ? (
              <div className="space-y-6">
                {/* Current Plan Badge */}
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
                        {subscription.billing_cycle || 'Free'} plan
                      </p>
                    </div>
                  </div>
                  
                  {/* Status Badge */}
                  <div className={`px-3 py-1.5 rounded-full text-xs font-medium border ${
                    subscription.status === 'active' && !subscription.cancel_at_period_end
                      ? 'bg-green-950/30 text-green-400 border-green-900/30'
                      : subscription.cancel_at_period_end
                      ? 'bg-amber-950/30 text-amber-400 border-amber-900/30'
                      : 'bg-red-950/30 text-red-400 border-red-900/30'
                  }`}>
                    {subscription.cancel_at_period_end ? 'Canceling' : subscription.status}
                  </div>
                </div>

                {/* Renewal Info */}
                <div className="flex items-center gap-3 text-sm text-[#7A6E65]">
                  <Calendar className="w-4 h-4" />
                  {subscription.cancel_at_period_end ? (
                    <span>Access until {formatDate(subscription.current_period_end)}</span>
                  ) : subscription.status === 'active' ? (
                    <span>Renews on {formatDate(subscription.current_period_end)}</span>
                  ) : (
                    <span>Ended on {formatDate(subscription.current_period_end)}</span>
                  )}
                </div>

                {/* Action Buttons */}
                <div className="flex flex-wrap gap-3 pt-4 border-t border-white/5">
                  {subscription.status === 'active' && !subscription.cancel_at_period_end && (
                    <>
                      {subscription.plan !== 'identity' && (
                        <button
                          onClick={() => handleUpgrade('identity')}
                          className="flex items-center gap-2 px-4 py-2 bg-[#d0ff59] text-black font-medium rounded-lg hover:bg-[#d0ff59]/90 transition-colors text-sm"
                        >
                          <Shield className="w-4 h-4" />
                          Upgrade to Identity
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

                  {subscription.cancel_at_period_end && (
                    <button
                      onClick={handleResume}
                      disabled={actionLoading}
                      className="flex items-center gap-2 px-4 py-2 bg-[#F59E0B] text-black font-medium rounded-lg hover:bg-[#F59E0B]/90 transition-colors text-sm disabled:opacity-50"
                    >
                      {actionLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
                      Resume Subscription
                    </button>
                  )}

                  {subscription.status === 'canceled' && (
                    <button
                      onClick={() => handleUpgrade(subscription.plan === 'identity' ? 'identity' : 'forge')}
                      className="flex items-center gap-2 px-4 py-2 bg-[#F59E0B] text-black font-medium rounded-lg hover:bg-[#F59E0B]/90 transition-colors text-sm"
                    >
                      <RefreshCw className="w-4 h-4" />
                      Reactivate
                    </button>
                  )}
                </div>
              </div>
            ) : (
              /* No Active Subscription */
              <div className="text-center py-8">
                <p className="text-[#7A6E65] mb-4">You're on The Spark (Free)</p>
                <button
                  onClick={() => handleUpgrade('forge')}
                  className="inline-flex items-center gap-2 px-6 py-3 bg-[#F59E0B] text-black font-medium rounded-xl hover:bg-[#F59E0B]/90 transition-colors"
                >
                  <Sparkles className="w-5 h-5" />
                  Upgrade to Forge
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

          {/* ── Account Actions ─────────────────────────────────── */}
          <section className="bg-[#141210] border border-white/5 rounded-2xl p-6">
            <div className="flex items-center gap-3 mb-6">
              <SignOutIcon className="w-5 h-5 text-red-400" />
              <h2 className="text-lg font-medium text-[#F5F1ED]">Account</h2>
            </div>

            <button
              onClick={logout}
              className="flex items-center gap-2 px-4 py-2 text-red-400 hover:bg-red-950/20 rounded-lg transition-colors text-sm"
            >
              <SignOutIcon className="w-4 h-4" />
              Sign Out
            </button>
          </section>

        </div>
      </div>
    </div>
  )
}

// ── Icons ─────────────────────────────────────────────────────────────────

function SignOutIcon({ className }: { className?: string }) {
  return (
    <svg className={className} width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
      <polyline points="16 17 21 12 16 7" />
      <line x1="21" y1="12" x2="9" y2="12" />
    </svg>
  )
}