import { useCurrentFrame } from '../hooks/useFrame'
import { interpolate } from '../utils/animation'
import type { SubtitleSegment } from '../types'

interface SubtitleProps {
  subtitles: SubtitleSegment[]
  height: number
}

/**
 * Subtitle display component.
 * Shows the current subtitle based on frame number.
 * Positioned at the bottom 15% of the video.
 */
export function Subtitle({ subtitles, height }: SubtitleProps) {
  const frame = useCurrentFrame()

  // Find current subtitle
  const current = subtitles.find(
    (s) => frame >= s.start_frame && frame < s.end_frame
  )

  if (!current) return null

  // Fade in/out
  const fadeInEnd = current.start_frame + 5
  const fadeOutStart = current.end_frame - 5
  const opacity = Math.min(
    interpolate(frame, [current.start_frame, fadeInEnd], [0, 1]),
    interpolate(frame, [fadeOutStart, current.end_frame], [1, 0])
  )

  const fontSize = Math.round(48 * (height / 1080))

  return (
    <div
      style={{
        position: 'absolute',
        bottom: 0,
        left: 0,
        right: 0,
        height: `${height * 0.15}px`,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 100,
      }}
    >
      <div
        style={{
          opacity,
          fontSize: `${fontSize}px`,
          fontWeight: 600,
          color: '#ffffff',
          textShadow: '0 2px 8px rgba(0,0,0,0.8), 0 0 4px rgba(0,0,0,0.5)',
          textAlign: 'center',
          padding: '0 5%',
          lineHeight: 1.4,
          maxWidth: '90%',
        }}
      >
        {current.text}
      </div>
    </div>
  )
}
