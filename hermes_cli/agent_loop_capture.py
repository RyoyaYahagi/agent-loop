"""Machine evidence capture helpers for agent-loop Evidence Ledgers.

These helpers deliberately collect source-of-truth data from the local process,
git, and GitHub CLI instead of asking an AI to write evidence by hand.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

Runner = Callable[..., subprocess.CompletedProcess[str]]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_ledger(path: str | Path) -> dict[str, Any]:
    ledger_path = Path(path)
    if not ledger_path.exists():
        return {}
    with ledger_path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("Evidence Ledger must be a JSON object")
    return data


def save_ledger(path: str | Path, ledger: Mapping[str, Any]) -> None:
    ledger_path = Path(path)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(json.dumps(ledger, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def initialize_ledger(
    *,
    ledger_path: str | Path,
    loop_run_id: str,
    repo: str | None = None,
    issue: str | int | None = None,
    pr: str | int | None = None,
    branch: str | None = None,
    base_ref: str | None = None,
    start_commit: str | None = None,
    required_checks: Sequence[str] | None = None,
    deliverables: Sequence[str] | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Create or update an Evidence Ledger with normalized loop metadata."""

    ledger_file = Path(ledger_path)
    ledger = {} if overwrite else load_ledger(ledger_file)
    ledger["loop_run_id"] = loop_run_id
    scope = ledger.setdefault("scope", {})
    if not isinstance(scope, dict):
        raise ValueError("ledger.scope must be an object")
    scope.update(
        {
            "repo": repo,
            "issue": str(issue) if issue is not None else None,
            "pr": str(pr) if pr is not None else None,
            "branch": branch,
            "base_ref": base_ref,
            "start_commit": start_commit,
            "required_checks": list(required_checks or []),
            "deliverables": list(deliverables or []),
            "initialized_at": scope.get("initialized_at") or utc_now(),
        }
    )
    for key in ("requirements", "tasks", "checks", "findings", "claims", "evaluations", "repairs", "usage_events"):
        value = ledger.setdefault(key, [])
        if not isinstance(value, list):
            raise ValueError(f"ledger.{key} must be a list")
    ledger.setdefault("regressions", {"new_failures": 0})
    if not isinstance(ledger["regressions"], dict):
        raise ValueError("ledger.regressions must be an object")
    machine = ledger.setdefault("machine_evidence", {})
    if not isinstance(machine, dict):
        raise ValueError("ledger.machine_evidence must be an object")
    for key in ("git_snapshots", "pr_snapshots"):
        value = machine.setdefault(key, [])
        if not isinstance(value, list):
            raise ValueError(f"ledger.machine_evidence.{key} must be a list")
    save_ledger(ledger_file, ledger)
    return ledger


def resolve_active_ledger_path(cwd: str | Path | None = None) -> Path | None:
    """Return the active Evidence Ledger path for automatic capture, if any.

    ``HERMES_LEDGER_PATH`` wins. Otherwise, ``evidence-ledger.json`` in the
    current working directory is active when it already exists. This is
    intentionally conservative and does not create ledgers implicitly.
    """

    env_path = os.getenv("HERMES_LEDGER_PATH")
    if env_path:
        return Path(env_path).expanduser().resolve()
    base = Path(cwd or os.getcwd()).resolve()
    candidate = base / "evidence-ledger.json"
    return candidate if candidate.exists() else None


