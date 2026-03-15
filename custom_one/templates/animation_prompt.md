# Animation Project Generation Instructions

You must create a complete React + Vite + TypeScript project for rendering video frames at 1920x1080, 30fps.

**CRITICAL**: Do NOT use Remotion. This is a plain React app with a custom frame-based rendering system.

## Project Structure

Create this exact structure:

```
package.json
vite.config.ts
tsconfig.json
index.html
src/
  main.tsx
  App.tsx
  lib/
    animation.ts     # interpolate(), spring(), clamp() utilities
    timeline.ts      # Scene/subtitle timing computation
    constants.ts     # FPS, WIDTH, HEIGHT
  components/
    Subtitle.tsx     # Bottom subtitle overlay
    scenes/
      Scene01.tsx    # One file per scene (Scene01, Scene02, ...)
      Scene02.tsx
      ...
```

## Step 1: Initialize Project

Run these commands to set up the project:

```bash
npm init -y
npm install react react-dom
npm install -D vite @vitejs/plugin-react typescript @types/react @types/react-dom
```

## Step 2: Core Configuration Files

### package.json scripts
```json
{
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview"
  }
}
```

### vite.config.ts
```typescript
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: { host: '0.0.0.0' },
});
```

### tsconfig.json
```json
{
  "compilerOptions": {
    "target": "ES2020",
    "module": "ESNext",
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "jsx": "react-jsx",
    "moduleResolution": "bundler",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true
  },
  "include": ["src"]
}
```

### index.html
```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=1920, height=1080" />
  <title>Video Animation</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { width: 1920px; height: 1080px; overflow: hidden; background: #000; }
    #root { width: 1920px; height: 1080px; overflow: hidden; }
  </style>
</head>
<body>
  <div id="root"></div>
  <script type="module" src="/src/main.tsx"></script>
</body>
</html>
```

## Step 3: Frame-Based Animation System

### src/lib/constants.ts
```typescript
export const FPS = 30;
export const WIDTH = 1920;
export const HEIGHT = 1080;
```

### src/lib/animation.ts
Implement these pure functions (no external dependencies):

```typescript
// interpolate(frame, inputRange, outputRange, options?)
// Maps a frame number from inputRange to outputRange
// options.extrapolateLeft/Right: 'clamp' | 'extend' (default: 'clamp')
export function interpolate(
  value: number,
  inputRange: number[],
  outputRange: number[],
  options?: { extrapolateLeft?: 'clamp' | 'extend'; extrapolateRight?: 'clamp' | 'extend' }
): number;

// spring({frame, fps, config: {damping, stiffness, mass}})
// Physics-based spring animation, returns 0..1
export function spring(opts: {
  frame: number;
  fps: number;
  config?: { damping?: number; stiffness?: number; mass?: number };
}): number;

// clamp(value, min, max)
export function clamp(value: number, min: number, max: number): number;
```

### src/lib/timeline.ts
Compute scene timing from subtitles data and audio durations:

```typescript
import subtitlesData from '../../public/subtitles.json';
import durationsData from '../../public/audio-durations.json';
import { FPS } from './constants';

const SCENE_BUFFER = 0.5; // seconds before/after each scene
const SEGMENT_GAP = 0.3;  // seconds between segments

export interface SegmentTiming {
  file: string;
  text: string;
  startFrame: number;
  endFrame: number;
  durationFrames: number;
}

export interface SceneTiming {
  scene: number;
  name: string;
  description: string;
  annotation: string;
  startFrame: number;
  endFrame: number;
  durationFrames: number;
  segments: SegmentTiming[];
}

// Compute timeline from data
export function computeTimeline(): { scenes: SceneTiming[]; totalFrames: number };

// Get current scene and segment for a given frame
export function getActiveScene(frame: number): SceneTiming | null;
export function getActiveSegment(frame: number): SegmentTiming | null;
```

### src/main.tsx
```typescript
import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';

createRoot(document.getElementById('root')!).render(<App />);
```

### src/App.tsx
The main app component must:
1. Read `window.__CURRENT_FRAME__` (set by Playwright during rendering)
2. Also support `?frame=N` URL parameter (for browser preview/debugging)
3. Use `requestAnimationFrame` loop to detect frame changes and re-render
4. Set `window.__FRAME_READY__ = true` after rendering

