from __future__ import annotations

from hermes_cli.agent_loop_pr_guard import evaluate_pr_state, render_japanese_report


def test_pr_guard_allows_green_ready_pr() -> None:
    result = evaluate_pr_state(
        {
            "isDraft": False,
            "mergeable": True,
            "statusCheckRollup": [
                {"name": "test", "conclusion": "SUCCESS"},
                {"name": "lint", "conclusion": "SUCCESS"},
            ],
        }
    )

    assert result.allowed is True


def test_pr_guard_blocks_missing_checks() -> None:
    result = evaluate_pr_state({"isDraft": False, "mergeable": True, "statusCheckRollup": []})

    assert result.allowed is False
    assert "checks missing" in result.reasons[0]


def test_pr_guard_blocks_failing_checks_and_renders_japanese() -> None:
    pr = {
        "number": 12,
        "title": "feat: sample",
        "url": "https://example.test/pr/12",
        "isDraft": False,
        "mergeable": True,
        "statusCheckRollup": [{"name": "typecheck", "conclusion": "FAILURE"}],
    }

    result = evaluate_pr_state(pr)
    report = render_japanese_report(result, pr)

    assert result.allowed is False
    assert "失敗しているCI/checks" in report
    assert "⛔ マージ禁止" in report


def test_pr_guard_can_require_review_approval() -> None:
    result = evaluate_pr_state(
        {
            "isDraft": False,
            "mergeable": True,
            "reviewDecision": "REVIEW_REQUIRED",
            "statusCheckRollup": [{"name": "test", "conclusion": "SUCCESS"}],
        },
        require_review_approval=True,
    )

    assert result.allowed is False
    assert any("APPROVED" in reason for reason in result.reasons)
