import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError

from .ai.ollama_provider import OllamaProvider, ProviderError, SYSTEM_PROMPT
from .approvals import ApprovalManager
from .brain import prompts
from .brain.core import Brain, UnknownRole
from .config import Settings
from .schemas import (
    ActionPlan,
    ApprovalCreate,
    ApprovalDecision,
    BrainAnswer,
    BrainAsk,
    ChatRequest,
    ChatResponse,
    VoiceCleanupRequest,
    VoiceCleanupResponse,
)
from .voice.service import VoiceService

API_VERSION = "0.1.0"
logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    provider: OllamaProvider | None = None,
) -> FastAPI:
    config = settings or Settings()
    model_provider = provider or OllamaProvider(config)
    app = FastAPI(title="LIFEKEY AI Local Backend", version=API_VERSION)
    app.state.approvals = ApprovalManager(
        ttl_s=config.approval_ttl_s,
        log_path=config.approval_log_path,
    )
    app.state.brain = Brain(model_provider, app.state.approvals)
    app.state.voice = VoiceService(app.state.brain)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:5173",
            "http://localhost:5173",
            "http://127.0.0.1:4173",
            "http://localhost:4173",
            "tauri://localhost",
            "http://tauri.localhost",
        ],
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @app.get("/api/health")
    async def health():
        return {"status": "ok", "service": "LIFEKEY AI local backend", "version": API_VERSION}

    @app.get("/api/ai/status")
    async def ai_status():
        return await app.state.brain.status()

    @app.get("/api/brain/roles")
    async def brain_roles():
        return sorted(prompts.ROLES)

    @app.post("/api/chat", response_model=ChatResponse)
    async def chat(request: ChatRequest):
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        if request.messages:
            messages.extend(
                {"role": item.role, "content": item.content}
                for item in request.messages
                if item.role != "system"
            )
        else:
            messages.extend(
                {"role": item.role, "content": item.content}
                for item in request.history
            )
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"Preferred language: {request.language}.\n"
                        f"Use simple language: "
                        f"{'yes' if request.simpleLanguage else 'no'}.\n"
                        f"Current request:\n{request.message.strip()}"
                    ),
                }
            )

        try:
            result = await app.state.brain.chat(messages)
        except ProviderError as cause:
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "ai_unavailable",
                    "message": "The local AI model could not answer. Check Ollama and the selected model.",
                },
            ) from cause

        plan = None
        raw_plan = result.get("plan")
        if raw_plan is not None:
            if not isinstance(raw_plan, dict):
                logger.warning("Local model returned an action plan in an invalid format.")
            else:
                try:
                    plan = ActionPlan.model_validate(raw_plan)
                except ValidationError:
                    logger.warning("Local model returned an invalid action plan.")

        return ChatResponse(
            reply=result["reply"][:9000],
            plan=plan,
            model=config.ollama_model,
            source=request.source,
        )

    @app.post("/api/brain/ask", response_model=BrainAnswer)
    async def brain_ask(request: BrainAsk):
        try:
            result = await app.state.brain.ask(
                request.module,
                request.task,
                request.input,
                request.context,
            )
        except UnknownRole as cause:
            raise HTTPException(
                status_code=404,
                detail=f"Unknown module role '{request.module}'.",
            ) from cause
        except ProviderError as cause:
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "ai_unavailable",
                    "message": "The local AI model could not answer. Check Ollama and the selected model.",
                },
            ) from cause

        return BrainAnswer(
            answer=result.answer,
            actions=[
                {
                    "action": action.action,
                    "summary": action.summary,
                    "params": action.params,
                    "requires_approval": action.requires_approval,
                    "approval_id": action.approval_id,
                }
                for action in result.actions
            ],
            provider="local",
            model=result.model,
            module=result.module,
        )

    @app.post("/api/voice/cleanup", response_model=VoiceCleanupResponse)
    async def voice_cleanup(request: VoiceCleanupRequest):
        result = await app.state.voice.cleanup(
            request.raw_text,
            request.language,
            request.style,
            "browser-speech-recognition",
        )
        return VoiceCleanupResponse.model_validate(result)

    @app.post("/api/approvals", status_code=201)
    async def request_approval(request: ApprovalCreate):
        manager: ApprovalManager = app.state.approvals
        if not manager.is_sensitive(request.action):
            return {"requires_approval": False}
        approval = manager.request(
            request.action,
            request.summary,
            request.params,
        )
        return {
            "requires_approval": True,
            "approval": approval.public(manager.clock(), manager.ttl_s),
        }

    @app.get("/api/approvals/pending")
    async def pending_approvals():
        manager: ApprovalManager = app.state.approvals
        return [
            approval.public(manager.clock(), manager.ttl_s)
            for approval in manager.pending()
        ]

    @app.post("/api/approvals/{approval_id}/decision")
    async def decide_approval(approval_id: str, decision: ApprovalDecision):
        manager: ApprovalManager = app.state.approvals
        approval = manager.decide(approval_id, decision.approve)
        if approval is None:
            raise HTTPException(
                status_code=404,
                detail="Approval not found, already decided, or expired.",
            )
        return approval.public(manager.clock(), manager.ttl_s)

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    config = Settings()
    uvicorn.run(
        "lifekey_backend.main:app",
        host=config.host,
        port=config.port,
        reload=False,
    )
