import json
import subprocess
import sys

import pytest

from hermes_cli.agent_loop_ledger_update import apply_updates
from hermes_cli.agent_loop_evaluator import evaluate_ledger, load_ledger


def test_apply_updates_upserts_semantic_entries(tmp_path):
    ledger = tmp_path / "evidence-ledger.json"
    updates = {
        "requirements": [
            {"id": "REQ-001", "text": "Feature works", "planned": True, "implemented": False, "evidence": []}
        ],
        "tasks": [
            {"id": "TASK-001", "text": "Implement feature", "requirements": ["REQ-001"], "implemented": False}
        ],
        "findings": [
            {"id": "FINDING-001", "source": "review", "severity": "important", "status": "open", "text": "Missing edge case"}
        ],
        "claims": [
            {"id": "CLAIM-001", "text": "Feature is complete", "kind": "completion", "status": "unsupported"}
        ],
    }

    summary = apply_updates(ledger, updates)

    assert summary["updated"]["requirements"] == {"created": 1, "updated": 0}
    data = json.loads(ledger.read_text(encoding="utf-8"))
    assert data["requirements"][0]["source"] == "annotation"
    assert data["tasks"][0]["source"] == "annotation"
    assert data["findings"][0]["status"] == "open"
    assert data["claims"][0]["status"] == "unsupported"
    assert data["regressions"] == {"new_failures": 0}


def test_apply_updates_updates_existing_by_id(tmp_path):
    ledger = tmp_path / "evidence-ledger.json"
    apply_updates(ledger, {"requirements": [{"id": "REQ-001", "text": "A", "planned": False}]})

    apply_updates(ledger, {"requirements": [{"id": "REQ-001", "text": "A", "planned": True, "implemented": True, "evidence": ["diff:x.py"]}]})

    data = json.loads(ledger.read_text(encoding="utf-8"))
    assert len(data["requirements"]) == 1
    assert data["requirements"][0]["planned"] is True
    assert data["requirements"][0]["implemented"] is True
    assert data["requirements"][0]["evidence"] == ["diff:x.py"]
    assert "created_at" in data["requirements"][0]
    assert "updated_at" in data["requirements"][0]


def test_apply_updates_rejects_unknown_fields_in_strict_mode(tmp_path):
    with pytest.raises(ValueError, match="unknown fields"):
        apply_updates(tmp_path / "evidence-ledger.json", {"claims": [{"id": "CLAIM-001", "text": "x", "kind": "completion", "status": "verified", "surprise": True}]})


def test_semantic_update_does_not_bypass_evaluator_trust(tmp_path):
    ledger = tmp_path / "evidence-ledger.json"
    ledger.write_text(
        json.dumps(
            {
                "checks": [
                    {
                        "id": "CHECK-001",
                        "type": "test",
                        "required": True,
                        "executed": True,
                        "exit_code": 0,
                        "source": "annotation",
                        "command": "pytest",
                        "cwd": str(tmp_path),
                        "evidence": {"stdout_log": "ai.txt", "stderr_log": "ai.err"},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    apply_updates(
        ledger,
        {
            "requirements": [{"id": "REQ-001", "text": "A", "planned": True, "implemented": True, "evidence": ["diff:a.py"]}],
            "tasks": [{"id": "TASK-001", "text": "Do A", "implemented": True, "evidence": ["diff:a.py"]}],
            "claims": [{"id": "CLAIM-001", "text": "complete", "kind": "completion", "status": "verified", "evidence": ["REQ-001"]}],
        },
    )

    result = evaluate_ledger(load_ledger(ledger))

    # Semantic/annotation updates cannot satisfy machine check evidence.
    assert result.verdict == "FAIL"
    assert result.metrics["check_execution_rate"].score == 0.0


def test_ledger_update_cli_applies_inline_json(tmp_path):
    ledger = tmp_path / "evidence-ledger.json"
    payload = json.dumps({"claims": [{"id": "CLAIM-001", "text": "done", "kind": "completion", "status": "unsupported"}]})

    completed = subprocess.run(
        [sys.executable, "scripts/ledger_update.py", "--ledger", str(ledger), "--json", payload],
        cwd="/home/yappa/.hermes/hermes-agent",
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(ledger.read_text(encoding="utf-8"))["claims"][0]["id"] == "CLAIM-001"
