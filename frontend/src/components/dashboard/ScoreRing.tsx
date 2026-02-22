'use client'

import { motion } from 'framer-motion'

// ── Score Ring ─────────────────────────────────────────────────────────────

interface ScoreRingProps {
  label: string
  value: number     // 0–100
  primary?: boolean
}

export default function ScoreRing({ label, value, primary }: ScoreRingProps) {
  const r    = 28
  const circ = 2 * Math.PI * r
  const dash = (value / 100) * circ

  return (
    <div className={`bg-[#141210] border rounded-2xl p-4 flex flex-col items-center gap-2 ${
      primary ? 'border-[#F59E0B]/20' : 'border-white/5'
    }`}>
      <p className="text-[#3D3630] text-xs uppercase tracking-wider font-mono text-center">
        {label}
      </p>
      <div className="relative w-16 h-16">
        <svg className="w-full h-full -rotate-90" viewBox="0 0 72 72">
          {/* Track */}
          <circle
            cx="36" cy="36" r={r}
            fill="none"
            stroke="#1E1B18"
            strokeWidth="4"
          />
          {/* Progress */}
          <motion.circle
            cx="36" cy="36" r={r}
            fill="none"
            stroke={primary ? '#F59E0B' : '#5C524A'}
            strokeWidth="4"
            strokeLinecap="round"
            strokeDasharray={circ}
            initial={{ strokeDashoffset: circ }}
            animate={{ strokeDashoffset: circ - dash }}
            transition={{ duration: 1, delay: 0.2, ease: 'easeOut' }}
          />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <span className={`font-mono text-sm font-medium ${primary ? 'text-[#F59E0B]' : 'text-[#C4BBB5]'}`}>
            {value.toFixed(0)}
          </span>
        </div>
      </div>
    </div>
  )
}

// ── Week Grid ──────────────────────────────────────────────────────────────

interface DayData {
  date: string
  completed: boolean
  reflected: boolean
  score: number | null
}

export function WeekGrid({ days }: { days: DayData[] }) {
  const dayLabels = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']

  // Build a 7-day array ending today
  const today = new Date()
  const grid = Array.from({ length: 7 }, (_, i) => {
    const d = new Date(today)
    d.setDate(today.getDate() - (6 - i))
    const dateStr = d.toISOString().split('T')[0]
    const data = days.find(day => day.date === dateStr)
    return {
      label: dayLabels[d.getDay()],
      dateStr,
      isToday: i === 6,
      ...data,
    }
  })

  return (
    <div className="grid grid-cols-7 gap-1.5">
      {grid.map((day, i) => (
        <div key={day.dateStr} className="flex flex-col items-center gap-1.5">
          <span className="text-[#3D3630] text-[10px] font-mono">{day.label}</span>
          <motion.div
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: i * 0.04 }}
            className={`w-8 h-8 rounded-lg flex items-center justify-center relative ${
              day.completed
                ? 'bg-[#F59E0B]/20 border border-[#F59E0B]/30'
                : day.isToday
                ? 'bg-[#1E1B18] border border-white/10 border-dashed'
                : 'bg-[#0A0908] border border-white/5'
            }`}
          >
            {day.completed && (
              <span className="text-[#F59E0B] text-xs">✓</span>
            )}
            {day.reflected && day.completed && (
              <div className="absolute -top-1 -right-1 w-2 h-2 rounded-full bg-[#F59E0B]" />
            )}
            {day.isToday && !day.completed && (
              <div className="w-1.5 h-1.5 rounded-full bg-[#3D3630]" />
            )}
          </motion.div>
        </div>
      ))}
    </div>
  )
}
