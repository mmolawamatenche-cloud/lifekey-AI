import json
import re
from dataclasses import dataclass
from typing import Any

from ..ai.ollama_provider import OllamaProvider, ProviderError
from ..approvals import ApprovalManager
from . import prompts

_ACTION_RE = re.compile(r"^[a-z][a-z_]*\.[a-z][a-z_]*$")
MAX_ACTIONS = 5


class UnknownRole(KeyError):
    pass


class AIOutputInvalid(ValueError):
    pass


class NoProviderAvailable(Exception):
    pass


@dataclass
class ProposedAction:
    action: str
    summary: str
    params: dict[str, Any]
    requires_approval: bool
    approval_id: str | None


@dataclass
class BrainResult:
    answer: str
    actions: list[ProposedAction]
    provider: str
    model: str
    module: str


class Brain:
    def __init__(self, provider: OllamaProvider, approvals: ApprovalManager):
        self._provider = provider
        self._approvals = approvals

    async def status(self) -> dict[str, Any]:
        local = await self._provider.status()
        return {
            "active": "local" if local["state"] == "ready" else "offline",
            "local": local,
            "cloud": {
                "state": "disabled",
                "model": None,
                "detail": "No cloud AI provider is configured.",
            },
        }

    async def chat(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        return await self._provider.chat(messages)

    async def ask(
        self,
        module: str,
        task: str,
        user_input: str,
        context: dict[str, Any],
    ) -> BrainResult:
        if module not in prompts.ROLES:
            raise UnknownRole(module)
        messages = [
            {"role": "system", "content": prompts.build_system(module)},
            {
                "role": "user",
                "content": prompts.build_user(task, user_input, context),
            },
        ]
        result = await self._provider.chat(
            messages,
            schema=prompts.ANSWER_SCHEMA,
        )
        raw_actions = result.get("actions")
        answer = result.get("answer")
        if not isinstance(answer, str):
            answer = result.get("_raw")
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError("The model returned an empty Brain answer.")
        return BrainResult(
            answer=answer.strip(),
            actions=self._gate(raw_actions if isinstance(raw_actions, list) else []),
            provider=self._provider.name,
            model=self._provider.model,
            module=module,
        )

    async def extract(
        self,
        module: str,
        user_input: str,
        schema: dict[str, Any],
    ) -> tuple[dict[str, Any], str, str]:
        if module not in prompts.EXTRACT_ROLES:
            raise UnknownRole(module)
        try:
            result = await self._provider.chat(
                [
                    {
                        "role": "system",
                        "content": prompts.build_extract_system(module),
                    },
                    {"role": "user", "content": user_input},
                ],
                schema=schema,
            )
        except ProviderError as cause:
            raise NoProviderAvailable from cause

        raw = result.get("_raw")
        if raw is not None:
            try:
                result = json.loads(raw)
            except (TypeError, ValueError) as cause:
                raise AIOutputInvalid("The model output was not valid JSON.") from cause
        if not isinstance(result, dict):
            raise AIOutputInvalid("The model output must be a JSON object.")
        return result, self._provider.name, self._provider.model

    def _gate(self, raw_actions: list[Any]) -> list[ProposedAction]:
        actions: list[ProposedAction] = []
        for item in raw_actions[:MAX_ACTIONS]:
            if not isinstance(item, dict):
                continue
            name = item.get("action")
            summary = item.get("summary")
            params = item.get("params", {})
            if not (
                isinstance(name, str)
                and _ACTION_RE.fullmatch(name)
                and isinstance(summary, str)
                and 0 < len(summary) <= 500
                and isinstance(params, dict)
            ):
                continue

            requires_approval = self._approvals.is_sensitive(name)
            approval = (
                self._approvals.request(name, summary, params)
                if requires_approval
                else None
            )
            actions.append(
                ProposedAction(
                    action=name,
                    summary=summary,
                    params=params,
                    requires_approval=requires_approval,
                    approval_id=approval.id if approval else None,
                )
            )
        return actions
