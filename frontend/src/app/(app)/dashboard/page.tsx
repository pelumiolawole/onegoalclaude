'use client'

import { useState } from 'react'
import useSWR from 'swr'
import { motion, AnimatePresence } from 'framer-motion'
import { api } from '@/lib/api'
import { useAuthStore } from '@/stores/auth'
import ReflectionModal from '@/components/reflection/ReflectionModal'
import TaskCard from '@/components/task/TaskCard'
import ScoreRing from '@/components/dashboard/ScoreRing'
import WeekGrid from '@/components/dashboard/WeekGrid'

export default function DashboardPage() {
  const { user } = useAuthStore()
  const [reflectionOpen, setReflectionOpen] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [expandedTask, setExpandedTask] = useState<string | null>(null)

  const { data, isLoading, mutate } = useSWR(
    '/progress/dashboard',
    () => api.progress.getDashboard(),
    { refreshInterval: 60_000 }
  )

  const { data: historyData, isLoading: historyLoading } = useSWR(
    historyOpen ? '/tasks/history/30' : null,
    () => api.tasks.getHistory(30)
  )

  const task   = data?.today_task
  const scores = data?.scores

  const greeting = getGreeting()
  const name     = user?.display_name?.split(' ')[0] || 'there'

  async function handleTaskComplete() {
    if (!task) return
    await api.tasks.complete(task.id)
    await mutate()
  }

  async function handleTaskSkip(reason: string) {
    if (!task) return
    await api.tasks.skip(task.id, reason)
    await mutate()
  }

  function handleReflectionDone() {
    setReflectionOpen(false)
    mutate()
  }

  function toggleTask(id: string) {
    setExpandedTask(prev => prev === id ? null : id)
  }

  return (
    <div className="p-6 md:p-8 pb-24 md:pb-8 max-w-3xl mx-auto">

      <InstallBanner />

      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        className="mb-8"
      >
        <p className="text-[#5C524A] text-sm mb-1">{greeting}</p>
        <h1 className="font-display text-3xl text-[#F5F1ED]">
          {name}
          {scores?.momentum_state === 'rising' && (
            <span className="ml-2 text-[#4ADE80] text-lg">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={{display:'inline'}}>
                <line x1="12" y1="19" x2="12" y2="5"/><polyline points="5 12 12 5 19 12"/>
              </svg>
            </span>
          )}
        </h1>
      </motion.div>

      {isLoading ? (
        <DashboardSkeleton />
      ) : (
        <div className="space-y-5">

          {/* Today's Task */}
          {task ? (
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.05 }}
            >
              <TaskCard
                task={task}
                onComplete={handleTaskComplete}
                onSkip={handleTaskSkip}
                onReflect={() => setReflectionOpen(true)}
              />
            </motion.div>
          ) : (
            <NoTaskCard />
          )}

          {/* Scores + Streak */}
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="grid grid-cols-2 sm:grid-cols-4 gap-3"
          >
            <ScoreRing
              label="Transformation"
              value={scores?.transformation ?? 0}
              primary
            />
            <ScoreTile label="Streak" value={scores?.streak ?? 0} unit="d" sub="current" />
            <ScoreTile label="Momentum" value={momentumLabel(scores?.momentum_state)} sub={scores?.momentum_state} colored />
            <ScoreTile label="Active" value={scores?.days_active ?? 0} unit="d" sub="total days" />
          </motion.div>

          {/* Week Activity */}
          {data?.week_activity && (
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.15 }}
              className="bg-[#141210] border border-white/5 rounded-2xl p-5"
            >
              <p className="text-[#5C524A] text-xs uppercase tracking-widest mb-4 font-mono">
                This week
              </p>
              <WeekGrid days={data.week_activity} />
            </motion.div>
          )}

          {/* Top Traits */}
          {data?.top_traits && data.top_traits.length > 0 && (
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.2 }}
              className="bg-[#141210] border border-white/5 rounded-2xl p-5"
            >
              <p className="text-[#5C524A] text-xs uppercase tracking-widest mb-4 font-mono">
                Identity traits
              </p>
              <div className="space-y-3">
                {data.top_traits.map((trait) => (
                  <div key={trait.name}>
                    <div className="flex justify-between items-center mb-1.5">
                      <span className="text-[#C4BBB5] text-sm capitalize">{trait.name}</span>
                      <span className={`text-xs font-mono flex items-center gap-1 ${
                        trait.trend === 'growing' ? 'text-[#4ADE80]' :
                        trait.trend === 'declining' ? 'text-[#F87171]' : 'text-[#5C524A]'
                      }`}>
                        <TrendArrowSmall trend={trait.trend} />
                        {trait.progress_pct.toFixed(0)}%
                      </span>
                    </div>
                    <div className="h-1.5 bg-[#1E1B18] rounded-full overflow-hidden">
                      <motion.div
                        className="h-full bg-[#F59E0B] rounded-full"
                        initial={{ width: 0 }}
                        animate={{ width: `${trait.progress_pct}%` }}
                        transition={{ duration: 0.8, delay: 0.3 }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </motion.div>
          )}

          {/* Goal Summary */}
          {data?.goal && (
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.25 }}
              className="bg-[#141210] border border-white/5 rounded-2xl p-5"
            >
              <p className="text-[#5C524A] text-xs uppercase tracking-widest mb-3 font-mono">
                Your goal
              </p>
              <p className="text-[#C4BBB5] text-sm mb-3 leading-relaxed">
                {data.goal.statement}
              </p>
              <div className="flex items-center gap-3">
                <div className="flex-1 h-1.5 bg-[#1E1B18] rounded-full overflow-hidden">
                  <motion.div
                    className="h-full bg-[#F59E0B]/60 rounded-full"
                    initial={{ width: 0 }}
                    animate={{ width: `${data.goal.progress}%` }}
                    transition={{ duration: 1, delay: 0.4 }}
                  />
                </div>
                <span className="text-[#5C524A] text-xs font-mono whitespace-nowrap">
                  {data.goal.objectives_done}/{data.goal.objectives_total} objectives
                </span>
              </div>
            </motion.div>
          )}

          {/* Latest Review Teaser */}
          {data?.latest_review && (
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.3 }}
              className="bg-[#F59E0B]/5 border border-[#F59E0B]/15 rounded-2xl p-5"
            >
              <p className="text-[#F59E0B] text-xs uppercase tracking-widest mb-2 font-mono">
                Weekly review
              </p>
              <p className="text-[#C4BBB5] text-sm">
                Week of {data.latest_review.week_start} —{' '}
                {data.latest_review.tasks_completed}/{data.latest_review.tasks_total} tasks,{' '}
                {data.latest_review.consistency_pct.toFixed(0)}% consistency
              </p>
            </motion.div>
          )}

          {/* Past Tasks — expandable diary */}
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.35 }}
            className="bg-[#141210] border border-white/5 rounded-2xl overflow-hidden"
          >
            <button
              onClick={() => setHistoryOpen(v => !v)}
              className="w-full flex items-center justify-between px-5 py-4 hover:bg-[#1E1B18] transition-colors"
            >
              <p className="text-[#5C524A] text-xs uppercase tracking-widest font-mono">
                Past tasks
              </p>
              <div className={`text-[#5C524A] transition-transform duration-200 ${historyOpen ? 'rotate-180' : ''}`}>
                <ChevronIcon />
              </div>
            </button>

            <AnimatePresence initial={false}>
              {historyOpen && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: 'auto', opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.25 }}
                  className="overflow-hidden"
                >
                  <div className="border-t border-white/5">
                    {historyLoading ? (
                      <div className="px-5 py-6 space-y-3">
                        {[...Array(4)].map((_, i) => (
                          <div key={i} className="h-12 bg-[#1E1B18] rounded-xl animate-pulse" />
                        ))}
                      </div>
                    ) : !historyData || historyData.tasks.length === 0 ? (
                      <p className="px-5 py-6 text-[#3D3630] text-sm">
                        No past tasks yet. Complete your first task to start building history.
                      </p>
                    ) : (
                      <div className="divide-y divide-white/5">
                        {/* Stats row */}
                        <div className="px-5 py-3 flex gap-5">
                          <span className="text-[#5C524A] text-xs font-mono">
                            <span className="text-[#4ADE80]">{historyData.stats.completed}</span> completed
                          </span>
                          <span className="text-[#5C524A] text-xs font-mono">
                            <span className="text-[#F87171]">{historyData.stats.missed + historyData.stats.skipped}</span> missed
                          </span>
                          <span className="text-[#5C524A] text-xs font-mono">
                            <span className="text-[#F59E0B]">{historyData.stats.completion_rate}%</span> rate
                          </span>
                        </div>

                        {/* Task rows — expandable */}
                        {historyData.tasks.map((t: any) => (
                          <div key={t.id}>
                            {/* Summary row — always visible */}
                            <button
                              onClick={() => toggleTask(t.id)}
                              className="w-full px-5 py-3.5 flex items-start gap-3 hover:bg-[#1E1B18] transition-colors text-left"
                            >
                              <div className="mt-0.5 shrink-0">
                                <StatusDot status={t.status} />
                              </div>
                              <div className="flex-1 min-w-0">
                                <p className={`text-sm leading-snug ${
                                  t.status === 'completed' ? 'text-[#C4BBB5]' : 'text-[#5C524A]'
                                }`}>
                                  {t.title}
                                </p>
                                {t.identity_focus && (
                                  <p className="text-[#3D3630] text-xs mt-0.5 truncate">
                                    {t.identity_focus}
                                  </p>
                                )}
                              </div>
                              <div className="shrink-0 text-right flex flex-col items-end gap-1">
                                <p className="text-[#3D3630] text-xs font-mono">
                                  {formatDate(t.date)}
                                </p>
                                {t.reflection_qa?.length > 0 && (
                                  <p className="text-[#F59E0B] text-[10px] font-mono">reflected</p>
                                )}
                              </div>
                              {/* Expand indicator */}
                              <div className={`text-[#3D3630] shrink-0 mt-0.5 transition-transform duration-200 ${expandedTask === t.id ? 'rotate-180' : ''}`}>
                                <ChevronIcon />
                              </div>
                            </button>

                            {/* Expanded detail */}
                            <AnimatePresence initial={false}>
                              {expandedTask === t.id && (
                                <motion.div
                                  initial={{ height: 0, opacity: 0 }}
                                  animate={{ height: 'auto', opacity: 1 }}
                                  exit={{ height: 0, opacity: 0 }}
                                  transition={{ duration: 0.2 }}
                                  className="overflow-hidden"
                                >
                                  <div className="px-5 pb-5 pt-1 bg-[#0F0D0B] border-t border-white/5 space-y-4">

                                    {/* Task description */}
                                    {t.description && (
                                      <div>
                                        <p className="text-[#3D3630] text-[10px] uppercase tracking-widest font-mono mb-1.5">
                                          Task
                                        </p>
                                        <p className="text-[#7A6E65] text-sm leading-relaxed">
                                          {t.description}
                                        </p>
                                      </div>
                                    )}

                                    {/* Identity anchor */}
                                    {t.identity_focus && (
                                      <div>
                                        <p className="text-[#3D3630] text-[10px] uppercase tracking-widest font-mono mb-1.5">
                                          Identity
                                        </p>
                                        <p className="text-[#F59E0B]/70 text-sm italic">
                                          {t.identity_focus}
                                        </p>
                                      </div>
                                    )}

                                    {/* Reflection Q&A */}
                                    {t.reflection_qa?.length > 0 ? (
                                      <div>
                                        <p className="text-[#3D3630] text-[10px] uppercase tracking-widest font-mono mb-3">
                                          Reflection
                                        </p>
                                        <div className="space-y-3">
                                          {t.reflection_qa.map((qa: any, i: number) => (
                                            <div key={i}>
                                              <p className="text-[#5C524A] text-xs mb-1 leading-relaxed">
                                                {qa.question}
                                              </p>
                                              <p className="text-[#C4BBB5] text-sm leading-relaxed pl-3 border-l border-[#F59E0B]/20">
                                                {qa.answer}
                                              </p>
                                            </div>
                                          ))}
                                        </div>
                                      </div>
                                    ) : (
                                      <div>
                                        <p className="text-[#3D3630] text-[10px] uppercase tracking-widest font-mono mb-1.5">
                                          Reflection
                                        </p>
                                        <p className="text-[#3D3630] text-sm italic">
                                          No reflection recorded.
                                        </p>
                                      </div>
                                    )}

                                    {/* AI insight */}
                                    {t.reflection_insight && (
                                      <div className="bg-[#F59E0B]/5 border border-[#F59E0B]/10 rounded-xl p-3">
                                        <p className="text-[#3D3630] text-[10px] uppercase tracking-widest font-mono mb-1.5">
                                          Coach insight
                                        </p>
                                        <p className="text-[#A09690] text-sm leading-relaxed italic">
                                          {t.reflection_insight}
                                        </p>
                                      </div>
                                    )}

                                    {/* Sentiment badge */}
                                    {t.reflection_sentiment && (
                                      <div className="flex items-center gap-2">
                                        <SentimentBadge sentiment={t.reflection_sentiment} />
                                      </div>
                                    )}

                                  </div>
                                </motion.div>
                              )}
                            </AnimatePresence>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </motion.div>

        </div>
      )}

      {/* Reflection modal */}
      <AnimatePresence>
        {reflectionOpen && task && (
          <ReflectionModal
            taskId={task.id}
            taskTitle={task.title}
            onClose={() => setReflectionOpen(false)}
            onDone={handleReflectionDone}
          />
        )}
      </AnimatePresence>
    </div>
  )
}

// ── Sub-components ─────────────────────────────────────────────────────────

function SentimentBadge({ sentiment }: { sentiment: string }) {
  const config: Record<string, { label: string; color: string }> = {
    positive:  { label: 'Positive',  color: 'text-[#4ADE80] bg-[#4ADE80]/10 border-[#4ADE80]/20' },
    neutral:   { label: 'Neutral',   color: 'text-[#94A3B8] bg-[#94A3B8]/10 border-[#94A3B8]/20' },
    negative:  { label: 'Negative',  color: 'text-[#F87171] bg-[#F87171]/10 border-[#F87171]/20' },
    mixed:     { label: 'Mixed',     color: 'text-[#F59E0B] bg-[#F59E0B]/10 border-[#F59E0B]/20' },
    resistant: { label: 'Resistant', color: 'text-[#F87171] bg-[#F87171]/10 border-[#F87171]/20' },
  }
  const c = config[sentiment] || config.neutral
  return (
    <span className={`text-[10px] font-mono px-2 py-0.5 rounded-full border ${c.color}`}>
      {c.label}
    </span>
  )
}

function TrendArrowSmall({ trend }: { trend: string }) {
  if (trend === 'growing') return (
    <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <line x1="12" y1="19" x2="12" y2="5"/><polyline points="5 12 12 5 19 12"/>
    </svg>
  )
  if (trend === 'declining') return (
    <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <line x1="12" y1="5" x2="12" y2="19"/><polyline points="19 12 12 19 5 12"/>
    </svg>
  )
  return (
    <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <line x1="5" y1="12" x2="19" y2="12"/>
    </svg>
  )
}

function StatusDot({ status }: { status: string }) {
  if (status === 'completed') return (
    <div className="w-5 h-5 rounded-full bg-[#4ADE80]/15 border border-[#4ADE80]/30 flex items-center justify-center">
      <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="#4ADE80" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="20 6 9 17 4 12"/>
      </svg>
    </div>
  )
  if (status === 'skipped') return (
    <div className="w-5 h-5 rounded-full bg-[#F59E0B]/10 border border-[#F59E0B]/20 flex items-center justify-center">
      <svg width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="#F59E0B" strokeWidth="3" strokeLinecap="round">
        <line x1="5" y1="12" x2="19" y2="12"/>
      </svg>
    </div>
  )
  return (
    <div className="w-5 h-5 rounded-full bg-[#F87171]/10 border border-[#F87171]/20 flex items-center justify-center">
      <svg width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="#F87171" strokeWidth="3" strokeLinecap="round">
        <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
      </svg>
    </div>
  )
}

function ChevronIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="6 9 12 15 18 9"/>
    </svg>
  )
}

