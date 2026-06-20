"""Bounded CI-repair-and-merge loop for AI-authored PRs.

This module codifies the user's desired operational behavior:

1. keep repairing a PR until CI/checks are green,
2. stop after bounded attempts instead of looping forever,
3. merge only after machine-readable checks prove the PR is safe,
4. avoid automatic merges to protected human-only branches such as `main` unless
   the caller explicitly opts in.

The module intentionally delegates the actual code changes to a configured
repair command. It does not ask the LLM whether CI passed; it reads GitHub PR
state through the merge guard.
"""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Mapping, Sequence

from hermes_cli.agent_loop_pr_guard import GuardResult, evaluate_pr_state, load_pr_with_gh, render_japanese_report

DEFAULT_ALLOWED_BASES = ("develop", "staging")


@dataclass(frozen=True)
class CiRepairMergeLimits:
    """Safety bounds for the CI repair loop.

    Attempts count repair executions, not PR-state checks. A PR that is already
    green can merge without consuming an attempt. A PR that never becomes green
    stops and hands off to humans.
    """

    max_attempts: int = 3
    poll_interval_seconds: int = 30
    max_wait_seconds: int = 900


@dataclass(frozen=True)
class MergeSafety:
    """Policy for whether automation is allowed to merge the PR after CI passes."""

    allowed_base_branches: tuple[str, ...] = DEFAULT_ALLOWED_BASES
    allow_main: bool = False
    require_review_approval: bool = False


def base_branch_allowed(pr: Mapping[str, object], safety: MergeSafety) -> tuple[bool, str]:
    """Return whether automation may merge into the PR base branch.

    This prevents a future agent from applying the "merge after green" rule to
    production/main by accident. The user can still opt in with `--allow-main`,
    but the default is integration branches only.
    """

    base = str(pr.get("baseRefName") or "")
    if base == "main" and not safety.allow_main:
        return False, "base branch is main; automatic main merges are disabled"
    if base not in safety.allowed_base_branches and not (base == "main" and safety.allow_main):
        return False, f"base branch {base or 'unknown'} is not in allowed list: {', '.join(safety.allowed_base_branches)}"
    return True, f"base branch {base} is allowed"


def run_repair_command(command: str, *, pr_number: str, attempt: int, timeout_seconds: int) -> int:
    """Run one configured repair attempt.

    The command receives environment variables so the repair agent can inspect
    the PR and know which bounded attempt it is executing.
    """

    env = os.environ.copy()
    env.update(
        {
            "AGENT_LOOP_PR_NUMBER": str(pr_number),
            "AGENT_LOOP_CI_REPAIR_ATTEMPT": str(attempt),
            "HERMES_AGENT_LOOP_PHASE": f"ci_repair_attempt_{attempt}",
        }
    )
    formatted = command.format(pr=shlex.quote(str(pr_number)), attempt=attempt)
    completed = subprocess.run(formatted, shell=True, env=env, text=True, timeout=timeout_seconds, check=False)
    return completed.returncode


def merge_pr(pr_number: str, *, method: str = "squash", delete_branch: bool = True, auto: bool = False) -> None:
    """Merge the PR using gh after all machine checks are green."""

    command = ["gh", "pr", "merge", str(pr_number), f"--{method}"]
    if delete_branch:
        command.append("--delete-branch")
    if auto:
        command.append("--auto")
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or f"gh exited {completed.returncode}")


def wait_for_non_pending_state(pr_number: str, *, safety: MergeSafety, limits: CiRepairMergeLimits) -> tuple[dict, GuardResult]:
    """Poll PR state until checks are green/failing/missing or the wait limit expires."""

    deadline = time.monotonic() + limits.max_wait_seconds
    last_pr = load_pr_with_gh(pr_number)
    last_result = evaluate_pr_state(last_pr, require_review_approval=safety.require_review_approval)
    while time.monotonic() < deadline:
        pending_only = any("未完了" in reason for reason in last_result.reasons)
        if last_result.allowed or not pending_only:
            return last_pr, last_result
        time.sleep(limits.poll_interval_seconds)
        last_pr = load_pr_with_gh(pr_number)
        last_result = evaluate_pr_state(last_pr, require_review_approval=safety.require_review_approval)
    return last_pr, last_result


