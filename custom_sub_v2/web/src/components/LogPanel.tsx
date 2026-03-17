import { useState, useEffect, useRef } from 'react'
import { getLogsUrl } from '../api/client'
import { useTheme } from '../theme'

interface Props {
  projectId: string
}

export function LogPanel({ projectId }: Props) {
  const { mode } = useTheme()
  const [lines, setLines] = useState<string[]>([])
  const containerRef = useRef<HTMLDivElement>(null)
  const eventSourceRef = useRef<EventSource | null>(null)

  useEffect(() => {
    setLines([])

    const es = new EventSource(getLogsUrl(projectId))
    eventSourceRef.current = es

    es.onmessage = (event) => {
      setLines((prev) => [...prev, event.data])
    }

    es.onerror = () => {
      // Will auto-reconnect
    }

    return () => {
      es.close()
      eventSourceRef.current = null
    }
  }, [projectId])

  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight
    }
  }, [lines])

  return (
    <div
      ref={containerRef}
      style={{
        fontFamily: '"SF Mono", "Fira Code", monospace',
        fontSize: 11,
        lineHeight: 1.7,
        color: mode === 'dark' ? '#a0a0b0' : '#444',
        whiteSpace: 'pre-wrap',
        wordBreak: 'break-all',
        maxHeight: 200,
        overflow: 'auto',
      }}
    >
      {lines.length === 0 ? (
        <span style={{ color: mode === 'dark' ? '#444' : '#bbb' }}>Waiting for logs...</span>
      ) : (
        lines.map((line, i) => <div key={i}>{line}</div>)
      )}
    </div>
  )
}
