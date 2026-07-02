"""Bounded controller for CI-driven agent-loop repair.

The deterministic evaluator remains the source of truth. This controller only
orchestrates retries: evaluate the ledger, optionally run a repair command with a
prompt built from evaluator repair tasks, then re-evaluate. It stops after bounded
attempts or repeated identical failures and emits a handoff report for humans.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from hermes_cli.agent_loop_capture import (
    append_evaluation_result,
    capture_git_snapshot,
    load_ledger as capture_load_ledger,
    normalize_required_checks,
    record_repair_task_status,
    run_logged_check,
    save_ledger,
    utc_now,
)
from hermes_cli.agent_loop_decision_log import record_ai_decision
from hermes_cli.agent_loop_evaluator import EvaluationResult, evaluate_ledger, load_ledger
from hermes_cli.agent_loop_knowledge import KnowledgeEntry, record_knowledge_entry


ESCALATION_EXIT_CODE = 3


@dataclass(frozen=True)
class ControllerLimits:
    max_attempts: int = 3
    max_same_failure_count: int = 2
    max_runtime_minutes: float = 30.0


@dataclass(frozen=True)
class RepairCommandResult:
    returncode: int
    stdout: str
    stderr: str


def _failure_fingerprint(result: EvaluationResult) -> str:
    parts = [f"{failure.metric}:{failure.reason}" for failure in result.blocking_failures]
    return "\n".join(sorted(parts))


def _format_failures(result: EvaluationResult) -> str:
    if not result.blocking_failures:
        return "- none"
    return "\n".join(f"- {failure.metric}: {failure.reason}" for failure in result.blocking_failures)


def _format_repair_tasks(result: EvaluationResult) -> str:
    if not result.repair_tasks:
        return "- none"
    lines: list[str] = []
    for task in result.repair_tasks:
        lines.append(f"- {task.id} ({task.metric}): {task.instruction}")
    return "\n".join(lines)


def build_repair_prompt(
    *,
    ledger_path: Path,
    result: EvaluationResult,
    attempt: int,
    limits: ControllerLimits,
) -> str:
    """Build the prompt handed to the LLM repair process."""

    return f"""You are repairing an autonomous development loop run that failed deterministic CI evaluation.

Hard rules:
- The deterministic evaluator is the source of truth; do not claim COMPLETE unless it returns PASS.
- Execute only the repair tasks below. Do not do broad refactors or unrelated work.
- Do not record machine evidence for checks yourself. The controller reruns declared required checks and captures git snapshots.
- If a requirement is ambiguous, a secret/permission is missing, or a critical risk appears, stop and report that human handoff is required.
- Keep the Evidence Ledger at {ledger_path} updated with requirements, tasks, findings, claims, checks, and repair lifecycle evidence.

Attempt: {attempt}/{limits.max_attempts}
Repeated-failure stop threshold: {limits.max_same_failure_count}
Runtime limit: {limits.max_runtime_minutes:g} minutes
Current evaluator verdict: {result.verdict}
Score: {result.score}/100

Blocking failures:
{_format_failures(result)}

Deterministic repair tasks:
{_format_repair_tasks(result)}

After repairs, leave code and ledger annotations ready for the controller verification pass. If repair is impossible or unsafe, leave clear notes in the ledger and final output for human handoff.
""".strip() + "\n"


def _write_prompt_file(ledger_path: Path, prompt: str, attempt: int) -> Path:
    prompt_dir = ledger_path.parent / ".agent-loop" / "repair-prompts"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = prompt_dir / f"repair-attempt-{attempt}.md"
    prompt_path.write_text(prompt, encoding="utf-8")
    return prompt_path


def _mark_repairs(result: EvaluationResult, *, ledger_path: Path, status: str, notes: str | None = None) -> None:
    for task in result.repair_tasks:
        record_repair_task_status(
            ledger_path=ledger_path,
            repair_id=task.id,
            metric=task.metric,
            instruction=task.instruction,
            status=status,
            notes=notes,
        )


def _render_handoff_report(
    *,
    ledger_path: Path,
    result: EvaluationResult,
    reason: str,
    attempts: int,
    same_failure_count: int,
) -> str:
    return f"""# Agent Loop Human Handoff Required

The bounded repair controller stopped without a PASS verdict.