def record_usage_event(
    *,
    ledger_path: str | Path,
    phase: str,
    agent_role: str,
    model: str | None,
    provider: str | None,
    session_id: str | None = None,
    agent_id: str | None = None,
    parent_session_id: str | None = None,
    api_call_index: int | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
    reasoning_tokens: int = 0,
    total_tokens: int | None = None,
    estimated_cost_usd: float | None = None,
    cost_status: str | None = None,
    cost_source: str | None = None,
    duration_seconds: float | None = None,
) -> dict[str, Any]:
    """Append per-API-call usage/cost telemetry to ``usage_events[]``."""

    ledger_file = Path(ledger_path)
    ledger = load_ledger(ledger_file)
    events = ledger.setdefault("usage_events", [])
    if not isinstance(events, list):
        raise ValueError("ledger.usage_events must be a list")
    if total_tokens is None:
        total_tokens = int(input_tokens or 0) + int(output_tokens or 0)
    entry = {
        "id": f"USAGE-{int(time.time() * 1000)}-{len(events) + 1}",
        "source": "machine",
        "timestamp": utc_now(),
        "phase": phase,
        "agent_role": agent_role,
        "agent_id": agent_id,
        "session_id": session_id,
        "parent_session_id": parent_session_id,
        "api_call_index": api_call_index,
        "model": model,
        "provider": provider,
        "tokens": {
            "input": int(input_tokens or 0),
            "output": int(output_tokens or 0),
            "total": int(total_tokens or 0),
            "cache_read": int(cache_read_tokens or 0),
            "cache_write": int(cache_write_tokens or 0),
            "reasoning": int(reasoning_tokens or 0),
        },
        "estimated_cost_usd": estimated_cost_usd,
        "cost_status": cost_status,
        "cost_source": cost_source,
        "duration_seconds": duration_seconds,
    }
    events.append(entry)
    save_ledger(ledger_file, ledger)
    return entry


def summarize_usage_events(ledger: Mapping[str, Any]) -> dict[str, Any]:
    """Aggregate ``usage_events[]`` by phase and agent for dashboards/reports."""

    events = ledger.get("usage_events", [])
    if not isinstance(events, list):
        events = []

    def empty_bucket() -> dict[str, Any]:
        return {
            "api_calls": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
            "reasoning_tokens": 0,
            "estimated_cost_usd": 0.0,
            "unknown_cost_events": 0,
        }

    total = empty_bucket()
    by_phase: dict[str, dict[str, Any]] = {}
    by_agent: dict[str, dict[str, Any]] = {}
    for event in events:
        if not isinstance(event, dict):
            continue
        raw_tokens = event.get("tokens")
        tokens: dict[str, Any] = raw_tokens if isinstance(raw_tokens, dict) else {}
        cost = event.get("estimated_cost_usd")
        phase = str(event.get("phase") or "unknown")
        agent_key = str(event.get("agent_id") or event.get("agent_role") or "unknown")
        for bucket in (total, by_phase.setdefault(phase, empty_bucket()), by_agent.setdefault(agent_key, empty_bucket())):
            bucket["api_calls"] += 1
            bucket["input_tokens"] += int(tokens.get("input") or 0)
            bucket["output_tokens"] += int(tokens.get("output") or 0)
            bucket["total_tokens"] += int(tokens.get("total") or 0)
            bucket["cache_read_tokens"] += int(tokens.get("cache_read") or 0)
            bucket["cache_write_tokens"] += int(tokens.get("cache_write") or 0)
            bucket["reasoning_tokens"] += int(tokens.get("reasoning") or 0)
            if isinstance(cost, (int, float)):
                bucket["estimated_cost_usd"] += float(cost)
            else:
                bucket["unknown_cost_events"] += 1
    for bucket in [total, *by_phase.values(), *by_agent.values()]:
        bucket["estimated_cost_usd"] = round(float(bucket["estimated_cost_usd"]), 8)
    return {"total": total, "by_phase": by_phase, "by_agent": by_agent, "event_count": len(events)}


def append_evaluation_result(
    *,
    ledger_path: str | Path,
    result: Any,
    trigger: str = "manual",
) -> dict[str, Any]:
    """Append a deterministic evaluator result to ledger.evaluations[]."""

    ledger_file = Path(ledger_path)
    ledger = load_ledger(ledger_file)
    evaluations = ledger.setdefault("evaluations", [])
    if not isinstance(evaluations, list):
        raise ValueError("ledger.evaluations must be a list")
    payload = result.to_dict() if hasattr(result, "to_dict") else dict(result)
    entry = {
        "id": f"EVAL-{int(time.time() * 1000)}",
        "source": "deterministic_evaluator",
        "trigger": trigger,
        "timestamp": utc_now(),
        "verdict": payload.get("verdict"),
        "score": payload.get("score"),
        "metrics": payload.get("metrics", {}),
        "blocking_failures": payload.get("blocking_failures", []),
        "repair_tasks": payload.get("repair_tasks", []),
    }
    evaluations.append(entry)
    save_ledger(ledger_file, ledger)
    return entry


