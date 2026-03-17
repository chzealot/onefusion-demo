import { useState, useEffect, useCallback } from 'react'
import { SessionList } from './components/SessionList'
import { WorkflowView } from './components/WorkflowView'
import { SubmitForm } from './components/SubmitForm'
import { ThemeToggle } from './components/ThemeToggle'
import { listSessions, type SessionItem } from './api/client'
import { useTheme } from './theme'

export function App() {
  const { colors } = useTheme()
  const [sessions, setSessions] = useState<SessionItem[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [showSubmit, setShowSubmit] = useState(false)

  const refresh = useCallback(async () => {
    const items = await listSessions()
    setSessions(items)
  }, [])

  useEffect(() => {
    refresh()
    const interval = setInterval(refresh, 5000)
    return () => clearInterval(interval)
  }, [refresh])

  return (
    <div style={{ display: 'flex', height: '100vh', background: colors.bg }}>
      {/* Left sidebar */}
      <div
        style={{
          width: '280px',
          borderRight: `1px solid ${colors.border}`,
          background: colors.bgSidebar,
          display: 'flex',
          flexDirection: 'column',
          flexShrink: 0,
        }}
      >
        <div
          style={{
            padding: '16px',
            borderBottom: `1px solid ${colors.border}`,
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <h2 style={{ fontSize: '15px', fontWeight: 700, color: colors.text, letterSpacing: '0.5px' }}>
            OneFusion
          </h2>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <ThemeToggle />
            <button
              onClick={() => setShowSubmit(true)}
              style={{
                padding: '5px 12px',
                background: colors.accent,
                color: '#fff',
                border: 'none',
                borderRadius: '6px',
                cursor: 'pointer',
                fontSize: '13px',
                fontWeight: 600,
              }}
            >
              + New
            </button>
          </div>
        </div>
        <SessionList sessions={sessions} selectedId={selectedId} onSelect={setSelectedId} />
      </div>

      {/* Main area */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {showSubmit ? (
          <SubmitForm
            onClose={() => setShowSubmit(false)}
            onSubmitted={(id) => {
              setShowSubmit(false)
              setSelectedId(id)
              refresh()
            }}
          />
        ) : selectedId ? (
          <WorkflowView
            projectId={selectedId}
            onDeleted={() => {
              setSelectedId(null)
              refresh()
            }}
          />
        ) : (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              height: '100%',
              color: colors.textMuted,
              fontSize: '14px',
            }}
          >
            Select a session or create a new one
          </div>
        )}
      </div>
    </div>
  )
}
