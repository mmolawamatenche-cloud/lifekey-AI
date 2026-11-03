#!/usr/bin/env python3
"""Verify the running LIFEKEY backend against the configured live Ollama model.

Run from the repository root:
    backend\.venv\Scripts\python.exe scripts\verify_live_model.py

Optional arguments:
    backend\.venv\Scripts\python.exe scripts\verify_live_model.py http://127.0.0.1:8000 qwen3:8b
"""

import argparse
import sys
from typing import Any

import httpx


def report(name: str, passed: bool, evidence: Any) -> bool:
    label = "PASS" if passed else "FAIL"
    print(f"[{label}] {name}: {evidence}")
    return passed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url", nargs="?", default="http://127.0.0.1:8000")
    parser.add_argument("model", nargs="?", help="Expected Ollama model name")
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")
    checks: list[bool] = []

    try:
        with httpx.Client(timeout=httpx.Timeout(180.0, connect=5.0)) as client:
            health_response = client.get(f"{base_url}/api/health")
            health = health_response.json()
            checks.append(
                report(
                    "backend health",
                    health_response.is_success and health.get("status") == "ok",
                    health,
                )
            )

            status_response = client.get(f"{base_url}/api/ai/status")
            status = status_response.json()
            local = status.get("local", {})
            model_matches = not args.model or local.get("model") == args.model
            checks.append(
                report(
                    "local model ready",
                    status_response.is_success
                    and local.get("state") == "ready"
                    and model_matches,
                    local,
                )
            )
            if not checks[-1]:
                raise RuntimeError(
                    "The configured local model is not ready; chat tests were not run."
                )

            chat_response = client.post(
                f"{base_url}/api/chat",
                json={
                    "message": (
                        "How many days are in a week? Answer with the number "
                        "and one short sentence of study advice."
                    ),
                    "language": "English (South Africa)",
                    "simpleLanguage": True,
                    "history": [],
                },
            )
            chat_body = chat_response.json()
            reply = chat_body.get("reply", "")
            useful = "7" in reply or "seven" in reply.lower()
            checks.append(
                report(
                    "real chat response",
                    chat_response.is_success and useful,
                    f"HTTP {chat_response.status_code}: {reply[:400]!r}",
                )
            )
            checks.append(
                report(
                    "chat response metadata",
                    chat_body.get("provider") == "local"
                    and (not args.model or chat_body.get("model") == args.model),
                    {
                        "provider": chat_body.get("provider"),
                        "model": chat_body.get("model"),
                    },
                )
            )
            checks.append(
                report(
                    "no private reasoning in chat reply",
                    "<think>" not in reply.lower(),
                    "checked response text",
                )
            )

            brain_response = client.post(
                f"{base_url}/api/brain/ask",
                json={
                    "module": "general",
                    "task": "Answer a simple factual question",
                    "input": "How many days are in a week? Answer briefly.",
                    "context": {},
                },
            )
            brain_body = brain_response.json()
            answer = brain_body.get("answer", "")
            checks.append(
                report(
                    "Brain structured response",
                    brain_response.is_success
                    and isinstance(answer, str)
                    and bool(answer.strip())
                    and isinstance(brain_body.get("actions"), list),
                    f"HTTP {brain_response.status_code}: {brain_body}",
                )
            )
            checks.append(
                report(
                    "Brain response metadata",
                    brain_body.get("provider") == "local"
                    and brain_body.get("module") == "general"
                    and (not args.model or brain_body.get("model") == args.model),
                    {
                        "provider": brain_body.get("provider"),
                        "model": brain_body.get("model"),
                        "module": brain_body.get("module"),
                    },
                )
            )

            voice_response = client.post(
                f"{base_url}/api/voice/cleanup",
                json={
                    "raw_text": "um please call me tomorrow",
                    "language": "English (South Africa)",
                    "style": "standard",
                },
            )
            voice_body = voice_response.json()
            clean_text = voice_body.get("clean_text")
            checks.append(
                report(
                    "live dictation cleanup",
                    voice_response.is_success
                    and voice_body.get("cleanup_status") == "done"
                    and isinstance(clean_text, str)
                    and bool(clean_text.strip()),
                    f"HTTP {voice_response.status_code}: {voice_body}",
                )
            )
    except (httpx.HTTPError, ValueError, RuntimeError) as cause:
        checks.append(report("live test completed", False, str(cause)))

    passed = all(checks) and bool(checks)
    print("RESULT:", "ALL PASSED" if passed else "FAILURES - live model NOT verified")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
