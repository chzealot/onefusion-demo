import { useState } from 'react'
import { submitArticle } from '../api/client'
import { useTheme } from '../theme'

interface Props {
  onClose: () => void
  onSubmitted: (projectId: string) => void
}

export function SubmitForm({ onClose, onSubmitted }: Props) {
  const { colors } = useTheme()
  const [article, setArticle] = useState('')
  const [requirements, setRequirements] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async () => {
    if (!article.trim()) return
    setLoading(true)
    try {
      const result = await submitArticle(article.trim(), requirements.trim())
      onSubmitted(result.project_id)
    } catch (e) {
      alert('Submit failed: ' + (e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ padding: '32px', maxWidth: '700px', margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
        <h2 style={{ fontSize: '18px', color: colors.text, fontWeight: 600 }}>New Video Project</h2>
        <button
          onClick={onClose}
          style={{ border: 'none', background: 'none', fontSize: '18px', cursor: 'pointer', color: colors.textMuted }}
        >
          x
        </button>
      </div>

      <div style={{ marginBottom: '16px' }}>
        <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, marginBottom: '8px', color: colors.textSecondary }}>
          Article Content *
        </label>
        <textarea
          value={article}
          onChange={(e) => setArticle(e.target.value)}
          placeholder="Paste your article here..."
          style={{
            width: '100%',
            height: '280px',
            padding: '12px',
            borderRadius: '8px',
            border: `1px solid ${colors.border}`,
            background: colors.bgInput,
            color: colors.text,
            resize: 'vertical',
            fontSize: '14px',
            lineHeight: 1.6,
            boxSizing: 'border-box',
          }}
        />
      </div>

      <div style={{ marginBottom: '24px' }}>
        <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, marginBottom: '8px', color: colors.textSecondary }}>
          Requirements (optional)
        </label>
        <textarea
          value={requirements}
          onChange={(e) => setRequirements(e.target.value)}
          placeholder="Special requirements for the video..."
          style={{
            width: '100%',
            height: '80px',
            padding: '12px',
            borderRadius: '8px',
            border: `1px solid ${colors.border}`,
            background: colors.bgInput,
            color: colors.text,
            resize: 'vertical',
            fontSize: '14px',
            boxSizing: 'border-box',
          }}
        />
      </div>

      <button
        onClick={handleSubmit}
        disabled={loading || !article.trim()}
        style={{
          padding: '10px 24px',
          background: loading ? colors.textMuted : colors.accent,
          color: '#fff',
          border: 'none',
          borderRadius: '8px',
          cursor: loading ? 'not-allowed' : 'pointer',
          fontSize: '15px',
          fontWeight: 600,
        }}
      >
        {loading ? 'Submitting...' : 'Submit & Generate'}
      </button>
    </div>
  )
}
