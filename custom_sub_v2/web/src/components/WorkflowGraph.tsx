import { useMemo } from 'react'
import {
  ReactFlow,
  Background,
  type Node,
  type Edge,
  ConnectionLineType,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { PipelineNode, type PipelineNodeData } from './PipelineNode'
import type { SessionProgress, SceneInfo, StepProgress } from '../api/client'
import { useTheme } from '../theme'

const nodeTypes = { pipeline: PipelineNode }

const X_GAP = 200
const Y_GAP = 80
const SCENE_X_OFFSET = 3
const Y_CENTER = 250

function stepStatus(steps: StepProgress[], name: string): PipelineNodeData['status'] {
  const step = steps.find((s) => s.name === name)
  if (!step) return 'pending'
  return step.status as PipelineNodeData['status']
}

function stepMessage(steps: StepProgress[], name: string): string {
  const step = steps.find((s) => s.name === name)
  return step?.message || ''
}

function sceneAnimateStatus(
  animationStep: PipelineNodeData['status'],
): PipelineNodeData['status'] {
  if (animationStep === 'completed' || animationStep === 'failed') return animationStep
  if (animationStep === 'in_progress') return 'in_progress'
  return 'pending'
}

function sceneRenderStatus(
  scene: SceneInfo,
  renderStep: PipelineNodeData['status'],
): PipelineNodeData['status'] {
  if (scene.ready) return 'completed'
  if (renderStep === 'in_progress') return 'in_progress'
  if (renderStep === 'failed') return 'failed'
  return 'pending'
}

interface Props {
  progress: SessionProgress
  scenes: SceneInfo[]
}

export function WorkflowGraph({ progress, scenes }: Props) {
  const { colors } = useTheme()

  const { nodes, edges } = useMemo(() => {
    const n: Node[] = []
    const e: Edge[] = []
    const sceneCount = Math.max(scenes.length, 1)
    const totalHeight = (sceneCount - 1) * Y_GAP
    const yStart = Y_CENTER - totalHeight / 2

    const edgeColor = colors.edgeColor
    const edgeStyle = { stroke: edgeColor, strokeWidth: 1.5 }
    const animatedEdgeStyle = { stroke: '#3b82f6', strokeWidth: 1.5 }

    const animStatus = stepStatus(progress.steps, 'animation')
    const renderStatus = stepStatus(progress.steps, 'render')

    // Col 0: Article
    n.push({
      id: 'article',
      type: 'pipeline',
      position: { x: 0, y: Y_CENTER - 20 },
      data: {
        label: 'Article',
        sublabel: progress.article_preview?.slice(0, 30) + '...',
        status: 'completed',
        nodeType: 'input',
      } satisfies PipelineNodeData,
    })

    // Col 1: Script
    const scriptSt = stepStatus(progress.steps, 'script')
    n.push({
      id: 'script',
      type: 'pipeline',
      position: { x: X_GAP, y: Y_CENTER - 20 },
      data: {
        label: 'Script',
        sublabel: stepMessage(progress.steps, 'script'),
        status: scriptSt,
        nodeType: 'step',
      } satisfies PipelineNodeData,
    })
    e.push({
      id: 'e-article-script',
      source: 'article',
      target: 'script',
      style: scriptSt === 'in_progress' ? animatedEdgeStyle : edgeStyle,
      animated: scriptSt === 'in_progress',
    })

    // Col 2: TTS
    const ttsSt = stepStatus(progress.steps, 'tts')
    n.push({
      id: 'tts',
      type: 'pipeline',
      position: { x: X_GAP * 2, y: Y_CENTER - 20 },
      data: {
        label: 'TTS',
        sublabel: stepMessage(progress.steps, 'tts'),
        status: ttsSt,
        nodeType: 'step',
      } satisfies PipelineNodeData,
    })
    e.push({
      id: 'e-script-tts',
      source: 'script',
      target: 'tts',
      style: ttsSt === 'in_progress' ? animatedEdgeStyle : edgeStyle,
      animated: ttsSt === 'in_progress',
    })

    // Col 3-4: Per-scene animate + render (fan-out)
    if (scenes.length > 0) {
      scenes.forEach((scene, i) => {
        const y = yStart + i * Y_GAP
        const animId = `scene-anim-${scene.scene}`
        const renderId = `scene-render-${scene.scene}`

        const aStatus = sceneAnimateStatus(animStatus)
        const rStatus = sceneRenderStatus(scene, renderStatus)

        n.push({
          id: animId,
          type: 'pipeline',
          position: { x: X_GAP * SCENE_X_OFFSET, y },
          data: {
            label: 'Animate',
            sublabel: `Scene ${scene.scene}: ${scene.name}`,
            status: aStatus,
            nodeType: 'scene',
          } satisfies PipelineNodeData,
        })

        n.push({
          id: renderId,
          type: 'pipeline',
          position: { x: X_GAP * (SCENE_X_OFFSET + 1), y },
          data: {
            label: 'Render',
            sublabel: scene.ready ? 'Video ready' : '',
            status: rStatus,
            nodeType: 'scene',
          } satisfies PipelineNodeData,
        })

        e.push({
          id: `e-tts-${animId}`,
          source: 'tts',
          target: animId,
          style: aStatus === 'in_progress' ? animatedEdgeStyle : edgeStyle,
          animated: aStatus === 'in_progress',
        })

        e.push({
          id: `e-${animId}-${renderId}`,
          source: animId,
          target: renderId,
          style: rStatus === 'in_progress' ? animatedEdgeStyle : edgeStyle,
          animated: rStatus === 'in_progress',
        })

        e.push({
          id: `e-${renderId}-merge`,
          source: renderId,
          target: 'merge',
          style: rStatus === 'completed' ? { stroke: '#22c55e', strokeWidth: 1.5 } : edgeStyle,
          animated: rStatus === 'in_progress',
        })
      })
    } else {
      n.push({
        id: 'scene-placeholder',
        type: 'pipeline',
        position: { x: X_GAP * SCENE_X_OFFSET, y: Y_CENTER - 20 },
        data: {
          label: 'Animate',
          sublabel: 'Waiting for scenes...',
          status: 'pending',
          nodeType: 'scene',
        } satisfies PipelineNodeData,
      })
      n.push({
        id: 'render-placeholder',
        type: 'pipeline',
        position: { x: X_GAP * (SCENE_X_OFFSET + 1), y: Y_CENTER - 20 },
        data: {
          label: 'Render',
          sublabel: '',
          status: 'pending',
          nodeType: 'scene',
        } satisfies PipelineNodeData,
      })
      e.push({ id: 'e-tts-ph', source: 'tts', target: 'scene-placeholder', style: edgeStyle })
      e.push({ id: 'e-ph-rph', source: 'scene-placeholder', target: 'render-placeholder', style: edgeStyle })
      e.push({ id: 'e-rph-merge', source: 'render-placeholder', target: 'merge', style: edgeStyle })
    }

    // Col 5: Merge
    const pkgSt = stepStatus(progress.steps, 'package')
    const mergeStatus: PipelineNodeData['status'] =
      pkgSt === 'completed' || pkgSt === 'in_progress'
        ? 'completed'
        : renderStatus === 'completed'
          ? 'completed'
          : renderStatus === 'in_progress'
            ? 'in_progress'
            : 'pending'
    n.push({
      id: 'merge',
      type: 'pipeline',
      position: { x: X_GAP * (SCENE_X_OFFSET + 2), y: Y_CENTER - 20 },
      data: {
        label: 'Merge',
        sublabel: mergeStatus === 'completed' ? 'output.mp4' : '',
        status: mergeStatus,
        nodeType: 'merge',
      } satisfies PipelineNodeData,
    })

    // Col 6: Package
    n.push({
      id: 'package',
      type: 'pipeline',
      position: { x: X_GAP * (SCENE_X_OFFSET + 3), y: Y_CENTER - 20 },
      data: {
        label: 'Package',
        sublabel: stepMessage(progress.steps, 'package'),
        status: pkgSt,
        nodeType: 'output',
      } satisfies PipelineNodeData,
    })
    e.push({
      id: 'e-merge-package',
      source: 'merge',
      target: 'package',
      style: pkgSt === 'in_progress' ? animatedEdgeStyle : edgeStyle,
      animated: pkgSt === 'in_progress',
    })

    return { nodes: n, edges: e }
  }, [progress, scenes, colors])

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      connectionLineType={ConnectionLineType.SmoothStep}
      defaultEdgeOptions={{ type: 'smoothstep' }}
      fitView
      fitViewOptions={{ padding: 0.3 }}
      nodesDraggable={false}
      nodesConnectable={false}
      elementsSelectable={false}
      panOnDrag
      zoomOnScroll
      minZoom={0.3}
      maxZoom={1.5}
      proOptions={{ hideAttribution: true }}
    >
      <Background color={colors.flowGrid} gap={20} size={1} />
    </ReactFlow>
  )
}
