'use client'

import { useRef, useMemo, useEffect, useState } from 'react'
import { Canvas, useFrame, useThree, extend } from '@react-three/fiber'
import * as THREE from 'three'
import { useScrollProgress } from '@/hooks/useScrollProgress'
import { useReducedMotion } from '@/hooks/useReducedMotion'
import { PARTICLES, COLORS, CAMERA } from '@/lib/landing/constants'

// Import Three.js JSX types
import type { ThreeElements } from '@react-three/fiber'

// Extend Three.js types for JSX
declare module '@react-three/fiber' {
  interface ThreeElements {
    points: ThreeElements['points']
    bufferGeometry: ThreeElements['bufferGeometry']
    bufferAttribute: ThreeElements['bufferAttribute']
    shaderMaterial: ThreeElements['shaderMaterial']
  }
}

const vertexShader = `
  uniform float uTime;
  uniform float uBreathPhase;
  uniform vec2 uMouse;
  uniform float uMouseInfluence;
  uniform float uScrollProgress;
  
  attribute float size;
  attribute float phase;
  attribute vec3 offset;
  
  varying float vAlpha;
  varying float vSize;
  
  const float PI = 3.14159265359;
  const float BREATH_SPEED = 1.5;
  const float BREATH_AMP = 0.08;
  
  void main() {
    float breath = sin(uTime * BREATH_SPEED + phase * PI * 2.0) * BREATH_AMP;
    breath *= (1.0 + uBreathPhase * 0.5);
    
    vec3 pos = offset * (1.0 + breath);
    
    float dist = distance(pos.xy, uMouse * 2.0);
    float mouseEffect = smoothstep(2.0, 0.0, dist) * uMouseInfluence;
    pos.xy += uMouse * mouseEffect;
    
    float flatten = uScrollProgress * 0.3;
    pos.y *= (1.0 - flatten * abs(pos.y));
    
    vec4 mvPosition = modelViewMatrix * vec4(pos, 1.0);
    
    float attenuation = 300.0 / -mvPosition.z;
    gl_PointSize = size * attenuation * (1.0 + breath * 2.0);
    
    gl_Position = projectionMatrix * mvPosition;
    
    vAlpha = 0.6 + breath * 2.0;
    vAlpha *= (1.0 - uScrollProgress * 0.3);
    vSize = size;
  }
`

const fragmentShader = `
  uniform vec3 uColor;
  uniform float uTime;
  
  varying float vAlpha;
  varying float vSize;
  
  void main() {
    vec2 center = gl_PointCoord - vec2(0.5);
    float dist = length(center);
    
    float alpha = 1.0 - smoothstep(0.3, 0.5, dist);
    alpha *= vAlpha;
    
    float core = 1.0 - smoothstep(0.0, 0.2, dist);
    vec3 color = mix(uColor, vec3(1.0, 0.9, 0.7), core * 0.5);
    
    float shimmer = sin(uTime * 3.0 + vSize * 10.0) * 0.1 + 0.9;
    color *= shimmer;
    
    gl_FragColor = vec4(color, alpha);
    
    if (alpha < 0.01) discard;
  }
`

interface ParticleSystemProps {
  count: number
  scrollProgress: number
  mousePosition: { x: number; y: number }
}

