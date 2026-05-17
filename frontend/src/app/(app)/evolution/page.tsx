'use client'

import { useMemo } from 'react'
import useSWR from 'swr'
import { motion } from 'framer-motion'
import { api } from '@/lib/api'
import { useAuthStore } from '@/stores/auth'

// ─── Types ────────────────────────────────────────────────────────────────────

interface Trait {
  name: string
  progress_pct: number
  trend: 'growing' | 'declining' | 'stable'
}

interface Task {
  id: string
  date: string
  title: string
  identity_focus: string
  status: string
  reflection_depth: number | null
  reflection_sentiment: string | null
  reflection_insight: string | null
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function formatDate(dateStr: string) {
  return new Date(dateStr).toLocaleDateString('en-GB', {
    day: 'numeric', month: 'short', year: 'numeric',
  })
}

function weekLabel(dateStr: string) {
  return new Date(dateStr).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
}

// Group tasks by week, return avg depth per week
function buildDepthArc(tasks: Task[]) {
  const byWeek: Record<string, number[]> = {}
  tasks.forEach(t => {
    if (!t.reflection_depth) return
    const d = new Date(t.date)
    const monday = new Date(d)
    monday.setDate(d.getDate() - ((d.getDay() + 6) % 7))
    const key = monday.toISOString().slice(0, 10)
    if (!byWeek[key]) byWeek[key] = []
    byWeek[key].push(t.reflection_depth)
  })
  return Object.entries(byWeek)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([week, depths]) => ({
      week,
      avg: depths.reduce((s, d) => s + d, 0) / depths.length,
    }))
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-[#5C524A] text-xs uppercase tracking-widest font-mono mb-4">
      {children}
    </p>
  )
}

function Card({ children, className = '', delay = 0 }: {
  children: React.ReactNode
  className?: string
  delay?: number
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay, duration: 0.4 }}
      className={`bg-[#141210] border border-white/5 rounded-2xl p-5 ${className}`}
    >
      {children}
    </motion.div>
  )
}

// Identity then vs now
function IdentityArc({ first, latest }: { first: Task | null; latest: Task | null }) {
  if (!first && !latest) return null

  return (
    <Card delay={0.05}>
      <SectionLabel>Who you were → who you are</SectionLabel>
      <div className="space-y-5">
        {first && (
          <div className="relative pl-4 border-l border-[#2A2520]">
            <p className="text-[#3D3630] text-[10px] uppercase tracking-widest font-mono mb-1.5">
              Day 1 — {formatDate(first.date)}
            </p>
            <p className="text-[#7A6E65] text-sm leading-relaxed italic">
              {first.identity_focus || first.title}
            </p>
          </div>
        )}

        {first && latest && first.id !== latest.id && (
          <div className="flex items-center gap-3 py-1">
            <div className="flex-1 h-px bg-gradient-to-r from-[#2A2520] via-[#F59E0B]/30 to-[#2A2520]" />
            <span className="text-[#F59E0B] text-xs font-mono shrink-0">
              {Math.round((new Date(latest.date).getTime() - new Date(first.date).getTime()) / 86400000)} days
            </span>
            <div className="flex-1 h-px bg-gradient-to-r from-[#2A2520] via-[#F59E0B]/30 to-[#2A2520]" />
          </div>
        )}

        {latest && latest.id !== first?.id && (
          <div className="relative pl-4 border-l border-[#F59E0B]/30">
            <p className="text-[#F59E0B]/60 text-[10px] uppercase tracking-widest font-mono mb-1.5">
              Today — {formatDate(latest.date)}
            </p>
            <p className="text-[#E8E2DC] text-sm leading-relaxed italic">
              {latest.identity_focus || latest.title}
            </p>
          </div>
        )}

        {first && first.id === latest?.id && (
          <p className="text-[#3D3630] text-sm italic">
            Complete more tasks to see your identity shift over time.
          </p>
        )}
      </div>
    </Card>
  )
}

