# {{ title }}

- Type: failure | pattern | decision | handoff
- Status: candidate | accepted | superseded | rejected
- Created at: {{ created_at }}
- Source ledger: {{ ledger_path }}
- Related run: {{ loop_run_id }}
- Tags: {{ tags }}

## Summary

Short reusable lesson. Future agents should understand this in 1-3 sentences.

## Context

What was happening when this was discovered?

## Symptom

What failure, confusion, or repeated pattern was observed?

## Root Cause

What caused it? Use `unknown` if not known yet.

## Fix / Decision

What fixed it, or what durable decision was made?

## Prevention

What should a future agent do before hitting this again?

## Evidence References

- Ledger IDs:
- Check IDs:
- PR / issue URLs:
- Log paths:

## Human Review Notes

Anything a human should confirm before accepting this as durable knowledge.