def record_repair_task_status(
    *,
    ledger_path: str | Path,
    repair_id: str,
    metric: str,
    instruction: str,
    status: str,
    evidence: Sequence[str] | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """Upsert lifecycle state for a deterministic repair task."""

    allowed = {"pending", "started", "completed", "skipped", "escalated", "failed"}
    if status not in allowed:
        raise ValueError(f"repair status must be one of: {', '.join(sorted(allowed))}")
    ledger_file = Path(ledger_path)
    ledger = load_ledger(ledger_file)
    repairs = ledger.setdefault("repairs", [])
    if not isinstance(repairs, list):
        raise ValueError("ledger.repairs must be a list")
    now = utc_now()
    entry = {
        "id": repair_id,
        "metric": metric,
        "instruction": instruction,
        "status": status,
        "evidence": list(evidence or []),
        "notes": notes,
    }
    for index, existing in enumerate(repairs):
        if isinstance(existing, dict) and existing.get("id") == repair_id:
            updated = {**existing, **entry, "updated_at": now}
            repairs[index] = updated
            save_ledger(ledger_file, ledger)
            return updated
    entry["created_at"] = now
    repairs.append(entry)
    save_ledger(ledger_file, ledger)
    return entry


def display_command(command: Sequence[str]) -> str:
    safe_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_@%+=:,./-")
    parts: list[str] = []
    for part in command:
        if not part:
            parts.append('""')
        elif all(char in safe_chars for char in part):
            parts.append(part)
        else:
            parts.append('"' + part.replace('\\', '\\\\').replace('"', '\\"') + '"')
    return " ".join(parts)


def _run_git(args: Sequence[str], cwd: Path, *, check: bool = False) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=check)
    return result.stdout.strip()


def _git_value(args: Sequence[str], cwd: Path) -> str | None:
    try:
        value = _run_git(args, cwd)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    return value or None


def git_context(cwd: str | Path) -> dict[str, Any]:
    path = Path(cwd).resolve()
    return {
        "branch": _git_value(["branch", "--show-current"], path),
        "commit": _git_value(["rev-parse", "HEAD"], path),
        "dirty": bool(_git_value(["status", "--porcelain"], path)),
    }


def _relative_to_ledger(ledger_path: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ledger_path.parent.resolve()))
    except ValueError:
        return str(path.resolve())


def _upsert_by_id(items: list[dict[str, Any]], item: dict[str, Any]) -> None:
    item_id = item.get("id")
    for index, existing in enumerate(items):
        if existing.get("id") == item_id:
            items[index] = {**existing, **item}
            return
    items.append(item)


def run_logged_check(
    *,
    ledger_path: str | Path,
    check_id: str,
    check_type: str,
    command: Sequence[str],
    cwd: str | Path = ".",
    required: bool = True,
    timeout: int | None = None,
    runner: Runner = subprocess.run,
) -> int:
    """Run a command and record deterministic machine evidence in a ledger."""

    ledger_file = Path(ledger_path)
    run_cwd = Path(cwd).resolve()
    started_at = utc_now()
    started = time.monotonic()
    completed = runner(
        list(command),
        cwd=run_cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    ended_at = utc_now()
    duration_seconds = round(time.monotonic() - started, 4)

    log_dir = ledger_file.parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    safe_id = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in check_id)
    stdout_log = log_dir / f"{safe_id}.stdout.log"
    stderr_log = log_dir / f"{safe_id}.stderr.log"
    stdout_log.write_text(completed.stdout or "", encoding="utf-8")
    stderr_log.write_text(completed.stderr or "", encoding="utf-8")

    context = git_context(run_cwd)
    check_entry = {
        "id": check_id,
        "type": check_type,
        "command": display_command(command),
        "command_argv": list(command),
        "required": required,
        "executed": True,
        "exit_code": completed.returncode,
        "source": "machine",
        "cwd": str(run_cwd),
        "branch": context["branch"],
        "commit": context["commit"],
        "dirty": context["dirty"],
        "started_at": started_at,
        "ended_at": ended_at,
        "duration_seconds": duration_seconds,
        "evidence": {
            "stdout_log": _relative_to_ledger(ledger_file, stdout_log),
            "stderr_log": _relative_to_ledger(ledger_file, stderr_log),
        },
    }

    ledger = load_ledger(ledger_file)
    checks = ledger.setdefault("checks", [])
    if not isinstance(checks, list):
        raise ValueError("ledger.checks must be a list")
    _upsert_by_id(checks, check_entry)
    save_ledger(ledger_file, ledger)
    return int(completed.returncode)