function ScoreTile({ label, value, unit, sub, colored }: {
  label: string
  value: string | number
  unit?: string
  sub?: string
  colored?: boolean
}) {
  const colorMap: Record<string, string> = {
    rising:   'text-[#4ADE80]',
    holding:  'text-[#94A3B8]',
    declining:'text-[#F87171]',
    critical: 'text-[#F87171]',
  }
  const textColor = colored && sub ? (colorMap[sub] || 'text-[#C4BBB5]') : 'text-[#C4BBB5]'

  return (
    <div className="bg-[#141210] border border-white/5 rounded-2xl p-4">
      <p className="text-[#3D3630] text-xs uppercase tracking-wider mb-1 font-mono">{label}</p>
      <p className={`font-mono text-2xl ${textColor}`}>
        {value}{unit && <span className="text-lg">{unit}</span>}
      </p>
      {sub && <p className="text-[#3D3630] text-xs mt-0.5 capitalize">{sub}</p>}
    </div>
  )
}

function NoTaskCard() {
  return (
    <div className="bg-[#141210] border border-dashed border-white/10 rounded-2xl p-8 text-center">
      <p className="text-[#5C524A] mb-2">No task for today yet.</p>
      <p className="text-[#3D3630] text-sm">Your task will be generated tonight for tomorrow.</p>
    </div>
  )
}

function DashboardSkeleton() {
  return (
    <div className="space-y-5 animate-pulse">
      <div className="h-48 bg-[#141210] rounded-2xl" />
      <div className="grid grid-cols-4 gap-3">
        {[...Array(4)].map((_, i) => <div key={i} className="h-24 bg-[#141210] rounded-2xl" />)}
      </div>
      <div className="h-32 bg-[#141210] rounded-2xl" />
    </div>
  )
}

function getGreeting() {
  const h = new Date().getHours()
  if (h < 12) return 'Good morning'
  if (h < 17) return 'Good afternoon'
  return 'Good evening'
}

function momentumLabel(state?: string) {
  const labels: Record<string, string> = {
    rising: 'Rising', holding: 'Steady',
    declining: 'Fading', critical: 'Critical',
  }
  return labels[state || 'holding'] || 'Steady'
}

function formatDate(dateStr: string): string {
  const d = new Date(dateStr)
  const today = new Date()
  const yesterday = new Date(today)
  yesterday.setDate(today.getDate() - 1)
  if (d.toDateString() === today.toDateString()) return 'Today'
  if (d.toDateString() === yesterday.toDateString()) return 'Yesterday'
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
}