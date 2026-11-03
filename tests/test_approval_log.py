import json

import pytest

from backend.lifekey_backend.approvals import ApprovalManager


def test_log_records_lifecycle_without_private_params(tmp_path):
    log_path = tmp_path / "approvals.jsonl"
    manager = ApprovalManager(ttl_s=60, log_path=str(log_path))
    approval = manager.request(
        "file.write",
        "Write notes.txt",
        {"secret": "do-not-log"},
    )
    manager.decide(approval.id, True)
    assert manager.consume(approval.id, "file.write")

    text = log_path.read_text(encoding="utf-8")
    records = [json.loads(line) for line in text.splitlines()]
    assert [record["event"] for record in records] == [
        "requested",
        "approved",
        "consumed",
    ]
    assert all(record["action"] == "file.write" for record in records)
    assert all(record["id"] == approval.id for record in records)
    assert all(set(record) == {"ts", "event", "id", "action", "summary"} for record in records)
    assert "do-not-log" not in text
    assert "secret" not in text


def test_log_is_disabled_by_default(tmp_path):
    manager = ApprovalManager()
    manager.request("file.write", "Write notes.txt", {})
    assert list(tmp_path.iterdir()) == []


def test_log_failure_is_visible_and_does_not_add_pending_approval(tmp_path):
    manager = ApprovalManager(log_path=str(tmp_path / "missing" / "approvals.jsonl"))
    with pytest.raises(OSError):
        manager.request("file.write", "Write notes.txt", {})
    assert manager.pending() == []


def test_denial_is_logged_without_marking_action_executed(tmp_path):
    log_path = tmp_path / "approvals.jsonl"
    manager = ApprovalManager(log_path=str(log_path))
    approval = manager.request("file.write", "Write notes.txt", {})
    manager.decide(approval.id, False)

    records = [json.loads(line) for line in log_path.read_text().splitlines()]
    assert [record["event"] for record in records] == ["requested", "denied"]
