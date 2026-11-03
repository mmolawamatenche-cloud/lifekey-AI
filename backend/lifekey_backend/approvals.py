import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

SAFE_ACTIONS = {"chat.reply", "plan.create"}


@dataclass
class Approval:
    id: str
    action: str
    summary: str
    params: dict[str, Any]
    created_at: float
    status: str = "pending"

    def public(self, now: float, ttl: int) -> dict[str, Any]:
        result = asdict(self)
        result["expires_in_s"] = max(0, int(self.created_at + ttl - now))
        return result


@dataclass
class ApprovalManager:
    ttl_s: int = 300
    clock: Callable[[], float] = time.time
    log_path: str = ""
    _items: dict[str, Approval] = field(default_factory=dict)

    @staticmethod
    def is_sensitive(action: str) -> bool:
        return action not in SAFE_ACTIONS

    def _expired(self, approval: Approval) -> bool:
        return self.clock() > approval.created_at + self.ttl_s

    def _log(self, event: str, approval: Approval) -> None:
        if not self.log_path:
            return
        record = {
            "ts": self.clock(),
            "event": event,
            "id": approval.id,
            "action": approval.action,
            "summary": approval.summary,
        }
        with open(self.log_path, "a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")

    def request(self, action: str, summary: str, params: dict[str, Any]) -> Approval:
        approval = Approval(
            id=uuid.uuid4().hex,
            action=action,
            summary=summary,
            params=params,
            created_at=self.clock(),
        )
        self._log("requested", approval)
        self._items[approval.id] = approval
        return approval

    def pending(self) -> list[Approval]:
        return [
            approval
            for approval in self._items.values()
            if approval.status == "pending" and not self._expired(approval)
        ]

    def decide(self, approval_id: str, approve: bool) -> Approval | None:
        approval = self._items.get(approval_id)
        if (
            approval is None
            or approval.status != "pending"
            or self._expired(approval)
        ):
            return None
        next_status = "approved" if approve else "denied"
        self._log(next_status, approval)
        approval.status = next_status
        return approval

    def consume(self, approval_id: str, action: str) -> bool:
        approval = self._items.get(approval_id)
        if (
            approval is None
            or approval.status != "approved"
            or approval.action != action
            or self._expired(approval)
        ):
            return False
        self._log("consumed", approval)
        approval.status = "consumed"
        return True
