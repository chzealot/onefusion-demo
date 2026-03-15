"""CLI entry point for remotion-sub."""

from __future__ import annotations

import asyncio
import sys

import click
from dotenv import load_dotenv

load_dotenv()


@click.group()
def main():
    """Remotion Sub - Article to Explainer Video Tool"""
    pass


@main.command()
@click.option("--host", default=None, help="Server host")
@click.option("--port", default=None, type=int, help="Server port")
def server(host: str | None, port: int | None):
    """Start the HTTP server with Web UI."""
    import uvicorn

    from remotion_sub.config import settings

    uvicorn.run(
        "remotion_sub.main:app",
        host=host or settings.host,
        port=port or settings.port,
        reload=False,
    )


@main.command()
@click.argument("article_file", type=click.Path(exists=True))
@click.option("--requirements", "-r", default="", help="Video requirements")
@click.option("--output", "-o", default="output.mp4", help="Output video file")
def run(article_file: str, requirements: str, output: str):
    """Generate a video from an article file."""
    asyncio.run(_run_pipeline(article_file, requirements, output))


async def _run_pipeline(article_file: str, requirements: str, output: str):
    from pathlib import Path

    from remotion_sub.database import init_db
    from remotion_sub.models.schemas import SessionStage
    from remotion_sub.services.pipeline import Pipeline
    from remotion_sub.services.session import SessionManager

    article = Path(article_file).read_text(encoding="utf-8")

    db = await init_db()
    sm = SessionManager(db)
    pl = Pipeline(sm)

    session_id = await sm.create(article, requirements)
    click.echo(f"Session created: {session_id}")

    task = asyncio.create_task(pl.run(session_id))
    sm.register_task(session_id, task)

    last_msg = ""
    while not task.done():
        try:
            detail = await sm.get_detail(session_id)
            msg = f"[{detail.status.value}] {detail.progress.message}"
            if msg != last_msg:
                click.echo(msg)
                last_msg = msg
        except Exception:
            pass
        await asyncio.sleep(2)

    detail = await sm.get_detail(session_id)
    if detail.status == SessionStage.COMPLETED:
        video_path = sm.get_video_path(session_id)
        if video_path:
            import shutil
            shutil.copy2(video_path, output)
            click.echo(f"Video saved to: {output}")
        else:
            click.echo("Warning: pipeline completed but no video found", err=True)
    else:
        click.echo(f"Pipeline failed: {detail.error}", err=True)
        sys.exit(1)

    await db.close()


@main.command("list")
def list_sessions():
    """List all sessions."""
    asyncio.run(_list_sessions())


async def _list_sessions():
    from remotion_sub.database import init_db
    from remotion_sub.services.session import SessionManager

    db = await init_db()
    sm = SessionManager(db)
    sessions = await sm.list_sessions()
    await db.close()

    if not sessions:
        click.echo("No sessions found.")
        return

    for s in sessions:
        click.echo(f"  {s.id}  [{s.status.value:20s}]  {s.article_title}")


@main.command()
@click.argument("session_id")
def status(session_id: str):
    """Show session status."""
    asyncio.run(_show_status(session_id))


async def _show_status(session_id: str):
    from remotion_sub.database import init_db
    from remotion_sub.services.session import SessionManager

    db = await init_db()
    sm = SessionManager(db)

    try:
        detail = await sm.get_detail(session_id)
    except FileNotFoundError:
        click.echo(f"Session {session_id} not found", err=True)
        await db.close()
        sys.exit(1)

    click.echo(f"Session:  {detail.id}")
    click.echo(f"Status:   {detail.status.value}")
    click.echo(f"Title:    {detail.article_title}")
    click.echo(f"Progress: {detail.progress.message}")
    if detail.error:
        click.echo(f"Error:    {detail.error}")
    click.echo(f"Video:    {'Yes' if detail.has_video else 'No'}")
    click.echo(f"Scenes:   {detail.scene_count}")
    click.echo(f"Zip:      {'Yes' if detail.has_project_zip else 'No'}")

    await db.close()


@main.command()
@click.argument("session_id")
@click.option("--prompt", "-p", required=True, help="Modification prompt")
def resume(session_id: str, prompt: str):
    """Resume a session with modifications."""
    asyncio.run(_resume_session(session_id, prompt))


async def _resume_session(session_id: str, prompt: str):
    from remotion_sub.database import init_db
    from remotion_sub.models.schemas import SessionStage
    from remotion_sub.services.pipeline import Pipeline
    from remotion_sub.services.session import SessionManager

    db = await init_db()
    sm = SessionManager(db)
    pl = Pipeline(sm)

    try:
        detail = await sm.get_detail(session_id)
    except FileNotFoundError:
        click.echo(f"Session {session_id} not found", err=True)
        await db.close()
        sys.exit(1)

    task = asyncio.create_task(pl.resume(session_id, prompt))
    sm.register_task(session_id, task)

    last_msg = ""
    while not task.done():
        try:
            detail = await sm.get_detail(session_id)
            msg = f"[{detail.status.value}] {detail.progress.message}"
            if msg != last_msg:
                click.echo(msg)
                last_msg = msg
        except Exception:
            pass
        await asyncio.sleep(2)

    detail = await sm.get_detail(session_id)
    if detail.status == SessionStage.COMPLETED:
        click.echo("Resume complete!")
    else:
        click.echo(f"Resume failed: {detail.error}", err=True)
        sys.exit(1)

    await db.close()


if __name__ == "__main__":
    main()
