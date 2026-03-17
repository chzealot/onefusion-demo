import type { SessionItem } from '../api/client'
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
  sessions: SessionItem[]
  selectedId: string | null
  onSelect: (id: string) => void
}

export function SessionList({ sessions, selectedId, onSelect }: Props) {
  const { colors } = useTheme()

  if (sessions.length === 0) {
    return (
      <div style={{ padding: '24px', textAlign: 'center', color: colors.textMuted, fontSize: '13px' }}>
        No sessions yet
      </div>
    )
  }

  return (
    <div style={{ overflow: 'auto', flex: 1 }}>
      {sessions.map((s) => (
        <div
          key={s.project_id}
          onClick={() => onSelect(s.project_id)}
          style={{
            padding: '10px 16px',
            borderBottom: `1px solid ${colors.borderLight}`,
            cursor: 'pointer',
            background: selectedId === s.project_id ? colors.bgHover : 'transparent',
            transition: 'background 0.15s',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
            <code style={{ fontSize: '11px', color: colors.textSecondary }}>{s.project_id}</code>
            <span
              style={{
                fontSize: '10px',
                padding: '1px 7px',
                borderRadius: '8px',
                color: '#fff',
                background: STATUS_COLORS[s.status] || '#555',
                fontWeight: 500,
              }}
            >
              {s.status.replace(/_/g, ' ')}
            </span>
          </div>
          <div
            style={{
              fontSize: '12px',
              color: colors.text,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {s.article_preview || '(empty)'}
          </div>
          <div style={{ fontSize: '10px', color: colors.textMuted, marginTop: '3px' }}>
            {new Date(s.created_at).toLocaleString()}
          </div>
        </div>
      ))}
    </div>
  )
}