- Ledger: `{ledger_path}`
- Stop reason: {reason}
- Attempts used: {attempts}
- Repeated identical failure count: {same_failure_count}
- Last verdict: {result.verdict}
- Last score: {result.score}/100

## Blocking failures

{_format_failures(result)}

## Last deterministic repair tasks

{_format_repair_tasks(result)}

## Human handoff guidance

Please inspect the ledger, command logs, and changed files. The controller intentionally stopped to avoid an unbounded LLM repair loop.
""".strip() + "\n"


def _record_controller_event(
    ledger_path: Path,
    *,
    event: str,
    details: dict[str, Any],
) -> None:
    ledger = load_ledger(ledger_path)
    events = ledger.setdefault("controller_events", [])
    if not isinstance(events, list):
        events = []
        ledger["controller_events"] = events
    events.append({"event": event, "timestamp": utc_now(), **details})
    save_ledger(ledger_path, ledger)


def _record_controller_decision(
    ledger_path: Path,
    *,
    phase: str,
    decision: str,
    rationale: str,
    evidence_refs: Sequence[str] = (),
    risks: Sequence[str] = (),
) -> None:
    """Record a concise controller decision without affecting evaluator truth.

    Controller decisions are audit trail annotations. They explain why the loop
    repaired, passed, or escalated, but machine evidence and evaluator gates keep
    final authority.
    """

    record_ai_decision(
        ledger_path=ledger_path,
        phase=phase,
        actor="controller",
        decision=decision,
        rationale=rationale,
        evidence_refs=evidence_refs,
        risks=risks,
        confidence="high",
    )


def run_verification_pass(
    *,
    ledger_path: Path,
    check_cwd: Path,
    regression_base_ref: str | None = None,
    regression_test_command: str | None = None,
) -> None:
    ledger = capture_load_ledger(ledger_path)
    scope = ledger.get("scope") if isinstance(ledger.get("scope"), dict) else {}
    required_checks = normalize_required_checks(scope.get("required_checks") if isinstance(scope, dict) else [], default_cwd=check_cwd)
    for check in required_checks:
        command = check.get("command_argv")
        if not command:
            continue
        run_logged_check(
            ledger_path=ledger_path,
            check_id=str(check["id"]),
            check_type=str(check.get("type") or "command"),
            command=command,
            cwd=check.get("cwd") or check_cwd,
            required=True,
            timeout=check.get("timeout"),
        )
    if regression_base_ref and regression_test_command:
        from hermes_cli.agent_loop_regression import compute_regressions_for_git

        compute_regressions_for_git(
            ledger_path=ledger_path,
            cwd=check_cwd,
            base_ref=regression_base_ref,
            test_command=regression_test_command,
        )
    base_ref = scope.get("base_ref") if isinstance(scope, dict) else None
    capture_git_snapshot(ledger_path=ledger_path, cwd=check_cwd, base_ref=str(base_ref) if base_ref else None)


def _run_repair_command(
    *,
    command: str,
    ledger_path: Path,
    prompt_path: Path,
    attempt: int,
    timeout_seconds: int,
) -> RepairCommandResult:
    env = os.environ.copy()
    env.update(
        {
            "HERMES_LEDGER_PATH": str(ledger_path),
            "HERMES_AGENT_LOOP_REPAIR_PROMPT_FILE": str(prompt_path),
            "HERMES_AGENT_LOOP_REPAIR_ATTEMPT": str(attempt),
            "HERMES_AGENT_LOOP_PHASE": f"repair_attempt_{attempt}",
        }
    )
    formatted_command = command.format(
        ledger=shlex.quote(str(ledger_path)),
        repair_prompt_file=shlex.quote(str(prompt_path)),
        attempt=attempt,
    )
    completed = subprocess.run(
        formatted_command,
        shell=True,
        cwd=ledger_path.parent,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
        env=env,
    )
    return RepairCommandResult(completed.returncode, completed.stdout or "", completed.stderr or "")


def _default_repair_command() -> str | None:
    raw = os.getenv("HERMES_AGENT_REPAIR_COMMAND", "").strip()
    if raw:
        return raw
    return None


def run_controller(
    *,
    ledger_path: Path,
    limits: ControllerLimits = ControllerLimits(),
    repair_command: str | None = None,
    output_report: Path | None = None,
    trigger_prefix: str = "repair_controller",
    comment_pr: bool = False,
    check_cwd: Path | None = None,
    regression_base_ref: str | None = None,
    regression_test_command: str | None = None,
) -> int:
    start = time.monotonic()
    repair_command = repair_command if repair_command is not None else _default_repair_command()
    previous_fingerprint: str | None = None
    same_failure_count = 0
    last_result: EvaluationResult | None = None

    for attempt in range(1, limits.max_attempts + 1):
        verification_cwd = check_cwd or ledger_path.parent
        try:
            run_verification_pass(
                ledger_path=ledger_path,
                check_cwd=verification_cwd,
                regression_base_ref=regression_base_ref,
                regression_test_command=regression_test_command,
            )
            result = evaluate_ledger(load_ledger(ledger_path))
        except json.JSONDecodeError as exc:
            dummy = EvaluationResult(
                verdict="FAIL",
                score=0.0,
                metrics={},
                blocking_failures=[],
                repair_tasks=[],
            )
            return _escalate(
                ledger_path=ledger_path,
                result=dummy,
                reason=f"ledger JSON parse failed: {exc}",
                attempts=attempt,
                same_failure_count=same_failure_count,
                output_report=output_report,
                comment_pr=comment_pr,
            )
        last_result = result
        append_evaluation_result(ledger_path=ledger_path, result=result, trigger=f"{trigger_prefix}_attempt_{attempt}")

        if result.verdict == "PASS":
            _record_controller_decision(
                ledger_path,
                phase=f"{trigger_prefix}_attempt_{attempt}",
                decision="Report PASS and stop repair loop",
                rationale=f"Deterministic evaluator returned PASS with score {result.score}/100.",
                evidence_refs=[f"evaluations[{len(load_ledger(ledger_path).get('evaluations', [])) - 1}]"],
            )
            _record_controller_event(
                ledger_path,
                event="pass",
                details={"attempt": attempt, "score": result.score},
            )
            print(f"Agent loop evaluator PASS after {attempt} attempt(s).")
            return 0

        fingerprint = _failure_fingerprint(result)
        same_failure_count = same_failure_count + 1 if fingerprint == previous_fingerprint else 1
        previous_fingerprint = fingerprint

        if same_failure_count >= limits.max_same_failure_count:
            return _escalate(
                ledger_path=ledger_path,
                result=result,
                reason=f"same evaluator failure repeated {same_failure_count} time(s)",
                attempts=attempt,
                same_failure_count=same_failure_count,
                output_report=output_report,
                comment_pr=comment_pr,
            )

        elapsed = time.monotonic() - start
        remaining = limits.max_runtime_minutes * 60 - elapsed
        if remaining <= 0:
            return _escalate(
                ledger_path=ledger_path,
                result=result,
                reason=f"runtime exceeded {limits.max_runtime_minutes:g} minutes",
                attempts=attempt,
                same_failure_count=same_failure_count,
                output_report=output_report,
                comment_pr=comment_pr,
            )

        if attempt >= limits.max_attempts:
            return _escalate(
                ledger_path=ledger_path,
                result=result,
                reason=f"max repair attempts reached ({limits.max_attempts})",
                attempts=attempt,
                same_failure_count=same_failure_count,
                output_report=output_report,
                comment_pr=comment_pr,
            )

        if not repair_command:
            return _escalate(
                ledger_path=ledger_path,
                result=result,
                reason="no repair command configured",
                attempts=attempt,
                same_failure_count=same_failure_count,
                output_report=output_report,
                comment_pr=comment_pr,
            )

        prompt = build_repair_prompt(ledger_path=ledger_path, result=result, attempt=attempt, limits=limits)
        prompt_path = _write_prompt_file(ledger_path, prompt, attempt)
        _record_controller_decision(
            ledger_path,
            phase=f"repair_attempt_{attempt}",
            decision="Run bounded repair command for evaluator failures",
            rationale="Evaluator returned FAIL, limits were not exceeded, and a repair command is configured.",
            evidence_refs=[str(prompt_path)],
            risks=["Repair command may fail or be unable to address ambiguous requirements; controller will re-evaluate after the attempt."],
        )
        _mark_repairs(result, ledger_path=ledger_path, status="started", notes=f"controller attempt {attempt}")
        print(f"Evaluator FAIL; running repair attempt {attempt}/{limits.max_attempts - 1} with prompt {prompt_path}")
        try:
            repair = _run_repair_command(
                command=repair_command,
                ledger_path=ledger_path,
                prompt_path=prompt_path,
                attempt=attempt,
                timeout_seconds=max(1, int(remaining)),
            )
        except subprocess.TimeoutExpired:
            _mark_repairs(result, ledger_path=ledger_path, status="failed", notes="repair command timed out")
            return _escalate(
                ledger_path=ledger_path,
                result=result,
                reason="repair command timed out",
                attempts=attempt,
                same_failure_count=same_failure_count,
                output_report=output_report,
                comment_pr=comment_pr,
            )

        _record_controller_event(
            ledger_path,
            event="repair_command",
            details={
                "attempt": attempt,
                "returncode": repair.returncode,
                "stdout_tail": repair.stdout[-4000:],
                "stderr_tail": repair.stderr[-4000:],
                "prompt_path": str(prompt_path),
            },
        )
        if repair.returncode == 0:
            _mark_repairs(result, ledger_path=ledger_path, status="completed", notes=f"repair command exited 0 on attempt {attempt}")
        else:
            _mark_repairs(result, ledger_path=ledger_path, status="failed", notes=f"repair command exited {repair.returncode}")

    if last_result is None:  # defensive; argparse prevents this in practice
        raise RuntimeError("controller ran without evaluating the ledger")
    return _escalate(
        ledger_path=ledger_path,
        result=last_result,
        reason=f"max repair attempts reached ({limits.max_attempts})",
        attempts=limits.max_attempts,
        same_failure_count=same_failure_count,
        output_report=output_report,
        comment_pr=comment_pr,
    )


def _pr_number_from_context(ledger_path: Path) -> str | None:
    ledger = load_ledger(ledger_path)
    scope = ledger.get("scope", {})
    if isinstance(scope, dict) and scope.get("pr"):
        return str(scope["pr"])
    event_path = os.getenv("GITHUB_EVENT_PATH")
    if not event_path:
        return None
    try:
        event = json.loads(Path(event_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    pull_request = event.get("pull_request")
    if isinstance(pull_request, dict) and pull_request.get("number"):
        return str(pull_request["number"])
    return None


def _comment_pr_handoff(*, ledger_path: Path, report: str) -> dict[str, Any]:
    pr_number = _pr_number_from_context(ledger_path)
    if not pr_number:
        return {"commented": False, "reason": "no PR number found in ledger scope or GitHub event"}
    if not (os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN")):
        return {"commented": False, "reason": "GH_TOKEN/GITHUB_TOKEN is not set"}
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".md", delete=False) as handle:
        handle.write(report)
        body_path = Path(handle.name)
    try:
        completed = subprocess.run(
            ["gh", "pr", "comment", pr_number, "--body-file", str(body_path)],
            cwd=ledger_path.parent,
            capture_output=True,
            text=True,
            check=False,
        )
    finally:
        body_path.unlink(missing_ok=True)
    if completed.returncode == 0:
        return {"commented": True, "pr": pr_number}
    return {
        "commented": False,
        "pr": pr_number,
        "reason": completed.stderr.strip() or completed.stdout.strip() or f"gh exited {completed.returncode}",
    }


def _record_escalation_knowledge(
    *,
    ledger_path: Path,
    result: EvaluationResult,
    reason: str,
    attempts: int,
    same_failure_count: int,
    report: str,
) -> str | None:
    """Persist a handoff knowledge candidate when automation gives up.

    Escalation is exactly when the system has something worth remembering: the
    controller hit a safety bound, the evaluator still failed, and a human needs
    context. This entry remains a `candidate` so it can be reviewed before future
    agents treat it as durable project guidance.
    """

    try:
        ledger = load_ledger(ledger_path)
        entry = KnowledgeEntry(
            title=f"Human handoff after agent-loop escalation: {reason}",
            entry_type="handoff",
            status="candidate",
            summary="Bounded repair stopped before PASS; preserve the failure pattern and handoff guidance for future agents.",
            context=f"Attempts: {attempts}\nRepeated identical failure count: {same_failure_count}\nLedger: {ledger_path}",
            symptom=_format_failures(result),
            root_cause="unknown",
            fix_or_decision=report,
            prevention="Before repeating this repair, search .agent-loop/knowledge for the same failure metrics and review the previous handoff.",
            evidence_references=[str(ledger_path)],
            tags=["agent-loop", "handoff", result.verdict.lower()],
            source_ledger=str(ledger_path),
            loop_run_id=str(ledger.get("loop_run_id", "")) or None,
        )
        path = record_knowledge_entry(ledger_path.parent, entry)
        return str(path)
    except Exception as exc:  # pragma: no cover - defensive: handoff must not be masked by knowledge capture failure
        return f"knowledge capture failed: {exc}"


def _escalate(
    *,
    ledger_path: Path,
    result: EvaluationResult,
    reason: str,
    attempts: int,
    same_failure_count: int,
    output_report: Path | None,
    comment_pr: bool,
) -> int:
    _mark_repairs(result, ledger_path=ledger_path, status="escalated", notes=reason)
    report = _render_handoff_report(
        ledger_path=ledger_path,
        result=result,
        reason=reason,
        attempts=attempts,
        same_failure_count=same_failure_count,
    )
    if output_report:
        output_report.parent.mkdir(parents=True, exist_ok=True)
        output_report.write_text(report, encoding="utf-8")
    _record_controller_decision(
        ledger_path,
        phase="escalation",
        decision="Stop repair loop and hand off to a human",
        rationale=f"Controller hit a hard stop condition: {reason}.",
        evidence_refs=[str(output_report) if output_report else "handoff_report:inline"],
        risks=["Further autonomous repair could loop indefinitely or make unsafe changes without human judgment."],
    )
    knowledge_result = _record_escalation_knowledge(
        ledger_path=ledger_path,
        result=result,
        reason=reason,
        attempts=attempts,
        same_failure_count=same_failure_count,
        report=report,
    )
    comment_result = _comment_pr_handoff(ledger_path=ledger_path, report=report) if comment_pr else {"commented": False, "reason": "disabled"}
    _record_controller_event(
        ledger_path,
        event="escalated",
        details={
            "reason": reason,
            "attempts": attempts,
            "same_failure_count": same_failure_count,
            "report": report,
            "knowledge": knowledge_result,
            "pr_comment": comment_result,
        },
    )
    print(report, file=sys.stderr)
    return ESCALATION_EXIT_CODE


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a bounded deterministic-evaluator repair loop for an Evidence Ledger")
    parser.add_argument("ledger", type=Path, help="Path to evidence-ledger.json")
    parser.add_argument("--max-attempts", type=int, default=3, help="Maximum evaluator attempts before human handoff")
    parser.add_argument(
        "--max-same-failure-count",
        type=int,
        default=2,
        help="Stop when the same evaluator failure fingerprint repeats this many times",
    )
    parser.add_argument("--max-runtime-minutes", type=float, default=30.0)
    parser.add_argument(
        "--repair-command",
        help=(
            "Shell command that performs one repair attempt. Placeholders: "
            "{ledger}, {repair_prompt_file}, {attempt}. If omitted, HERMES_AGENT_REPAIR_COMMAND is used."
        ),
    )
    parser.add_argument("--output-report", type=Path, help="Write human handoff markdown here on escalation")
    parser.add_argument("--comment-pr", action="store_true", help="Post the human handoff report as a PR comment with gh CLI on escalation")
    parser.add_argument("--trigger-prefix", default="repair_controller")
    parser.add_argument("--check-cwd", type=Path, help="Working directory for controller-owned required checks. Defaults to ledger parent.")
    parser.add_argument("--regression-base-ref")
    parser.add_argument("--regression-test-command")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.max_attempts < 1:
        raise SystemExit("--max-attempts must be >= 1")
    if args.max_same_failure_count < 1:
        raise SystemExit("--max-same-failure-count must be >= 1")
    if args.max_runtime_minutes <= 0:
        raise SystemExit("--max-runtime-minutes must be > 0")
    return run_controller(
        ledger_path=args.ledger,
        limits=ControllerLimits(
            max_attempts=args.max_attempts,
            max_same_failure_count=args.max_same_failure_count,
            max_runtime_minutes=args.max_runtime_minutes,
        ),
        repair_command=args.repair_command,
        output_report=args.output_report,
        trigger_prefix=args.trigger_prefix,
        comment_pr=args.comment_pr,
        check_cwd=args.check_cwd,
        regression_base_ref=args.regression_base_ref,
        regression_test_command=args.regression_test_command,
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
