# Knowledge Asset Design

The agent-loop should not only decide whether a single PR passes. It should turn failures, fixes, repeated patterns, and project-specific lessons into durable knowledge assets that future agents can reuse.

## Goals

1. **Accumulate learning** — every meaningful failure or repeated repair should become reusable knowledge, not a one-off log line.
2. **Separate evidence from lessons** — raw command output and PR state remain in the ledger; generalized lessons go into knowledge assets.
3. **Make handoff useful** — when the loop stops, humans should see not only what failed but what the system learned.
4. **Improve future loops** — future repair prompts should load relevant knowledge before attempting fixes.
5. **Keep knowledge reviewable** — entries are small Markdown files committed to the repo or exported as artifacts, so humans can edit or delete them.

## Storage Layout

Recommended project layout:

```text
.agent-loop/
  knowledge/
    index.json
    failures/
      YYYYMMDD-HHMMSS-slug.md
    patterns/
      YYYYMMDD-HHMMSS-slug.md
    decisions/
      YYYYMMDD-HHMMSS-slug.md
    handoffs/
      YYYYMMDD-HHMMSS-slug.md
```

This repo provides a generic template under `templates/knowledge-entry.md` and a CLI helper under `scripts/knowledge_record.py`.

## Entry Types

### Failure Knowledge

Use when a run fails or escalates.

Should capture:

- trigger: CI failure, evaluator gate, review finding, merge conflict, auth issue, flaky test, ambiguous spec
- symptom: what the agent saw
- root cause: what actually caused it, if known
- fix attempted: what was tried
- final status: fixed, escalated, deferred, accepted risk
- prevention: what future agents should do first
- evidence: ledger IDs, check IDs, PR URL, log paths

### Pattern Knowledge

Use when a repair repeats or a successful workflow emerges.

Examples:

- “Next.js authenticated server pages need `dynamic = "force-dynamic"`.”
- “This repo requires develop-branch PRs, not main.”
- “RLS migrations must include service role policy and indexes.”

### Decision Knowledge

Use when the human or project makes a durable choice.

Examples:

- “Humans merge main; agents merge only develop.”
- “Use MCP for agent-facing dashboard access, REST for browser UI.”

### Handoff Knowledge

Use when automation stops and humans need context.

Should include:

- stop reason
- attempts used
- repeated failure fingerprint
- last blocking failures
- proposed next human action
- reusable lesson candidates

## Promotion Rules

Not every observation becomes durable knowledge. Promote only when at least one is true:

- the same failure happened more than once
- the fix required non-obvious reasoning
- the user corrected the agent
- the project has a stable convention that future agents need
- a CI or review failure can be prevented next time
- a human handoff contains a lesson that should survive the run

Do not promote:

- transient commit SHAs
- temporary branch names unless needed for handoff
- raw long logs
- facts likely stale within a week
- secrets or credentials

## Loop Integration

### During evaluation

The evaluator keeps deterministic pass/fail authority. It may identify knowledge candidates from:

- repeated blocking failures
- unresolved critical findings
- unsupported or contradicted claims
- repeated repair task fingerprints

### During repair

Before each repair attempt, the controller should load relevant knowledge:

1. current repository path
2. failure metrics
3. check types
4. affected files, if known
5. previous matching knowledge entries

The repair prompt should include only concise relevant entries, not the whole knowledge base.

### On escalation

When bounded repair stops, the controller should create a handoff report and a knowledge candidate. The candidate is reviewable; humans can decide whether to commit it.

## Code Commenting Policy

This project should be intentionally comment-rich in the orchestration layer.

Use comments/docstrings for:

- why a class or function exists
- what authority it has and does not have
- what failure mode it prevents
- what invariants must not be broken
- where the data comes from and whether it is trusted

Avoid comments that merely restate a line of code.

Good example:

```python
class KnowledgeEntry:
    """A durable lesson extracted from an agent-loop run.

    Knowledge entries are not evidence and must not make the evaluator pass.
    They exist to improve future prompts and human handoffs. Keeping this type
    separate from ledger checks prevents learned advice from being mistaken for
    machine proof.
    """
```

Bad example:

```python
count += 1  # increment count
```

## Safety Rules

- Knowledge cannot override evaluator gates.
- Knowledge cannot verify claims.
- Knowledge cannot replace command evidence.
- Knowledge entries should be small and reviewable.
- Write potentially sensitive details as references to evidence paths, not copied secrets/log dumps.

## Future Extensions

- MCP tools: `list_knowledge`, `search_knowledge`, `record_knowledge_candidate`.
- Dashboard panel: recent failures, repeated patterns, suggested knowledge promotions.
- Automatic deduplication by failure fingerprint and tags.
- Human approval flow before promoting candidates to committed knowledge.
