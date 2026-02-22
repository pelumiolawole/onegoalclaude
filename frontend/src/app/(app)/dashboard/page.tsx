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

  const { data, isLoading, mutate } = useSWR(
    '/progress/dashboard',
    () => api.progress.getDashboard(),
    { refreshInterval: 60_000 }
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

  return (
    <div className="p-6 md:p-8 max-w-3xl mx-auto">

      {/* ── Header ─────────────────────────────────────── */}
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        className="mb-8"
      >
        <p className="text-[#5C524A] text-sm mb-1">{greeting}</p>
        <h1 className="font-display text-3xl text-[#F5F1ED]">
          {name}
          {scores?.momentum_state === 'rising' && (
            <span className="ml-2 text-[#4ADE80] text-lg">↑</span>
          )}
        </h1>
      </motion.div>

      {isLoading ? (
        <DashboardSkeleton />
      ) : (
        <div className="space-y-5">

          {/* ── Today's Task ───────────────────────────── */}
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

          {/* ── Scores + Streak ─────────────────────────── */}
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
            <ScoreTile label="Streak" value={`${scores?.streak ?? 0}d`} sub="current" />
            <ScoreTile label="Momentum" value={momentumLabel(scores?.momentum_state)} sub={scores?.momentum_state} colored />
            <ScoreTile label="Active" value={`${scores?.days_active ?? 0}d`} sub="total days" />
          </motion.div>

          {/* ── Week Activity ──────────────────────────── */}
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

          {/* ── Top Traits ────────────────────────────── */}
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
                      <span className={`text-xs font-mono ${
                        trait.trend === 'growing' ? 'text-[#4ADE80]' :
                        trait.trend === 'declining' ? 'text-[#F87171]' : 'text-[#5C524A]'
                      }`}>
                        {trait.trend === 'growing' ? '↑' : trait.trend === 'declining' ? '↓' : '—'}
                        {' '}{trait.progress_pct.toFixed(0)}%
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

          {/* ── Goal Summary ───────────────────────────── */}
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

          {/* ── Latest Review Teaser ──────────────────── */}
          {data?.latest_review && (
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.3 }}
              className="bg-[#F59E0B]/5 border border-[#F59E0B]/15 rounded-2xl p-5 cursor-pointer hover:border-[#F59E0B]/25 transition-colors"
            >
              <p className="text-[#F59E0B] text-xs uppercase tracking-widest mb-2 font-mono">
                Weekly evolution letter
              </p>
              <p className="text-[#C4BBB5] text-sm">
                Week of {data.latest_review.week_start} —{' '}
                {data.latest_review.tasks_completed}/{data.latest_review.tasks_total} tasks,{' '}
                {data.latest_review.consistency_pct.toFixed(0)}% consistency
              </p>
            </motion.div>
          )}
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

function ScoreTile({ label, value, sub, colored }: {
  label: string; value: string; sub?: string; colored?: boolean
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
      <p className={`font-display text-2xl ${textColor}`}>{value}</p>
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
