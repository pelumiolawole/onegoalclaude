'use client'

import { useRef, useEffect, useState, Suspense, lazy } from 'react'
import { useScrollProgress } from '@/hooks/useScrollProgress'
import { useReducedMotion } from '@/hooks/useReducedMotion'

// Lazy load the heavy Three.js component
const ParticleCanvas = lazy(() => import('./ParticleCanvas'))

export function Singularity() {
  const containerRef = useRef<HTMLDivElement>(null)
  const [mousePosition, setMousePosition] = useState({ x: 0, y: 0 })
  const { progress } = useScrollProgress()
  const reducedMotion = useReducedMotion()
  const [isMobile, setIsMobile] = useState(false)

  useEffect(() => {
    setIsMobile(window.innerWidth < 768)
    const handleResize = () => setIsMobile(window.innerWidth < 768)
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [])

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!containerRef.current) return
      const rect = containerRef.current.getBoundingClientRect()
      setMousePosition({
        x: e.clientX - rect.left - rect.width / 2,
        y: -(e.clientY - rect.top - rect.height / 2),
      })
    }

    window.addEventListener('mousemove', handleMouseMove)
    return () => window.removeEventListener('mousemove', handleMouseMove)
  }, [])

  if (isMobile || reducedMotion) {
    return (
      <div
        ref={containerRef}
        className="fixed inset-0 z-0"
        style={{
          pointerEvents: 'none',
          background: 'radial-gradient(circle at center, #1a150f 0%, #0a0908 100%)',
        }}
      />
    )
  }

  return (
    <div
      ref={containerRef}
      className="fixed inset-0 z-0"
      style={{ pointerEvents: 'none' }}
    >
      <Suspense fallback={
        <div style={{
          background: 'radial-gradient(circle at center, #1a150f 0%, #0a0908 100%)',
          width: '100%',
          height: '100%'
        }} />
      }>
        <ParticleCanvas 
          scrollProgress={progress} 
          mousePosition={mousePosition}
        />
      </Suspense>
    </div>
  )
}