"""TTS test script for Alibaba Cloud DashScope WebSocket API."""

import asyncio
import json
import os
import uuid

import websockets
from dotenv import load_dotenv

load_dotenv()

DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
TTS_VOICE = os.getenv("TTS_VOICE", "longshuo")

TEST_TEXT = "你好，这是一段测试语音合成的文本。"
OUTPUT_FILE = "test_output.mp3"

WS_URL = "wss://dashscope.aliyuncs.com/api-ws/v1/inference"


async def test_tts():
    task_id = str(uuid.uuid4())
    audio_chunks: list[bytes] = []

    headers = {"Authorization": f"Bearer {DASHSCOPE_API_KEY}"}

    print(f"API Key: {DASHSCOPE_API_KEY[:8]}...{DASHSCOPE_API_KEY[-4:]}")
    print(f"Voice: {TTS_VOICE}")
    print(f"Text: {TEST_TEXT}")
    print(f"URL: {WS_URL}")
    print()

    async with websockets.connect(WS_URL, additional_headers=headers) as ws:
        # run-task
        run_msg = {
            "header": {
                "action": "run-task",
                "task_id": task_id,
                "streaming": "duplex",
            },
            "payload": {
                "task_group": "audio",
                "task": "tts",
                "function": "SpeechSynthesizer",
                "model": "cosyvoice-v1",
                "parameters": {
                    "text_type": "PlainText",
                    "voice": TTS_VOICE,
                    "format": "mp3",
                    "sample_rate": 22050,
                },
                "input": {},
            },
        }
        print("[SEND] run-task")
        await ws.send(json.dumps(run_msg))

        async for message in ws:
            if isinstance(message, bytes):
                audio_chunks.append(message)
                print(f"  [RECV] audio chunk: {len(message)} bytes")
                continue

            event = json.loads(message)
            action = event.get("header", {}).get("event") or event.get("header", {}).get("action")
            print(f"  [RECV] event: {action}")

            if action == "task-started":
                # send text
                await ws.send(json.dumps({
                    "header": {
                        "action": "continue-task",
                        "task_id": task_id,
                        "streaming": "duplex",
                    },
                    "payload": {"input": {"text": TEST_TEXT}},
                }))
                # finish
                await ws.send(json.dumps({
                    "header": {
                        "action": "finish-task",
                        "task_id": task_id,
                        "streaming": "duplex",
                    },
                    "payload": {"input": {}},
                }))
                print("  [SENT] text + finish")

            elif action == "task-finished":
                print(">>> Task finished!")
                break

            elif action == "task-failed":
                code = event.get("header", {}).get("error_code", "unknown")
                msg = event.get("header", {}).get("error_message", "unknown")
                print(f">>> FAILED: [{code}] {msg}")
                print(json.dumps(event, indent=2, ensure_ascii=False))
                return

    audio = b"".join(audio_chunks)
    if audio:
        with open(OUTPUT_FILE, "wb") as f:
            f.write(audio)
        print(f"\nSaved: {OUTPUT_FILE} ({len(audio)} bytes, {len(audio)/1024:.1f} KB)")
    else:
        print("\nNo audio data received!")


if __name__ == "__main__":
    if not DASHSCOPE_API_KEY:
        print("ERROR: DASHSCOPE_API_KEY not set in .env")
    else:
        asyncio.run(test_tts())
