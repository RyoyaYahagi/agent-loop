"""Durable knowledge capture for agent-loop runs.

The evaluator decides whether a run passes. This module has a different job: it
turns useful lessons from failed or repeated runs into small, reviewable Markdown
assets. Keeping this separate is intentional. A lesson can guide the next agent,
but it must never count as evidence that makes the current evaluator pass.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from hermes_cli.agent_loop_capture import load_ledger

KNOWLEDGE_TYPES = {"failure", "pattern", "decision", "handoff"}
KNOWLEDGE_STATUSES = {"candidate", "accepted", "superseded", "rejected"}


def utc_now() -> str:
    """Return a stable UTC timestamp for filenames and entry metadata."""

    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def slugify(text: str, *, max_length: int = 64) -> str:
    """Convert human text into a safe filename slug.

    Knowledge files are meant to be committed and browsed by humans, so the slug
    should be readable while still avoiding shell-hostile characters.
    """

    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", text.strip().lower()).strip("-._")
    return (slug or "knowledge")[:max_length].strip("-._") or "knowledge"


@dataclass(frozen=True)
class KnowledgeEntry:
    """A durable lesson extracted from an agent-loop run.

    This is intentionally not part of the evaluator's proof model. Evidence lives
    in the ledger; this object records reusable advice, failure explanations, and
    human handoff context that future agents can load before attempting repairs.
    """

    title: str
    entry_type: str
    status: str = "candidate"
    summary: str = ""
    context: str = ""
    symptom: str = ""
    root_cause: str = "unknown"
    fix_or_decision: str = ""
    prevention: str = ""
    evidence_references: Sequence[str] = ()
    tags: Sequence[str] = ()
    source_ledger: str | None = None
    loop_run_id: str | None = None
    created_at: str = ""

    def normalized(self) -> "KnowledgeEntry":
        """Validate enums and fill creation time without mutating the entry."""

        if self.entry_type not in KNOWLEDGE_TYPES:
            raise ValueError(f"entry_type must be one of {sorted(KNOWLEDGE_TYPES)}")
        if self.status not in KNOWLEDGE_STATUSES:
            raise ValueError(f"status must be one of {sorted(KNOWLEDGE_STATUSES)}")
        return KnowledgeEntry(**{**asdict(self), "created_at": self.created_at or utc_now()})


def _entry_dir(root: Path, entry_type: str) -> Path:
    """Map entry type to the durable on-disk category directory."""

    directory_name = {
        "failure": "failures",
        "pattern": "patterns",
        "decision": "decisions",
        "handoff": "handoffs",
    }[entry_type]
    return root / ".agent-loop" / "knowledge" / directory_name


def render_markdown(entry: KnowledgeEntry) -> str:
    """Render one knowledge entry as small, reviewable Markdown."""

    entry = entry.normalized()
    refs = "\n".join(f"- {ref}" for ref in entry.evidence_references) or "- none"
    tags = ", ".join(entry.tags) if entry.tags else "none"
    return f"""# {entry.title}

- Type: {entry.entry_type}
- Status: {entry.status}
- Created at: {entry.created_at}
- Source ledger: {entry.source_ledger or "none"}
- Related run: {entry.loop_run_id or "none"}
- Tags: {tags}

## Summary

{entry.summary or "TBD"}

## Context

{entry.context or "TBD"}

## Symptom

{entry.symptom or "TBD"}

## Root Cause

{entry.root_cause or "unknown"}

## Fix / Decision

{entry.fix_or_decision or "TBD"}

## Prevention

{entry.prevention or "TBD"}

## Evidence References

{refs}

## Human Review Notes

