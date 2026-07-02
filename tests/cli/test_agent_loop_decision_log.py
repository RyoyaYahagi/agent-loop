from __future__ import annotations

import json

from hermes_cli.agent_loop_decision_log import record_ai_decision


def test_record_ai_decision_appends_annotation(tmp_path) -> None:
    ledger_path = tmp_path / "evidence-ledger.json"
    ledger_path.write_text("{}", encoding="utf-8")

    entry = record_ai_decision(
        ledger_path=ledger_path,
        phase="repair_attempt_1",
        actor="ai",
        decision="Fix failing typecheck before review",
        rationale="CI reported a type error and merge guard blocks non-green checks.",
        options_considered=["handoff", "fix type error"],
        selected_option="fix type error",
        evidence_refs=["checks[CHECK-typecheck]"],
        risks=["Additional type errors may appear"],
        confidence="high",
    )

    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert entry["id"] == "DECISION-001"
    assert entry["source"] == "annotation"
    assert entry["timestamp"]
    assert ledger["ai_decision_logs"][0]["decision"] == "Fix failing typecheck before review"


def test_record_ai_decision_generates_next_id(tmp_path) -> None:
    ledger_path = tmp_path / "evidence-ledger.json"
    ledger_path.write_text('{"ai_decision_logs":[{"id":"DECISION-001"}]}', encoding="utf-8")

    entry = record_ai_decision(
        ledger_path=ledger_path,
        phase="merge_guard",
        actor="controller",
        decision="Block merge",
        rationale="Checks are missing.",
    )

    assert entry["id"] == "DECISION-002"
