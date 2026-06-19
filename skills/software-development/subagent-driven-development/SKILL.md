---
name: subagent-driven-development
description: "Execute plans via delegate_task subagents (2-stage review)."
version: 1.3.0
author: Hermes Agent (adapted from obra/superpowers)
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [delegation, subagent, implementation, workflow, parallel]
    related_skills: [writing-plans, requesting-code-review, test-driven-development, github-issues, agent-loop-evaluation]
---

# Subagent-Driven Development

## Overview

Execute implementation plans by dispatching fresh subagents per task with systematic two-stage review.

**Core principle:** Fresh subagent per task + two-stage review (spec then quality) = high quality, fast iteration.

## When to Use

Use this skill when:
- You have an implementation plan (from writing-plans skill or user requirements)
- Tasks are mostly independent
- Quality and spec compliance are important
- You want automated review between tasks

**vs. manual execution:**
- Fresh context per task (no confusion from accumulated state)
- Automated review process catches issues early
- Consistent quality checks across all tasks
- Subagents can ask questions before starting work

## The Process

### 1. Read and Parse Plan

Read the plan file. Extract ALL tasks with their full text and context upfront. **Before dispatching any subagents, verify the actual environment state via terminal (pwd, ls, git status, etc.) — do not rely on session_search or historical memory about file paths, repo locations, or installed tools. Shared workspaces and containerized backends can diverge from cached knowledge.** Create a todo list:

```python
# Read the plan
read_file("docs/plans/feature-plan.md")

# Verify actual environment state via terminal
terminal("pwd && ls -la && git status")

# Create todo list with all tasks
todo([
    {"id": "task-1", "content": "Create User model with email field", "status": "pending"},
    {"id": "task-2", "content": "Add password hashing utility", "status": "pending"},
    {"id": "task-3", "content": "Create login endpoint", "status": "pending"},
])
```

**Key:** Read the plan ONCE. Extract everything. Don't make subagents read the plan file — provide the full task text directly in context. **Verify environment via terminal before every dispatch — never assume paths from memory.**

### 2. Per-Task Workflow

For EACH task in the plan:

#### Step 1: Dispatch Implementer Subagent

Use `delegate_task` with complete context:

```python
delegate_task(
    goal="Implement Task 1: Create User model with email and password_hash fields",
    context="""
    TASK FROM PLAN:
    - Create: src/models/user.py
    - Add User class with email (str) and password_hash (str) fields
    - Use bcrypt for password hashing
    - Include __repr__ for debugging

    FOLLOW TDD:
    1. Write failing test in tests/models/test_user.py
    2. Run: pytest tests/models/test_user.py -v (verify FAIL)
    3. Write minimal implementation
    4. Run: pytest tests/models/test_user.py -v (verify PASS)
    5. Run: pytest tests/ -q (verify no regressions)
    6. Commit: git add -A && git commit -m "feat: add User model with password hashing"

    PROJECT CONTEXT:
    - Python 3.11, Flask app in src/app.py
    - Existing models in src/models/
    - Tests use pytest, run from project root
    - bcrypt already in requirements.txt
    """,
    toolsets=['terminal', 'file']
)
```

#### Step 2: Dispatch Spec Compliance Reviewer

After the implementer completes, verify against the original spec:

```python
delegate_task(
    goal="Review if implementation matches the spec from the plan",
    context="""
    ORIGINAL TASK SPEC:
    - Create src/models/user.py with User class
    - Fields: email (str), password_hash (str)
    - Use bcrypt for password hashing
    - Include __repr__

    CHECK:
    - [ ] All requirements from spec implemented?
    - [ ] File paths match spec?
    - [ ] Function signatures match spec?
    - [ ] Behavior matches expected?
    - [ ] Nothing extra added (no scope creep)?

    OUTPUT: PASS or list of specific spec gaps to fix.
    """,
    toolsets=['file']
)
```

**If spec issues found:** Fix gaps, then re-run spec review. Continue only when spec-compliant.

#### Step 3: Dispatch Code Quality Reviewer

After spec compliance passes:

```python
delegate_task(
    goal="Review code quality for Task 1 implementation",
    context="""
    FILES TO REVIEW:
    - src/models/user.py
    - tests/models/test_user.py

    CHECK:
    - [ ] Follows project conventions and style?
    - [ ] Proper error handling?
    - [ ] Clear variable/function names?
    - [ ] Adequate test coverage?
    - [ ] No obvious bugs or missed edge cases?
    - [ ] No security issues?

    OUTPUT FORMAT:
    - Critical Issues: [must fix before proceeding]
    - Important Issues: [should fix]
    - Minor Issues: [optional]
    - Verdict: APPROVED or REQUEST_CHANGES
    """,
    toolsets=['file']
)
```