def capture_git_snapshot(
    *,
    ledger_path: str | Path,
    cwd: str | Path = ".",
    base_ref: str | None = None,
) -> dict[str, Any]:
    """Append a machine-collected git snapshot to the ledger."""

    ledger_file = Path(ledger_path)
    run_cwd = Path(cwd).resolve()
    timestamp = utc_now()
    branch = _git_value(["branch", "--show-current"], run_cwd)
    head_commit = _git_value(["rev-parse", "HEAD"], run_cwd)
    base_commit = _git_value(["rev-parse", base_ref], run_cwd) if base_ref else None
    changed_files_raw = _git_value(["diff", "--name-only", base_ref or "HEAD"], run_cwd)
    if not changed_files_raw:
        changed_files_raw = _git_value(["status", "--porcelain"], run_cwd) or ""
        changed_files = [line[3:] for line in changed_files_raw.splitlines() if len(line) > 3]
    else:
        changed_files = changed_files_raw.splitlines()
    diff_stat = _git_value(["diff", "--stat", base_ref or "HEAD"], run_cwd)
    dirty = bool(_git_value(["status", "--porcelain"], run_cwd))

    snapshot = {
        "id": f"GIT-{int(time.time() * 1000)}",
        "source": "machine",
        "timestamp": timestamp,
        "cwd": str(run_cwd),
        "branch": branch,
        "head_commit": head_commit,
        "base_ref": base_ref,
        "base_commit": base_commit,
        "dirty": dirty,
        "changed_files": changed_files,
        "diff_stat": diff_stat or "",
    }

    ledger = load_ledger(ledger_file)
    machine = ledger.setdefault("machine_evidence", {})
    if not isinstance(machine, dict):
        raise ValueError("ledger.machine_evidence must be an object")
    snapshots = machine.setdefault("git_snapshots", [])
    if not isinstance(snapshots, list):
        raise ValueError("ledger.machine_evidence.git_snapshots must be a list")
    snapshots.append(snapshot)
    save_ledger(ledger_file, ledger)
    return snapshot


def capture_pr_snapshot(
    *,
    ledger_path: str | Path,
    pr: str | int,
    cwd: str | Path = ".",
    runner: Runner = subprocess.run,
) -> dict[str, Any]:
    """Capture GitHub PR source-of-truth metadata using gh CLI."""

    fields = "number,title,body,state,isDraft,mergeable,reviewDecision,headRefName,baseRefName,additions,deletions,changedFiles,files,commits,statusCheckRollup,url,updatedAt"
    completed = runner(
        ["gh", "pr", "view", str(pr), "--json", fields],
        cwd=Path(cwd).resolve(),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or f"gh pr view {pr} failed")
    payload = json.loads(completed.stdout)
    snapshot = {
        "id": f"PR-{pr}-{int(time.time() * 1000)}",
        "source": "machine",
        "timestamp": utc_now(),
        "cwd": str(Path(cwd).resolve()),
        "gh_command": f"gh pr view {pr} --json {fields}",
        "data": payload,
    }

    ledger_file = Path(ledger_path)
    ledger = load_ledger(ledger_file)
    machine = ledger.setdefault("machine_evidence", {})
    if not isinstance(machine, dict):
        raise ValueError("ledger.machine_evidence must be an object")
    snapshots = machine.setdefault("pr_snapshots", [])
    if not isinstance(snapshots, list):
        raise ValueError("ledger.machine_evidence.pr_snapshots must be a list")
    snapshots.append(snapshot)
    save_ledger(ledger_file, ledger)
    return snapshot


