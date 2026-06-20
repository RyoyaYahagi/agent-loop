"""PR merge guard for AI-authored pull requests.

This module exists because a human-readable PR body is not enough. The AI may
write a nice Japanese checklist while CI is still failing or missing. The guard
checks GitHub's machine-readable PR state and fails closed when it cannot prove
that the PR is safe to merge.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class GuardResult:
    """Result of the merge gate.

    `allowed=False` means automation must not merge. A human can still override
    outside the tool, but the report should make the risk explicit in Japanese.
    """

    allowed: bool
    reasons: tuple[str, ...]
    summary: str


def _check_conclusion(check: Mapping[str, Any]) -> str | None:
    """Extract a normalized conclusion from GitHub status/check-rollup entries."""

    conclusion = check.get("conclusion") or check.get("state")
    if isinstance(conclusion, str):
        return conclusion.upper()
    return None


def _check_name(check: Mapping[str, Any]) -> str:
    """Return the most useful display name for a check-run/status entry."""

    for key in ("name", "context", "workflowName"):
        value = check.get(key)
        if isinstance(value, str) and value:
            return value
    return "unknown-check"


def evaluate_pr_state(pr: Mapping[str, Any], *, require_review_approval: bool = False) -> GuardResult:
    """Evaluate whether an AI-authored PR is safe for automation to merge.

    The policy is intentionally fail-closed:
    - draft PRs are blocked
    - missing checks are blocked
    - any non-success check is blocked
    - optional review approval requirement can block unapproved PRs
    """

    reasons: list[str] = []
    if pr.get("isDraft"):
        reasons.append("PRがDraftのため、マージ禁止です。")

    checks = pr.get("statusCheckRollup")
    if not isinstance(checks, list) or not checks:
        reasons.append("CI/checksが取得できない、または未実行です。checks missing としてマージ禁止です。")
    else:
        failing: list[str] = []
        pending: list[str] = []
        for check in checks:
            if not isinstance(check, Mapping):
                continue
            conclusion = _check_conclusion(check)
            name = _check_name(check)
            if conclusion in {"SUCCESS", "NEUTRAL", "SKIPPED"}:
                continue
            if conclusion in {"PENDING", "QUEUED", "IN_PROGRESS", "EXPECTED", None}:
                pending.append(name)
            else:
                failing.append(f"{name}: {conclusion}")
        if pending:
            reasons.append("未完了のCI/checksがあります: " + ", ".join(pending))
        if failing:
            reasons.append("失敗しているCI/checksがあります: " + ", ".join(failing))

    review_decision = pr.get("reviewDecision")
    if require_review_approval and review_decision != "APPROVED":
        reasons.append(f"reviewDecisionがAPPROVEDではありません: {review_decision or 'unknown'}")

    mergeable = pr.get("mergeable")
    if mergeable is False:
        reasons.append("GitHub上でmergeable=falseです。競合またはmerge blockの可能性があります。")

    if reasons:
        return GuardResult(False, tuple(reasons), "マージ禁止: CI/PR状態が安全条件を満たしていません。")
    return GuardResult(True, tuple(), "マージ可能: Draftではなく、取得できたchecksはすべて成功しています。")


def render_japanese_report(result: GuardResult, pr: Mapping[str, Any]) -> str:
    """Render a short Japanese report suitable for PR comments or CI logs."""

    title = pr.get("title") or "unknown"
    number = pr.get("number") or "unknown"
    url = pr.get("url") or ""
    status = "✅ マージ可能" if result.allowed else "⛔ マージ禁止"
    reasons = "\n".join(f"- {reason}" for reason in result.reasons) or "- なし"
    return f"""# AI PR Merge Guard

{status}

- PR: #{number} {title}
- URL: {url}
- Summary: {result.summary}

## 理由

{reasons}

## 人間が見るべきポイント

- CIが未実行・失敗・保留のままマージされていないか
- required checks がGitHub branch protectionにも設定されているか
- 高リスク差分はPR本文の日本語レビュー観点で確認済みか
""".strip() + "\n"


def load_pr_with_gh(pr_number: str | None = None) -> dict[str, Any]:
    """Load PR state through `gh pr view`.

    This is kept small and explicit so CI logs show exactly which fields the
    merge guard relies on.
    """

    fields = "number,title,url,isDraft,mergeable,reviewDecision,statusCheckRollup"
    command = ["gh", "pr", "view"]
    if pr_number:
        command.append(str(pr_number))
    command.extend(["--json", fields])
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or f"gh exited {completed.returncode}")
    return json.loads(completed.stdout)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fail-closed merge guard for AI-authored PRs")
    parser.add_argument("pr", nargs="?", help="PR number or URL. Omit inside a checked-out PR branch.")
    parser.add_argument("--json-file", help="Read gh pr view JSON from a file instead of calling gh")
    parser.add_argument("--require-review-approval", action="store_true", help="Require GitHub reviewDecision=APPROVED")
    parser.add_argument("--report", help="Write Japanese report markdown to this path")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.json_file:
        with open(args.json_file, encoding="utf-8") as handle:
            pr = json.load(handle)
    else:
        pr = load_pr_with_gh(args.pr)
    result = evaluate_pr_state(pr, require_review_approval=args.require_review_approval)
    report = render_japanese_report(result, pr)
    if args.report:
        with open(args.report, "w", encoding="utf-8") as handle:
            handle.write(report)
    print(report)
    return 0 if result.allowed else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
