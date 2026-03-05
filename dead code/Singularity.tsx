'use client'

import { useRef, useEffect, useState, Suspense, lazy } from 'react'
import { useScrollProgress } from '@/hooks/useScrollProgress'
import { useReducedMotion } from '@/hooks/useReducedMotion'
import { PARTICLES } from '@/lib/landing/constants'

// Lazy load the Three.js component
const ParticleCanvas = lazy(() => import('./ParticleCanvas'))

// WebGL detection helper
function isWebGLAvailable(): boolean {
  try {
    const canvas = document.createElement('canvas')
    const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl')
    return !!gl
  } catch (e) {
    return false
  }
}

// Check if Safari (known problematic)
function isSafari(): boolean {
  if (typeof window === 'undefined') return false
  const ua = window.navigator.userAgent.toLowerCase()
  return ua.includes('safari') && !ua.includes('chrome') && !ua.includes('chromium')
}

// Check if iOS
function isIOS(): boolean {
  if (typeof window === 'undefined') return false
  return /iPad|iPhone|iPod/.test(window.navigator.userAgent)
}

export function Singularity() {
  const containerRef = useRef<HTMLDivElement>(null)
  const [mousePosition, setMousePosition] = useState({ x: 0, y: 0 })
  const [isMounted, setIsMounted] = useState(false)
  const [webglFailed, setWebglFailed] = useState(false)
  const { progress } = useScrollProgress()
  const reducedMotion = useReducedMotion()

  const [isMobile, setIsMobile] = useState(false)

  useEffect(() => {
    setIsMounted(true)
    setIsMobile(window.innerWidth < 768)
    
    // Check WebGL availability
    if (!isWebGLAvailable() || isSafari() || isIOS()) {
      console.log('WebGL not available or Safari/iOS detected, using fallback')
      setWebglFailed(true)
    }

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

  // Show fallback for: SSR, mobile, reduced motion, WebGL failure, or Safari/iOS
  if (!isMounted || isMobile || reducedMotion || webglFailed || isSafari() || isIOS()) {
    return (
      <div
        ref={containerRef}
        className="fixed inset-0 z-0 overflow-hidden"
        style={{ 
          pointerEvents: 'none',
          background: 'radial-gradient(ellipse at center, #1a150f 0%, #0d0b08 40%, #0a0908 100%)'
        }}
      >
        {/* Animated stars CSS fallback */}
        {Array.from({ length: 100 }).map((_, i) => (
          <div
            key={i}
            className="absolute rounded-full bg-amber-400 animate-pulse"
            style={{
              left: `${Math.random() * 100}%`,
              top: `${Math.random() * 100}%`,
              width: `${Math.random() * 3 + 1}px`,
              height: `${Math.random() * 3 + 1}px`,
              animationDelay: `${Math.random() * 3}s`,
              animationDuration: `${Math.random() * 3 + 2}s`,
              opacity: 0.6,
            }}
          />
        ))}
        
        {/* Central glow */}
        <div 
          className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 rounded-full"
          style={{
            width: '600px',
            height: '600px',
            background: 'radial-gradient(circle, rgba(201, 154, 46, 0.15) 0%, transparent 70%)',
          }}
        />
      </div>
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
          background: 'radial-gradient(ellipse at center, #1a150f 0%, #0a0908 100%)',
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