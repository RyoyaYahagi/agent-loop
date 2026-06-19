---
name: agent-loop-evaluation
description: Use when evaluating autonomous AI development loops with evidence-backed metrics, hard gates, deterministic repair tasks, and truthful completion checks.
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [agent-loop, evaluation, verification, evidence, autonomous-development]
    related_skills: [subagent-driven-development, requesting-code-review, writing-plans, systematic-debugging]
---

# Agent Loop Evaluation

## Overview

Use this skill to audit and improve autonomous AI development loops. The central rule is:

> **AI self-report is not evidence. No evidence, no credit.**

A loop is good when it converts requirements into verified implementation through a traceable sequence of planning, execution, checks, fixes, rechecks, truthful claims, and process improvements. Speed is secondary. Correctness, completeness, truthfulness, and repeatability come first.

## When to Use

- After an autonomous issue implementation or batch of issue implementations
- Before claiming an AI development run is complete
- When checking whether the AI really planned, checked, fixed, and rechecked work
- When a user asks whether an AI completion report is trustworthy
- When improving the development loop itself
- In CI as a required status check for agent-produced PRs

## The 7-Stage System

1. **Skill rules** — This skill defines what must be measured and which failures block completion.
2. **Evidence Ledger** — Store requirements, tasks, checks, findings, claims, regressions, and machine-collected evidence in JSON.
3. **Machine capture wrappers** — Use `scripts/ledger_run.py`, `scripts/ledger_git_snapshot.py`, and `scripts/ledger_pr_snapshot.py` so commands/git/PR state are recorded by tools, not AI prose.
4. **Deterministic evaluator** — Run `python scripts/evaluate_agent_loop.py evidence-ledger.json` to compute metrics.
5. **Acceptance gates** — Hard thresholds block completion when evidence is missing, AI-authored, or contradictory.
6. **Repair task generation** — Failed metrics produce deterministic repair tasks.
7. **Controller loop** — If evaluator returns FAIL, execute only repair tasks, update evidence, and re-run evaluator.
8. **CI gate** — Run the evaluator from GitHub Actions or another CI trigger so ignored failures block merge/completion.

## Core Definitions

- **Loop Run:** One bounded agent workflow, usually one issue, PR, or batch.
- **Requirement:** A specific obligation extracted from issue body, acceptance criteria, docs, or user request.
- **Task:** A planned unit of work meant to satisfy one or more requirements.
- **Check:** A verification action such as test, typecheck, lint, build, security review, PR state check, or issue state check.
- **Finding:** A problem discovered by a check or review.
- **Fix:** A code/docs/process change addressing a finding.
- **Recheck:** Re-running the same or equivalent check after a fix.
- **Claim:** Anything the AI says is true, especially completion claims.
- **Evidence:** Source-of-truth artifact: machine-captured git diff, file content, command output, exit code, PR/issue state, or reviewer output.
- **Machine Evidence:** Evidence written by capture scripts/CI/tooling with `source: "machine"`; this is required for check execution credit.
- **AI Annotation:** AI-authored mapping or explanation. Useful context, but not proof by itself.

## Metrics and Default Gates

| Metric | Default Gate | Blocks? | Meaning |
|---|---:|:---:|---|
| Plan Coverage | >= 95% | Yes | Requirements represented in the plan |
| Traceability | >= 95% | Yes | Requirements/tasks backed by implementation evidence |
| Check Execution Rate | 100% | Yes | Required checks ran, passed, and have evidence |
| Fix Responsiveness | 100% | Yes | Actionable findings fixed or explicitly deferred/accepted |
| Recheck Rate | 100% | Yes | Fixed findings were rechecked |
| Claim Verification | 100% | Yes | Claims have evidence |
| Contradicted Claims | 0 | Fail-closed | Any claim contradicted by evidence fails the run |
| Unsupported Completion Claims | 0 | Fail-closed | Completion claims without evidence fail the run |
| Unresolved Critical Findings | 0 | Fail-closed | Critical/blocker findings cannot remain unresolved |
| New Test Failures | 0 | Fail-closed | New regressions block completion |

## Evidence Ledger Format

Start from `templates/evidence-ledger.json` in this skill directory. Minimum shape:

```json
{
  "loop_run_id": "issue-123-2026-06-18",
  "requirements": [
    {
      "id": "REQ-001",
      "text": "Add schema validation",
      "planned": true,
      "implemented": true,
      "evidence": ["diff:packages/schema/src/validators.ts"]
    }
  ],
  "tasks": [
    {
      "id": "TASK-001",
      "text": "Update validator",
      "implemented": true,
      "evidence": ["diff:packages/schema/src/validators.ts"]
    }
  ],
  "machine_evidence": {
    "git_snapshots": [],
    "pr_snapshots": []
  },
  "checks": [
    {
      "id": "CHECK-001",
      "type": "typecheck",
      "command": "npm run typecheck",
      "command_argv": ["npm", "run", "typecheck"],
      "required": true,
      "executed": true,
      "exit_code": 0,
      "source": "machine",
      "cwd": "/repo",
      "branch": "feature/issue-123",
      "commit": "abc123",
      "evidence": {
        "stdout_log": "logs/CHECK-001.stdout.log",
        "stderr_log": "logs/CHECK-001.stderr.log"
      }
    }
  ],
  "findings": [
    {
      "id": "FINDING-001",
      "source": "spec-review",
      "severity": "important",
      "status": "fixed",
      "fix_evidence": ["diff:validators.ts"],
      "recheck_evidence": ["CHECK-001"]
    }
  ],
  "claims": [
    {
      "id": "CLAIM-001",
      "text": "typecheck passed",
      "kind": "completion",
      "status": "verified",
      "evidence": ["CHECK-001"]
    }
  ],
  "regressions": {"new_failures": 0}
}
```

