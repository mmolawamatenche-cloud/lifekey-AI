import asyncio
import json

import httpx
from fastapi.testclient import TestClient

from backend.lifekey_backend.ai.ollama_provider import (
    OllamaProvider,
    ProviderError,
)
from backend.lifekey_backend.config import Settings
from backend.lifekey_backend.main import create_app

SEEN: list[dict] = []


def ollama_transport(*, up=True, models=("qwen3:4b",), content=None):
    def handle(request: httpx.Request) -> httpx.Response:
        if not up:
            raise httpx.ConnectError("Ollama unavailable")
        if request.url.path == "/api/tags":
            return httpx.Response(
                200,
                json={"models": [{"name": name} for name in models]},
            )
        if request.url.path == "/api/chat":
            SEEN.append(json.loads(request.read()))
            return httpx.Response(
                200,
                json={
                    "message": {
                        "content": content
                        or json.dumps({"reply": "Hello from local AI."})
                    }
                },
            )
        return httpx.Response(404)

    return httpx.MockTransport(handle)


def make_client(transport=None):
    settings = Settings(
        _env_file=None,
        ollama_model="qwen3:4b",
        request_timeout_s=1,
    )
    provider = OllamaProvider(
        settings,
        transport=transport or ollama_transport(),
    )
    return TestClient(create_app(settings, provider))


def test_health_and_local_model_status():
    client = make_client()
    assert client.get("/api/health").json()["status"] == "ok"
    status = client.get("/api/ai/status").json()
    assert status["active"] == "local"
    assert status["local"]["state"] == "ready"
    assert status["cloud"]["state"] == "disabled"


def test_chat_accepts_existing_frontend_request_shape():
    SEEN.clear()
    client = make_client()
    response = client.post(
        "/api/chat",
        json={
            "message": "Help me plan my study week.",
            "language": "English (South Africa)",
            "simpleLanguage": True,
            "history": [{"role": "assistant", "content": "Sure."}],
        },
    )
    assert response.status_code == 200
    assert response.json()["reply"] == "Hello from local AI."
    assert response.json()["provider"] == "local"
    assert response.json()["model"] == "qwen3:4b"
    assert "format" not in SEEN[-1]


def test_chat_accepts_messages_api_and_plan():
    plan = {
        "title": "A study plan",
        "description": "Small daily steps.",
        "steps": [
            {"title": f"Step {index}", "detail": "Study for 20 minutes."}
            for index in range(1, 4)
        ],
    }
    client = make_client(
        ollama_transport(
            content=json.dumps({"reply": "Here is a plan.", "plan": plan})
        )
    )
    response = client.post(
        "/api/chat",
        json={
            "messages": [{"role": "user", "content": "Help me study."}],
            "source": "assistant",
        },
    )
    assert response.status_code == 200
    assert response.json()["plan"]["title"] == "A study plan"
    assert response.json()["source"] == "assistant"


def test_invalid_or_empty_chat_request_is_rejected():
    client = make_client()
    assert client.post("/api/chat", json={}).status_code == 422
    assert client.post("/api/chat", json={"messages": []}).status_code == 422


def test_unavailable_ollama_returns_status_and_service_error():
    client = make_client(ollama_transport(up=False))
    assert client.get("/api/ai/status").json()["local"]["state"] == "unreachable"
    response = client.post("/api/chat", json={"message": "Hi"})
    assert response.status_code == 503
    assert response.json()["detail"]["error"] == "ai_unavailable"


def test_model_missing_is_reported():
    client = make_client(ollama_transport(models=("llama3:8b",)))
    assert client.get("/api/ai/status").json()["local"]["state"] == "model_missing"


def test_plain_chat_preserves_free_form_model_text():
    provider = OllamaProvider(
        Settings(_env_file=None),
        transport=ollama_transport(content="not json"),
    )
    result = asyncio.run(provider.chat([{"role": "user", "content": "Hi"}]))
    assert result["reply"] == "not json"
