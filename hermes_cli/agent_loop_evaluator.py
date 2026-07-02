"""Deterministic evaluator for autonomous AI development loop evidence ledgers.

The evaluator deliberately treats AI self-report as claims, not evidence.  A loop
run only passes when required checks, traceability, claim verification, and
fix/recheck gates are backed by ledger entries.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping

from hermes_cli.agent_loop_capture import append_evaluation_result, normalize_required_checks, utc_now


DEFAULT_ACCEPTANCE: dict[str, float | int] = {
    "plan_coverage_min": 0.95,
    "traceability_min": 0.95,
    "check_execution_rate_min": 1.0,
    "fix_responsiveness_min": 1.0,
    "recheck_rate_min": 1.0,
    "claim_verification_min": 1.0,
    "contradicted_claims_max": 0,
    "unsupported_completion_claims_max": 0,
    "unresolved_critical_findings_max": 0,
    "new_test_failures_max": 0,
    "schema_validation_max": 0,
    "declared_checks_executed_min": 1.0,
    "evidence_freshness_min": 1.0,
    "minimum_content_min": 1.0,
    "finding_waivers_approved_min": 1.0,
    "claim_evidence_resolvable_min": 1.0,
    "regression_evidence_min": 1.0,
}


@dataclass(frozen=True)
class MetricResult:
    score: float
    threshold: float
    passed: bool
    detail: str


@dataclass(frozen=True)
class BlockingFailure:
    metric: str
    reason: str
    severity: str = "blocker"


@dataclass(frozen=True)
class RepairTask:
    id: str
    metric: str
    instruction: str


@dataclass(frozen=True)
class EvaluationResult:
    verdict: str
    score: float
    metrics: dict[str, MetricResult]
    blocking_failures: list[BlockingFailure] = field(default_factory=list)
    repair_tasks: list[RepairTask] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_ledger(path: str | Path) -> dict[str, Any]:
    ledger_path = Path(path)
    with ledger_path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("Evidence ledger must be a JSON object")
    data["__ledger_path"] = str(ledger_path.resolve())
    return data


def _items(ledger: Mapping[str, Any], key: str) -> list[dict[str, Any]]:
    value = ledger.get(key, [])
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def validate_ledger_schema(ledger: Mapping[str, Any]) -> list[str]:
    violations: list[str] = []
    if ledger.get("schema_version") != 2:
        violations.append("schema_version must be 2")
    for key in ("requirements", "tasks", "checks", "findings", "claims", "evaluations", "repairs", "usage_events", "ai_decision_logs"):
        value = ledger.get(key, [])
        if not isinstance(value, list):
            violations.append(f"{key} must be a list")
            continue
        for index, item in enumerate(value):
            if not isinstance(item, dict):
                violations.append(f"{key}[{index}] must be an object")
    scope = ledger.get("scope")
    if not isinstance(scope, dict):
        violations.append("scope must be an object")
    machine = ledger.get("machine_evidence")
    if not isinstance(machine, dict):
        violations.append("machine_evidence must be an object")
    else:
        for key in ("git_snapshots", "pr_snapshots"):
            value = machine.get(key, [])
            if not isinstance(value, list):
                violations.append(f"machine_evidence.{key} must be a list")
            else:
                for index, item in enumerate(value):
                    if not isinstance(item, dict):
                        violations.append(f"machine_evidence.{key}[{index}] must be an object")
    if ledger.get("regressions") is not None and not isinstance(ledger.get("regressions"), dict):
        violations.append("regressions must be an object")
    return violations


def _has_evidence(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return any(_has_evidence(item) for item in value)
    if isinstance(value, dict):
        return any(_has_evidence(item) for item in value.values())
    return value is not None


def _evidence_file_exists(ledger: Mapping[str, Any], evidence_path: Any) -> bool:
    if not isinstance(evidence_path, str) or not evidence_path.strip():
        return False
    ledger_path = ledger.get("__ledger_path")
    if not isinstance(ledger_path, str) or not ledger_path:
        return True
    path = Path(evidence_path)
    if not path.is_absolute():
        path = Path(ledger_path).parent / path
    return path.is_file()


def _has_machine_check_evidence(check: Mapping[str, Any], ledger: Mapping[str, Any]) -> bool:
    """Return true only for source-of-truth command evidence, not AI text."""

    if check.get("source") != "machine":
        return False
    if not isinstance(check.get("command"), str) or not check.get("command", "").strip():
        return False
    if not isinstance(check.get("cwd"), str) or not check.get("cwd", "").strip():
        return False
    if "exit_code" not in check:
        return False
    if check.get("timed_out") is True:
        return False
    evidence = check.get("evidence")
    if not isinstance(evidence, dict):
        return False
    return _evidence_file_exists(ledger, evidence.get("stdout_log")) and _evidence_file_exists(
        ledger, evidence.get("stderr_log")
    )


def _latest_git_snapshot(ledger: Mapping[str, Any]) -> dict[str, Any] | None:
    machine = ledger.get("machine_evidence")
    if not isinstance(machine, dict):
        return None
    snapshots = machine.get("git_snapshots")
    if not isinstance(snapshots, list):
        return None
    for item in reversed(snapshots):
        if isinstance(item, dict):
            return item
    return None


def _fresh_machine_check(check: Mapping[str, Any], ledger: Mapping[str, Any]) -> bool:
    snapshot = _latest_git_snapshot(ledger)
    if not snapshot:
        return False
    return (
        _has_machine_check_evidence(check, ledger)
        and check.get("executed") is True
        and check.get("exit_code") == 0
        and check.get("timed_out") is not True
        and check.get("commit") == snapshot.get("head_commit")
        and snapshot.get("dirty") is False
    )


def _resolves_evidence_ref(ledger: Mapping[str, Any], ref: Any) -> bool:
    if not isinstance(ref, str) or not ref.strip():
        return False
    checks = {str(item.get("id")) for item in _items(ledger, "checks") if item.get("id")}
    snapshot_ids: set[str] = set()
    machine = ledger.get("machine_evidence")
    if isinstance(machine, dict):
        for key in ("git_snapshots", "pr_snapshots"):
            values = machine.get(key, [])
            if isinstance(values, list):
                snapshot_ids.update(str(item.get("id")) for item in values if isinstance(item, dict) and item.get("id"))
    return ref in checks or ref in snapshot_ids or _evidence_file_exists(ledger, ref)


def _waiver_is_approved(finding: Mapping[str, Any]) -> bool:
    approved_by = str(finding.get("approved_by") or "").strip()
    reason = str(finding.get("reason") or "").strip()
    disallowed = {"ai", "agent", "assistant", "llm", "claude", "controller", "bot"}
    return bool(approved_by and reason and approved_by.lower() not in disallowed)


def _ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 1.0
    return numerator / denominator


def _metric(score: float, threshold: float, detail: str, *, at_most: bool = False) -> MetricResult:
    passed = score <= threshold if at_most else score >= threshold
    return MetricResult(score=round(score, 4), threshold=threshold, passed=passed, detail=detail)


def _repair_task(metric: str, instruction: str, index: int) -> RepairTask:
    return RepairTask(id=f"REPAIR-{index:03d}", metric=metric, instruction=instruction)


def evaluate_ledger(
    ledger: Mapping[str, Any],
    acceptance: Mapping[str, float | int] | None = None,
) -> EvaluationResult:
    """Evaluate a ledger and return fail-closed metrics plus repair tasks.

    Ledger conventions are intentionally simple JSON:
    - requirements: planned/implemented/evidence
    - tasks: implemented/evidence
    - checks: required/executed/exit_code/evidence
    - findings: severity/status/fix_evidence/recheck_evidence
    - claims: kind/status/evidence
    - regressions: {new_failures: int}
    """

    criteria = {**DEFAULT_ACCEPTANCE, **dict(acceptance or {})}
    requirements = _items(ledger, "requirements")
    tasks = _items(ledger, "tasks")
    checks = _items(ledger, "checks")
    findings = _items(ledger, "findings")
    claims = _items(ledger, "claims")

    planned_reqs = sum(1 for req in requirements if req.get("planned") is True)
    implemented_reqs = sum(
        1
        for req in requirements
        if req.get("implemented") is True and _has_evidence(req.get("evidence"))
    )
    traced_tasks = sum(
        1
        for task in tasks
        if task.get("implemented") is True and _has_evidence(task.get("evidence"))
    )

    schema_violations = validate_ledger_schema(ledger)
    scope = ledger.get("scope") if isinstance(ledger.get("scope"), dict) else {}
    declared_checks = normalize_required_checks(scope.get("required_checks") if isinstance(scope, dict) else [])
    declared_ids = {check["id"] for check in declared_checks}
    required_checks = [check for check in checks if check.get("required", True) is not False]
    executed_required_checks = [
        check
        for check in required_checks
        if _fresh_machine_check(check, ledger)
    ]
    checks_by_id = {str(check.get("id")): check for check in checks if check.get("id")}
    executed_declared_checks = [check_id for check_id in declared_ids if _fresh_machine_check(checks_by_id.get(check_id, {}), ledger)]
    latest_snapshot = _latest_git_snapshot(ledger)
    fresh_checks = [check for check in checks if _fresh_machine_check(check, ledger)]

    invalid_waived_findings = [
        finding for finding in findings if str(finding.get("status", "")).lower() in {"accepted_risk", "deferred"} and not _waiver_is_approved(finding)
    ]
    actionable_findings = [
        finding
        for finding in findings
        if str(finding.get("status", "")).lower() not in {"accepted_risk", "deferred"} or finding in invalid_waived_findings
    ]
    fixed_findings = [
        finding
        for finding in actionable_findings
        if str(finding.get("status", "")).lower() == "fixed"
        and _has_evidence(finding.get("fix_evidence"))
    ]
    rechecked_fixed_findings = [
        finding for finding in fixed_findings if _has_evidence(finding.get("recheck_evidence"))
    ]

    verified_claims_raw = [
        claim
        for claim in claims
        if str(claim.get("status", "")).lower() == "verified"
        and _has_evidence(claim.get("evidence"))
    ]
    verified_claims = [claim for claim in verified_claims_raw if all(_resolves_evidence_ref(ledger, ref) for ref in (claim.get("evidence") if isinstance(claim.get("evidence"), list) else [claim.get("evidence")]))]
    unresolved_verified_claims = [claim for claim in verified_claims_raw if claim not in verified_claims]
    contradicted_claims = [
        claim for claim in claims if str(claim.get("status", "")).lower() == "contradicted"
    ]
    unsupported_completion_claims = [
        claim
        for claim in claims
        if str(claim.get("kind", "")).lower() == "completion"
        and str(claim.get("status", "")).lower() in {"unsupported", "ambiguous", ""}
    ]
    unresolved_critical_findings = [
        finding
        for finding in findings
        if str(finding.get("severity", "")).lower() in {"critical", "blocker"}
        and str(finding.get("status", "")).lower() not in {"fixed", "accepted_risk", "deferred"}
    ]

    regressions = ledger.get("regressions", {})
    if not isinstance(regressions, dict):
        regressions = {}
    new_failures = int(regressions.get("new_failures") or 0)
    regression_ok = (
        regressions.get("source") == "machine"
        and latest_snapshot is not None
        and regressions.get("head_commit") == latest_snapshot.get("head_commit")
    )
    minimum_parts = [
        planned_reqs >= 1,
        len(declared_ids) >= 1,
        latest_snapshot is not None,
        any(str(claim.get("kind", "")).lower() == "completion" for claim in claims),
    ]

    metrics = {
        "schema_validation": _metric(
            float(len(schema_violations)),
            float(criteria["schema_validation_max"]),
            "; ".join(schema_violations) or "schema valid",
            at_most=True,
        ),
        "minimum_content": _metric(
            _ratio(sum(1 for item in minimum_parts if item), len(minimum_parts)),
            float(criteria["minimum_content_min"]),
            "requires planned requirement, declared check, git snapshot, and completion claim",
        ),
        "plan_coverage": _metric(
            _ratio(planned_reqs, len(requirements)),
            float(criteria["plan_coverage_min"]),
            f"{planned_reqs}/{len(requirements)} requirements planned",
        ),
        "traceability": _metric(
            _ratio(implemented_reqs + traced_tasks, len(requirements) + len(tasks)),
            float(criteria["traceability_min"]),
            f"{implemented_reqs}/{len(requirements)} requirements and {traced_tasks}/{len(tasks)} tasks have implementation evidence",
        ),
        "check_execution_rate": _metric(
            _ratio(len(executed_required_checks), len(required_checks)),
            float(criteria["check_execution_rate_min"]),
            f"{len(executed_required_checks)}/{len(required_checks)} required checks passed with evidence",
        ),
        "declared_checks_executed": _metric(
            _ratio(len(executed_declared_checks), len(declared_ids)),
            float(criteria["declared_checks_executed_min"]),
            f"{len(executed_declared_checks)}/{len(declared_ids)} declared required checks passed with fresh machine evidence",
        ),
        "evidence_freshness": _metric(
            1.0 if latest_snapshot and latest_snapshot.get("dirty") is False and len(fresh_checks) == len([c for c in checks if c.get("required", True) is not False]) else 0.0,
            float(criteria["evidence_freshness_min"]),
            "latest git snapshot must exist, be clean, and required check commits must match it",
        ),
        "fix_responsiveness": _metric(
            _ratio(len(fixed_findings), len(actionable_findings)),
            float(criteria["fix_responsiveness_min"]),
            f"{len(fixed_findings)}/{len(actionable_findings)} actionable findings fixed with evidence",
        ),
        "recheck_rate": _metric(
            _ratio(len(rechecked_fixed_findings), len(fixed_findings)),
            float(criteria["recheck_rate_min"]),
            f"{len(rechecked_fixed_findings)}/{len(fixed_findings)} fixed findings rechecked",
        ),
        "claim_verification": _metric(
            _ratio(len(verified_claims), len(claims)),
            float(criteria["claim_verification_min"]),
            f"{len(verified_claims)}/{len(claims)} claims verified with evidence",
        ),
        "claim_evidence_resolvable": _metric(
            _ratio(len(verified_claims), len(verified_claims_raw)),
            float(criteria["claim_evidence_resolvable_min"]),
            f"{len(unresolved_verified_claims)} verified claims have unresolved evidence references",
        ),
        "contradicted_claims": _metric(
            float(len(contradicted_claims)),
            float(criteria["contradicted_claims_max"]),
            f"{len(contradicted_claims)} contradicted claims",
            at_most=True,
        ),
        "unsupported_completion_claims": _metric(
            float(len(unsupported_completion_claims)),
            float(criteria["unsupported_completion_claims_max"]),
            f"{len(unsupported_completion_claims)} unsupported/ambiguous completion claims",
            at_most=True,
        ),
        "unresolved_critical_findings": _metric(
            float(len(unresolved_critical_findings)),
            float(criteria["unresolved_critical_findings_max"]),
            f"{len(unresolved_critical_findings)} unresolved critical/blocker findings",
            at_most=True,
        ),
        "new_test_failures": _metric(
            float(new_failures),
            float(criteria["new_test_failures_max"]),
            f"{new_failures} new test failures",
            at_most=True,
        ),
        "finding_waivers_approved": _metric(
            1.0 if not invalid_waived_findings else 0.0,
            float(criteria["finding_waivers_approved_min"]),
            f"{len(invalid_waived_findings)} deferred/accepted_risk findings lack human approval",
        ),
        "regression_evidence": _metric(
            1.0 if regression_ok else 0.0,
            float(criteria["regression_evidence_min"]),
            "regressions must be source=machine and match latest git snapshot head_commit",
        ),
    }

    failures: list[BlockingFailure] = []
    repairs: list[RepairTask] = []
    for name, metric in metrics.items():
        if metric.passed:
            continue
        failures.append(BlockingFailure(metric=name, reason=metric.detail))
        repairs.append(_repair_for_metric(name, metric.detail, len(repairs) + 1))

    # Weighted score is informational only. Any failed hard gate still fails the run.
    weights = {
        "plan_coverage": 0.15,
        "traceability": 0.15,
        "check_execution_rate": 0.15,
        "fix_responsiveness": 0.15,
        "recheck_rate": 0.10,
        "claim_verification": 0.20,
        "contradicted_claims": 0.05,
        "unsupported_completion_claims": 0.03,
        "unresolved_critical_findings": 0.01,
        "new_test_failures": 0.01,
        "schema_validation": 0.0,
        "minimum_content": 0.0,
        "declared_checks_executed": 0.0,
        "evidence_freshness": 0.0,
        "finding_waivers_approved": 0.0,
        "claim_evidence_resolvable": 0.0,
        "regression_evidence": 0.0,
    }
    normalized = 0.0
    for name, weight in weights.items():
        metric = metrics[name]
        if name in {"contradicted_claims", "unsupported_completion_claims", "unresolved_critical_findings", "new_test_failures"}:
            component = 1.0 if metric.passed else 0.0
        else:
            component = min(metric.score / metric.threshold, 1.0) if metric.threshold else 1.0
        normalized += component * weight

    return EvaluationResult(
        verdict="PASS" if not failures else "FAIL",
        score=round(normalized * 100, 2),
        metrics=metrics,
        blocking_failures=failures,
        repair_tasks=repairs,
    )


def _repair_for_metric(metric: str, detail: str, index: int) -> RepairTask:
    instructions = {
        "plan_coverage": (
            "Extract every missing requirement from the issue/spec and add concrete plan tasks "
            "with file paths, verification commands, and acceptance criteria. Re-run evaluation."
        ),
        "traceability": (
            "For each untraced requirement/task, attach deterministic evidence from git diff, "
            "file contents, commits, or implement the missing work. Do not mark complete without evidence."
        ),
        "check_execution_rate": (
            "Do not hand-write check evidence. Let the controller or ledger-run capture required machine checks, then re-evaluate."
        ),
        "schema_validation": "Fix the ledger JSON/schema shape. schema_version must be 2 and list entries must be objects.",
        "minimum_content": "Add at least one planned requirement, declared required check, git snapshot, and completion claim.",
        "declared_checks_executed": "Ensure every scope.required_checks id is runnable and captured by the controller with fresh machine evidence.",
        "evidence_freshness": "Commit or clean relevant changes, then let the controller rerun checks and capture a fresh git snapshot.",
        "finding_waivers_approved": "Either fix the finding or add a human approved_by and reason for accepted_risk/deferred.",
        "claim_evidence_resolvable": "Point verified claims at a real check id, snapshot id, or existing evidence file.",
        "regression_evidence": "Run agent-loop-regression so regressions are machine-computed for the current snapshot.",
        "fix_responsiveness": (
            "Fix only unresolved actionable findings. Attach fix evidence for each finding, "
            "or explicitly mark as deferred/accepted_risk with a reason if human approval is required."
        ),
        "recheck_rate": (
            "Rerun the original check for every fixed finding. Attach recheck evidence. "
            "If the recheck fails, mark the finding unresolved and repair again."
        ),
        "claim_verification": (
            "For each unsupported claim, provide deterministic evidence or downgrade/remove the claim. "
            "For contradicted claims, correct the report and keep the run failed until repaired."
        ),
        "contradicted_claims": (
            "Correct every contradicted claim against source-of-truth evidence. Do not claim completion "
            "until the contradiction is resolved and verified."
        ),
        "unsupported_completion_claims": (
            "Attach source-of-truth evidence for each completion claim, or downgrade the completion report. "
            "Unsupported completion claims block completion."
        ),
        "unresolved_critical_findings": (
            "Resolve all critical/blocker findings with fix evidence and recheck evidence, or stop and escalate to the user."
        ),
        "new_test_failures": (
            "Fix new regressions introduced by this loop run. Record before/after test output and rerun evaluation."
        ),
    }
    return _repair_task(metric, f"{instructions.get(metric, 'Repair this failed metric.')} Failure detail: {detail}", index)


def _format_markdown(result: EvaluationResult) -> str:
    lines = [
        "# Agent Loop Evaluation Report",
        "",
        f"- Overall Verdict: {result.verdict}",
        f"- Loop Quality Score: {result.score}/100",
        f"- Blocking Failures: {len(result.blocking_failures)}",
        "",
        "## Scorecard",
        "",
        "| Metric | Score | Threshold | Pass | Detail |",
        "|---|---:|---:|:---:|---|",
    ]
    for name, metric in result.metrics.items():
        lines.append(
            f"| {name} | {metric.score} | {metric.threshold} | {'✅' if metric.passed else '❌'} | {metric.detail} |"
        )
    if result.blocking_failures:
        lines.extend(["", "## Blocking Failures", ""])
        for failure in result.blocking_failures:
            lines.append(f"- **{failure.metric}**: {failure.reason}")
    if result.repair_tasks:
        lines.extend(["", "## Deterministic Repair Tasks", ""])
        for task in result.repair_tasks:
            lines.append(f"### {task.id}: {task.metric}")
            lines.append(task.instruction)
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate an autonomous AI development loop Evidence Ledger")
    parser.add_argument("ledger", type=Path, help="Path to evidence-ledger.json")
    parser.add_argument("--format", choices=["json", "markdown"], default="markdown")
    parser.add_argument("--output", type=Path, help="Optional output path for the report")
    parser.add_argument("--json-output", type=Path, help="Write full evaluator JSON here")
    parser.add_argument("--summary-output", type=Path, help="Write dashboard run summary JSON here")
    parser.add_argument("--record", action="store_true", help="Append this evaluation result to ledger.evaluations[]")
    parser.add_argument("--trigger", default="manual", help="Trigger label used when --record is set")
    parser.add_argument("--allow-fail", action="store_true", help="Always exit 0 after writing the report")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        ledger = load_ledger(args.ledger)
        result = evaluate_ledger(ledger)
    except json.JSONDecodeError as exc:
        result = EvaluationResult(
            verdict="FAIL",
            score=0.0,
            metrics={"schema_validation": MetricResult(1.0, 0.0, False, f"invalid JSON: {exc}")},
            blocking_failures=[BlockingFailure(metric="schema_validation", reason=f"invalid JSON: {exc}")],
            repair_tasks=[_repair_for_metric("schema_validation", str(exc), 1)],
        )
        ledger = {"loop_run_id": None}
    if args.record:
        append_evaluation_result(ledger_path=args.ledger, result=result, trigger=args.trigger)
    rendered = json.dumps(result.to_dict(), indent=2, ensure_ascii=False) if args.format == "json" else _format_markdown(result)
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    if args.json_output:
        args.json_output.write_text(json.dumps(result.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.summary_output:
        raw = args.ledger.read_bytes()
        summary = {
            "verdict": result.verdict,
            "score": result.score,
            "blocking_failures": [asdict(failure) for failure in result.blocking_failures],
            "ledger_sha256": hashlib.sha256(raw).hexdigest(),
            "loop_run_id": ledger.get("loop_run_id"),
            "generated_at": utc_now(),
        }
        args.summary_output.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.allow_fail:
        return 0
    return 0 if result.verdict == "PASS" else 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
