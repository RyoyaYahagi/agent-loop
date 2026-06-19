# Parallel Grouping Pattern for Issue Implementation

When implementing a medium-to-large issue (8+ endpoints, multiple services), group tasks into phases and run independent subagents in parallel within each phase.

## Pattern

```
Phase 1: Shared foundation (1 subagent)
  → api-response.ts, to-error-response.ts, auth helpers, ownership checks

Phase 2: Service layer (N parallel subagents, no cross-dependencies)
  → Subagent A: session-service + question-service
  → Subagent B: answer-service + draft-service
  → Subagent C: review-service + finalize-service

Phase 3: API routes (N parallel subagents, depends on Phase 2)
  → Subagent D: rule-sessions/ + [sessionId]/ routes
  → Subagent E: answers/ + next-question/ routes
  → Subagent F: review/ + finalize/ routes

Phase 4: Verification (parent session)
  → tsc --noEmit, npm test, git commit
```

## Rules

- **Inside a phase**: tasks must be independent (no two subagents write the same file)
- **Across phases**: later phases depend on earlier phases completing
- **Parent session**: manages the todo list, orchestrates phases, runs final verification
- **Subagent context**: each subagent gets the full file paths and code it must create; do not make subagents discover the plan themselves

## When to use

- Issue touches 6+ new files
- Clear natural groupings exist (e.g., CRUD services vs. route handlers)
- Type-checking at the end is acceptable (don’t need per-subagent type safety)

## When NOT to use

- Small issues (≤3 files) — single subagent or manual is faster
- Heavy cross-file dependencies where every file imports from every other file
- Tasks that must share state during implementation (not just after)
