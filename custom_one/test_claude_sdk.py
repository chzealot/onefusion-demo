"""Test Claude Code SDK connection with OpenRouter."""

import asyncio
import os
import sys

from dotenv import load_dotenv

load_dotenv()

from claude_code_sdk import ClaudeCodeOptions, query
from claude_code_sdk.types import AssistantMessage, ResultMessage, SystemMessage


async def main():
    api_key = os.getenv("CLAUDE_CODE_API_KEY", "")
    base_url = os.getenv("CLAUDE_CODE_BASE_URL", "")
    model = os.getenv("CLAUDE_CODE_MODEL", "anthropic/claude-opus-4.6")

    print(f"API Key: {api_key[:12]}...{api_key[-4:]}")
    print(f"Base URL: {base_url}")
    print(f"Model: {model}")
    print()

    env = os.environ.copy()
    env["ANTHROPIC_BASE_URL"] = base_url or "https://openrouter.ai/api"
    env["ANTHROPIC_AUTH_TOKEN"] = api_key
    env["ANTHROPIC_API_KEY"] = ""  # Must be explicitly empty for OpenRouter

    options = ClaudeCodeOptions(
        model=model,
        permission_mode="bypassPermissions",
        allowed_tools=["Write", "Bash"],
        max_turns=3,
        env=env,
        cwd=os.getcwd(),
        # Print stderr to see CLI errors
        debug_stderr=sys.stderr,
    )

    print("Sending test prompt...")
    print("=" * 60)

    try:
        async for message in query(
            prompt='Say "hello" in one word. Do not use any tools.',
            options=options,
        ):
            if isinstance(message, SystemMessage):
                print(f"[System] subtype={message.subtype} data={message.data}")
            elif isinstance(message, AssistantMessage):
                for block in message.content:
                    if hasattr(block, "text"):
                        print(f"[Assistant] {block.text}")
                    elif hasattr(block, "name"):
                        print(f"[Tool Use] {block.name}")
            elif isinstance(message, ResultMessage):
                print(f"[Result] session_id={message.session_id} error={message.is_error}")
                print(f"  cost=${message.total_cost_usd} turns={message.num_turns}")
            else:
                print(f"[Unknown] {type(message).__name__}: {message}")
    except Exception as e:
        print(f"\nERROR: {e}")
        print(f"Type: {type(e).__name__}")


if __name__ == "__main__":
    asyncio.run(main())