// Trait bars
function TraitProgression({ traits }: { traits: Trait[] }) {
  if (!traits || traits.length === 0) return null

  return (
    <Card delay={0.1}>
      <SectionLabel>Identity traits building</SectionLabel>
      <div className="space-y-4">
        {traits.map((trait, i) => (
          <div key={trait.name}>
            <div className="flex justify-between items-center mb-2">
              <span className="text-[#C4BBB5] text-sm capitalize">{trait.name}</span>
              <span className={`text-xs font-mono flex items-center gap-1 ${
                trait.trend === 'growing'   ? 'text-[#4ADE80]' :
                trait.trend === 'declining' ? 'text-[#F87171]' :
                'text-[#5C524A]'
              }`}>
                {trait.trend === 'growing' ? '↑' : trait.trend === 'declining' ? '↓' : '→'}
                {trait.progress_pct.toFixed(0)}%
              </span>
            </div>
            <div className="h-2 bg-[#1E1B18] rounded-full overflow-hidden">
              <motion.div
                className={`h-full rounded-full ${
                  trait.trend === 'growing' ? 'bg-[#F59E0B]' :
                  trait.trend === 'declining' ? 'bg-[#F87171]/50' :
                  'bg-[#5C524A]'
                }`}
                initial={{ width: 0 }}
                animate={{ width: `${trait.progress_pct}%` }}
                transition={{ duration: 1, delay: 0.2 + i * 0.1, ease: 'easeOut' }}
              />
            </div>
          </div>
        ))}
      </div>
    </Card>
  )
}

// Reflection depth arc — SVG sparkline
function DepthArc({ data }: { data: { week: string; avg: number }[] }) {
  if (data.length < 2) return null

  const W = 280
  const H = 80
  const pad = 8
  const max = 10
  const xs = data.map((_, i) => pad + (i / (data.length - 1)) * (W - pad * 2))
  const ys = data.map(d => H - pad - ((d.avg / max) * (H - pad * 2)))
  const path = xs.map((x, i) => `${i === 0 ? 'M' : 'L'} ${x} ${ys[i]}`).join(' ')
  const fill = `${path} L ${xs[xs.length - 1]} ${H} L ${xs[0]} ${H} Z`

  return (
    <Card delay={0.15}>
      <SectionLabel>Reflection depth over time</SectionLabel>
      <div className="relative">
        <svg width="100%" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="overflow-visible">
          <defs>
            <linearGradient id="depthGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#F59E0B" stopOpacity="0.15" />
              <stop offset="100%" stopColor="#F59E0B" stopOpacity="0" />
            </linearGradient>
          </defs>
          {/* Fill */}
          <path d={fill} fill="url(#depthGrad)" />
          {/* Line */}
          <motion.path
            d={path}
            fill="none"
            stroke="#F59E0B"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
            initial={{ pathLength: 0, opacity: 0 }}
            animate={{ pathLength: 1, opacity: 1 }}
            transition={{ duration: 1.2, delay: 0.3, ease: 'easeInOut' }}
          />
          {/* Dots */}
          {xs.map((x, i) => (
            <motion.circle
              key={i}
              cx={x}
              cy={ys[i]}
              r="3"
              fill="#F59E0B"
              initial={{ scale: 0, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{ delay: 0.8 + i * 0.05 }}
            />
          ))}
        </svg>
        {/* Week labels */}
        <div className="flex justify-between mt-2">
          <span className="text-[#3D3630] text-[10px] font-mono">{weekLabel(data[0].week)}</span>
          {data.length > 2 && (
            <span className="text-[#3D3630] text-[10px] font-mono">
              {weekLabel(data[Math.floor(data.length / 2)].week)}
            </span>
          )}
          <span className="text-[#3D3630] text-[10px] font-mono">{weekLabel(data[data.length - 1].week)}</span>
        </div>
      </div>
      <p className="text-[#3D3630] text-xs mt-3">
        Higher means more honest, more specific answers. A rising arc means you're going deeper.
      </p>
    </Card>
  )
}

// Milestone moments
function Milestones({ tasks, streak }: { tasks: Task[]; streak: number }) {
  const milestones = useMemo(() => {
    const list: { label: string; detail: string; date?: string; amber?: boolean }[] = []

    const completed = tasks.filter(t => t.status === 'completed')
    if (completed.length > 0) {
      const first = completed[completed.length - 1] // history is newest-first
      list.push({
        label: 'First task completed',
        detail: first.title,
        date: first.date,
      })
    }

    if (completed.length >= 7) {
      list.push({
        label: '7 tasks done',
        detail: 'One week of showing up',
        amber: true,
      })
    }

    if (completed.length >= 30) {
      list.push({
        label: '30 tasks done',
        detail: 'A month of identity work',
        amber: true,
      })
    }

    const breakthroughs = tasks.filter(t => t.reflection_sentiment === 'breakthrough')
    if (breakthroughs.length > 0) {
      list.push({
        label: 'First breakthrough',
        detail: breakthroughs[0].reflection_insight?.slice(0, 80) + '…' || 'A moment of genuine insight',
        date: breakthroughs[0].date,
        amber: true,
      })
    }

    if (streak >= 7) {
      list.push({
        label: `${streak}-day streak`,
        detail: 'Consistency is identity in action',
        amber: true,
      })
    }

    return list
  }, [tasks, streak])

  if (milestones.length === 0) return null

  return (
    <Card delay={0.2}>
      <SectionLabel>Moments that marked the shift</SectionLabel>
      <div className="space-y-4">
        {milestones.map((m, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, x: -8 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.3 + i * 0.08 }}
            className="flex gap-3"
          >
            <div className="mt-1 shrink-0">
              <div className={`w-2 h-2 rounded-full ${m.amber ? 'bg-[#F59E0B]' : 'bg-[#3D3630]'}`} />
            </div>
            <div>
              <p className={`text-sm font-medium ${m.amber ? 'text-[#F59E0B]' : 'text-[#C4BBB5]'}`}>
                {m.label}
              </p>
              <p className="text-[#5C524A] text-xs mt-0.5 leading-relaxed">{m.detail}</p>
              {m.date && (
                <p className="text-[#3D3630] text-[10px] font-mono mt-0.5">{formatDate(m.date)}</p>
              )}
            </div>
          </motion.div>
        ))}
      </div>
    </Card>
  )
}

