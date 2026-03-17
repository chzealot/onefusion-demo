import { useState, useEffect, useRef } from 'react'

const params = new URLSearchParams(window.location.search)
const isRenderMode = params.get('mode') === 'render'
const targetFrame = isRenderMode ? parseInt(params.get('frame') || '0', 10) : null
const configFps = parseInt(params.get('fps') || '30', 10)

/**
 * Hook that returns the current frame number.
 *
 * In render mode (?mode=render&frame=N): returns the target frame (static).
 * In preview mode (default): increments based on real-time at the configured FPS.
 */
export function useCurrentFrame(): number {
  if (isRenderMode && targetFrame !== null) {
    return targetFrame
  }

  const [frame, setFrame] = useState(0)
  const startTimeRef = useRef(performance.now())

  useEffect(() => {
    let id: number
    const tick = () => {
      const elapsed = performance.now() - startTimeRef.current
      setFrame(Math.floor((elapsed / 1000) * configFps))
      id = requestAnimationFrame(tick)
    }
    id = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(id)
  }, [])

  return frame
}

/**
 * Returns true when in headless render mode.
 */
export function isRendering(): boolean {
  return isRenderMode
}

/**
 * Get the configured FPS.
 */
export function getFps(): number {
  return configFps
}