```typescript
import React, { useEffect, useState, useCallback } from 'react';
import { computeTimeline, getActiveScene } from './lib/timeline';
import Subtitle from './components/Subtitle';
// Import all scene components
import Scene01 from './components/scenes/Scene01';
import Scene02 from './components/scenes/Scene02';
// ... import all scenes

declare global {
  interface Window {
    __CURRENT_FRAME__: number;
    __FRAME_READY__: boolean;
  }
}

// Initialize
window.__CURRENT_FRAME__ = window.__CURRENT_FRAME__ ?? 0;
window.__FRAME_READY__ = false;

const { scenes, totalFrames } = computeTimeline();

export default function App() {
  const [frame, setFrame] = useState(window.__CURRENT_FRAME__);

  useEffect(() => {
    // Poll for frame changes (set by Playwright)
    let rafId: number;
    const check = () => {
      const newFrame = window.__CURRENT_FRAME__;
      if (newFrame !== frame) {
        setFrame(newFrame);
      }
      rafId = requestAnimationFrame(check);
    };
    rafId = requestAnimationFrame(check);

    // Also support URL parameter
    const params = new URLSearchParams(window.location.search);
    const urlFrame = params.get('frame');
    if (urlFrame !== null) {
      window.__CURRENT_FRAME__ = parseInt(urlFrame, 10);
    }

    return () => cancelAnimationFrame(rafId);
  }, [frame]);

  // Signal frame ready after render
  useEffect(() => {
    window.__FRAME_READY__ = true;
  });

  // Render active scene
  const activeScene = getActiveScene(frame);

  return (
    <div style={{ width: 1920, height: 1080, position: 'relative', overflow: 'hidden', background: '#0a0a1a' }}>
      {/* Scene content - rendered based on active scene */}
      {scenes.map(scene => (
        <SceneRenderer key={scene.scene} scene={scene} frame={frame} active={activeScene?.scene === scene.scene} />
      ))}

      {/* Subtitle overlay - bottom 15% */}
      <Subtitle frame={frame} />
    </div>
  );
}

// Map scene number to component - YOU MUST create a case for each scene
function SceneRenderer({ scene, frame, active }: { scene: SceneTiming; frame: number; active: boolean }) {
  if (!active) return null;
  const localFrame = frame - scene.startFrame;
  switch (scene.scene) {
    case 1: return <Scene01 frame={localFrame} scene={scene} />;
    case 2: return <Scene02 frame={localFrame} scene={scene} />;
    // Add all scenes here
    default: return null;
  }
}
```

## Step 4: Scene Components

For each scene in the subtitles data below, create a SEPARATE file `src/components/scenes/SceneNN.tsx`.

**Each scene MUST**:
- Have its own file (Scene01.tsx, Scene02.tsx, etc.)
- Implement visuals matching the `description` field
- Contain at least 5 visual elements (icons, charts, text, shapes, etc.)
- Include at least 3 animation effects using interpolate/spring
- Be at least 80 lines of code
- Use CSS-in-JS (inline styles) for all styling
- Use SVG for icons and illustrations (no external dependencies)

**Layout rules**:
- Full canvas: 1920x1080
- Top 15% (0-162px): Title area
- Middle 70% (162-918px): Main content/animation area
- Bottom 15% (918-1080px): Reserved for subtitles
- Scene backgrounds should fill the entire 1920x1080 area
- UI components should stay within the middle 70%

**Visual style**:
- Modern, tech-oriented design
- Dark gradient backgrounds (deep blue/purple tones)
- Accent colors: cyan (#00d4ff), orange (#ff6b35)
- Large, readable text (minimum 36px for body, 72px+ for headings)
- Smooth animations with spring physics and easing

**ABSOLUTELY FORBIDDEN**:
- Generic/template scene components
- TODO comments or placeholders
- Using the same layout for all scenes
- External image dependencies
- Time-based animations (setTimeout, setInterval, Date.now())
- All animations must be purely frame-number-based

### Subtitle Component

`src/components/Subtitle.tsx`:
- Position: bottom center, within the bottom 15% area (y: 918-1080px)
- White text, 48px font size, with text shadow for readability
- Show/hide based on current frame matching subtitle segment timing
- Fade in over 5 frames at segment start, fade out over 5 frames at segment end

## Subtitles Data

```json
{{SUBTITLES_JSON}}
```

## Audio Durations (seconds per segment)

```json
{{AUDIO_DURATIONS_JSON}}
```

## IMPORTANT: Complete Implementation Checklist

Before you finish, verify:
- [ ] Every scene has its own component file
- [ ] Every scene has at least 5 visual elements and 3 animations
- [ ] No TODO, placeholder, or generic components exist
- [ ] `window.__FRAME_READY__` is set to `true` after each render
- [ ] Timeline computation matches audio durations with 0.5s scene buffer and 0.3s segment gap
- [ ] The App.tsx switch statement covers ALL scenes
- [ ] Subtitle component correctly shows/hides based on frame timing
- [ ] All text follows Chinese typography rules (spaces between CJK and Latin/numbers)
- [ ] `npm run dev` starts without errors

Generate ALL files now. Do not stop or ask questions. Complete everything in one pass.
