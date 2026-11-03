import json

import httpx
from fastapi.testclient import TestClient

from backend.lifekey_backend.ai.ollama_provider import OllamaProvider
from backend.lifekey_backend.config import Settings
from backend.lifekey_backend.main import create_app

SEEN: list[dict] = []
ASK = {
    "module": "planner",
    "task": "Plan my week",
    "input": "I need to study",
    "context": {"goal": "finish revision"},
}


def client(reply: str, *, up: bool = True) -> TestClient:
    def handle(request: httpx.Request) -> httpx.Response:
        if not up:
            raise httpx.ConnectError("Ollama unavailable")
        if request.url.path == "/api/tags":
            return httpx.Response(
                200,
                json={"models": [{"name": "qwen3:4b"}]},
            )
        if request.url.path == "/api/chat":
            SEEN.append(json.loads(request.content))
            return httpx.Response(
                200,
                json={"message": {"content": reply}},
            )
        return httpx.Response(404)

    settings = Settings(_env_file=None, ollama_model="qwen3:4b")
    provider = OllamaProvider(settings, httpx.MockTransport(handle))
    return TestClient(create_app(settings, provider))


def test_brain_proposes_actions_and_sensitive_actions_need_approval():
    reply = json.dumps(
        {
            "answer": "Here is a plan.",
            "actions": [
                {"action": "plan.create", "summary": "Save plan", "params": {}},
                {
                    "action": "file.write",
                    "summary": "Write plan.txt",
                    "params": {"path": "plan.txt"},
                },
            ],
        }
    )
    test_client = client(reply)
    response = test_client.post("/api/brain/ask", json=ASK)
    assert response.status_code == 200
    result = response.json()
    assert result["answer"] == "Here is a plan."
    safe, sensitive = result["actions"]
    assert safe["requires_approval"] is False
    assert safe["approval_id"] is None
    assert sensitive["requires_approval"] is True
    assert sensitive["approval_id"]
    assert [
        item["id"] for item in test_client.get("/api/approvals/pending").json()
    ] == [sensitive["approval_id"]]


def test_brain_plain_text_has_no_actions_and_roles_are_available():
    test_client = client("A simple answer.")
    response = test_client.post("/api/brain/ask", json=ASK)
    assert response.status_code == 200
    assert response.json()["answer"] == "A simple answer."
    assert response.json()["actions"] == []
    assert "neurolia" in test_client.get("/api/brain/roles").json()


def test_brain_drops_invalid_and_excess_actions():
    actions = [
        {"action": "Bad Name!", "summary": "x", "params": {}},
        {"action": "file.write", "summary": "", "params": {}},
        "invalid",
        {"action": "file.write", "summary": "Write default file params"},
        {"action": "file.write", "summary": "Write file", "params": {}},
        *[
            {"action": "file.write", "summary": "Write file", "params": {}}
            for _ in range(9)
        ],
    ]
    response = client(
        json.dumps({"answer": "Done.", "actions": actions})
    ).post("/api/brain/ask", json=ASK)
    assert response.status_code == 200
    assert len(response.json()["actions"]) == 2
    assert response.json()["actions"][0]["params"] == {}


def test_brain_marks_context_untrusted_and_unknown_roles_are_rejected():
    SEEN.clear()
    test_client = client(json.dumps({"answer": "Understood.", "actions": []}))
    response = test_client.post("/api/brain/ask", json=ASK)
    assert response.status_code == 200
    messages = SEEN[-1]["messages"]
    assert SEEN[-1]["format"]["type"] == "object"
    assert set(SEEN[-1]["format"]["properties"]) == {"answer", "actions"}
    assert "action plan" in messages[0]["content"]
    assert "untrusted" in messages[1]["content"]
    assert '"goal": "finish revision"' in messages[1]["content"]
    assert test_client.post(
        "/api/brain/ask",
        json={**ASK, "module": "unknown"},
    ).status_code == 404


def test_brain_sends_schema_but_plain_chat_does_not():
    SEEN.clear()
    test_client = client(json.dumps({"answer": "OK", "actions": []}))
    brain_response = test_client.post("/api/brain/ask", json=ASK)
    assert brain_response.status_code == 200
    assert SEEN[-1]["format"]["required"] == ["answer", "actions"]

    SEEN.clear()
    chat_response = test_client.post(
        "/api/chat",
        json={"message": "Say hello.", "history": []},
    )
    assert chat_response.status_code == 200
    assert "format" not in SEEN[-1]


def test_brain_reports_ai_offline_without_fabricated_answer():
    response = client("not used", up=False).post("/api/brain/ask", json=ASK)
    assert response.status_code == 503
    assert "answer" not in response.json()
    assert response.json()["detail"]["error"] == "ai_unavailable"


def test_approval_decisions_expire_in_single_use_manager():
    test_client = client(json.dumps({"answer": "OK", "actions": []}))
    request = test_client.post(
        "/api/approvals",
        json={
            "action": "file.write",
            "summary": "Write a file",
            "params": {"path": "notes.txt"},
        },
    )
    assert request.status_code == 201
    approval_id = request.json()["approval"]["id"]
    decision = test_client.post(
        f"/api/approvals/{approval_id}/decision",
        json={"approve": True},
    )
    assert decision.status_code == 200
    assert decision.json()["status"] == "approved"
    assert test_client.post(
        f"/api/approvals/{approval_id}/decision",
        json={"approve": False},
    ).status_code == 404
