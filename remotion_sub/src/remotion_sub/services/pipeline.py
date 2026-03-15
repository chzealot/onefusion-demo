"""Pipeline orchestrator: script -> TTS -> Remotion code -> render."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from remotion_sub.models.schemas import SessionStage
from remotion_sub.services import remotion_generator, renderer, scriptwriter, tts
from remotion_sub.services.session import SessionManager

logger = logging.getLogger(__name__)

MAX_RENDER_RETRIES = 3


class Pipeline:
    def __init__(self, session_manager: SessionManager) -> None:
        self.sm = session_manager

    async def run(self, session_id: str) -> None:
        """Execute the full pipeline: script -> TTS -> Remotion code -> render."""
        detail = await self.sm.get_detail(session_id)
        session_dir = self.sm.session_dir(session_id)
        video_config = {
            "width": detail.video_width,
            "height": detail.video_height,
            "fps": detail.video_fps,
        }

        try:
            # Stage 1: Generate subtitles script
            await self.sm.update_status(
                session_id, SessionStage.GENERATING_SCRIPT,
                percent=0, message="Generating video script from article...",
            )

            async def on_script_progress(msg: str):
                await self.sm.update_status(
                    session_id, SessionStage.GENERATING_SCRIPT,
                    percent=50, message=msg,
                )

            subtitles = await scriptwriter.generate_script(
                session_dir, detail.article, detail.requirements,
                on_progress=on_script_progress,
            )
            await self.sm.save_subtitles(session_id, subtitles)
            await self.sm.update_status(
                session_id, SessionStage.GENERATING_SCRIPT,
                percent=100, message=f"Script generated: {len(subtitles)} scenes",
            )

            # Stage 2: Generate TTS audio
            await self.sm.update_status(
                session_id, SessionStage.GENERATING_TTS,
                percent=0, message="Generating TTS audio...",
            )
            durations = await tts.generate_all(session_dir, subtitles)
            await self.sm.save_audio_durations(session_id, durations)

            total_audio_duration = await tts.combine_audio(
                session_dir, subtitles, durations,
            )
            fps = video_config["fps"]
            total_frames = int(total_audio_duration * fps) + fps  # +1s buffer
            await self.sm.update_status(
                session_id, SessionStage.GENERATING_TTS,
                percent=100,
                message=f"TTS complete: {len(durations)} segments, {total_audio_duration:.1f}s",
                video_duration_sec=total_audio_duration,
                total_frames=total_frames,
            )

            # Stage 3: Generate Remotion project
            await self.sm.update_status(
                session_id, SessionStage.GENERATING_REMOTION,
                percent=0, message="Generating Remotion project with Claude Code...",
            )

            async def on_remotion_progress(msg: str):
                await self.sm.update_status(
                    session_id, SessionStage.GENERATING_REMOTION,
                    percent=50, message=msg,
                )

            claude_session_id = await remotion_generator.generate_remotion(
                session_dir, subtitles, durations, video_config,
                on_progress=on_remotion_progress,
            )
            await self.sm.update_status(
                session_id, SessionStage.GENERATING_REMOTION,
                percent=100, message="Remotion project generated",
                claude_session_id=claude_session_id,
            )

            # Stage 4: Render video
            await self._render_with_retry(
                session_id, session_dir, video_config, claude_session_id,
            )

            # Stage 5: Archive project
            await self.sm.archive_project(session_id)
            await self.sm.update_status(
                session_id, SessionStage.COMPLETED,
                percent=100, message="Video generation complete!",
            )

        except asyncio.CancelledError:
            await self.sm.update_status(
                session_id, SessionStage.STOPPED, message="Pipeline cancelled by user",
            )
            raise
        except Exception as e:
            logger.exception("Pipeline failed for session %s", session_id)
            await self.sm.update_status(
                session_id, SessionStage.ERROR,
                error=str(e), message=f"Error: {e}",
            )

    async def _render_with_retry(
        self,
        session_id: str,
        session_dir: Path,
        video_config: dict,
        claude_session_id: str | None,
    ) -> None:
        """Render video with automatic error fix retry."""
        for attempt in range(1, MAX_RENDER_RETRIES + 1):
            try:
                await self.sm.update_status(
                    session_id, SessionStage.RENDERING,
                    percent=0,
                    message=f"Rendering video (attempt {attempt}/{MAX_RENDER_RETRIES})...",
                )

                async def on_render_progress(msg: str):
                    await self.sm.update_status(
                        session_id, SessionStage.RENDERING,
                        percent=50, message=msg,
                    )

                # Render all individual scenes first
                subtitles = await self.sm.load_subtitles(session_id)
                scene_nums = [s["scene"] for s in subtitles]
                for scene_num in scene_nums:
                    await renderer.render_scene(
                        session_dir, scene_num, video_config, on_render_progress,
                    )

                # Then render the full video
                await renderer.render_full(session_dir, video_config, on_render_progress)
                return  # Success

            except Exception as e:
                error_msg = str(e)
                logger.warning(
                    "Render attempt %d failed for %s: %s",
                    attempt, session_id, error_msg,
                )

                if attempt < MAX_RENDER_RETRIES:
                    await self.sm.update_status(
                        session_id, SessionStage.GENERATING_REMOTION,
                        percent=50,
                        message=f"Render failed, fixing with Claude Code (attempt {attempt})...",
                    )

                    async def on_fix_progress(msg: str):
                        await self.sm.update_status(
                            session_id, SessionStage.GENERATING_REMOTION,
                            percent=75, message=msg,
                        )

                    claude_session_id = await remotion_generator.fix_remotion_errors(
                        session_dir, error_msg, claude_session_id,
                        on_progress=on_fix_progress,
                    )
                else:
                    raise RuntimeError(
                        f"Video rendering failed after {MAX_RENDER_RETRIES} attempts: {error_msg}"
                    )

    async def resume(self, session_id: str, prompt: str, images: list[str] | None = None) -> None:
        """Resume a session with new modification prompt."""
        detail = await self.sm.get_detail(session_id)
        session_dir = self.sm.session_dir(session_id)
        video_config = {
            "width": detail.video_width,
            "height": detail.video_height,
            "fps": detail.video_fps,
        }

        try:
            # Restore project from zip if needed
            remotion_dir = session_dir / "remotion"
            if not remotion_dir.exists() or not any(remotion_dir.iterdir()):
                await self.sm.restore_project(session_id)

            await self.sm.update_status(
                session_id, SessionStage.GENERATING_REMOTION,
                percent=0, message="Modifying Remotion project with Claude Code...",
            )

            async def on_progress(msg: str):
                await self.sm.update_status(
                    session_id, SessionStage.GENERATING_REMOTION,
                    percent=50, message=msg,
                )

            claude_session_id = await remotion_generator.resume_remotion(
                session_dir, prompt, detail.claude_session_id,
                on_progress=on_progress,
            )

            await self.sm.update_status(
                session_id, SessionStage.GENERATING_REMOTION,
                percent=100, message="Modifications applied",
                claude_session_id=claude_session_id,
                resume_count=detail.resume_count + 1,
            )

            # Re-render
            await self._render_with_retry(
                session_id, session_dir, video_config, claude_session_id,
            )

            # Re-archive
            await self.sm.archive_project(session_id)
            await self.sm.update_status(
                session_id, SessionStage.COMPLETED,
                percent=100, message="Video modification complete!",
            )

        except asyncio.CancelledError:
            await self.sm.update_status(
                session_id, SessionStage.STOPPED, message="Resume cancelled",
            )
            raise
        except Exception as e:
            logger.exception("Resume failed for session %s", session_id)
            await self.sm.update_status(
                session_id, SessionStage.ERROR,
                error=str(e), message=f"Resume error: {e}",
            )

    async def render_full_video(self, session_id: str) -> None:
        """Render only the full video (skip script/TTS/code generation)."""
        detail = await self.sm.get_detail(session_id)
        session_dir = self.sm.session_dir(session_id)
        video_config = {
            "width": detail.video_width,
            "height": detail.video_height,
            "fps": detail.video_fps,
        }

        try:
            await self._render_with_retry(
                session_id, session_dir, video_config, detail.claude_session_id,
            )
            await self.sm.update_status(
                session_id, SessionStage.COMPLETED,
                percent=100, message="Full video rendered!",
            )
        except asyncio.CancelledError:
            await self.sm.update_status(
                session_id, SessionStage.STOPPED, message="Render cancelled",
            )
            raise
        except Exception as e:
            logger.exception("Render failed for session %s", session_id)
            await self.sm.update_status(
                session_id, SessionStage.ERROR,
                error=str(e), message=f"Render error: {e}",
            )