function ParticleSystem({ count, scrollProgress, mousePosition }: ParticleSystemProps) {
  const meshRef = useRef<THREE.Points>(null)
  const { viewport } = useThree()
  const reducedMotion = useReducedMotion()

  const { offsets, sizes, phases } = useMemo(() => {
    const offsets = new Float32Array(count * 3)
    const sizes = new Float32Array(count)
    const phases = new Float32Array(count)

    const goldenRatio = (1 + Math.sqrt(5)) / 2

    for (let i = 0; i < count; i++) {
      const y = 1 - (i / (count - 1)) * 2
      const radius = Math.sqrt(1 - y * y)
      const theta = goldenRatio * i * Math.PI * 2

      const x = Math.cos(theta) * radius
      const z = Math.sin(theta) * radius

      const randomOffset = 0.1
      offsets[i * 3] = x * (1 + (Math.random() - 0.5) * randomOffset)
      offsets[i * 3 + 1] = y * (1 + (Math.random() - 0.5) * randomOffset)
      offsets[i * 3 + 2] = z * (1 + (Math.random() - 0.5) * randomOffset)

      sizes[i] = Math.random() * 3 + 1
      phases[i] = Math.random()
    }

    return { offsets, sizes, phases }
  }, [count])

  const uniforms = useMemo(() => ({
    uTime: { value: 0 },
    uColor: { value: new THREE.Color(COLORS.gold.primary) },
    uBreathPhase: { value: 0 },
    uMouse: { value: new THREE.Vector2(0, 0) },
    uMouseInfluence: { value: PARTICLES.MOUSE_INFLUENCE },
    uScrollProgress: { value: 0 },
  }), [])

  useFrame((state) => {
    if (!meshRef.current) return

    const material = meshRef.current.material as THREE.ShaderMaterial

    const timeScale = reducedMotion ? 0.3 : 1.0
    material.uniforms.uTime.value = state.clock.elapsedTime * timeScale

    material.uniforms.uScrollProgress.value = scrollProgress
    material.uniforms.uBreathPhase.value = Math.sin(state.clock.elapsedTime * 0.5) * 0.5 + 0.5

    const targetX = (mousePosition.x / viewport.width) * 2
    const targetY = (mousePosition.y / viewport.height) * 2
    material.uniforms.uMouse.value.x += (targetX - material.uniforms.uMouse.value.x) * 0.05
    material.uniforms.uMouse.value.y += (targetY - material.uniforms.uMouse.value.y) * 0.05

    meshRef.current.rotation.y += 0.001 * timeScale
    meshRef.current.rotation.x = scrollProgress * 0.3
  })

  return (
    <points ref={meshRef}>
      <bufferGeometry>
        <bufferAttribute
          attach="attributes-offset"
          count={offsets.length / 3}
          array={offsets}
          itemSize={3}
        />
        <bufferAttribute
          attach="attributes-size"
          count={sizes.length}
          array={sizes}
          itemSize={1}
        />
        <bufferAttribute
          attach="attributes-phase"
          count={phases.length}
          array={phases}
          itemSize={1}
        />
      </bufferGeometry>
      <shaderMaterial
        vertexShader={vertexShader}
        fragmentShader={fragmentShader}
        uniforms={uniforms}
        transparent
        depthWrite={false}
        blending={THREE.AdditiveBlending}
      />
    </points>
  )
}

function CameraController({ scrollProgress }: { scrollProgress: number }) {
  const { camera } = useThree()

  useFrame(() => {
    const targetZ = CAMERA.INITIAL_Z - scrollProgress * 2
    camera.position.z += (targetZ - camera.position.z) * 0.05
    camera.rotation.z = scrollProgress * 0.1
  })

  return null
}

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

  const particleCount = isMobile || reducedMotion
    ? PARTICLES.COUNT_MOBILE
    : PARTICLES.COUNT

  return (
    <div
      ref={containerRef}
      className="fixed inset-0 z-0"
      style={{ pointerEvents: 'none' }}
    >
      <Canvas
        camera={{ position: [0, 0, CAMERA.INITIAL_Z], fov: CAMERA.FOV }}
        dpr={[1, 2]}
        gl={{
          antialias: false,
          alpha: true,
          powerPreference: 'high-performance',
        }}
        style={{ background: 'transparent' }}
      >
        <CameraController scrollProgress={progress} />
        <ParticleSystem
          count={particleCount}
          scrollProgress={progress}
          mousePosition={mousePosition}
        />
      </Canvas>
    </div>
  )
}