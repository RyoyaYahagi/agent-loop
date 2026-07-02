"""Machine regression detection for agent-loop ledgers."""

from __future__ import annotations

import argparse
import json
import shlex
import shutil
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from hermes_cli.agent_loop_capture import _git_value, save_ledger, load_ledger, utc_now


def parse_junit_failures(path: str | Path) -> set[str]:
    root = ET.parse(path).getroot()
    failures: set[str] = set()
    for testcase in root.iter("testcase"):
        classname = testcase.attrib.get("classname", "")
        name = testcase.attrib.get("name", "")
        test_id = f"{classname}::{name}" if classname else name
        if any(child.tag.rsplit("}", 1)[-1] in {"failure", "error"} for child in list(testcase)):
            failures.add(test_id)
    return failures


def diff_junit_failures(base_junit: str | Path, head_junit: str | Path) -> dict[str, Any]:
    base_failed = parse_junit_failures(base_junit)
    head_failed = parse_junit_failures(head_junit)
    new_failure_ids = sorted(head_failed - base_failed)
    return {
        "source": "machine",
        "new_failures": len(new_failure_ids),
        "new_failure_ids": new_failure_ids,
        "base_junit": str(base_junit),
        "head_junit": str(head_junit),
        "computed_at": utc_now(),
    }


def _run_test_command(command_template: str, *, cwd: Path, junit_path: Path) -> int:
    command = command_template.format(junit=shlex.quote(str(junit_path)))
    completed = subprocess.run(command, shell=True, cwd=cwd, text=True, check=False)
    return completed.returncode


def compute_regressions_for_git(
    *,
    ledger_path: str | Path,
    cwd: str | Path,
    base_ref: str,
    test_command: str,
) -> dict[str, Any]:
    repo = Path(cwd).resolve()
    ledger_file = Path(ledger_path)
    head_commit = _git_value(["rev-parse", "HEAD"], repo)
    base_commit = _git_value(["rev-parse", base_ref], repo)
    out_dir = ledger_file.parent / ".agent-loop" / "regressions"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = int(time.time() * 1000)
    head_junit = out_dir / f"head-{stamp}.xml"
    base_junit = out_dir / f"base-{stamp}.xml"

    _run_test_command(test_command, cwd=repo, junit_path=head_junit)
    temp_parent = Path(tempfile.mkdtemp(prefix="agent-loop-regression-"))
    worktree = temp_parent / "base"
    base_run_failed = False
    try:
        add = subprocess.run(["git", "worktree", "add", "--detach", str(worktree), base_ref], cwd=repo, capture_output=True, text=True, check=False)
        if add.returncode != 0:
            base_run_failed = True
        else:
            base_run_failed = _run_test_command(test_command, cwd=worktree, junit_path=base_junit) != 0 and not base_junit.exists()
    finally:
        subprocess.run(["git", "worktree", "remove", "--force", str(worktree)], cwd=repo, capture_output=True, text=True, check=False)
        shutil.rmtree(temp_parent, ignore_errors=True)

    if base_run_failed or not base_junit.exists():
        base_failed: set[str] = set()
        head_failed = parse_junit_failures(head_junit) if head_junit.exists() else set()
        new_failure_ids = sorted(head_failed - base_failed)
        regression = {
            "source": "machine",
            "new_failures": len(new_failure_ids),
            "new_failure_ids": new_failure_ids,
            "base_run_failed": True,
            "base_commit": base_commit,
            "head_commit": head_commit,
            "base_junit": str(base_junit),
            "head_junit": str(head_junit),
            "computed_at": utc_now(),
        }
    else:
        regression = diff_junit_failures(base_junit, head_junit)
        regression.update({"base_commit": base_commit, "head_commit": head_commit, "base_run_failed": False})

    ledger = load_ledger(ledger_file)
    ledger["regressions"] = regression
    save_ledger(ledger_file, ledger)
    return regression


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compute machine regression evidence for an agent-loop ledger")
    parser.add_argument("--ledger", type=Path, help="Ledger to update")
    parser.add_argument("--base-junit", type=Path)
    parser.add_argument("--head-junit", type=Path)
    parser.add_argument("--base-ref")
    parser.add_argument("--test-command")
    parser.add_argument("--cwd", type=Path, default=Path("."))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.base_junit and args.head_junit:
        result = diff_junit_failures(args.base_junit, args.head_junit)
        if args.ledger:
            ledger = load_ledger(args.ledger)
            ledger["regressions"] = result
            save_ledger(args.ledger, ledger)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result["new_failures"] == 0 else 1
    if args.ledger and args.base_ref and args.test_command:
        result = compute_regressions_for_git(
            ledger_path=args.ledger,
            cwd=args.cwd,
            base_ref=args.base_ref,
            test_command=args.test_command,
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result["new_failures"] == 0 else 1
    raise SystemExit("pass either --base-junit/--head-junit or --ledger/--base-ref/--test-command")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
