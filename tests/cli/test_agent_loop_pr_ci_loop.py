from __future__ import annotations

import json

from hermes_cli.agent_loop_pr_ci_loop import MergeSafety, _record_ci_decision, base_branch_allowed


def test_base_branch_allowed_for_develop_by_default() -> None:
    allowed, reason = base_branch_allowed({"baseRefName": "develop"}, MergeSafety())

    assert allowed is True
    assert "develop" in reason


def test_base_branch_blocks_main_by_default() -> None:
    allowed, reason = base_branch_allowed({"baseRefName": "main"}, MergeSafety())

    assert allowed is False
    assert "main" in reason


def test_base_branch_allows_main_when_explicitly_enabled() -> None:
    allowed, reason = base_branch_allowed({"baseRefName": "main"}, MergeSafety(allow_main=True))

    assert allowed is True
    assert "main" in reason


def test_base_branch_blocks_unknown_base() -> None:
    allowed, reason = base_branch_allowed({"baseRefName": "feature-x"}, MergeSafety())

    assert allowed is False
    assert "allowed list" in reason


def test_ci_loop_decision_logging_is_optional_but_records_when_ledger_exists(tmp_path) -> None:
    ledger_path = tmp_path / "evidence-ledger.json"
    ledger_path.write_text("{}", encoding="utf-8")

    _record_ci_decision(
        ledger_path,
        phase="merge_guard",
        decision="Block automatic merge",
        rationale="base branch is not allowed",
        evidence_refs=["pr:1"],
    )
    _record_ci_decision(None, phase="noop", decision="ignored", rationale="no ledger")

    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert ledger["ai_decision_logs"][0]["actor"] == "ci-repair-merge-loop"
    assert ledger["ai_decision_logs"][0]["decision"] == "Block automatic merge"
