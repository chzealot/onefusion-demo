import { memo } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import { useTheme } from '../theme'

export interface PipelineNodeData {
  label: string
  sublabel?: string
  status: 'pending' | 'in_progress' | 'completed' | 'failed'
  nodeType: 'input' | 'step' | 'scene' | 'merge' | 'output'
  [key: string]: unknown
}

const ICONS: Record<string, string> = {
  input: '\u{1F4C4}',
  step: '\u{2699}\u{FE0F}',
  scene: '\u{1F3AC}',
  merge: '\u{1F500}',
  output: '\u{1F4E6}',
}

const STEP_ICONS: Record<string, string> = {
  Script: '\u{270D}\u{FE0F}',
  TTS: '\u{1F50A}',
  Animate: '\u{1F3A8}',
  Render: '\u{1F3A5}',
  Package: '\u{1F4E6}',
}

function StatusDot({ status }: { status: string }) {
  const colors: Record<string, string> = {
    pending: '#888',
    in_progress: '#3b82f6',
    completed: '#22c55e',
    failed: '#ef4444',
  }
  const isActive = status === 'in_progress'

  return (
    <span
      style={{
        display: 'inline-block',
        width: 8,
        height: 8,
        borderRadius: '50%',
        background: colors[status] || '#888',
        animation: isActive ? 'pulse 1.5s ease-in-out infinite' : 'none',
        flexShrink: 0,
      }}
    />
  )
}

export const PipelineNode = memo(function PipelineNode({ data }: NodeProps) {
  const d = data as PipelineNodeData
  const { colors } = useTheme()
  const icon = STEP_ICONS[d.label] || ICONS[d.nodeType] || ''

  const statusStyles = {
    pending: { bg: colors.nodePendingBg, border: colors.nodePendingBorder, glow: 'none' },
    in_progress: { bg: colors.nodeActiveBg, border: colors.nodeActiveBorder, glow: '0 0 12px rgba(59,130,246,0.3)' },
    completed: { bg: colors.nodeCompletedBg, border: colors.nodeCompletedBorder, glow: '0 0 8px rgba(34,197,94,0.2)' },
    failed: { bg: colors.nodeFailedBg, border: colors.nodeFailedBorder, glow: '0 0 8px rgba(239,68,68,0.2)' },
  }

  const style = statusStyles[d.status] || statusStyles.pending

  return (
    <>
      <Handle type="target" position={Position.Left} style={{ background: colors.textMuted, border: 'none', width: 6, height: 6 }} />
      <div
        style={{
          background: style.bg,
          border: `1.5px solid ${style.border}`,
          borderRadius: 10,
          padding: '10px 16px',
          minWidth: 120,
          boxShadow: style.glow,
          transition: 'all 0.3s ease',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <StatusDot status={d.status} />
          <span style={{ fontSize: 13, fontWeight: 600, color: colors.text }}>
            {icon} {d.label}
          </span>
        </div>
        {d.sublabel && (
          <div style={{ fontSize: 10, color: colors.textSecondary, marginTop: 3, paddingLeft: 14 }}>
            {d.sublabel}
          </div>
        )}
      </div>
      <Handle type="source" position={Position.Right} style={{ background: colors.textMuted, border: 'none', width: 6, height: 6 }} />
    </>
  )
})