Review whether this should be promoted from `candidate` to `accepted`.
"""


def _load_index(index_path: Path) -> dict[str, Any]:
    """Load the lightweight index used by dashboards/MCP search tools."""

    if not index_path.exists():
        return {"entries": []}
    data = json.loads(index_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("entries", []), list):
        raise ValueError(f"Invalid knowledge index: {index_path}")
    return data


def record_knowledge_entry(repo_root: str | Path, entry: KnowledgeEntry) -> Path:
    """Write a knowledge Markdown file and update `.agent-loop/knowledge/index.json`.

    The index intentionally stores only metadata and a relative path. The full
    lesson remains in Markdown so humans can review it in PR diffs.
    """

    root = Path(repo_root)
    entry = entry.normalized()
    target_dir = _entry_dir(root, entry.entry_type)
    target_dir.mkdir(parents=True, exist_ok=True)

    timestamp = entry.created_at.replace("-", "").replace(":", "").replace("Z", "")[:15]
    filename = f"{timestamp}-{slugify(entry.title)}.md"
    target = target_dir / filename
    target.write_text(render_markdown(entry), encoding="utf-8")

    index_path = root / ".agent-loop" / "knowledge" / "index.json"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index = _load_index(index_path)
    rel = target.relative_to(root).as_posix()
    index["entries"].append(
        {
            "title": entry.title,
            "type": entry.entry_type,
            "status": entry.status,
            "created_at": entry.created_at,
            "path": rel,
            "tags": list(entry.tags),
            "source_ledger": entry.source_ledger,
            "loop_run_id": entry.loop_run_id,
        }
    )
    index_path.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return target


def build_failure_candidate_from_ledger(ledger_path: str | Path, *, title: str | None = None) -> KnowledgeEntry:
    """Create a failure knowledge candidate from the latest ledger evaluation.

    This does not infer hidden causes. It captures the observed blocking failures
    and repair tasks so a human or future agent can enrich the root cause later.
    """

    path = Path(ledger_path)
    ledger = load_ledger(path)
    evaluations = ledger.get("evaluations") or []
    latest = evaluations[-1] if evaluations else {}
    failures = latest.get("blocking_failures") or []
    repairs = latest.get("repair_tasks") or []
    failure_lines = [f"- {f.get('metric')}: {f.get('reason')}" for f in failures if isinstance(f, Mapping)]
    repair_lines = [f"- {r.get('id')}: {r.get('instruction')}" for r in repairs if isinstance(r, Mapping)]
    summary = "Latest evaluator verdict was not PASS; human review or bounded repair is required."
    if latest.get("verdict") == "PASS":
        summary = "Latest evaluator verdict was PASS, but this entry was recorded as a reusable lesson candidate."

    return KnowledgeEntry(
        title=title or f"Agent-loop failure candidate for {ledger.get('loop_run_id', path.stem)}",
        entry_type="failure",
        summary=summary,
        context=f"Loop run: {ledger.get('loop_run_id', 'unknown')}\nLedger: {path}",
        symptom="\n".join(failure_lines) or "No blocking failures recorded in latest evaluation.",
        root_cause="unknown",
        fix_or_decision="Pending. See repair tasks below.\n\n" + ("\n".join(repair_lines) or "No repair tasks recorded."),
        prevention="Load this knowledge before future repairs that show the same failure fingerprint.",
        evidence_references=[str(path)],
        tags=["agent-loop", "failure", str(latest.get("verdict", "unknown")).lower()],
        source_ledger=str(path),
        loop_run_id=str(ledger.get("loop_run_id", "")) or None,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """CLI for recording knowledge assets from humans, agents, or ledgers."""

    parser = argparse.ArgumentParser(description="Record agent-loop knowledge assets")
    parser.add_argument("--repo-root", default=".", help="Repository root that owns .agent-loop/knowledge")
    parser.add_argument("--type", choices=sorted(KNOWLEDGE_TYPES), default="failure")
    parser.add_argument("--status", choices=sorted(KNOWLEDGE_STATUSES), default="candidate")
    parser.add_argument("--title", required=False)
    parser.add_argument("--summary", default="")
    parser.add_argument("--context", default="")
    parser.add_argument("--symptom", default="")
    parser.add_argument("--root-cause", default="unknown")
    parser.add_argument("--fix-or-decision", default="")
    parser.add_argument("--prevention", default="")
    parser.add_argument("--evidence", action="append", default=[])
    parser.add_argument("--tag", action="append", default=[])
    parser.add_argument("--ledger", help="Build a failure candidate from an evidence ledger")
    args = parser.parse_args(argv)

    if args.ledger:
        entry = build_failure_candidate_from_ledger(args.ledger, title=args.title)
    else:
        if not args.title:
            parser.error("--title is required unless --ledger is provided")
        entry = KnowledgeEntry(
            title=args.title,
            entry_type=args.type,
            status=args.status,
            summary=args.summary,
            context=args.context,
            symptom=args.symptom,
            root_cause=args.root_cause,
            fix_or_decision=args.fix_or_decision,
            prevention=args.prevention,
            evidence_references=args.evidence,
            tags=args.tag,
        )

    target = record_knowledge_entry(args.repo_root, entry)
    print(target)
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through script wrapper
    raise SystemExit(main())