## Evaluation Workflow

1. **Define loop run** — Identify repo, issue/PR, branch, start/end commits, required checks, and deliverables.
2. **Extract requirements** — Parse the full issue/user request, not just checklists.
3. **Extract AI claims** — Decompose completion reports into atomic claims.
4. **Collect evidence with capture wrappers** — Do not hand-write check evidence. Use:
   ```bash
   python scripts/ledger_run.py --ledger evidence-ledger.json --check-id CHECK-001 --type test -- pytest -q
   python scripts/ledger_git_snapshot.py --ledger evidence-ledger.json --base-ref origin/main
   python scripts/ledger_pr_snapshot.py --ledger evidence-ledger.json --pr 123
   ```
   `ledger_run.py` records command argv, cwd, branch, commit, exit code, timestamps, duration, and stdout/stderr log files with `source: "machine"`.
5. **Run evaluator**:
   ```bash
   python scripts/evaluate_agent_loop.py evidence-ledger.json --format markdown
   ```
6. **If PASS** — Completion may be reported.
7. **If FAIL** — Do not claim completion. Execute only generated repair tasks, update the ledger, and re-run evaluator.

## Deterministic Repair Rules

- **Plan Coverage fails:** Add concrete plan tasks for missing requirements. Do not implement code in this repair step.
- **Traceability fails:** Attach evidence or implement only the missing requirement/task.
- **Check Execution fails:** Run the missing check through `scripts/ledger_run.py` so command/cwd/branch/commit/exit code/stdout/stderr are machine-recorded. AI-authored check evidence does not count.
- **Fix Responsiveness fails:** Fix only unresolved findings or explicitly defer/accept risk with reason.
- **Recheck Rate fails:** Rerun the original check for each fixed finding.
- **Claim Verification fails:** Provide evidence or downgrade/remove the claim.
- **Contradicted Claim exists:** Correct the report and keep the run failed until evidence verifies the corrected claim.

## Hard Rules

- The agent may not claim `COMPLETE` unless the evaluator returns `PASS`.
- `unknown`, `ambiguous`, and `unsupported` are failures for completion claims.
- A fixed finding without recheck evidence is not fixed for completion purposes.
- A check without `source: "machine"`, command output log files, and exit code does not count as executed.
- A GitHub issue/PR state claim must be verified with `gh issue view` / `gh pr view` or equivalent API output.
- A high score cannot override fail-closed conditions.

## CI Usage

The workflow `.github/workflows/agent-loop-evaluation.yml` supports flexible triggers:

- `pull_request`
- `push`
- `workflow_dispatch` with custom ledger path
- `workflow_call` from other workflows

It is **not limited to push**. Use `workflow_dispatch` for manual checks, `pull_request` for PR gates, and `workflow_call` to make other pipelines invoke the evaluator after generating/updating a ledger.

## Report Template

```markdown
# Agent Loop Evaluation Report

- Overall Verdict: PASS / FAIL
- Loop Quality Score: N/100
- Blocking Failures: N

## Scorecard
| Metric | Score | Threshold | Pass | Detail |

## Blocking Failures
- metric: reason

## Deterministic Repair Tasks
- Run/fix/recheck exactly as generated by the evaluator.
```

## Common Pitfalls

1. **Using AI text as evidence.** Treat it as a claim only; required check evidence must be `source: "machine"`.
2. **Skipping recheck after fixes.** The fix does not count until rechecked.
3. **Claiming tests passed without output.** Missing output means unsupported.
4. **Checking only issue checklists.** The full issue body is the spec.
5. **Letting score override contradictions.** Contradicted completion claims are fail-closed.
6. **Running CI only on push.** Use workflow dispatch, PR, scheduled, or workflow_call triggers as needed.

## Verification Checklist

- [ ] Evidence Ledger exists and is committed or attached as artifact
- [ ] All requirements from full spec are listed
- [ ] All completion claims are decomposed and verified
- [ ] Required checks were captured via `scripts/ledger_run.py` or equivalent machine tooling
- [ ] Required checks have `source: "machine"`, command, cwd, exit code, and stdout/stderr log files
- [ ] Findings have fix status and fix evidence
- [ ] Fixed findings have recheck evidence
- [ ] Evaluator returns PASS before completion is claimed