// Latest coach insight
function LatestInsight({ tasks }: { tasks: Task[] }) {
  const withInsight = tasks.find(t => t.reflection_insight)
  if (!withInsight) return null

  return (
    <Card delay={0.25} className="bg-[#F59E0B]/5 border-[#F59E0B]/10">
      <SectionLabel>What your coach sees in you</SectionLabel>
      <div className="flex gap-3">
        <div className="w-7 h-7 rounded-full bg-[#F59E0B]/15 border border-[#F59E0B]/20 flex items-center justify-center shrink-0 mt-0.5">
          <span className="text-[#F59E0B] text-xs">✦</span>
        </div>
        <p className="text-[#A09690] text-sm leading-relaxed italic">
          {withInsight.reflection_insight}
        </p>
      </div>
      <p className="text-[#3D3630] text-[10px] font-mono mt-3 ml-10">
        From your reflection on {formatDate(withInsight.date)}
      </p>
    </Card>
  )
}

// Transformation score ring (reused pattern from dashboard)
function ScoreRing({ value }: { value: number }) {
  const r = 36
  const circ = 2 * Math.PI * r
  const filled = (value / 100) * circ

  return (
    <div className="flex flex-col items-center gap-2">
      <div className="relative w-24 h-24">
        <svg width="96" height="96" viewBox="0 0 96 96">
          <circle cx="48" cy="48" r={r} fill="none" stroke="#1E1B18" strokeWidth="6" />
          <motion.circle
            cx="48" cy="48" r={r}
            fill="none"
            stroke="#F59E0B"
            strokeWidth="6"
            strokeLinecap="round"
            strokeDasharray={`${circ}`}
            initial={{ strokeDashoffset: circ }}
            animate={{ strokeDashoffset: circ - filled }}
            transition={{ duration: 1.4, delay: 0.2, ease: 'easeOut' }}
            transform="rotate(-90 48 48)"
          />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="text-[#F5F1ED] font-mono text-2xl font-bold">{value}</span>
        </div>
      </div>
      <p className="text-[#5C524A] text-xs uppercase tracking-widest font-mono">Transformation</p>
    </div>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function EvolutionPage() {
  const { user } = useAuthStore()
  const name = user?.display_name?.split(' ')[0] || 'there'

  const { data: dashboard, isLoading: dashLoading } = useSWR(
    '/progress/dashboard',
    () => api.progress.getDashboard()
  )

  const { data: historyData, isLoading: histLoading } = useSWR(
    '/tasks/history/90',
    () => api.tasks.getHistory(90)
  )

  const isLoading = dashLoading || histLoading

  const tasks: Task[] = historyData?.tasks || []
  const traits: Trait[] = dashboard?.top_traits || []
  const score = dashboard?.scores?.transformation ?? 0
  const streak = dashboard?.scores?.streak ?? 0

  // Oldest completed task = Day 1
  const completedTasks = tasks.filter(t => t.status === 'completed')
  const firstTask = completedTasks.length > 0 ? completedTasks[completedTasks.length - 1] : null
  const latestTask = completedTasks.length > 0 ? completedTasks[0] : null

  const depthArc = useMemo(() => buildDepthArc(tasks), [tasks])

  const daysActive = completedTasks.length
  const totalTasks = tasks.length

  return (
    <div className="p-6 md:p-8 pb-24 md:pb-8 max-w-2xl mx-auto">

      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        className="mb-8"
      >
        <p className="text-[#5C524A] text-xs uppercase tracking-widest font-mono mb-1">Your evolution</p>
        <h1 className="font-display text-3xl text-[#F5F1ED]">
          Who you're becoming
        </h1>
        <p className="text-[#3D3630] text-sm mt-2">
          {daysActive} tasks completed across {totalTasks > 0 ? Math.ceil(totalTasks / 7) : 0} weeks
        </p>
      </motion.div>

      {isLoading ? (
        <EvolutionSkeleton />
      ) : (
        <div className="space-y-4">

          {/* Transformation score — centred hero */}
          {score > 0 && (
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.02 }}
              className="bg-[#141210] border border-white/5 rounded-2xl p-6 flex flex-col items-center gap-4"
            >
              <ScoreRing value={score} />
              <div className="text-center">
                <p className="text-[#C4BBB5] text-sm">
                  {score < 30
                    ? 'The foundation is being laid.'
                    : score < 60
                    ? 'The shift is happening. Keep going.'
                    : score < 80
                    ? 'You\'re becoming who you said you would.'
                    : 'This is who you are now.'}
                </p>
              </div>
            </motion.div>
          )}

          {/* Identity then vs now */}
          <IdentityArc first={firstTask} latest={latestTask} />

          {/* Trait progression */}
          <TraitProgression traits={traits} />

          {/* Depth arc */}
          <DepthArc data={depthArc} />

          {/* Latest coach insight */}
          <LatestInsight tasks={tasks} />

          {/* Milestones */}
          <Milestones tasks={tasks} streak={streak} />

          {/* Empty state */}
          {completedTasks.length === 0 && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="bg-[#141210] border border-dashed border-white/10 rounded-2xl p-10 text-center"
            >
              <p className="text-[#F59E0B] text-2xl mb-3">✦</p>
              <p className="text-[#5C524A] text-sm mb-1">Your evolution starts with the first task.</p>
              <p className="text-[#3D3630] text-sm">
                Complete today's task and come back here to watch who you're becoming.
              </p>
            </motion.div>
          )}

        </div>
      )}
    </div>
  )
}

function EvolutionSkeleton() {
  return (
    <div className="space-y-4 animate-pulse">
      <div className="h-40 bg-[#141210] rounded-2xl" />
      <div className="h-32 bg-[#141210] rounded-2xl" />
      <div className="h-48 bg-[#141210] rounded-2xl" />
      <div className="h-24 bg-[#141210] rounded-2xl" />
      <div className="h-36 bg-[#141210] rounded-2xl" />
    </div>
  )
}