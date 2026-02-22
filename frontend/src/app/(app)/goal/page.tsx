'use client'

import useSWR from 'swr'
import { motion } from 'framer-motion'
import { api } from '@/lib/api'

export default function GoalPage() {
  const { data, isLoading } = useSWR('/goals/active', () => api.goals.getActive())

  if (isLoading) return <GoalSkeleton />

  const { goal, objectives, identity_traits, scores } = data || {}

  return (
    <div className="p-6 md:p-8 max-w-3xl mx-auto space-y-5">

      <motion.h1
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        className="font-display text-3xl text-[#F5F1ED]"
      >
        Your goal
      </motion.h1>

      {/* ── Goal statement ───────────────────────────── */}
      {goal && (
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.05 }}
          className="bg-[#141210] border border-[#F59E0B]/20 rounded-2xl p-6"
        >
          <p className="text-[#F59E0B] text-xs uppercase tracking-widest font-mono mb-3">
            One Goal
          </p>
          <p className="font-display text-2xl text-[#F5F1ED] leading-snug mb-4">
            {goal.statement}
          </p>

          {goal.why && (
            <p className="text-[#7A6E65] text-sm italic border-t border-white/5 pt-4 mb-4">
              "{goal.why}"
            </p>
          )}

          {/* Progress */}
          <div className="flex items-center gap-3">
            <div className="flex-1 h-1.5 bg-[#1E1B18] rounded-full overflow-hidden">
              <motion.div
                className="h-full bg-[#F59E0B] rounded-full"
                initial={{ width: 0 }}
                animate={{ width: `${goal.progress}%` }}
                transition={{ duration: 1 }}
              />
            </div>
            <span className="text-[#5C524A] text-xs font-mono whitespace-nowrap">
              {goal.progress.toFixed(0)}% complete
            </span>
          </div>

          <div className="mt-3 flex gap-4 text-xs text-[#3D3630] font-mono">
            <span>Started: {goal.started_at?.slice(0, 10)}</span>
            <span>{goal.estimated_weeks}w estimated</span>
            <span>Difficulty: {goal.difficulty}/10</span>
          </div>
        </motion.div>
      )}

      {/* ── Required identity ────────────────────────── */}
      {goal?.required_identity && (
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.08 }}
          className="bg-[#1E1B18] border border-white/5 rounded-2xl p-5"
        >
          <p className="text-[#5C524A] text-xs uppercase tracking-widest font-mono mb-2">
            Who you must become
          </p>
          <p className="text-[#C4BBB5] leading-relaxed">
            {goal.required_identity}
          </p>
        </motion.div>
      )}

      {/* ── Objectives ───────────────────────────────── */}
      {objectives?.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
        >
          <p className="text-[#5C524A] text-xs uppercase tracking-widest font-mono mb-3">
            Objectives
          </p>
          <div className="space-y-3">
            {objectives.map((obj: any, i: number) => (
              <div
                key={obj.id}
                className={`flex gap-4 rounded-xl p-4 border ${
                  obj.status === 'completed'
                    ? 'bg-[#0F1A0F] border-[#22C55E]/15'
                    : obj.status === 'in_progress'
                    ? 'bg-[#141210] border-[#F59E0B]/15'
                    : 'bg-[#0A0908] border-white/5 opacity-60'
                }`}
              >
                <div className={`w-7 h-7 rounded-full flex items-center justify-center shrink-0 mt-0.5 text-xs font-mono ${
                  obj.status === 'completed' ? 'bg-[#22C55E]/20 text-[#22C55E]' :
                  obj.status === 'in_progress' ? 'bg-[#F59E0B]/20 text-[#F59E0B]' :
                  'bg-[#1E1B18] text-[#3D3630]'
                }`}>
                  {obj.status === 'completed' ? '✓' : i + 1}
                </div>
                <div className="flex-1">
                  <div className="flex items-center justify-between mb-1">
                    <p className={`font-medium text-sm ${
                      obj.status === 'completed' ? 'text-[#4ADE80]' :
                      obj.status === 'in_progress' ? 'text-[#E8E2DC]' : 'text-[#5C524A]'
                    }`}>
                      {obj.title}
                    </p>
                    <span className="text-[#3D3630] text-xs font-mono">{obj.estimated_weeks}w</span>
                  </div>
                  <p className="text-[#5C524A] text-xs leading-relaxed">{obj.description}</p>
                  {obj.status === 'in_progress' && obj.progress > 0 && (
                    <div className="mt-2 h-1 bg-[#1E1B18] rounded-full overflow-hidden">
                      <div
                        className="h-full bg-[#F59E0B]/50 rounded-full"
                        style={{ width: `${obj.progress}%` }}
                      />
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </motion.div>
      )}

      {/* ── Identity traits ──────────────────────────── */}
      {identity_traits?.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
        >
          <p className="text-[#5C524A] text-xs uppercase tracking-widest font-mono mb-3">
            Identity traits
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {identity_traits.map((trait: any, i: number) => (
              <motion.div
                key={trait.id}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.15 + i * 0.06 }}
                className="bg-[#141210] border border-white/5 rounded-xl p-4"
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[#E8E2DC] text-sm font-medium capitalize">{trait.name}</span>
                  <span className={`text-xs font-mono px-2 py-0.5 rounded-full ${
                    trait.trend === 'growing' ? 'bg-green-950/30 text-[#4ADE80]' :
                    trait.trend === 'declining' ? 'bg-red-950/30 text-[#F87171]' :
                    'bg-[#1E1B18] text-[#5C524A]'
                  }`}>
                    {trait.trend === 'growing' ? '↑' : trait.trend === 'declining' ? '↓' : '→'}
                    {trait.progress_pct.toFixed(0)}%
                  </span>
                </div>
                <div className="h-1.5 bg-[#1E1B18] rounded-full overflow-hidden mb-2">
                  <motion.div
                    className="h-full bg-[#F59E0B] rounded-full"
                    initial={{ width: 0 }}
                    animate={{ width: `${trait.progress_pct}%` }}
                    transition={{ duration: 0.8, delay: 0.2 + i * 0.06 }}
                  />
                </div>
                <div className="flex justify-between items-center">
                  <p className="text-[#3D3630] text-xs">{trait.category}</p>
                  <p className="text-[#3D3630] text-xs font-mono">
                    {trait.current_score.toFixed(1)} → {trait.target_score.toFixed(1)}
                  </p>
                </div>
                {trait.description && (
                  <p className="text-[#5C524A] text-xs mt-2 leading-relaxed">{trait.description}</p>
                )}
              </motion.div>
            ))}
          </div>
        </motion.div>
      )}
    </div>
  )
}

function GoalSkeleton() {
  return (
    <div className="p-6 md:p-8 max-w-3xl mx-auto space-y-5 animate-pulse">
      <div className="h-8 bg-[#141210] rounded-xl w-32" />
      <div className="h-40 bg-[#141210] rounded-2xl" />
      <div className="h-24 bg-[#141210] rounded-2xl" />
      <div className="grid grid-cols-2 gap-3">
        {[...Array(4)].map((_, i) => <div key={i} className="h-28 bg-[#141210] rounded-xl" />)}
      </div>
    </div>
  )
}