def run_ci_repair_merge_loop(
    *,
    pr_number: str,
    repair_command: str | None,
    limits: CiRepairMergeLimits,
    safety: MergeSafety,
    merge: bool,
    merge_method: str,
    delete_branch: bool,
    auto_merge: bool,
) -> int:
    """Repair until CI passes, then optionally merge.

    Return codes:
    - 0: PR is green and merged, or green with `--no-merge`
    - 1: stopped before green/merge; human handoff required
    """

    for attempt in range(0, limits.max_attempts + 1):
        pr, guard = wait_for_non_pending_state(pr_number, safety=safety, limits=limits)
        print(render_japanese_report(guard, pr))

        if guard.allowed:
            allowed, reason = base_branch_allowed(pr, safety)
            if not allowed:
                print(f"⛔ 自動マージ禁止: {reason}", file=sys.stderr)
                return 1
            if merge:
                merge_pr(pr_number, method=merge_method, delete_branch=delete_branch, auto=auto_merge)
                print(f"✅ CI green確認後にPR #{pr_number} を {merge_method} merge しました。")
            else:
                print(f"✅ CI green確認済みです。--no-merge のためmergeは実行していません。")
            return 0

        if attempt >= limits.max_attempts:
            print("⛔ 最大修正回数に到達しました。人間にバトンタッチしてください。", file=sys.stderr)
            return 1
        if not repair_command:
            print("⛔ repair command が未設定です。自動修正できないため人間にバトンタッチしてください。", file=sys.stderr)
            return 1

        print(f"CI/checksがgreenではありません。修正 attempt {attempt + 1}/{limits.max_attempts} を実行します。")
        returncode = run_repair_command(
            repair_command,
            pr_number=pr_number,
            attempt=attempt + 1,
            timeout_seconds=limits.max_wait_seconds,
        )
        if returncode != 0:
            print(f"修正コマンドが exit {returncode} で終了しました。次のループでPR状態を再確認します。", file=sys.stderr)

    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Repair an AI-authored PR until CI is green, then merge safely")
    parser.add_argument("pr", help="PR number or URL")
    parser.add_argument("--repair-command", default=os.getenv("AGENT_LOOP_CI_REPAIR_COMMAND", ""), help="Command for one repair attempt. Placeholders: {pr}, {attempt}")
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--poll-interval-seconds", type=int, default=30)
    parser.add_argument("--max-wait-seconds", type=int, default=900)
    parser.add_argument("--allowed-base", action="append", default=[], help="Base branch automation may merge into. Repeatable. Defaults: develop, staging")
    parser.add_argument("--allow-main", action="store_true", help="Allow automatic merge into main. Off by default.")
    parser.add_argument("--require-review-approval", action="store_true")
    parser.add_argument("--merge-method", choices=["squash", "merge", "rebase"], default="squash")
    parser.add_argument("--no-delete-branch", action="store_true")
    parser.add_argument("--auto-merge", action="store_true", help="Use gh pr merge --auto after guard passes")
    parser.add_argument("--no-merge", action="store_true", help="Stop after green check without merging")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.max_attempts < 0:
        raise SystemExit("--max-attempts must be >= 0")
    if args.poll_interval_seconds < 1:
        raise SystemExit("--poll-interval-seconds must be >= 1")
    if args.max_wait_seconds < 1:
        raise SystemExit("--max-wait-seconds must be >= 1")

    allowed_bases = tuple(args.allowed_base) if args.allowed_base else DEFAULT_ALLOWED_BASES
    return run_ci_repair_merge_loop(
        pr_number=args.pr,
        repair_command=args.repair_command or None,
        limits=CiRepairMergeLimits(
            max_attempts=args.max_attempts,
            poll_interval_seconds=args.poll_interval_seconds,
            max_wait_seconds=args.max_wait_seconds,
        ),
        safety=MergeSafety(
            allowed_base_branches=allowed_bases,
            allow_main=args.allow_main,
            require_review_approval=args.require_review_approval,
        ),
        merge=not args.no_merge,
        merge_method=args.merge_method,
        delete_branch=not args.no_delete_branch,
        auto_merge=args.auto_merge,
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
