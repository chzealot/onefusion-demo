import { createContext, useContext, useState, useEffect, type ReactNode } from 'react'

export interface ThemeColors {
  // Backgrounds
  bg: string
  bgSidebar: string
  bgPanel: string
  bgCard: string
  bgInput: string
  bgHover: string
  // Borders
  border: string
  borderLight: string
  // Text
  text: string
  textSecondary: string
  textMuted: string
  // Accents
  accent: string
  // Node statuses
  nodePendingBg: string
  nodePendingBorder: string
  nodeActiveBg: string
  nodeActiveBorder: string
  nodeCompletedBg: string
  nodeCompletedBorder: string
  nodeFailedBg: string
  nodeFailedBorder: string
  // Flow
  edgeColor: string
  flowBg: string
  flowGrid: string
}

const dark: ThemeColors = {
  bg: '#0a0a0f',
  bgSidebar: '#0f0f18',
  bgPanel: '#0c0c14',
  bgCard: '#1a1a2e',
  bgInput: '#12121c',
  bgHover: '#1a1a2e',
  border: '#1e1e2e',
  borderLight: '#1a1a2a',
  text: '#e0e0e0',
  textSecondary: '#aaa',
  textMuted: '#555',
  accent: '#6366f1',
  nodePendingBg: '#1a1a2e',
  nodePendingBorder: '#2a2a40',
  nodeActiveBg: '#0f1a3a',
  nodeActiveBorder: '#3b82f6',
  nodeCompletedBg: '#0a1f1a',
  nodeCompletedBorder: '#22c55e',
  nodeFailedBg: '#1f0a0a',
  nodeFailedBorder: '#ef4444',
  edgeColor: '#2a2a40',
  flowBg: '#0a0a0f',
  flowGrid: '#1a1a2a',
}

const light: ThemeColors = {
  bg: '#f5f6fa',
  bgSidebar: '#ffffff',
  bgPanel: '#ffffff',
  bgCard: '#f0f1f5',
  bgInput: '#f8f9fc',
  bgHover: '#eef0f5',
  border: '#e0e2ea',
  borderLight: '#eaecf2',
  text: '#1a1a2e',
  textSecondary: '#555',
  textMuted: '#999',
  accent: '#6366f1',
  nodePendingBg: '#f0f1f5',
  nodePendingBorder: '#d0d2da',
  nodeActiveBg: '#e8f0fe',
  nodeActiveBorder: '#3b82f6',
  nodeCompletedBg: '#e6f9ed',
  nodeCompletedBorder: '#22c55e',
  nodeFailedBg: '#fde8e8',
  nodeFailedBorder: '#ef4444',
  edgeColor: '#c8cad2',
  flowBg: '#f5f6fa',
  flowGrid: '#e0e2ea',
}

type Mode = 'dark' | 'light'

interface ThemeContextValue {
  mode: Mode
  colors: ThemeColors
  toggle: () => void
}

const ThemeContext = createContext<ThemeContextValue>({
  mode: 'dark',
  colors: dark,
  toggle: () => {},
})

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setMode] = useState<Mode>(() => {
    const saved = localStorage.getItem('theme')
    return saved === 'light' ? 'light' : 'dark'
  })

  useEffect(() => {
    localStorage.setItem('theme', mode)
  }, [mode])

  const toggle = () => setMode((m) => (m === 'dark' ? 'light' : 'dark'))
  const colors = mode === 'dark' ? dark : light

  return (
    <ThemeContext.Provider value={{ mode, colors, toggle }}>
      {children}
    </ThemeContext.Provider>
  )
}

export function useTheme() {
  return useContext(ThemeContext)
}
