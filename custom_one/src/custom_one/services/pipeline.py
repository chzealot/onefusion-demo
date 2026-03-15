from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from custom_one.models.schemas import SessionStage
from custom_one.services import animation_generator, script_generator, tts_service, video_renderer
from custom_one.services.session_manager import SessionManager

logger = logging.getLogger(__name__)

MAX_RENDER_RETRIES = 3


class Pipeline:
    def __init__(self, session_manager: SessionManager) -> None:
        self.sm = session_manager

    async def run(self, session_id: str) -> None:
        """Execute the full pipeline: script → TTS → animation → render."""
        session = await self.sm.load(session_id)
        session_dir = self.sm._session_dir(session_id)

        try:
            # Stage 1: Generate subtitles script
            await self.sm.update_status(
                session_id, SessionStage.GENERATING_SCRIPT,
                percent=0, message="Generating video script from article...",
            )
            subtitles = await script_generator.generate_script(
                session.article, session.requirements,
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
            durations = await tts_service.generate_all(session_dir, subtitles)
            await self.sm.save_audio_durations(session_id, durations)

            total_audio_duration = await tts_service.combine_audio(
                session_dir, subtitles, durations,
            )
            total_frames = int(total_audio_duration * 30) + 30  # +1s buffer
            await self.sm.update_status(
                session_id, SessionStage.GENERATING_TTS,
                percent=100,
                message=f"TTS complete: {len(durations)} segments, {total_audio_duration:.1f}s",
                video_duration_sec=total_audio_duration,
                total_frames=total_frames,
            )

            # Stage 3: Generate animation project
            await self.sm.update_status(
                session_id, SessionStage.GENERATING_ANIMATION,
                percent=0, message="Generating animation project with Claude Code...",
            )

            async def on_anim_progress(msg: str):
                await self.sm.update_status(
                    session_id, SessionStage.GENERATING_ANIMATION,
                    percent=50, message=msg,
                )

            claude_session_id = await animation_generator.generate_animation(
                session_dir, subtitles, durations, on_progress=on_anim_progress,
            )
            await self.sm.update_status(
                session_id, SessionStage.GENERATING_ANIMATION,
                percent=100, message="Animation project generated",
                claude_session_id=claude_session_id,
            )

            # Stage 4: Render video
            await self._render_with_retry(session_id, session_dir, total_frames, claude_session_id)

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
        total_frames: int,
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

                await video_renderer.render_video(
                    session_dir, total_frames, on_progress=on_render_progress,
                )
                return  # Success

            except Exception as e:
                error_msg = str(e)
                logger.warning(
                    "Render attempt %d failed for %s: %s",
                    attempt, session_id, error_msg,
                )

                if attempt < MAX_RENDER_RETRIES:
                    await self.sm.update_status(
                        session_id, SessionStage.GENERATING_ANIMATION,
                        percent=50,
                        message=f"Render failed, fixing with Claude Code (attempt {attempt})...",
                    )

                    async def on_fix_progress(msg: str):
                        await self.sm.update_status(
                            session_id, SessionStage.GENERATING_ANIMATION,
                            percent=75, message=msg,
                        )

                    claude_session_id = await animation_generator.fix_animation_errors(
                        session_dir, error_msg, claude_session_id,
                        on_progress=on_fix_progress,
                    )
                else:
                    raise RuntimeError(
                        f"Video rendering failed after {MAX_RENDER_RETRIES} attempts: {error_msg}"
                    )

    async def resume(self, session_id: str, prompt: str, images: list[str] | None = None) -> None:
        """Resume a session with new modification prompt."""
        session = await self.sm.load(session_id)
        session_dir = self.sm._session_dir(session_id)

        try:
            # Restore project from zip if needed
            animation_dir = session_dir / "animation"
            if not animation_dir.exists() or not any(animation_dir.iterdir()):
                await self.sm.restore_project(session_id)

            await self.sm.update_status(
                session_id, SessionStage.GENERATING_ANIMATION,
                percent=0, message="Modifying animation with Claude Code...",
            )

            async def on_progress(msg: str):
                await self.sm.update_status(
                    session_id, SessionStage.GENERATING_ANIMATION,
                    percent=50, message=msg,
                )

            claude_session_id = await animation_generator.resume_animation(
                session_dir, prompt, session.claude_session_id,
                on_progress=on_progress,
            )

            await self.sm.update_status(
                session_id, SessionStage.GENERATING_ANIMATION,
                percent=100, message="Modifications applied",
                claude_session_id=claude_session_id,
                resume_count=session.resume_count + 1,
            )

            # Re-render
            total_frames = session.total_frames or int(session.video_duration_sec * 30) + 30
            await self._render_with_retry(
                session_id, session_dir, total_frames, claude_session_id,
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