def build_init_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Initialize an agent-loop Evidence Ledger with loop metadata")
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--loop-run-id", required=True)
    parser.add_argument("--repo")
    parser.add_argument("--issue")
    parser.add_argument("--pr")
    parser.add_argument("--branch")
    parser.add_argument("--base-ref")
    parser.add_argument("--start-commit")
    parser.add_argument("--required-check", action="append", default=[])
    parser.add_argument("--deliverable", action="append", default=[])
    parser.add_argument("--overwrite", action="store_true")
    return parser


def init_main(argv: list[str] | None = None) -> int:
    args = build_init_parser().parse_args(argv)
    ledger = initialize_ledger(
        ledger_path=args.ledger,
        loop_run_id=args.loop_run_id,
        repo=args.repo,
        issue=args.issue,
        pr=args.pr,
        branch=args.branch,
        base_ref=args.base_ref,
        start_commit=args.start_commit,
        required_checks=args.required_check,
        deliverables=args.deliverable,
        overwrite=args.overwrite,
    )
    print(json.dumps(ledger, indent=2, ensure_ascii=False))
    return 0


def build_repair_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Record lifecycle status for an agent-loop repair task")
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--repair-id", required=True)
    parser.add_argument("--metric", required=True)
    parser.add_argument("--instruction", required=True)
    parser.add_argument("--status", required=True, choices=["pending", "started", "completed", "skipped", "escalated", "failed"])
    parser.add_argument("--evidence", action="append", default=[])
    parser.add_argument("--notes")
    return parser


def repair_main(argv: list[str] | None = None) -> int:
    args = build_repair_parser().parse_args(argv)
    entry = record_repair_task_status(
        ledger_path=args.ledger,
        repair_id=args.repair_id,
        metric=args.metric,
        instruction=args.instruction,
        status=args.status,
        evidence=args.evidence,
        notes=args.notes,
    )
    print(json.dumps(entry, indent=2, ensure_ascii=False))
    return 0


def build_run_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a command and append machine check evidence to an Evidence Ledger")
    parser.add_argument("--ledger", required=True, type=Path, help="Path to evidence-ledger.json")
    parser.add_argument("--check-id", required=True, help="Check ID to upsert, e.g. CHECK-001")
    parser.add_argument("--type", default="command", help="Check type, e.g. unit-tests/typecheck/lint")
    parser.add_argument("--cwd", default=".", type=Path, help="Working directory for the command")
    parser.add_argument("--optional", action="store_true", help="Mark the check as not required")
    parser.add_argument("--timeout", type=int, help="Command timeout in seconds")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="Command to run after --")
    return parser


def run_main(argv: list[str] | None = None) -> int:
    args = build_run_parser().parse_args(argv)
    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise SystemExit("missing command; pass it after --")
    return run_logged_check(
        ledger_path=args.ledger,
        check_id=args.check_id,
        check_type=args.type,
        command=command,
        cwd=args.cwd,
        required=not args.optional,
        timeout=args.timeout,
    )


def build_git_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Append a machine git snapshot to an Evidence Ledger")
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--cwd", default=".", type=Path)
    parser.add_argument("--base-ref")
    return parser


def git_main(argv: list[str] | None = None) -> int:
    args = build_git_parser().parse_args(argv)
    snapshot = capture_git_snapshot(ledger_path=args.ledger, cwd=args.cwd, base_ref=args.base_ref)
    print(json.dumps(snapshot, indent=2, ensure_ascii=False))
    return 0


def build_pr_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Append a machine GitHub PR snapshot to an Evidence Ledger")
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--pr", required=True)
    parser.add_argument("--cwd", default=".", type=Path)
    return parser


def pr_main(argv: list[str] | None = None) -> int:
    args = build_pr_parser().parse_args(argv)
    snapshot = capture_pr_snapshot(ledger_path=args.ledger, pr=args.pr, cwd=args.cwd)
    print(json.dumps(snapshot, indent=2, ensure_ascii=False))
    return 0
