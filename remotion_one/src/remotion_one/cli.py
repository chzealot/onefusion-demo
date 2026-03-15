"""CLI interface for RemotionOne."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time

import httpx


DEFAULT_BASE_URL = "http://localhost:8000"


def main():
    parser = argparse.ArgumentParser(
        prog="remotion-one",
        description="Article to explainer video tool",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # serve
    p_serve = sub.add_parser("serve", help="Start the API server")
    p_serve.add_argument("--host", default="0.0.0.0")
    p_serve.add_argument("--port", type=int, default=8000)

    # submit
    p_submit = sub.add_parser("submit", help="Submit an article")
    p_submit.add_argument("--article", required=True, help="Article text or @filepath")
    p_submit.add_argument("--requirements", default="", help="Additional requirements")
    p_submit.add_argument("--width", type=int, default=None)
    p_submit.add_argument("--height", type=int, default=None)
    p_submit.add_argument("--fps", type=int, default=None)
    p_submit.add_argument("--voice", default=None, choices=["yunxi", "xiaoxiao", "yunyang", "xiaoyi"])
    p_submit.add_argument("--base-url", default=DEFAULT_BASE_URL)

    # status
    p_status = sub.add_parser("status", help="Check session status")
    p_status.add_argument("session_id")
    p_status.add_argument("--watch", action="store_true", help="Poll until completion")
    p_status.add_argument("--base-url", default=DEFAULT_BASE_URL)

    # resume
    p_resume = sub.add_parser("resume", help="Resume session with new prompt")
    p_resume.add_argument("session_id")
    p_resume.add_argument("--prompt", required=True)
    p_resume.add_argument("--base-url", default=DEFAULT_BASE_URL)

    # download
    p_download = sub.add_parser("download", help="Download session artifacts")
    p_download.add_argument("session_id")
    p_download.add_argument("--type", choices=["video", "subtitles", "project"], default="video")
    p_download.add_argument("--output", default=None, help="Output file path")
    p_download.add_argument("--base-url", default=DEFAULT_BASE_URL)

    # list
    p_list = sub.add_parser("list", help="List all sessions")
    p_list.add_argument("--base-url", default=DEFAULT_BASE_URL)

    args = parser.parse_args()

    if args.command == "serve":
        _cmd_serve(args)
    elif args.command == "submit":
        asyncio.run(_cmd_submit(args))
    elif args.command == "status":
        asyncio.run(_cmd_status(args))
    elif args.command == "resume":
        asyncio.run(_cmd_resume(args))
    elif args.command == "download":
        asyncio.run(_cmd_download(args))
    elif args.command == "list":
        asyncio.run(_cmd_list(args))


def _cmd_serve(args):
    import uvicorn
    uvicorn.run(
        "remotion_one.main:app",
        host=args.host,
        port=args.port,
        reload=True,
    )


async def _cmd_submit(args):
    article = args.article
    if article.startswith("@"):
        with open(article[1:], "r", encoding="utf-8") as f:
            article = f.read()

    payload = {"article": article, "requirements": args.requirements}
    if args.width:
        payload["video_width"] = args.width
    if args.height:
        payload["video_height"] = args.height
    if args.fps:
        payload["video_fps"] = args.fps
    if args.voice:
        payload["tts_voice"] = args.voice

    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{args.base_url}/api/sessions", json=payload)
        resp.raise_for_status()
        data = resp.json()
        print(f"Session created: {data['session_id']}")
        print(f"Status: {data['status']}")
        print(f"\nTrack progress:")
        print(f"  remotion-one status {data['session_id']} --watch")


async def _cmd_status(args):
    async with httpx.AsyncClient() as client:
        while True:
            resp = await client.get(f"{args.base_url}/api/sessions/{args.session_id}")
            resp.raise_for_status()
            data = resp.json()

            if args.watch:
                sys.stdout.write(f"\r[{data['progress']:3d}%] {data['status']}: {data['current_step']}")
                sys.stdout.flush()
                if data["status"] in ("completed", "error"):
                    print()
                    if data["error"]:
                        print(f"Error: {data['error']}")
                    else:
                        print("Completed successfully!")
                    break
                await asyncio.sleep(3)
            else:
                print(json.dumps(data, indent=2, ensure_ascii=False))
                break


async def _cmd_resume(args):
    payload = {"prompt": args.prompt}
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{args.base_url}/api/sessions/{args.session_id}/resume",
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
        print(f"Resume started for session: {data['session_id']}")
        print(f"\nTrack progress:")
        print(f"  remotion-one status {data['session_id']} --watch")


async def _cmd_download(args):
    ext_map = {"video": ".mp4", "subtitles": ".json", "project": ".zip"}
    output = args.output or f"{args.session_id}{ext_map[args.type]}"

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{args.base_url}/api/sessions/{args.session_id}/{args.type}",
        )
        resp.raise_for_status()
        with open(output, "wb") as f:
            f.write(resp.content)
        print(f"Downloaded: {output}")


async def _cmd_list(args):
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{args.base_url}/api/sessions")
        resp.raise_for_status()
        sessions = resp.json()
        if not sessions:
            print("No sessions found.")
            return
        for s in sessions:
            status_icon = {
                "completed": "OK", "error": "ERR",
                "created": "..", "scripting": ">>",
                "tts_generating": ">>", "coding": ">>",
                "rendering": ">>",
            }.get(s["status"], "??")
            print(f"[{status_icon}] {s['session_id']}  {s['status']:15s}  {s['progress']:3d}%  {s['current_step']}")


if __name__ == "__main__":
    main()
