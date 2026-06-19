---
name: development-subagent-pipeline
description: "Investigate codebase with a lightweight model, summarize findings, then delegate implementation to subagents."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
---

# Subagent Investigation Pipeline

## Overview

Before implementing any non-trivial task, run a lightweight investigation subagent to understand the codebase, then summarize the findings. Use that summary to either implement directly or dispatch a focused implementer subagent.

**Core principle:** Never start coding in the dark. A cheap nano/flash model can save expensive tokens later by pointing you to the right files and constraints upfront.

## When to Use

- Task touches unfamiliar code
- Task involves more than 2 files or crosses module boundaries
- Need to understand existing patterns before adding new code
- Want to parallelize work but aren't sure what's safe to split

**Skip when:** The task is a one-line fix in a file you already have open, or the user explicitly provided all necessary context.

## Model Selection by Task Weight

`delegate_task` inherits the parent session's model and **cannot switch models** via the child call. To use a different model for a subagent, first switch the parent session's model with `/model`, then call `delegate_task`.

| Phase | Weight | Suggested Parent Model |
|-------|--------|----------------------|
| Investigation | light | gpt-5.4-mini |
| Summarization | light | gpt-5.4-mini |
| Planning | standard | gpt-5.4-medium, kimi-k2.6 |
| Implementation | standard/heavy | kimi-k2.6, gpt-5.4 |
| Review | standard | kimi-k2.6 |
| Final Check | light | gpt-5.5-low |

### How to Dispatch with `delegate_task`

```python
# 1. Switch parent model if needed
/model gpt-5.4-mini

# 2. Dispatch investigator subagent
delegate_task(
  goal="Investigate the codebase for ...",
  context="Task: implement feature X. Search for relevant files and return a concise summary.",
  toolsets=["search", "file", "terminal"],
  role="leaf"
)

# 3. Switch parent model back for heavier work
/model kimi-k2.6

# 4. Dispatch implementer subagent with investigation summary
delegate_task(
  goal="Implement ...",
  context="Investigation summary: ...\nKey files: ...\nMust follow: ...",
  toolsets=["file", "patch", "terminal"],
  role="leaf"
)
```

**Why `delegate_task`?**
- **Context isolation:** Each child gets its own conversation and terminal session
- **Built-in:** No external process to manage; works inside Docker
- **Synchronous:** Parent waits for the child summary

**Trade-off:** Child sessions cannot use a different model than the parent. If you need a light model for investigation and a heavy model for implementation, you must `/model` switch in between.

## The Pipeline

### Phase 1: Investigation (light model)

The investigator should:
1. Search for files related to the task
2. Read relevant entry points and existing patterns
3. Identify files that need to change, conventions, dependencies, potential conflicts, missing context

**Investigator prompt template:**
```
You are an Investigator. Your job is to understand the codebase context for this task.

Task: {task_description}

Investigate and return a JSON object with:
- relevantFiles: array of file paths and why they matter
- conventions: array of patterns you see
- conflicts: array of potential issues
- missingInfo: array of questions we need answered before implementing
- suggestedPlan: brief suggested order of implementation steps
```

### Phase 2: Summarization (light model)

Distill investigation output into a concise brief:
- Condense file lists to only the most important
- Highlight the top 3 conventions that MUST be followed
- Surface any blockers or missing info
- Produce a 1-paragraph execution summary

### Phase 3: Decision — Parent vs. Subagent

**Implement in parent session if:**
- The task is complex and benefits from the heavy model
- You need to preserve context across multiple file edits
- The task requires your direct reasoning (safety-critical logic)

**Delegate to `delegate_task` if:**
- The task is well-scoped and independent
- Parallel execution with other tasks is possible

### Phase 4: Implementation

If implementing in parent:
1. Use the summary as your map
2. Read files as needed
3. Make changes
4. Run validation

If delegating:
1. Use `delegate_task` with the summary as context
2. Set `toolsets` to only what's needed
3. Do NOT make the subagent re-investigate — provide the findings directly

### Phase 5: Validation

Always run the smallest useful check set:
```bash
npm run lint
npm run typecheck
npm run build
```

## Efficiency Rules

1. **Investigation budget:** Max 2-3 tool calls for investigation
2. **Summarization budget:** One-shot prompt. No back-and-forth.
3. **Implementation budget:** Use the investigation output to avoid re-reading files
4. **Token math:** A nano/flash investigation (5k tokens) that prevents a standard model from reading 10 files it didn't need to (30k tokens) is a net save.

## Context Hygiene Between Phases

Treat each pipeline phase as a **separate reasoning surface**. Do not let one phase's raw tool output leak into the next phase's context.

### How to enforce it

**1. Prefer `delegate_task` for each phase**

Each `delegate_task` runs in its own isolated session. The parent only receives the child's summary.

**2. If you must do it in the parent session, clean up between phases**

- **`/compress`** — Summarizes middle turns while keeping the goal and recent context
- **`/new`** — Use when a major issue is complete and you are starting a genuinely new task
- **File offload** — Write investigation results to a file, then `/compress` and `read_file` only the condensed summary

### Practical rules

| Situation | Action |
|-----------|--------|
| Switching from investigation to implementation | `delegate_task` for both, or write summary to file + `/compress` |
| Reviewing code you just wrote | `delegate_task` for reviewer, or `/compress` before starting review |
| Starting a new GitHub issue | `/new` |
| Same issue, but token count is high | `/compress` |

### What NOT to do

- **Do not copy-paste a full `search_files` result into the parent context** and then continue with implementation
- **Do not chain multiple `delegate_task` calls in the same parent turn without reading the summaries**
- **Do not rely on the child's temp files as the source of truth.** Always distill before passing downstream.

## Pitfalls

- **Don't skip investigation for "small" tasks.** A one-line change in the wrong place costs more than a cheap investigation.
- **Don't let the investigator write code.** Its job is to read and map, not to implement.
- **Don't re-investigate in every subagent.** Pass the summary downstream via `context`.
- **Don't ignore blockers.** If the summary says "missing: user auth middleware", stop and ask the user.
- **Don't assume parent and child share filesystem state.** `delegate_task` runs in a **separate terminal session**. If the child writes to a temp file, the parent must read it from the same absolute path.
- **Don't forget `delegate_task` uses the parent model.** If you dispatched an investigator after `/model gpt-5.4-mini`, a subsequent `delegate_task` for implementation will also use `gpt-5.4-mini` unless you `/model` switch back first.
- **Don't give subagents open-ended goals.** Each `delegate_task` should have a single, verifiable deliverable.
- **Toolsets matter.** Restrict `toolsets` to only what the subagent needs. An investigator needs `["search","file","terminal"]`. An implementer may need `["file","patch","terminal"]` but usually does not need `["web","browser","image_gen"]`.
