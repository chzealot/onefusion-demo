const BASE = '/api'

export interface SessionItem {
  project_id: string
  agent_id: string
  status: string
  created_at: string
  updated_at: string
  article_preview: string
}

export interface StepProgress {
  name: string
  status: string
  message: string
  started_at: string | null
  completed_at: string | null
}

export interface SessionProgress {
  project_id: string
  agent_id: string
  status: string
  steps: StepProgress[]
  created_at: string
  updated_at: string
  error: string | null
  article_preview: string
}

export interface SceneInfo {
  scene: number
  name: string
  video_url: string | null
  preview_url: string | null
  ready: boolean
}

export async function listSessions(): Promise<SessionItem[]> {
  const resp = await fetch(`${BASE}/sessions`)
  const data = await resp.json()
  return data.sessions
}

export async function getProgress(projectId: string): Promise<SessionProgress> {
  const resp = await fetch(`${BASE}/sessions/${projectId}`)
  return resp.json()
}

export async function submitArticle(article: string, requirements: string = ''): Promise<{ project_id: string; agent_id: string }> {
  const resp = await fetch(`${BASE}/sessions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ article, requirements }),
  })
  return resp.json()
}

export async function resumeSession(projectId: string, prompt: string): Promise<void> {
  await fetch(`${BASE}/sessions/${projectId}/resume`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt }),
  })
}

export async function stopSession(projectId: string): Promise<void> {
  await fetch(`${BASE}/sessions/${projectId}/stop`, { method: 'POST' })
}

export async function deleteSession(projectId: string): Promise<void> {
  await fetch(`${BASE}/sessions/${projectId}`, { method: 'DELETE' })
}

export async function listScenes(projectId: string): Promise<SceneInfo[]> {
  const resp = await fetch(`${BASE}/sessions/${projectId}/scenes`)
  const data = await resp.json()
  return data.scenes
}

export function getVideoUrl(projectId: string): string {
  return `${BASE}/sessions/${projectId}/video`
}

export function getSceneVideoUrl(projectId: string, sceneNum: number): string {
  return `${BASE}/sessions/${projectId}/scenes/${sceneNum}/video`
}

export function getLogsUrl(projectId: string): string {
  return `${BASE}/sessions/${projectId}/logs`
}