**If quality issues found:** Fix issues, re-review. Continue only when approved.

#### Step 4: Mark Complete

```python
todo([{"id": "task-1", "content": "Create User model with email field", "status": "completed"}], merge=True)
```

### 3. Final Review (including Omissions Check)

After ALL tasks are complete, dispatch a final integration reviewer that checks for **both** integration consistency **and** spec omissions.

**If a large number of issues were implemented in rapid succession** (e.g., sequential MVP issues that all follow the same DB → Schema → Service → API → docs pattern), the final review MUST also include a **Post-Batch Spot-Check** before declaring completion. Speed from pattern repetition risks copy-paste drift — a file may have the correct name but wrong logic, or a migration may miss a critical index or RLS policy.

**Spot-check procedure:**
1. Pick 1–3 representative implementations from the batch (the most complex, the first, and the last).
2. For each, read the **actual file content** of:
   - The database migration (verify columns, constraints, RLS, indexes against the issue spec)
   - The Zod / TypeScript schema (verify all fields and types from the issue are present)
   - The core service file (verify the key business logic functions exist and match the issue description)
3. Run the full test suite.
4. Run typecheck (`tsc --noEmit` or equivalent).
5. Run lint and verify no *new* errors were introduced by this batch (pre-existing warnings are acceptable if documented).
6. **If any discrepancy is found**, assume the same pattern error may exist in other tasks from the same batch. Search for the pattern across all related files and fix systematically.

**Reporting:** Include the spot-check results in the final implementation report. Example:
```
Spot-check: #93 Structured Trading Rules
- Migration: 6 JSONB fields + status enum + RLS + indexes ✅
- Schema: All fields typed with Type Guards ✅
- Service: Risk review service has 7 deterministic checks ✅
- Tests: 355/355 pass ✅
- TypeCheck: 0 errors ✅
- Lint: 0 new errors ✅
```

**Integration reviewer prompt:**

```python
delegate_task(
    goal="Review the entire implementation for consistency, integration issues, AND spec omissions",
    context="""
    All tasks from the plan are complete. Review the full implementation:

    INTEGRATION CHECKS:
    - Do all components work together?
    - Any inconsistencies between tasks?
    - All tests passing?

    OMISSIONS CHECK (compare against original issue/plan):
    - Every file from the spec exists and has correct content?
    - Every checklist item in the issue was addressed?
    - Required schemas, types, and exports are present?
    - Documentation that was asked for was created?
    - Security checks or validations that were specified were implemented?
    - Any TODOs or placeholder code that should have been real implementations?

    OUTPUT FORMAT:
    - PASS items: [nothing to fix]
    - FIX items: [specific files/changes needed, with suggested code if possible]
    """,
    toolsets=['terminal', 'file']
)
```

**If omissions are found**, do not declare completion. Dispatch fix subagents for the gaps and re-run the omissions check. Only finish when the reviewer reports no outstanding omissions.

### 4. Verify and Commit

```bash
# Run full test suite
pytest tests/ -q

# Review all changes
git diff --stat

# Final commit if needed
git add -A && git commit -m "feat: complete [feature name] implementation"
```

### 5. Evidence-Gated Loop Evaluation

For autonomous or issue-driven runs where the agent might claim planning/checking/fixing/completion, load `agent-loop-evaluation` before final reporting. Treat the implementation report as untrusted claims until a deterministic Evidence Ledger verifies them.

Minimum rule set:
1. Record requirements, tasks, checks, findings, fixes, rechecks, claims, and regressions in an Evidence Ledger.
2. Run the deterministic evaluator (for Hermes Agent repos: `python scripts/evaluate_agent_loop.py <ledger>`).
3. If any hard gate fails, do **not** claim completion or proceed to the next issue. Execute only the generated repair tasks, update evidence, and re-run the evaluator.
4. Completion is allowed only after evaluator PASS. AI text is never evidence; command output, git/file diffs, PR/issue state, and review artifacts are evidence.

Use this especially when the user asks whether the AI really planned, checked, fixed, or completed work, or when they want CI to block bad agent-loop metrics.

## Task Granularity

**Each task = 2-5 minutes of focused work.**

**Too big:**
- "Implement user authentication system"

**Right size:**
- "Create User model with email and password fields"
- "Add password hashing function"
- "Create login endpoint"
- "Add JWT token generation"
- "Create registration endpoint"

