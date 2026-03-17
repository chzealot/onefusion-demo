import { useEffect } from 'react'
import { Subtitle } from './components/Subtitle'
import { useCurrentFrame, isRendering } from './hooks/useFrame'
import type { SceneConfig } from './types'

// Scene config is injected by the build pipeline into window.__SCENE_CONFIG__
// Scene ID tells which scene component to load
declare global {
  interface Window {
    __SCENE_CONFIG__: SceneConfig
    __SCENE_ID__: string
    __SCENE_READY__: boolean
  }
}

// Default config for development
const defaultConfig: SceneConfig = {
  scene: 1,
  name: 'Preview Scene',
  annotation: '',
  description: 'This is a preview scene. Config will be injected at runtime.',
  subtitles: [],
  total_frames: 150,
  fps: 30,
  width: 1920,
  height: 1080,
}

// Dynamic scene component loader
// Each scene exports a SceneContent component
const sceneModules = import.meta.glob('./scenes/*/index.tsx', { eager: true }) as Record<string, { SceneContent: React.FC<{ config: SceneConfig }> }>

function getSceneComponent(sceneId: string): React.FC<{ config: SceneConfig }> | null {
  const key = `./scenes/${sceneId}/index.tsx`
  const mod = sceneModules[key]
  return mod?.SceneContent || null
}

export function App() {
  const config = window.__SCENE_CONFIG__ || defaultConfig
  const sceneId = window.__SCENE_ID__ || 'Scene01'
  const frame = useCurrentFrame()

  const SceneContent = getSceneComponent(sceneId)

  // Signal readiness for Playwright render mode
  useEffect(() => {
    if (isRendering()) {
      requestAnimationFrame(() => {
        window.__SCENE_READY__ = true
      })
    }
  }, [frame])

  return (
    <div
      style={{
        width: `${config.width}px`,
        height: `${config.height}px`,
        position: 'relative',
        overflow: 'hidden',
        backgroundColor: '#000',
      }}
    >
      {/* Main content area (middle 70%) */}
      <div
        style={{
          position: 'absolute',
          top: `${config.height * 0.15}px`,
          left: 0,
          right: 0,
          height: `${config.height * 0.7}px`,
          overflow: 'hidden',
        }}
      >
        {SceneContent ? (
          <SceneContent config={config} />
        ) : (
          <div style={{ color: '#fff', textAlign: 'center', paddingTop: '20%' }}>
            Scene not found: {sceneId}
          </div>
        )}
      </div>

      {/* Subtitle area (bottom 15%) */}
      <Subtitle subtitles={config.subtitles} height={config.height} />

      {/* Preview mode: show frame counter */}
      {!isRendering() && (
        <div
          style={{
            position: 'absolute',
            top: 8,
            right: 12,
            color: 'rgba(255,255,255,0.4)',
            fontSize: '12px',
            fontFamily: 'monospace',
          }}
        >
          frame: {frame} / {config.total_frames}
        </div>
      )}
    </div>
  )
}
