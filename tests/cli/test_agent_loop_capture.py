import json
from pathlib import Path

from hermes_cli.agent_loop_capture import (
    append_evaluation_result,
    capture_git_snapshot,
    initialize_ledger,
    record_repair_task_status,
    record_usage_event,
    run_logged_check,
    summarize_usage_events,
)
from hermes_cli.agent_loop_evaluator import evaluate_ledger, load_ledger


def test_initialize_ledger_records_loop_metadata_and_required_checks(tmp_path):
    ledger_path = tmp_path / "evidence-ledger.json"

    ledger = initialize_ledger(
        ledger_path=ledger_path,
        loop_run_id="issue-123-run",
        repo="owner/repo",
        issue="123",
        pr="456",
        branch="feature/issue-123",
        base_ref="develop",
        required_checks=["CHECK-unit:pytest -q", "typecheck"],
        deliverables=["API", "tests"],
    )

    assert ledger_path.exists()
    assert ledger["loop_run_id"] == "issue-123-run"
    assert ledger["scope"]["repo"] == "owner/repo"
    assert ledger["scope"]["issue"] == "123"
    assert ledger["scope"]["pr"] == "456"
    assert ledger["scope"]["branch"] == "feature/issue-123"
    assert ledger["scope"]["base_ref"] == "develop"
    assert ledger["schema_version"] == 2
    assert ledger["scope"]["required_checks"][0]["id"] == "CHECK-unit"
    assert ledger["scope"]["required_checks"][0]["command_argv"] == ["pytest", "-q"]
    assert ledger["scope"]["required_checks"][1]["id"] == "typecheck"
    assert ledger["scope"]["required_checks"][1]["command_argv"] is None
    assert ledger["scope"]["deliverables"] == ["API", "tests"]
    assert ledger["requirements"] == []
    assert ledger["tasks"] == []
    assert ledger["checks"] == []
    assert ledger["findings"] == []
    assert ledger["claims"] == []
    assert ledger["regressions"] == {}
    assert ledger["machine_evidence"] == {"git_snapshots": [], "pr_snapshots": []}
    assert ledger["evaluations"] == []
    assert ledger["repairs"] == []
    assert ledger["usage_events"] == []


def test_record_usage_event_tracks_phase_agent_tokens_and_cost(tmp_path):
    ledger_path = tmp_path / "evidence-ledger.json"
    ledger_path.write_text(json.dumps({"usage_events": []}), encoding="utf-8")

    event = record_usage_event(
        ledger_path=ledger_path,
        phase="repair_attempt_2",
        agent_role="subagent",
        agent_id="subagent-7",
        session_id="child-session",
        parent_session_id="parent-session",
        api_call_index=3,
        model="test-model",
        provider="test-provider",
        input_tokens=100,
        output_tokens=25,
        cache_read_tokens=40,
        cache_write_tokens=5,
        reasoning_tokens=9,
        total_tokens=125,
        estimated_cost_usd=0.0123,
        cost_status="estimated",
        cost_source="test-pricing",
        duration_seconds=1.25,
    )

    assert event["phase"] == "repair_attempt_2"
    assert event["agent_role"] == "subagent"
    assert event["agent_id"] == "subagent-7"
    assert event["parent_session_id"] == "parent-session"
    assert event["tokens"] == {
        "input": 100,
        "output": 25,
        "total": 125,
        "cache_read": 40,
        "cache_write": 5,
        "reasoning": 9,
    }
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert ledger["usage_events"][0]["estimated_cost_usd"] == 0.0123


def test_summarize_usage_events_groups_by_phase_and_agent(tmp_path):
    ledger = {"usage_events": []}
    ledger_path = tmp_path / "evidence-ledger.json"
    ledger_path.write_text(json.dumps(ledger), encoding="utf-8")
    record_usage_event(
        ledger_path=ledger_path,
        phase="plan",
        agent_role="parent",
        agent_id="parent",
        model="m",
        provider="p",
        input_tokens=10,
        output_tokens=5,
        estimated_cost_usd=0.1,
    )
    record_usage_event(
        ledger_path=ledger_path,
        phase="plan",
        agent_role="subagent",
        agent_id="child-a",
        model="m",
        provider="p",
        input_tokens=20,
        output_tokens=10,
        estimated_cost_usd=None,
    )

    summary = summarize_usage_events(json.loads(ledger_path.read_text(encoding="utf-8")))

    assert summary["event_count"] == 2
    assert summary["total"]["api_calls"] == 2
    assert summary["total"]["input_tokens"] == 30
    assert summary["total"]["output_tokens"] == 15
    assert summary["total"]["estimated_cost_usd"] == 0.1
    assert summary["total"]["unknown_cost_events"] == 1
    assert summary["by_phase"]["plan"]["total_tokens"] == 45
    assert summary["by_agent"]["child-a"]["api_calls"] == 1


