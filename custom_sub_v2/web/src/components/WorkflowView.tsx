import { useState, useEffect, useCallback } from 'react'
import {
  getProgress,
  listScenes,
  stopSession,
  deleteSession,
  resumeSession,
  getVideoUrl,
  type SessionProgress,
  type SceneInfo,
} from '../api/client'
import { WorkflowGraph } from './WorkflowGraph'
import { LogPanel } from './LogPanel'
import { useTheme } from '../theme'

const STATUS_COLORS: Record<string, string> = {
  pending: '#f59e0b',
  generating_script: '#3b82f6',
  generating_tts: '#3b82f6',
  generating_animation: '#8b5cf6',
  rendering: '#a855f7',
  completed: '#22c55e',
  failed: '#ef4444',
  stopped: '#6b7280',
}

interface Props {
  projectId: string
  onDeleted: () => void
}

export function WorkflowView({ projectId, onDeleted }: Props) {
  const { colors } = useTheme()
  const [progress, setProgress] = useState<SessionProgress | null>(null)
  const [scenes, setScenes] = useState<SceneInfo[]>([])
  const [resumePrompt, setResumePrompt] = useState('')
  const [bottomTab, setBottomTab] = useState<'info' | 'logs' | 'video'>('info')

  const fetchData = useCallback(async () => {
    const p = await getProgress(projectId)
    setProgress(p)
    if (p.status !== 'pending') {
      const sc = await listScenes(projectId)
      setScenes(sc)
    }
  }, [projectId])

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 3000)
    return () => clearInterval(interval)
  }, [fetchData])

  if (!progress) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: colors.textMuted }}>
        Loading...
      </div>
    )
  }

  const isActive = ['pending', 'generating_script', 'generating_tts', 'generating_animation', 'rendering'].includes(
    progress.status,
  )
  const canResume = ['completed', 'failed', 'stopped'].includes(progress.status)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Top bar */}
      <div
        style={{
          padding: '10px 20px',
          borderBottom: `1px solid ${colors.border}`,
          background: colors.bgSidebar,
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexShrink: 0,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <code style={{ fontSize: 13, color: colors.textSecondary }}>{progress.project_id}</code>
          <span
            style={{
              fontSize: 11,
              padding: '2px 10px',
              borderRadius: 10,
              color: '#fff',
              background: STATUS_COLORS[progress.status] || '#555',
              fontWeight: 500,
            }}
          >
            {progress.status.replace(/_/g, ' ')}
          </span>
          {progress.error && (
            <span style={{ fontSize: 12, color: '#ef4444' }}>{progress.error}</span>
          )}
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          {isActive && (
            <button
              onClick={async () => {
                await stopSession(projectId)
                fetchData()
              }}
              style={btnStyle('#f59e0b')}
            >
              Stop
            </button>
          )}
          <button
            onClick={async () => {
              if (confirm('Delete this session?')) {
                await deleteSession(projectId)
                onDeleted()
              }
            }}
            style={btnStyle('#ef4444')}
          >
            Delete
          </button>
        </div>
      </div>

      {/* Workflow graph */}
      <div style={{ flex: 1, minHeight: 0, background: colors.flowBg }}>
        <WorkflowGraph progress={progress} scenes={scenes} />
      </div>

      {/* Bottom panel */}
      <div
        style={{
          borderTop: `1px solid ${colors.border}`,
          background: colors.bgPanel,
          flexShrink: 0,
        }}
      >
        {/* Tab bar */}
        <div style={{ display: 'flex', borderBottom: `1px solid ${colors.border}` }}>
          {(['info', 'logs', 'video'] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setBottomTab(tab)}
              style={{
                padding: '8px 20px',
                border: 'none',
                background: bottomTab === tab ? colors.bgHover : 'transparent',
                color: bottomTab === tab ? colors.text : colors.textMuted,
                cursor: 'pointer',
                fontSize: 12,
                fontWeight: 600,
                textTransform: 'capitalize',
                borderBottom: bottomTab === tab ? `2px solid ${colors.accent}` : '2px solid transparent',
              }}
            >
              {tab === 'info' ? 'Info' : tab === 'logs' ? 'Logs' : 'Video'}
            </button>
          ))}
        </div>

        {/* Tab content */}
        <div style={{ maxHeight: 240, overflow: 'auto', padding: '12px 20px' }}>
          {bottomTab === 'info' && (
            <div>
              <div style={{ fontSize: 12, color: colors.textSecondary, marginBottom: 8 }}>
                Agent: {progress.agent_id} | Created: {new Date(progress.created_at).toLocaleString()}
              </div>
              <div style={{ fontSize: 12, color: colors.textSecondary, lineHeight: 1.6, marginBottom: 12 }}>
                {progress.article_preview}...
              </div>

              {/* Steps summary */}
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
                {progress.steps.map((step) => {
                  const stepBg =
                    step.status === 'completed'
                      ? colors.nodeCompletedBg
                      : step.status === 'in_progress'
                        ? colors.nodeActiveBg
                        : step.status === 'failed'
                          ? colors.nodeFailedBg
                          : colors.bgCard
                  const stepBorder =
                    step.status === 'completed'
                      ? colors.nodeCompletedBorder
                      : step.status === 'in_progress'
                        ? colors.nodeActiveBorder
                        : step.status === 'failed'
                          ? colors.nodeFailedBorder
                          : colors.border
                  return (
                    <div
                      key={step.name}
                      style={{
                        fontSize: 11,
                        padding: '4px 10px',
                        borderRadius: 6,
                        background: stepBg,
                        border: `1px solid ${stepBorder}`,
                        color: colors.text,
                      }}
                    >
                      {step.name}: {step.message || step.status}
                    </div>
                  )
                })}
              </div>

              {/* Resume form */}
              {canResume && (
                <div style={{ display: 'flex', gap: 8 }}>
                  <input
                    value={resumePrompt}
                    onChange={(e) => setResumePrompt(e.target.value)}
                    placeholder="Enter modification instructions..."
                    style={{
                      flex: 1,
                      padding: '6px 10px',
                      borderRadius: 6,
                      border: `1px solid ${colors.border}`,
                      background: colors.bgInput,
                      color: colors.text,
                      fontSize: 13,
                    }}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && resumePrompt.trim()) {
                        resumeSession(projectId, resumePrompt.trim()).then(() => {
                          setResumePrompt('')
                          fetchData()
                        })
                      }
                    }}
                  />
                  <button
                    onClick={async () => {
                      if (resumePrompt.trim()) {
                        await resumeSession(projectId, resumePrompt.trim())
                        setResumePrompt('')
                        fetchData()
                      }
                    }}
                    style={btnStyle(colors.accent)}
                  >
                    Resume
                  </button>
                </div>
              )}
            </div>
          )}

          {bottomTab === 'logs' && <LogPanel projectId={projectId} />}

          {bottomTab === 'video' && (
            <div>
              {progress.status === 'completed' ? (
                <video
                  controls
                  style={{ width: '100%', maxHeight: 200, borderRadius: 8, background: '#000' }}
                  src={getVideoUrl(projectId)}
                />
              ) : (
                <div style={{ fontSize: 13, color: colors.textMuted, textAlign: 'center', padding: 20 }}>
                  Video will appear here when rendering completes
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function btnStyle(bg: string): React.CSSProperties {
  return {
    padding: '5px 14px',
    background: bg,
    color: '#fff',
    border: 'none',
    borderRadius: 6,
    cursor: 'pointer',
    fontSize: 12,
    fontWeight: 600,
  }
}
