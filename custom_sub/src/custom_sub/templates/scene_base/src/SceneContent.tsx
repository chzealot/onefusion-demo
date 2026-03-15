import { useCurrentFrame } from './hooks/useFrame'
import { interpolate, spring, Easing } from './utils/animation'
import type { SceneConfig } from './types'

interface Props {
  config: SceneConfig
}

/**
 * Main scene content component.
 * This file will be replaced/modified by the Claude Agent SDK
 * to create custom animations for each scene.
 */
export function SceneContent({ config }: Props) {
  const frame = useCurrentFrame()

  // Default placeholder animation
  const titleOpacity = interpolate(frame, [0, 20], [0, 1])
  const titleY = spring(frame, { stiffness: 80, damping: 15, from: -50, to: 0 })
  const descOpacity = interpolate(frame, [15, 35], [0, 1], { easing: Easing.easeOut })

  return (
    <div
      style={{
        width: '100%',
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '5%',
        background: 'linear-gradient(135deg, #0f0c29 0%, #302b63 50%, #24243e 100%)',
      }}
    >
      <h1
        style={{
          fontSize: '48px',
          fontWeight: 800,
          color: '#fff',
          opacity: titleOpacity,
          transform: `translateY(${titleY}px)`,
          textAlign: 'center',
          marginBottom: '24px',
        }}
      >
        {config.name}
      </h1>
      <p
        style={{
          fontSize: '24px',
          color: 'rgba(255,255,255,0.8)',
          opacity: descOpacity,
          textAlign: 'center',
          maxWidth: '80%',
          lineHeight: 1.6,
        }}
      >
        {config.description}
      </p>
    </div>
  )
}
