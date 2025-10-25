from __future__ import annotations
import os
import sys
import time
import json
import argparse


def main():
    ap = argparse.ArgumentParser(description="Ping DeepSeek native API to verify connectivity.")
    ap.add_argument("--model", default=os.getenv("JUDGE2_MODEL") or "deepseek-chat",
                    help="DeepSeek model id (default: deepseek-chat or $JUDGE2_MODEL)")
    ap.add_argument("--message", default="Reply with exactly: pong",
                    help="Message to send in the test chat completion")
    ap.add_argument("--base-url", default=os.getenv("DEEPSEEK_BASE_URL") or "https://api.deepseek.com",
                    help="DeepSeek base URL")
    ap.add_argument("--timeout", type=float, default=60.0, help="Request timeout seconds (best-effort)")
    ap.add_argument("--dotenv", default=".env", help="Path to .env file to load (optional)")
    ap.add_argument("--api-key", default=None, help="Explicit DeepSeek API key (overrides env)")
    args = ap.parse_args()

    # Load .env if available
    try:
        from dotenv import load_dotenv  # type: ignore
        if args.dotenv and os.path.exists(args.dotenv):
            load_dotenv(args.dotenv)
        else:
            load_dotenv()
    except Exception:
        pass

    key = args.api_key or os.getenv("DEEPSEEK_API_KEY")
    if not key:
        print(json.dumps({
            "status": "error",
            "stage": "env",
            "error": "DEEPSEEK_API_KEY not set",
            "cwd": os.getcwd(),
            "python": sys.executable,
            "venv": os.environ.get("VIRTUAL_ENV") or "",
        }))
        sys.exit(2)

    try:
        from openai import OpenAI  # type: ignore
    except Exception as e:
        print(json.dumps({
            "status": "error",
            "stage": "import",
            "error": f"openai import failed: {e}",
            "hint": "pip install openai",
        }))
        sys.exit(3)

    try:
        client = OpenAI(base_url=args.base_url, api_key=key)
        t0 = time.time()
        resp = client.chat.completions.create(
            model=args.model,
            messages=[
                {"role": "system", "content": "You are a helpful assistant"},
                {"role": "user", "content": args.message}
            ],
            temperature=0.0,
        )
        dt = time.time() - t0
        content = resp.choices[0].message.content if resp.choices else ""
        print(json.dumps({
            "status": "ok",
            "provider": "deepseek-native",
            "model": args.model,
            "latency_s": round(dt, 3),
            "response": content,
        }, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({
            "status": "error",
            "stage": "call",
            "error": str(e),
            "model": args.model,
        }))
        sys.exit(1)


if __name__ == "__main__":
    main()
