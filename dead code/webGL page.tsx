'use client'

import { useEffect, useState } from 'react'
import { Singularity } from '@/components/landing/genesis/Singularity'
import { ContentOverlay } from '@/components/landing/shared/ContentOverlay'
import { StaticLanding } from '@/components/landing/fallback/StaticLanding'
import { useWebGLSupport } from '@/hooks/useWebGLSupport'
import { useReducedMotion } from '@/hooks/useReducedMotion'

export default function LandingPage() {
  const [mounted, setMounted] = useState(false)
  const webgl = useWebGLSupport()
  const reducedMotion = useReducedMotion()
  
  useEffect(() => {
    setMounted(true)
  }, [])
  
  if (!mounted) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ background: '#0A0908' }}>
        <div 
          className="w-32 h-32 rounded-full animate-pulse"
          style={{ 
            background: 'radial-gradient(circle, rgba(245,158,11,0.4) 0%, rgba(217,119,6,0.2) 50%, transparent 70%)',
            filter: 'blur(8px)'
          }} 
        />
      </div>
    )
  }
  
  const showStatic = !webgl.supported || webgl.version !== 'webgl2' || reducedMotion
  
  if (showStatic) {
    return <StaticLanding />
  }
  
  return (
    <main className="relative">
      <Singularity />
      <ContentOverlay />
      <div className="h-[500vh]" />
    </main>
  )
}