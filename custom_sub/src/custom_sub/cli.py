"""CLI interface for custom_sub."""

from __future__ import annotations

import asyncio
import json
import sys
import time

import click

from custom_sub.config import settings


def _run(coro):
    """Run an async coroutine."""
    return asyncio.run(coro)


@click.group()
def cli():
    """custom_sub - Article to explainer video tool."""
    pass


@cli.command()
@click.argument("article_file", type=click.Path(exists=True))
@click.option("--requirements", "-r", default="", help="Specific requirements")
@click.option("--width", type=int, default=None, help="Video width")
@click.option("--height", type=int, default=None, help="Video height")
@click.option("--fps", type=int, default=None, help="Video FPS")
@click.option("--wait/--no-wait", default=True, help="Wait for completion")
def submit(article_file, requirements, width, height, fps, wait):
    """Submit an article file to generate a video."""
    with open(article_file, "r") as f:
        article = f.read()

    async def _submit():
        from custom_sub.services.session import session_manager
        from custom_sub.services.pipeline import start_pipeline

        session_id = await session_manager.create_session(
            article=article,
            requirements=requirements,
            video_width=width,
            video_height=height,
            video_fps=fps,
        )
        click.echo(f"Session created: {session_id}")

        await start_pipeline(session_id)

        if wait:
            click.echo("Waiting for pipeline to complete...")
            while True:
                progress = await session_manager.get_progress(session_id)
                status = progress.status
                steps_info = " → ".join(
                    f"{s.name.value}:{s.status}"
                    for s in progress.steps
                )
                click.echo(f"\r  [{status.value}] {steps_info}", nl=False)

                if status in ("completed", "failed", "stopped"):
                    click.echo()
                    if status == "failed":
                        click.echo(f"Error: {progress.error}", err=True)
                    elif status == "completed":
                        sdir = session_manager.session_dir(session_id)
                        click.echo(f"Output: {sdir / 'output.mp4'}")
                    break
                await asyncio.sleep(2)
        else:
            click.echo("Pipeline started in background.")

        return session_id

    _run(_submit())


@cli.command()
@click.argument("session_id")
def progress(session_id):
    """Check progress of a session."""
    async def _progress():
        from custom_sub.services.session import session_manager

        if not session_manager.session_exists(session_id):
            click.echo("Session not found", err=True)
            sys.exit(1)

        p = await session_manager.get_progress(session_id)
        click.echo(f"Session: {p.session_id}")
        click.echo(f"Status:  {p.status.value}")
        click.echo(f"Created: {p.created_at}")
        click.echo(f"Updated: {p.updated_at}")
        if p.error:
            click.echo(f"Error:   {p.error}")
        click.echo("Steps:")
        for step in p.steps:
            icon = {"pending": "⏳", "in_progress": "🔄", "completed": "✅", "failed": "❌"}.get(step.status, "?")
            click.echo(f"  {icon} {step.name.value}: {step.status} {step.message}")

    _run(_progress())


@cli.command()
@click.argument("session_id")
@click.argument("prompt")
def resume(session_id, prompt):
    """Resume a session with a modification prompt."""
    async def _resume():
        from custom_sub.services.pipeline import resume_pipeline

        await resume_pipeline(session_id, prompt)
        click.echo("Resume started.")

    _run(_resume())


@cli.command("list")
def list_sessions():
    """List all sessions."""
    async def _list():
        from custom_sub.services.session import session_manager

        items = await session_manager.list_sessions()
        if not items:
            click.echo("No sessions found.")
            return
        for item in items:
            click.echo(
                f"  {item.session_id}  [{item.status.value:20s}]  "
                f"{item.created_at:%Y-%m-%d %H:%M}  "
                f"{item.article_preview[:60]}..."
            )

    _run(_list())


@cli.command()
@click.argument("session_id")
def stop(session_id):
    """Stop a running session."""
    async def _stop():
        from custom_sub.services.pipeline import stop_pipeline
        await stop_pipeline(session_id)
        click.echo("Session stopped.")

    _run(_stop())


@cli.command()
@click.argument("session_id")
@click.confirmation_option(prompt="Delete session and all data?")
def delete(session_id):
    """Delete a session."""
    async def _delete():
        from custom_sub.services.pipeline import stop_pipeline, is_running
        from custom_sub.services.session import session_manager

        if is_running(session_id):
            await stop_pipeline(session_id)
        await session_manager.delete_session(session_id)
        click.echo("Session deleted.")

    _run(_delete())


@cli.command()
@click.option("--host", default=None, help="Server host")
@click.option("--port", type=int, default=None, help="Server port")
def serve(host, port):
    """Start the HTTP server."""
    import uvicorn
    from custom_sub.main import app

    uvicorn.run(
        app,
        host=host or settings.host,
        port=port or settings.port,
    )


if __name__ == "__main__":
    cli()
