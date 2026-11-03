import json
import re
from typing import Any

import httpx

from ..config import Settings

_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)
_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)

SYSTEM_PROMPT = (
    "You are LIFEKEY AI, an accessible practical problem-solving assistant and "
    "learning companion. Support coding in Python, JavaScript, HTML, and CSS. "
    "Explain code for beginners, identify likely bugs, show corrected examples, "
    "and suggest simple tests. For problem statements, identify the core problem, "
    "context, likely causes, evidence, desired outcome, and measurable success "
    "criteria; separate facts from assumptions. For documents, provide a plain "
    "language summary, purpose, strengths, unclear information, questions to verify, "
    "and prioritised improvements. Respect the user's preferred language and "
    "simple-language preference. Be specific, supportive, concise, and honest about "
    "uncertainty. Never invent official requirements, deadlines, job vacancies, "
    "prices, legal rules, or medical facts. Do not claim to perform external actions "
    "or access local files. Avoid asking for sensitive personal information unless "
    "essential. When enough information is available and a plan is useful, include "
    "3 to 7 realistic ordered steps with specific titles and helpful details. If "
    "essential information is missing, ask one useful clarifying question and omit "
    "the plan. Answer naturally in plain language; do not wrap ordinary answers in "
    "JSON."
)


class ProviderError(Exception):
    """Raised when the local model cannot produce a usable answer."""


class OllamaProvider:
    name = "local"

    def __init__(
        self,
        settings: Settings,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.base = settings.ollama_base_url.rstrip("/")
        self.model = settings.ollama_model
        self.think = settings.ollama_think
        self.timeout = settings.request_timeout_s
        self._transport = transport

    def _client(self, timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=timeout, transport=self._transport)

    async def status(self) -> dict[str, str | None]:
        try:
            async with self._client(3.0) as client:
                response = await client.get(f"{self.base}/api/tags")
                response.raise_for_status()
                models = [
                    model.get("name", "")
                    for model in response.json().get("models", [])
                ]
        except (httpx.HTTPError, ValueError):
            return {
                "state": "unreachable",
                "model": self.model,
                "detail": "Ollama is not reachable. Start Ollama and try again.",
            }

        wanted = self.model if ":" in self.model else f"{self.model}:"
        if not any(name == self.model or name.startswith(wanted) for name in models):
            return {
                "state": "model_missing",
                "model": self.model,
                "detail": f"Model '{self.model}' is not downloaded in Ollama.",
            }
        return {
            "state": "ready",
            "model": self.model,
            "detail": "Ollama is reachable and the configured model is available.",
        }

    async def chat(
        self,
        messages: list[dict[str, str]],
        schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        body = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "think": self.think,
        }
        if schema is not None:
            body["format"] = schema
        try:
            async with self._client(self.timeout) as client:
                response = await client.post(f"{self.base}/api/chat", json=body)
                response.raise_for_status()
                content = response.json()["message"]["content"]
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as cause:
            raise ProviderError(
                f"The local model request failed ({type(cause).__name__})."
            ) from cause

        text = _THINK.sub("", content).strip()
        fenced = _FENCE.match(text)
        if fenced:
            text = fenced.group(1)
        if not text:
            raise ProviderError("The local model returned an empty answer.")
        try:
            result = json.loads(text)
        except ValueError:
            if schema is not None:
                return {"_raw": text}
            result = {"reply": text}

        if not isinstance(result, dict):
            if schema is not None:
                return {"_raw": text}
            result = {"reply": text}

        if schema is not None:
            answer = result.get("answer")
            if not isinstance(answer, str):
                return {"_raw": text}
            result["answer"] = answer.strip()
            return result

        reply = result.get("reply")
        if not isinstance(reply, str) or not reply.strip():
            return {"reply": text}
        result["reply"] = reply.strip()
        return result