## Red Flags — Never Do These

- Start implementation without verifying the actual environment via terminal (paths, repo state, tool availability)
- Rely on session_search or historical memory about filesystem state when the current environment may differ
- Start implementation without a plan
- Skip reviews (spec compliance OR code quality)
- Proceed with unfixed critical/important issues
- Dispatch multiple implementation subagents for tasks that touch the same files
- Make subagent read the plan file (provide full text in context instead)
- Skip scene-setting context (subagent needs to understand where the task fits)
- Ignore subagent questions (answer before letting them proceed)
- Accept "close enough" on spec compliance
- Skip review loops (reviewer found issues → implementer fixes → review again)
- Let implementer self-review replace actual review (both are needed)
- **Start code quality review before spec compliance is PASS** (wrong order)
- Move to next task while either review has open issues
- **Claim completion after rapid batch implementation without running a post-batch spot-check** (speed creates false confidence; verify representative files against the spec)

## Handling Issues

### Due Diligence Rule: Try Before You Declare Failure

If you recognize that something from the spec or checklist was not completed, **do not immediately report "I couldn't do it."** Instead:

1. **Attempt the missing item first** — create the file, run the test, write the doc, whatever was skipped
2. **If you succeed**, report it as completed
3. **If you still cannot do it after a good-faith attempt**, report:
   - What you tried
   - Why it failed (specific error, blocker, missing dependency)
   - What would be needed to resolve it

**Never check off a checklist item you did not actually do.** If the issue has a checklist, mark only the items you completed as `[x]`. Leave uncompleted items as `[ ]` and explain why in your report.

This applies to:
- Missing files from the spec
- Skipped tests
- Undone documentation
- Incomplete security checks
- Any checklist item in the issue body

### If Subagent Asks Questions

- Answer clearly and completely
- Provide additional context if needed
- Don't rush them into implementation

### If Reviewer Finds Issues

- Implementer subagent (or a new one) fixes them
- Reviewer reviews again
- Repeat until approved
- Don't skip the re-review

### If Subagent Fails a Task

- Dispatch a new fix subagent with specific instructions about what went wrong
- Don't try to fix manually in the controller session (context pollution)

## Efficiency Notes

**Why fresh subagent per task:**
- Prevents context pollution from accumulated state
- Each subagent gets clean, focused context
- No confusion from prior tasks' code or reasoning

**Why two-stage review:**
- Spec review catches under/over-building early
- Quality review ensures the implementation is well-built
- Catches issues before they compound across tasks

**Cost trade-off:**
- More subagent invocations (implementer + 2 reviewers per task)
- But catches issues early (cheaper than debugging compounded problems later)

## Issue-Driven Repository Workflow Variant

When the user wants implementation to be driven from GitHub issues rather than a standalone feature brief, add these steps before the normal per-task workflow:

1. Select the next issue using an explicit rule (priority label, milestone, or agreed queue order). Do not guess informally.
2. Read the issue body plus the local governing docs for the touched area.
3. Create and save a plan file before any code changes.
4. Open a per-issue execution record in the repo. Use `docs/ai-handoffs/issue-{number}-handoff.md` as the convention if the project has a `docs/ai-handoffs/` directory. See the skill template at `templates/ai-handoff.md` for the recommended structure. The document should include:
   - List of all created/modified files with what they enable
   - Review findings and what was/wasn't fixed with reasons
   - Technical debt items
   - Things the next AI should know (branch, test status, DB tables, etc.)
   - Completion checklist status
   This preserves context for future AI sessions working on the same codebase.
5. If the workflow includes an external reporting channel (Discord, Slack, etc.), send status updates at minimum for: start, plan ready, blocker/needs-decision, implementation complete, and final verification result.
6. If work becomes blocked by missing product or architecture decisions, stop advancing that task, record the blocker, and report it instead of improvising around the missing decision.
7. Reserve a final review/verification pass after implementation rather than treating implementer output as completion. Dispatch a review subagent to check for omissions against the full issue body.

This variant is especially important for safety-sensitive products where issue text is not the only source of truth and durable decisions must be reflected back into docs, ADRs, tests, or schemas.

### Queue progression: next issue without approval

When the user instructs you to implement issues sequentially (e.g., "issue 50から順番に実装して" or "implement issues in order"), the workflow is:

1. Implement the current issue fully (including trying omitted items, creating the handoff doc, and running the review pass)
2. Report completion to the user with the full implementation report format above
3. **Proceed to the next issue automatically** — no need to wait for explicit approval
4. If you reach an issue number that does not exist, report that fact and ask for the next target

