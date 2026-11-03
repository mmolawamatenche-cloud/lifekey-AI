from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class ConversationMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str = Field(min_length=1, max_length=16000)


class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=1000)


class ChatRequest(BaseModel):
    message: str | None = Field(default=None, max_length=6000)
    language: str = Field(default="English (South Africa)", max_length=80)
    simpleLanguage: bool = True
    history: list[HistoryMessage] = Field(default_factory=list, max_length=8)
    messages: list[ConversationMessage] | None = Field(default=None, max_length=50)
    source: str = Field(default="app", max_length=40)

    @model_validator(mode="after")
    def require_message(self):
        if self.messages:
            if not any(item.role == "user" for item in self.messages):
                raise ValueError("messages must contain at least one user message")
        elif not (self.message and self.message.strip()):
            raise ValueError("Please enter a message before sending.")
        return self


class PlanStep(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    detail: str = Field(max_length=500)


class ActionPlan(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(max_length=500)
    steps: list[PlanStep] = Field(min_length=3, max_length=7)


class ChatResponse(BaseModel):
    reply: str
    plan: ActionPlan | None = None
    provider: Literal["local"] = "local"
    model: str
    source: str


class BrainAsk(BaseModel):
    module: str = Field(default="general", max_length=40)
    task: str = Field(min_length=1, max_length=500)
    input: str = Field(default="", max_length=16000)
    context: dict[str, Any] = Field(default_factory=dict)


class ProposedActionOut(BaseModel):
    action: str
    summary: str
    params: dict[str, Any]
    requires_approval: bool
    approval_id: str | None


class BrainAnswer(BaseModel):
    answer: str
    actions: list[ProposedActionOut]
    provider: Literal["local"]
    model: str
    module: str


class ApprovalCreate(BaseModel):
    action: str = Field(min_length=1, max_length=80)
    summary: str = Field(min_length=1, max_length=500)
    params: dict[str, Any] = Field(default_factory=dict)


class ApprovalDecision(BaseModel):
    approve: bool


class SlangTranslation(BaseModel):
    heard: str = Field(min_length=1, max_length=500)
    meaning: str = Field(min_length=1, max_length=500)


class DictationOut(BaseModel):
    clean_text: str = Field(min_length=1, max_length=16000)
    summary: str = Field(min_length=1, max_length=2000)
    key_points: list[str] = Field(max_length=50)
    to_do: list[str] = Field(max_length=50)
    slang_translated: list[SlangTranslation] = Field(max_length=50)
    unclear: list[str] = Field(max_length=50)


class VoiceCleanupRequest(BaseModel):
    raw_text: str = Field(max_length=16000)
    language: str | None = Field(default=None, max_length=80)
    style: Literal["standard", "keep_voice"] = "standard"


class VoiceCleanupResponse(BaseModel):
    raw_text: str
    language: str | None
    stt_engine: str
    style: Literal["standard", "keep_voice"]
    cleanup_status: Literal["done", "empty", "ai_offline", "ai_invalid"]
    clean_text: str | None = None
    summary: str | None = None
    key_points: list[str] = Field(default_factory=list)
    to_do: list[str] = Field(default_factory=list)
    slang_translated: list[SlangTranslation] = Field(default_factory=list)
    unclear: list[str] = Field(default_factory=list)
    provider: str | None = None
    model: str | None = None
