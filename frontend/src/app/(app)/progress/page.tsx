'use client'

import useSWR from 'swr'
import { motion } from 'framer-motion'
import {
  LineChart, Line, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid
} from 'recharts'
import { api } from '@/lib/api'

export default function ProgressPage() {
  const { data: scores }   = useSWR('/progress/scores',          () => api.progress.getScores())
  const { data: timeline } = useSWR('/progress/timeline',        () => api.progress.getTimeline(30))
  const { data: traits }   = useSWR('/progress/traits/timeline', () => api.progress.getTraitsTimeline())
  const { data: streak }   = useSWR('/progress/streak',          () => api.progress.getStreak())
  const { data: patterns } = useSWR('/progress/patterns',        () => api.progress.getPatterns())

  const hasTimeline     = timeline?.timeline?.length > 0
  const hasTraits       = traits?.traits?.length > 0
  const hasStarted      = scores && scores.transformation_score > 0
  const hasStreakData    = streak && Object.keys(streak.calendar || {}).length > 0

  return (
    <div className="p-6 md:p-8 pb-24 md:pb-8 max-w-3xl mx-auto space-y-6">

      <motion.h1
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        className="font-display text-3xl text-[#F5F1ED]"
      >
        Your progress
      </motion.h1>

      {/* Score breakdown */}
      {scores ? (
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
                {hasStarted && (
                  <span className={`mb-1.5 text-sm font-mono px-2 py-0.5 rounded-lg ${gradeStyle(scores.grade)}`}>
                    {scores.grade}
                  </span>
                )}
              </div>
            </div>
            <div className={`text-right text-sm ${momentumColor(scores.momentum_state)}`}>
              <p className="font-medium">{scores.momentum_label}</p>
              <p className="text-xs opacity-70 mt-0.5">{scores.streak?.current}d streak</p>
            </div>
          </div>

          {hasStarted ? (
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
          ) : (
            <p className="text-[#3D3630] text-sm border-t border-white/5 pt-4">
              Complete your first task to start building your score.
            </p>
          )}
        </motion.div>
      ) : (
        <ScoreSkeleton />
      )}

      {/* Score timeline chart */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="bg-[#141210] border border-white/5 rounded-2xl p-5"
      >
        <p className="text-[#5C524A] text-xs uppercase tracking-widest font-mono mb-5">
          30-day trajectory
        </p>
        {hasTimeline ? (
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
        ) : (
          <p className="text-[#3D3630] text-sm">
            Your trajectory will appear here after your first completed task.
          </p>
        )}
      </motion.div>

      {/* Identity traits */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.15 }}
        className="bg-[#141210] border border-white/5 rounded-2xl p-5"
      >
        <p className="text-[#5C524A] text-xs uppercase tracking-widest font-mono mb-4">
          Identity traits
        </p>
        {hasTraits ? (
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
                    <TrendArrow trend={trait.trend} />
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
        ) : (
          <p className="text-[#3D3630] text-sm">
            Your identity traits will appear here as you complete tasks.
          </p>
        )}
      </motion.div>

      {/* Streak calendar */}
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
          {streak && (
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
          )}
        </div>

        {hasStreakData ? (
          <div className="grid grid-cols-[repeat(30,1fr)] gap-0.5">
            {Object.entries(streak.calendar || {}).slice(-30).map(([d, data]: any) => (
              <div
                key={d}
                title={d}
                className={`aspect-square rounded-sm ${
                  data.completed ? 'bg-[#F59E0B]' : 'bg-[#1E1B18]'
                }`}
              />
            ))}
          </div>
        ) : (
          <p className="text-[#3D3630] text-sm">
            Your activity calendar will fill in as you show up each day.
          </p>
        )}
      </motion.div>

      {/* Behavioural patterns */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.25 }}
        className="bg-[#141210] border border-white/5 rounded-2xl p-5"
      >
        <div className="flex items-center justify-between mb-4">
          <p className="text-[#5C524A] text-xs uppercase tracking-widest font-mono">
            What the system knows about you
          </p>
          {patterns && !patterns.locked && (
            <span className="text-[#008e97] text-xs font-mono px-2 py-0.5 border border-[#008e97]/30 rounded-full">
              Identity
            </span>
          )}
        </div>

        {!patterns ? (
          <PatternsSkeleton />
        ) : patterns.locked ? (
          <div className="text-center py-6">
            <div className="w-10 h-10 rounded-full bg-[#1E1B18] flex items-center justify-center mx-auto mb-3">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#3D3630" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
                <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
              </svg>
            </div>
            <p className="text-[#5C524A] text-sm mb-1">Available on The Identity plan</p>
            <p className="text-[#3D3630] text-xs mb-4">
              The system is already learning your patterns. Upgrade to see what it knows.
            </p>
            <a
              href="/settings/upgrade?plan=identity"
              className="inline-flex items-center gap-2 px-4 py-2 bg-[#008e97]/10 border border-[#008e97]/20 rounded-xl text-[#008e97] text-sm hover:bg-[#008e97]/20 transition-all"
            >
              Commit fully
            </a>
          </div>
        ) : patterns.patterns?.length === 0 && !patterns.snapshot ? (
          <p className="text-[#3D3630] text-sm">
            Patterns will emerge as you engage with the product over time.
          </p>
        ) : (
          <div className="space-y-5">

            {/* Behaviour summary from latest snapshot */}
            {patterns.snapshot?.behavior_summary && (
              <div className="bg-[#0A0908] rounded-xl p-4 border border-white/5">
                <p className="text-[#C4BBB5] text-sm leading-relaxed italic">
                  "{patterns.snapshot.behavior_summary}"
                </p>
                {patterns.snapshot.dominant_pattern && (
                  <p className="text-[#3D3630] text-xs font-mono mt-2">
                    Dominant pattern: {patterns.snapshot.dominant_pattern}
                  </p>
                )}
              </div>
            )}

            {/* How you work */}
            {patterns.snapshot && (
              <div>
                <p className="text-[#3D3630] text-xs uppercase tracking-widest font-mono mb-3">
                  How you work
                </p>
                <div className="grid grid-cols-2 gap-2">
                  {patterns.snapshot.most_active_day && (
                    <div className="bg-[#1E1B18] rounded-xl p-3">
                      <p className="text-[#3D3630] text-[10px] uppercase tracking-wider font-mono mb-1">Most active</p>
                      <p className="text-[#C4BBB5] text-sm capitalize">{patterns.snapshot.most_active_day}</p>
                    </div>
                  )}
                  {patterns.snapshot.morning_person_score !== undefined && (
                    <div className="bg-[#1E1B18] rounded-xl p-3">
                      <p className="text-[#3D3630] text-[10px] uppercase tracking-wider font-mono mb-1">Morning person</p>
                      <p className="text-[#C4BBB5] text-sm">
                        {patterns.snapshot.morning_person_score >= 0.6
                          ? 'Yes'
                          : patterns.snapshot.morning_person_score <= 0.4
                          ? 'No'
                          : 'Mixed'}
                      </p>
                    </div>
                  )}
                  {patterns.snapshot.breakthrough_episodes !== undefined && (
                    <div className="bg-[#1E1B18] rounded-xl p-3">
                      <p className="text-[#3D3630] text-[10px] uppercase tracking-wider font-mono mb-1">Breakthroughs</p>
                      <p className="text-[#4ADE80] text-sm font-mono">{patterns.snapshot.breakthrough_episodes}</p>
                    </div>
                  )}
                  {patterns.snapshot.resistance_episodes !== undefined && (
                    <div className="bg-[#1E1B18] rounded-xl p-3">
                      <p className="text-[#3D3630] text-[10px] uppercase tracking-wider font-mono mb-1">Resistance</p>
                      <p className="text-[#F87171] text-sm font-mono">{patterns.snapshot.resistance_episodes}</p>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Named patterns */}
            {patterns.patterns?.length > 0 && (
              <div>
                <p className="text-[#3D3630] text-xs uppercase tracking-widest font-mono mb-3">
                  Detected patterns
                </p>
                <div className="space-y-2">
                  {patterns.patterns.map((p: any, i: number) => (
                    <motion.div
                      key={i}
                      initial={{ opacity: 0, x: -6 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: 0.25 + i * 0.04 }}
                      className={`flex gap-3 rounded-xl p-3 border ${
                        p.type === 'breakthrough'
                          ? 'bg-green-950/10 border-green-900/20'
                          : p.type === 'resistance'
                          ? 'bg-red-950/10 border-red-900/20'
                          : 'bg-[#1E1B18] border-white/5'
                      }`}
                    >
                      <div className={`w-1.5 rounded-full shrink-0 mt-1 ${
                        p.type === 'breakthrough' ? 'bg-[#4ADE80]' :
                        p.type === 'resistance' ? 'bg-[#F87171]' : 'bg-[#5C524A]'
                      }`} style={{ minHeight: '16px' }} />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between gap-2 mb-0.5">
                          <p className={`text-sm font-medium capitalize truncate ${
                            p.type === 'breakthrough' ? 'text-[#4ADE80]' :
                            p.type === 'resistance' ? 'text-[#F87171]' : 'text-[#C4BBB5]'
                          }`}>
                            {p.name}
                          </p>
                          <span className="text-[#3D3630] text-[10px] font-mono shrink-0">
                            {Math.round(p.confidence * 100)}% confidence
                          </span>
                        </div>
                        <p className="text-[#5C524A] text-xs leading-relaxed">{p.description}</p>
                        <p className="text-[#3D3630] text-[10px] font-mono mt-1">
                          {p.evidence_count} {p.evidence_count === 1 ? 'instance' : 'instances'} · first seen {p.first_detected}
                        </p>
                      </div>
                    </motion.div>
                  ))}
                </div>
              </div>
            )}

          </div>
        )}
      </motion.div>

    </div>
  )
}

// ── Sub-components ────────────────────────────────────────────────────────────

function TrendArrow({ trend }: { trend: string }) {
  if (trend === 'growing') {
    return (
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#4ADE80" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
        <line x1="12" y1="19" x2="12" y2="5" />
        <polyline points="5 12 12 5 19 12" />
      </svg>
    )
  }
  if (trend === 'declining') {
    return (
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#F87171" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
        <line x1="12" y1="5" x2="12" y2="19" />
        <polyline points="19 12 12 19 5 12" />
      </svg>
    )
  }
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#5C524A" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <line x1="5" y1="12" x2="19" y2="12" />
    </svg>
  )
}

function ScoreSkeleton() {
  return (
    <div className="bg-[#141210] border border-white/5 rounded-2xl p-5 animate-pulse">
      <div className="h-4 w-32 bg-[#1E1B18] rounded mb-4" />
      <div className="h-12 w-24 bg-[#1E1B18] rounded mb-5" />
      <div className="grid grid-cols-4 gap-3">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="h-20 bg-[#1E1B18] rounded-xl" />
        ))}
      </div>
    </div>
  )
}

function PatternsSkeleton() {
  return (
    <div className="animate-pulse space-y-3">
      <div className="h-16 bg-[#1E1B18] rounded-xl" />
      <div className="grid grid-cols-2 gap-2">
        {[...Array(4)].map((_, i) => <div key={i} className="h-14 bg-[#1E1B18] rounded-xl" />)}
      </div>
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