def test_run_logged_check_records_machine_check_logs_and_exit_code(tmp_path):
    ledger_path = tmp_path / "evidence-ledger.json"
    ledger_path.write_text(json.dumps({"checks": []}), encoding="utf-8")

    exit_code = run_logged_check(
        ledger_path=ledger_path,
        check_id="CHECK-001",
        check_type="unit-tests",
        command=["python", "-c", "print('ok')"],
        cwd=tmp_path,
    )

    assert exit_code == 0
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    check = ledger["checks"][0]
    assert check["id"] == "CHECK-001"
    assert check["source"] == "machine"
    assert check["executed"] is True
    assert check["exit_code"] == 0
    assert check["cwd"] == str(tmp_path)
    assert check["command"] == "python -c \"print('ok')\""
    assert check["evidence"]["stdout_log"]
    assert (tmp_path / check["evidence"]["stdout_log"]).read_text(encoding="utf-8") == "ok\n"
    assert (tmp_path / check["evidence"]["stderr_log"]).exists()


def test_evaluator_rejects_ai_authored_check_as_not_executed(tmp_path):
    ledger_path = tmp_path / "evidence-ledger.json"
    ledger_path.write_text(
        json.dumps(
            {
                "requirements": [],
                "tasks": [],
                "checks": [
                    {
                        "id": "CHECK-001",
                        "type": "unit-tests",
                        "command": "pytest",
                        "required": True,
                        "executed": True,
                        "exit_code": 0,
                        "source": "ai",
                        "evidence": "AI says tests passed",
                    }
                ],
                "findings": [],
                "claims": [],
                "regressions": {"new_failures": 0},
            }
        ),
        encoding="utf-8",
    )

    result = evaluate_ledger(load_ledger(ledger_path))

    assert result.verdict == "FAIL"
    assert result.metrics["check_execution_rate"].score == 0.0
    assert any(f.metric == "check_execution_rate" for f in result.blocking_failures)


def test_capture_git_snapshot_records_machine_diff_metadata(tmp_path):
    ledger_path = tmp_path / "evidence-ledger.json"
    ledger_path.write_text(json.dumps({}), encoding="utf-8")

    (tmp_path / "tracked.txt").write_text("before\n", encoding="utf-8")
    import subprocess

    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "tracked.txt"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=tmp_path, check=True, capture_output=True, text=True)
    (tmp_path / "tracked.txt").write_text("after\n", encoding="utf-8")

    snapshot = capture_git_snapshot(ledger_path=ledger_path, cwd=tmp_path)

    assert snapshot["source"] == "machine"
    assert snapshot["head_commit"]
    assert snapshot["dirty"] is True
    assert "tracked.txt" in snapshot["changed_files"]
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert ledger["machine_evidence"]["git_snapshots"][0]["id"] == snapshot["id"]


def test_append_evaluation_result_persists_verdict_metrics_and_repairs(tmp_path):
    ledger_path = tmp_path / "evidence-ledger.json"
    ledger_path.write_text(
        json.dumps(
            {
                "requirements": [{"id": "REQ-001", "text": "Need A", "planned": False}],
                "tasks": [],
                "checks": [],
                "findings": [],
                "claims": [],
                "regressions": {"new_failures": 0},
            }
        ),
        encoding="utf-8",
    )
    result = evaluate_ledger(load_ledger(ledger_path))

    entry = append_evaluation_result(ledger_path=ledger_path, result=result, trigger="manual")

    assert entry["source"] == "deterministic_evaluator"
    assert entry["trigger"] == "manual"
    assert entry["verdict"] == "FAIL"
    assert "plan_coverage" in entry["metrics"]
    assert entry["blocking_failures"]
    assert entry["repair_tasks"]
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert ledger["evaluations"][0]["id"] == entry["id"]


def test_record_repair_task_status_tracks_lifecycle(tmp_path):
    ledger_path = tmp_path / "evidence-ledger.json"
    ledger_path.write_text(json.dumps({}), encoding="utf-8")

    started = record_repair_task_status(
        ledger_path=ledger_path,
        repair_id="REPAIR-001",
        metric="check_execution_rate",
        instruction="Run missing checks",
        status="started",
    )
    completed = record_repair_task_status(
        ledger_path=ledger_path,
        repair_id="REPAIR-001",
        metric="check_execution_rate",
        instruction="Run missing checks",
        status="completed",
        evidence=["CHECK-001"],
    )

    assert started["created_at"]
    assert completed["updated_at"]
    assert completed["status"] == "completed"
    assert completed["evidence"] == ["CHECK-001"]
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert len(ledger["repairs"]) == 1
    assert ledger["repairs"][0]["id"] == "REPAIR-001"
