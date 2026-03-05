'use client'

import { useRef, useMemo, useEffect } from 'react'
import { Canvas, useThree } from '@react-three/fiber'
import * as THREE from 'three'
import { PARTICLES, COLORS, CAMERA } from '@/lib/landing/constants'

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

function ParticleScene({ count, scrollProgress, mousePosition }: { 
  count: number
  scrollProgress: number
  mousePosition: { x: number; y: number }
}) {
  const { scene, camera, viewport } = useThree()
  const pointsRef = useRef<THREE.Points | null>(null)
  const materialRef = useRef<THREE.ShaderMaterial | null>(null)
  const rafRef = useRef<number>(0)

  useEffect(() => {
    // Create geometry
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

    const geometry = new THREE.BufferGeometry()
    geometry.setAttribute('offset', new THREE.BufferAttribute(offsets, 3))
    geometry.setAttribute('size', new THREE.BufferAttribute(sizes, 1))
    geometry.setAttribute('phase', new THREE.BufferAttribute(phases, 1))

    // Create material
    const material = new THREE.ShaderMaterial({
      vertexShader,
      fragmentShader,
      uniforms: {
        uTime: { value: 0 },
        uColor: { value: new THREE.Color(COLORS.gold.primary) },
        uBreathPhase: { value: 0 },
        uMouse: { value: new THREE.Vector2(0, 0) },
        uMouseInfluence: { value: PARTICLES.MOUSE_INFLUENCE },
        uScrollProgress: { value: 0 },
      },
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    })
    materialRef.current = material

    // Create points
    const points = new THREE.Points(geometry, material)
    pointsRef.current = points
    scene.add(points)

    // Animation loop
    const animate = () => {
      if (!material || !points) return
      
      material.uniforms.uTime.value += 0.016
      material.uniforms.uScrollProgress.value = scrollProgress
      material.uniforms.uBreathPhase.value = Math.sin(material.uniforms.uTime.value * 0.5) * 0.5 + 0.5

      const targetX = (mousePosition.x / viewport.width) * 2
      const targetY = (mousePosition.y / viewport.height) * 2
      material.uniforms.uMouse.value.x += (targetX - material.uniforms.uMouse.value.x) * 0.05
      material.uniforms.uMouse.value.y += (targetY - material.uniforms.uMouse.value.y) * 0.05

      points.rotation.y += 0.001
      points.rotation.x = scrollProgress * 0.3

      // Camera animation
      const targetZ = CAMERA.INITIAL_Z - scrollProgress * 2
      camera.position.z += (targetZ - camera.position.z) * 0.05
      camera.rotation.z = scrollProgress * 0.1

      rafRef.current = requestAnimationFrame(animate)
    }

    animate()

    // Cleanup
    return () => {
      cancelAnimationFrame(rafRef.current)
      scene.remove(points)
      geometry.dispose()
      material.dispose()
    }
  }, [scene, camera, viewport, count, scrollProgress, mousePosition])

  return null
}

export default function ParticleCanvas({ 
  scrollProgress, 
  mousePosition 
}: { 
  scrollProgress: number
  mousePosition: { x: number; y: number }
}) {
  return (
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
      <ParticleScene
        count={PARTICLES.COUNT}
        scrollProgress={scrollProgress}
        mousePosition={mousePosition}
      />
    </Canvas>
  )
}