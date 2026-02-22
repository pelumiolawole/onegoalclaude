'use client'

import useSWR from 'swr'
import { motion } from 'framer-motion'
import {
  LineChart, Line, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid
} from 'recharts'
import { api } from '@/lib/api'

export default function ProgressPage() {
  const { data: scores }   = useSWR('/progress/scores',   () => api.progress.getScores())
  const { data: timeline } = useSWR('/progress/timeline', () => api.progress.getTimeline(30))
  const { data: traits }   = useSWR('/progress/traits',   () => api.progress.getTraitsTimeline())
  const { data: streak }   = useSWR('/progress/streak',   () => api.progress.getStreak())

  return (
    <div className="p-6 md:p-8 max-w-3xl mx-auto space-y-6">

      <motion.h1
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        className="font-display text-3xl text-[#F5F1ED]"
      >
        Your progress
      </motion.h1>

      {/* ── Score breakdown ──────────────────────────── */}
      {scores && (
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.05 }}
          className="bg-[#141210] border border-white/5 rounded-2xl p-5"
        >
          <div className="flex items-center justify-between mb-5">
            <div>
              <p className="text-[#5C524A] text-xs uppercase tracking-widest font-mono mb-1">
                Transformation Score
              </p>
              <div className="flex items-end gap-3">
                <span className="font-display text-5xl text-[#F59E0B]">
                  {scores.transformation_score.toFixed(1)}
                </span>
                <span className="text-[#5C524A] text-sm mb-1.5">/ 100</span>
                <span className={`mb-1.5 text-sm font-mono px-2 py-0.5 rounded-lg ${gradeStyle(scores.grade)}`}>
                  {scores.grade}
                </span>
              </div>
            </div>
            <div className={`text-right text-sm ${momentumColor(scores.momentum_state)}`}>
              <p className="font-medium">{scores.momentum_label}</p>
              <p className="text-xs opacity-70 mt-0.5">{scores.streak?.current}d streak</p>
            </div>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {Object.entries(scores.breakdown || {}).map(([key, val]: any) => (
              <div key={key} className="bg-[#1E1B18] rounded-xl p-3">
                <p className="text-[#3D3630] text-[10px] uppercase tracking-wider font-mono mb-1">
                  {val.label}
                </p>
                <p className="text-[#C4BBB5] text-lg font-mono">{val.score.toFixed(0)}</p>
                <div className="flex items-center justify-between mt-1">
                  <span className={`text-xs font-mono px-1.5 py-0.5 rounded ${gradeStyle(val.grade)}`}>
                    {val.grade}
                  </span>
                  <span className="text-[#3D3630] text-[10px]">{val.weight}</span>
                </div>
              </div>
            ))}
          </div>
        </motion.div>
      )}

      {/* ── Score timeline chart ──────────────────────── */}
      {timeline?.timeline?.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="bg-[#141210] border border-white/5 rounded-2xl p-5"
        >
          <p className="text-[#5C524A] text-xs uppercase tracking-widest font-mono mb-5">
            30-day trajectory
          </p>
          <ResponsiveContainer width="100%" height={160}>
            <LineChart data={timeline.timeline}>
              <CartesianGrid stroke="#1E1B18" strokeDasharray="0" vertical={false} />
              <XAxis
                dataKey="date"
                tick={{ fill: '#3D3630', fontSize: 10, fontFamily: 'DM Mono' }}
                tickFormatter={d => d.slice(5)}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                domain={[0, 100]}
                tick={{ fill: '#3D3630', fontSize: 10, fontFamily: 'DM Mono' }}
                axisLine={false}
                tickLine={false}
                width={28}
              />
              <Tooltip
                contentStyle={{
                  background: '#1E1B18',
                  border: '1px solid rgba(255,255,255,0.07)',
                  borderRadius: '12px',
                  color: '#C4BBB5',
                  fontSize: '12px',
                }}
                cursor={{ stroke: '#F59E0B', strokeWidth: 1, strokeOpacity: 0.3 }}
              />
              <Line
                type="monotone"
                dataKey="transformation_score"
                stroke="#F59E0B"
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4, fill: '#F59E0B' }}
                name="Score"
              />
            </LineChart>
          </ResponsiveContainer>
        </motion.div>
      )}

      {/* ── Identity traits ──────────────────────────── */}
      {traits?.traits?.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
          className="bg-[#141210] border border-white/5 rounded-2xl p-5"
        >
          <p className="text-[#5C524A] text-xs uppercase tracking-widest font-mono mb-4">
            Identity traits
          </p>
          <div className="space-y-4">
            {traits.traits.map((trait: any, i: number) => (
              <motion.div
                key={trait.name}
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.15 + i * 0.05 }}
              >
                <div className="flex justify-between items-center mb-1.5">
                  <div className="flex items-center gap-2">
                    <span className="text-[#C4BBB5] text-sm capitalize">{trait.name}</span>
                    <span className="text-[#3D3630] text-xs">{trait.category}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={`text-xs ${
                      trait.trend === 'growing'   ? 'text-[#4ADE80]' :
                      trait.trend === 'declining' ? 'text-[#F87171]' : 'text-[#5C524A]'
                    }`}>
                      {trait.trend === 'growing' ? '↑' : trait.trend === 'declining' ? '↓' : '→'}
                    </span>
                    <span className="text-[#5C524A] text-xs font-mono">
                      {trait.current.toFixed(1)} / {trait.target.toFixed(1)}
                    </span>
                  </div>
                </div>
                <div className="h-2 bg-[#1E1B18] rounded-full overflow-hidden">
                  <motion.div
                    className="h-full rounded-full"
                    style={{
                      background: trait.trend === 'declining'
                        ? '#F87171'
                        : 'linear-gradient(90deg, #D97706, #F59E0B)',
                    }}
                    initial={{ width: 0 }}
                    animate={{ width: `${trait.progress_pct}%` }}
                    transition={{ duration: 1, delay: 0.2 + i * 0.05 }}
                  />
                </div>
              </motion.div>
            ))}
          </div>
        </motion.div>
      )}

      {/* ── Streak calendar ──────────────────────────── */}
      {streak && (
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="bg-[#141210] border border-white/5 rounded-2xl p-5"
        >
          <div className="flex items-center justify-between mb-5">
            <p className="text-[#5C524A] text-xs uppercase tracking-widest font-mono">
              30-day activity
            </p>
            <div className="flex items-center gap-4">
              <span className="text-[#C4BBB5] text-sm">
                <span className="font-mono text-[#F59E0B]">{streak.current_streak}</span>
                <span className="text-[#5C524A] ml-1 text-xs">current</span>
              </span>
              <span className="text-[#C4BBB5] text-sm">
                <span className="font-mono">{streak.longest_streak}</span>
                <span className="text-[#5C524A] ml-1 text-xs">best</span>
              </span>
            </div>
          </div>

          {/* 30-day grid */}
          <div className="grid grid-cols-[repeat(30,1fr)] gap-0.5">
            {Object.entries(streak.calendar || {}).slice(-30).map(([date, data]: any) => (
              <div
                key={date}
                title={date}
                className={`aspect-square rounded-sm ${
                  data.completed ? 'bg-[#F59E0B]' : 'bg-[#1E1B18]'
                }`}
              />
            ))}
          </div>
        </motion.div>
      )}
    </div>
  )
}

function gradeStyle(grade: string) {
  const map: Record<string, string> = {
    'A': 'bg-green-950/40 text-green-400',
    'B': 'bg-[#F59E0B]/15 text-[#F59E0B]',
    'C': 'bg-slate-900/40 text-slate-400',
    'D': 'bg-orange-950/40 text-orange-400',
    'F': 'bg-red-950/40 text-red-400',
  }
  return map[grade] || map['C']
}

function momentumColor(state: string) {
  const map: Record<string, string> = {
    rising:   'text-[#4ADE80]',
    holding:  'text-[#94A3B8]',
    declining:'text-[#F87171]',
    critical: 'text-[#F87171]',
  }
  return map[state] || 'text-[#94A3B8]'
}
