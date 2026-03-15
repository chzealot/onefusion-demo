export interface SubtitleSegment {
  file: string
  text: string
  rate: string
  pitch: string
  duration_ms: number
  start_frame: number
  end_frame: number
}

export interface SceneConfig {
  scene: number
  name: string
  annotation: string
  description: string
  subtitles: SubtitleSegment[]
  total_frames: number
  fps: number
  width: number
  height: number
}
