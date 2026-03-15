/**
 * Frame-based animation utilities.
 * All animations should use these functions (NOT CSS transitions or GSAP timelines)
 * to ensure frame-perfect rendering in both preview and render modes.
 */

type ExtrapolateType = 'clamp' | 'extend'

interface InterpolateOptions {
  extrapolateLeft?: ExtrapolateType
  extrapolateRight?: ExtrapolateType
  easing?: (t: number) => number
}

/**
 * Interpolate a value based on the current frame.
 *
 * @example
 * // Fade in from frame 0 to 30
 * const opacity = interpolate(frame, [0, 30], [0, 1])
 *
 * // Move from left to center between frames 10-40
 * const x = interpolate(frame, [10, 40], [-100, 0])
 */
export function interpolate(
  frame: number,
  inputRange: number[],
  outputRange: number[],
  options?: InterpolateOptions
): number {
  const {
    extrapolateLeft = 'clamp',
    extrapolateRight = 'clamp',
    easing,
  } = options || {}

  if (inputRange.length !== outputRange.length || inputRange.length < 2) {
    throw new Error('inputRange and outputRange must have equal length >= 2')
  }

  // Handle out-of-range: left
  if (frame <= inputRange[0]) {
    if (extrapolateLeft === 'clamp') return outputRange[0]
    const slope =
      (outputRange[1] - outputRange[0]) / (inputRange[1] - inputRange[0])
    return outputRange[0] + slope * (frame - inputRange[0])
  }

  // Handle out-of-range: right
  const last = inputRange.length - 1
  if (frame >= inputRange[last]) {
    if (extrapolateRight === 'clamp') return outputRange[last]
    const slope =
      (outputRange[last] - outputRange[last - 1]) /
      (inputRange[last] - inputRange[last - 1])
    return outputRange[last] + slope * (frame - inputRange[last])
  }

  // Find segment
  for (let i = 0; i < inputRange.length - 1; i++) {
    if (frame >= inputRange[i] && frame <= inputRange[i + 1]) {
      let t =
        (frame - inputRange[i]) / (inputRange[i + 1] - inputRange[i])
      if (easing) t = easing(t)
      return outputRange[i] + t * (outputRange[i + 1] - outputRange[i])
    }
  }

  return outputRange[last]
}

/**
 * Spring animation based on frame number.
 * Returns a value from 0 to 1 (or custom from/to).
 */
export function spring(
  frame: number,
  config?: {
    fps?: number
    damping?: number
    mass?: number
    stiffness?: number
    from?: number
    to?: number
  }
): number {
  const {
    fps = 30,
    damping = 10,
    mass = 1,
    stiffness = 100,
    from = 0,
    to = 1,
  } = config || {}

  const t = frame / fps
  const omega = Math.sqrt(stiffness / mass)
  const zeta = damping / (2 * Math.sqrt(stiffness * mass))

  let progress: number
  if (zeta < 1) {
    // Underdamped
    const omegaD = omega * Math.sqrt(1 - zeta * zeta)
    progress =
      1 -
      Math.exp(-zeta * omega * t) *
        (Math.cos(omegaD * t) +
          (zeta * omega / omegaD) * Math.sin(omegaD * t))
  } else {
    // Critically/overdamped
    progress = 1 - Math.exp(-omega * t) * (1 + omega * t)
  }

  progress = Math.min(1, Math.max(0, progress))
  return from + (to - from) * progress
}

// --- Common easing functions ---

export const Easing = {
  linear: (t: number) => t,
  easeIn: (t: number) => t * t,
  easeOut: (t: number) => t * (2 - t),
  easeInOut: (t: number) => (t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t),
  easeInCubic: (t: number) => t * t * t,
  easeOutCubic: (t: number) => 1 - Math.pow(1 - t, 3),
  easeInOutCubic: (t: number) =>
    t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2,
  bounce: (t: number) => {
    const n1 = 7.5625
    const d1 = 2.75
    if (t < 1 / d1) return n1 * t * t
    if (t < 2 / d1) return n1 * (t -= 1.5 / d1) * t + 0.75
    if (t < 2.5 / d1) return n1 * (t -= 2.25 / d1) * t + 0.9375
    return n1 * (t -= 2.625 / d1) * t + 0.984375
  },
}
