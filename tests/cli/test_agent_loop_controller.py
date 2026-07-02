import json
import sys
from pathlib import Path

from hermes_cli.agent_loop_controller import ControllerLimits, ESCALATION_EXIT_CODE, build_repair_prompt, run_controller
from hermes_cli.agent_loop_evaluator import evaluate_ledger, load_ledger


def _write_failing_check_ledger(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "loop_run_id": "test-run",
                "scope": {
                    "required_checks": [
                        {
                            "id": "CHECK-001",
                            "command_argv": [sys.executable, "-c", "raise SystemExit(1)"],
                            "cwd": str(path.parent),
                            "timeout": 10,
                            "type": "unit-tests",
                        }
                    ],
                    "required_status_checks": [],
                },
                "machine_evidence": {"git_snapshots": [], "pr_snapshots": []},
                "requirements": [{"id": "REQ-001", "text": "test", "planned": True, "implemented": True, "evidence": ["x"]}],
                "tasks": [],
                "checks": [],
                "findings": [],
                "claims": [{"id": "CLAIM-001", "text": "complete", "kind": "completion", "status": "verified", "evidence": ["CHECK-001"]}],
                "evaluations": [],
                "repairs": [],
                "usage_events": [],
                "ai_decision_logs": [],
                "regressions": {"source": "machine", "new_failures": 0, "head_commit": None},
            }
        ),
        encoding="utf-8",
    )


def test_repair_prompt_includes_hard_limits_and_tasks(tmp_path):
    ledger_path = tmp_path / "evidence-ledger.json"
    _write_failing_check_ledger(ledger_path)
    result = evaluate_ledger(load_ledger(ledger_path))

    prompt = build_repair_prompt(
        ledger_path=ledger_path,
        result=result,
        attempt=1,
        limits=ControllerLimits(max_attempts=3, max_same_failure_count=2, max_runtime_minutes=30),
    )

    assert "deterministic evaluator is the source of truth" in prompt
    assert "Attempt: 1/3" in prompt
    assert "declared_checks_executed" in prompt
    assert "controller reruns declared required checks" in prompt


def test_controller_escalates_without_repair_command_and_writes_handoff_report(tmp_path):
    ledger_path = tmp_path / "evidence-ledger.json"
    report_path = tmp_path / "handoff.md"
    _write_failing_check_ledger(ledger_path)

    exit_code = run_controller(
        ledger_path=ledger_path,
        limits=ControllerLimits(max_attempts=3, max_same_failure_count=2, max_runtime_minutes=1),
        repair_command=None,
        output_report=report_path,
    )

    assert exit_code == ESCALATION_EXIT_CODE
    report = report_path.read_text(encoding="utf-8")
    assert "Human Handoff Required" in report
    assert "no repair command configured" in report
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert ledger["controller_events"][-1]["event"] == "escalated"
    assert ledger["repairs"][0]["status"] == "escalated"


def test_controller_runs_repair_command_then_passes(tmp_path):
    ledger_path = tmp_path / "evidence-ledger.json"
    _write_failing_check_ledger(ledger_path)
    repair_script = tmp_path / "repair.py"
    repair_script.write_text(
        """
import json
import os
from pathlib import Path

ledger_path = Path(os.environ["HERMES_LEDGER_PATH"])
stdout_log = ledger_path.parent / "logs" / "CHECK-001.stdout.log"
stderr_log = ledger_path.parent / "logs" / "CHECK-001.stderr.log"
stdout_log.parent.mkdir(parents=True, exist_ok=True)
stdout_log.write_text("ok\\n", encoding="utf-8")
stderr_log.write_text("", encoding="utf-8")
ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
ledger["scope"]["required_checks"][0]["command_argv"] = [r'''""" + sys.executable + """''', "-c", "print('ok')"]
ledger_path.write_text(json.dumps(ledger), encoding="utf-8")
""".strip(),
        encoding="utf-8",
    )

    exit_code = run_controller(
        ledger_path=ledger_path,
        limits=ControllerLimits(max_attempts=3, max_same_failure_count=3, max_runtime_minutes=1),
        repair_command=f"{sys.executable} {repair_script}",
    )

    assert exit_code == 0
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert [entry["verdict"] for entry in ledger["evaluations"]] == ["FAIL", "PASS"]
    assert ledger["controller_events"][-1]["event"] == "pass"
    assert ledger["repairs"][0]["status"] == "completed"


def test_controller_escalates_when_same_failure_repeats(tmp_path):
    ledger_path = tmp_path / "evidence-ledger.json"
    _write_failing_check_ledger(ledger_path)

    exit_code = run_controller(
        ledger_path=ledger_path,
        limits=ControllerLimits(max_attempts=5, max_same_failure_count=2, max_runtime_minutes=1),
        repair_command=f"{sys.executable} -c 'print(\"no-op\")'",
    )

    assert exit_code == ESCALATION_EXIT_CODE
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert ledger["controller_events"][-1]["reason"] == "same evaluator failure repeated 2 time(s)"