Exception: if the user says "stop" or "wait", halt immediately.

**Start a fresh conversation for each new issue.** Do not continue implementation of a new issue inside an already-long session. Benefits:
- Clean context per issue (no accumulated confusion from prior issue's code or reasoning)
- Implementation reports are self-contained and traceable
- Easier to resume or review later by issue number

Exception: trivial follow-ups (e.g., `.gitignore` tweaks immediately after a commit) may stay in the same session.

### Implementation report format

When reporting completion, do not just list files. **File listings alone are insufficient.** The report MUST include all of the following:

1. **What each file enables** — functional description of what can now be done, not just paths. Example: "`src/app/api/rule-sessions/route.ts` — POST/GET endpoints so clients can create and list rule sessions" NOT just "Created `src/app/api/rule-sessions/route.ts`"
2. **Original issue summary** — purpose and background of the issue being implemented, in your own words
3. **Uncertainties or questions encountered** — any ambiguous specs, missing requirements, or assumptions made during implementation
4. **Parts you are not confident about** — areas that may need review, refactoring, or future rework

**If you know something was not done, report it honestly.** Do not hide omissions. Include:
- What was skipped and why
- What would be needed to complete it
- Any risks of the omission

**Example report:**
```
## Issue #49: Rule Session API MVP

### What each file enables
- `src/app/api/rule-sessions/route.ts` — POST/GET endpoints so clients can create and list rule sessions
- `src/features/rules/services/rule-session-service.ts` — CRUD operations + automatic versioning on finalize

### Original issue summary
Build a minimal API for rule design sessions: create, list, get detail, save answers, get next questions, run AI review, and finalize rules.

### Uncertainties
- `applyAnswerToRuleJson` uses `as any` for timeHorizon parsing; should switch to `TimeHorizonSchema.safeParse()` per issue notes but was skipped for MVP speed
- Transaction safety across answer insert + rule_json update is not enforced (noted for follow-up)

### Not confident about
- `rule-review-service.ts` assumes `safety.passed = true` from MockProvider; real safety check flow is punted to a later issue

### Omissions / not done
- `docs/api.md` not created (will add in follow-up)
- Security checklist manual verification not performed
```

### Issue body as the full specification

The entire issue body is the specification, not just the completion checklist. When implementing:

- Read the full issue body carefully, including sections like "Background", "Basic Policy", "Design", "Security Checklist", "Privacy Policy", etc.
- Implement everything described in the issue body, even if it is not listed in an explicit checklist
- Do not skip items just because they are not in a "完了条件" or "Completion Criteria" section
- If the issue body describes a file, schema, API, or behavior that should exist, create it even if it is not checkboxed

**If you recognize something from the issue body was not completed, attempt it before reporting failure.** Do not immediately say "I couldn't do it." Try first. If you still cannot do it after a good-faith attempt, report:
- What you tried
- Why it failed (specific error, blocker, missing dependency)
- What would be needed to resolve it

This is the Due Diligence Rule: try before you declare failure.

### Issue lifecycle: do not auto-close

**Never close the GitHub issue from the agent.** Instead:
- If the issue body contains a checklist, check off ONLY the items that were actually implemented as `[x]`
- Leave uncompleted items as `[ ]` and explain why in your report
- Never check off an item you did not actually do
- Leave the issue OPEN so the human can verify, run final checks, and close it manually
- Only close an issue if the user explicitly instructs you to

## Integration with Other Skills

### With writing-plans

This skill EXECUTES plans created by the writing-plans skill:
1. User requirements → writing-plans → implementation plan
2. Implementation plan → subagent-driven-development → working code

### With test-driven-development

Implementer subagents should follow TDD:
1. Write failing test first
2. Implement minimal code
3. Verify test passes
4. Commit

Include TDD instructions in every implementer context.

### With requesting-code-review

The two-stage review process IS the code review. For final integration review, use the requesting-code-review skill's review dimensions.

### With systematic-debugging

If a subagent encounters bugs during implementation:
1. Follow systematic-debugging process
2. Find root cause before fixing
3. Write regression test
4. Resume implementation

## Subagent Investigation Pipeline

Before implementing any non-trivial task, run a lightweight investigation subagent to understand the codebase, then summarize the findings. Use that summary to either implement directly or dispatch a focused implementer subagent.

**Core principle:** Never start coding in the dark. A cheap nano/flash model can save expensive tokens later by pointing you to the right files and constraints upfront.

**When to use:** Task touches unfamiliar code, involves more than 2 files, crosses module boundaries, or you need to understand existing patterns before adding new code.

**Skip when:** The task is a one-line fix in a file you already have open, or the user explicitly provided all necessary context.

### Model Selection by Task Weight

`delegate_task` inherits the parent session's model and **cannot switch models** via the child call. To use a different model for a subagent, first switch the parent session's model with `/model`, then call `delegate_task`.

| Phase | Weight | Suggested Parent Model |
|-------|--------|----------------------|
| Investigation | light | gpt-5.4-mini |
| Summarization | light | gpt-5.4-mini |
| Planning | standard | gpt-5.4-medium, kimi-k2.6 |
| Implementation | standard/heavy | kimi-k2.6, gpt-5.4 |
| Review | standard | kimi-k2.6 |
| Final Check | light | gpt-5.5-low |

### The Pipeline

1. **Investigation** (light model) — Search files, read entry points, identify conventions, conflicts, missing info
2. **Summarization** (light model) — Distill to concise brief: top files, top 3 conventions, blockers
3. **Decision** — Implement in parent (complex, safety-critical) or delegate to `delegate_task` (well-scoped, independent)
4. **Implementation** — Use the summary as your map; do NOT make subagents re-investigate
5. **Validation** — Run lint, typecheck, build

**Efficiency rules:**
- Investigation budget: max 2-3 tool calls
- Summarization budget: one-shot prompt
- Never give subagents open-ended goals; each `delegate_task` should have a single, verifiable deliverable
- Restrict `toolsets` to only what the subagent needs

**Context hygiene:** Treat each pipeline phase as a separate reasoning surface. Use `delegate_task` for each phase (isolated sessions), or `/compress` between phases in the parent session. Do not copy-paste full `search_files` results into parent context and continue with implementation.

For the full pipeline guide, model switching details, and pitfalls, see `references/subagent-investigation-pipeline.md`.

## Example Workflow

```
[Read plan: docs/plans/auth-feature.md]
[Create todo list with 5 tasks]

--- Task 1: Create User model ---
[Dispatch implementer subagent]
  Implementer: "Should email be unique?"
  You: "Yes, email must be unique"
  Implementer: Implemented, 3/3 tests passing, committed.

[Dispatch spec reviewer]
  Spec reviewer: ✅ PASS — all requirements met

[Dispatch quality reviewer]
  Quality reviewer: ✅ APPROVED — clean code, good tests

[Mark Task 1 complete]

--- Task 2: Password hashing ---
[Dispatch implementer subagent]
  Implementer: No questions, implemented, 5/5 tests passing.

[Dispatch spec reviewer]
  Spec reviewer: ❌ Missing: password strength validation (spec says "min 8 chars")

[Implementer fixes]
  Implementer: Added validation, 7/7 tests passing.

[Dispatch spec reviewer again]
  Spec reviewer: ✅ PASS

[Dispatch quality reviewer]
  Quality reviewer: Important: Magic number 8, extract to constant
  Implementer: Extracted MIN_PASSWORD_LENGTH constant
  Quality reviewer: ✅ APPROVED

[Mark Task 2 complete]

... (continue for all tasks)

[After all tasks: dispatch final integration reviewer]
[Run full test suite: all passing]
[Done!]
```

## Remember

```
Fresh subagent per task
Two-stage review every time
Spec compliance FIRST
Code quality SECOND
Never skip reviews
Catch issues early
```

**Quality is not an accident. It's the result of systematic process.**

## Further reading (load when relevant)

When the orchestration involves significant context usage, long review loops, or complex validation checkpoints, load these references for the specific discipline:

- **`references/context-budget-discipline.md`** — Four-tier context degradation model (PEAK / GOOD / DEGRADING / POOR), read-depth rules that scale with context window size, and early warning signs of silent degradation. Load when a run will clearly consume significant context (multi-phase plans, many subagents, large artifacts).
- **`references/gates-taxonomy.md`** — The four canonical gate types (Pre-flight, Revision, Escalation, Abort) with behavior, recovery, and examples. Load when designing or reviewing any workflow that has validation checkpoints — use the vocabulary explicitly so each gate has defined entry, failure behavior, and resumption rules.
- **`references/subagent-investigation-pipeline.md`** — Lightweight investigation subagent pattern: search codebase, summarize findings, then decide whether to implement in parent or delegate to `delegate_task`. Includes model selection table, phase breakdown, efficiency rules, and context-hygiene guidelines.

Both references adapted from gsd-build/get-shit-done (MIT © 2025 Lex Christopherson).
