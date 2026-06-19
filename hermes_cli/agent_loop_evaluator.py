"""Deterministic evaluator for autonomous AI development loop evidence ledgers.

The evaluator deliberately treats AI self-report as claims, not evidence.  A loop
run only passes when required checks, traceability, claim verification, and
fix/recheck gates are backed by ledger entries.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping

from hermes_cli.agent_loop_capture import append_evaluation_result


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
    evidence = check.get("evidence")
    if not isinstance(evidence, dict):
        return False
    return _evidence_file_exists(ledger, evidence.get("stdout_log")) and _evidence_file_exists(
        ledger, evidence.get("stderr_log")
    )


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

    required_checks = [check for check in checks if check.get("required", True) is not False]
    executed_required_checks = [
        check
        for check in required_checks
        if check.get("executed") is True
        and check.get("exit_code") == 0
        and _has_machine_check_evidence(check, ledger)
    ]

    actionable_findings = [
        finding
        for finding in findings
        if str(finding.get("status", "")).lower() not in {"accepted_risk", "deferred"}
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

    verified_claims = [
        claim
        for claim in claims
        if str(claim.get("status", "")).lower() == "verified"
        and _has_evidence(claim.get("evidence"))
    ]
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

    metrics = {
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
            "Run the missing required check through scripts/ledger_run.py or equivalent machine capture. "
            "Record source=machine, cwd, branch, commit, command, exit_code, timestamps, and stdout/stderr log files. "
            "AI-authored check evidence does not count. If it fails, create findings instead of claiming completion."
        ),
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
    parser.add_argument("--record", action="store_true", help="Append this evaluation result to ledger.evaluations[]")
    parser.add_argument("--trigger", default="manual", help="Trigger label used when --record is set")
    parser.add_argument("--allow-fail", action="store_true", help="Always exit 0 after writing the report")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = evaluate_ledger(load_ledger(args.ledger))
    if args.record:
        append_evaluation_result(ledger_path=args.ledger, result=result, trigger=args.trigger)
    rendered = json.dumps(result.to_dict(), indent=2, ensure_ascii=False) if args.format == "json" else _format_markdown(result)
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    if args.allow_fail:
        return 0
    return 0 if result.verdict == "PASS" else 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
