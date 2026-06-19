import json
from pathlib import Path

from hermes_cli.agent_loop_evaluator import evaluate_ledger, load_ledger


def _write_ledger(tmp_path: Path, data: dict) -> Path:
    logs = tmp_path / "logs"
    logs.mkdir(exist_ok=True)
    (logs / "CHECK-001.stdout.log").write_text("passed\n", encoding="utf-8")
    (logs / "CHECK-001.stderr.log").write_text("", encoding="utf-8")
    path = tmp_path / "ledger.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _passing_ledger() -> dict:
    return {
        "loop_run_id": "issue-1-test",
        "requirements": [
            {
                "id": "REQ-001",
                "text": "Add evaluator",
                "planned": True,
                "implemented": True,
                "evidence": ["diff:hermes_cli/agent_loop_evaluator.py"],
            }
        ],
        "tasks": [
            {
                "id": "TASK-001",
                "text": "Implement evaluator",
                "implemented": True,
                "evidence": ["diff:hermes_cli/agent_loop_evaluator.py"],
            }
        ],
        "checks": [
            {
                "id": "CHECK-001",
                "type": "unit-tests",
                "command": "pytest tests/cli/test_agent_loop_evaluator.py -q",
                "required": True,
                "executed": True,
                "exit_code": 0,
                "source": "machine",
                "cwd": ".",
                "branch": "feature/test",
                "commit": "abc123",
                "evidence": {
                    "stdout_log": "logs/CHECK-001.stdout.log",
                    "stderr_log": "logs/CHECK-001.stderr.log",
                },
            }
        ],
        "findings": [
            {
                "id": "FINDING-001",
                "source": "spec-review",
                "severity": "important",
                "status": "fixed",
                "fix_evidence": ["diff:fix"],
                "recheck_evidence": ["CHECK-001"],
            }
        ],
        "claims": [
            {
                "id": "CLAIM-001",
                "text": "unit tests passed",
                "kind": "completion",
                "status": "verified",
                "evidence": ["CHECK-001"],
            }
        ],
        "regressions": {"new_failures": 0},
    }


def test_evaluate_ledger_passes_when_all_hard_gates_are_satisfied(tmp_path):
    ledger_path = _write_ledger(tmp_path, _passing_ledger())

    result = evaluate_ledger(load_ledger(ledger_path))

    assert result.verdict == "PASS"
    assert result.blocking_failures == []
    assert result.metrics["check_execution_rate"].score == 1.0
    assert result.metrics["claim_verification"].score == 1.0


def test_missing_required_check_blocks_completion_and_generates_repair(tmp_path):
    ledger = _passing_ledger()
    ledger["checks"][0]["executed"] = False
    ledger["checks"][0]["exit_code"] = None
    ledger["checks"][0]["evidence"] = ""
    ledger_path = _write_ledger(tmp_path, ledger)

    result = evaluate_ledger(load_ledger(ledger_path))

    assert result.verdict == "FAIL"
    assert any(f.metric == "check_execution_rate" for f in result.blocking_failures)
    assert any("Run the missing required check" in task.instruction for task in result.repair_tasks)


def test_contradicted_completion_claim_is_fail_closed(tmp_path):
    ledger = _passing_ledger()
    ledger["claims"][0]["status"] = "contradicted"
    ledger_path = _write_ledger(tmp_path, ledger)

    result = evaluate_ledger(load_ledger(ledger_path))

    assert result.verdict == "FAIL"
    assert any(f.metric == "contradicted_claims" for f in result.blocking_failures)
    assert result.metrics["claim_verification"].score == 0.0


def test_fixed_finding_without_recheck_blocks_completion(tmp_path):
    ledger = _passing_ledger()
    ledger["findings"][0]["recheck_evidence"] = []
    ledger_path = _write_ledger(tmp_path, ledger)

    result = evaluate_ledger(load_ledger(ledger_path))

    assert result.verdict == "FAIL"
    assert any(f.metric == "recheck_rate" for f in result.blocking_failures)
    assert any("Rerun the original check" in task.instruction for task in result.repair_tasks)
