from __future__ import annotations

from hermes_cli.agent_loop_pr_ci_loop import MergeSafety, base_branch_allowed


def test_base_branch_allowed_for_develop_by_default() -> None:
    allowed, reason = base_branch_allowed({"baseRefName": "develop"}, MergeSafety())

    assert allowed is True
    assert "develop" in reason


def test_base_branch_blocks_main_by_default() -> None:
    allowed, reason = base_branch_allowed({"baseRefName": "main"}, MergeSafety())

    assert allowed is False
    assert "main" in reason


def test_base_branch_allows_main_when_explicitly_enabled() -> None:
    allowed, reason = base_branch_allowed({"baseRefName": "main"}, MergeSafety(allow_main=True))

    assert allowed is True
    assert "main" in reason


def test_base_branch_blocks_unknown_base() -> None:
    allowed, reason = base_branch_allowed({"baseRefName": "feature-x"}, MergeSafety())

    assert allowed is False
    assert "allowed list" in reason
