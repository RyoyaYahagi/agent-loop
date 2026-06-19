"""Deterministic updaters for agent-loop Evidence Ledgers.

This module deliberately does not decide whether an implementation is correct.
It only validates and upserts structured entries that may have been proposed by
an LLM, a human, or another tool. Trust decisions remain in
agent_loop_evaluator.py and machine capture wrappers.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from hermes_cli.agent_loop_capture import load_ledger, save_ledger, utc_now

LEDGER_LISTS = {
    "requirements": {"required": {"id", "text"}, "allowed": {"id", "text", "planned", "implemented", "evidence", "source", "notes", "tasks", "checks"}},
    "tasks": {"required": {"id", "text"}, "allowed": {"id", "text", "requirements", "implemented", "evidence", "source", "notes", "paths", "checks"}},
    "findings": {"required": {"id", "source", "severity", "status"}, "allowed": {"id", "source", "severity", "status", "text", "evidence", "fix_evidence", "recheck_evidence", "reason", "notes"}},
    "claims": {"required": {"id", "text", "kind", "status"}, "allowed": {"id", "text", "kind", "status", "evidence", "source", "notes"}},
}

BOOLEAN_FIELDS = {
    "requirements": {"planned", "implemented"},
    "tasks": {"implemented"},
}

ENUM_FIELDS = {
    "findings": {
        "severity": {"info", "minor", "important", "critical", "blocker"},
        "status": {"open", "fixed", "accepted_risk", "deferred"},
    },
    "claims": {
        "kind": {"completion", "check", "implementation", "review", "status", "other"},
        "status": {"verified", "unsupported", "ambiguous", "contradicted"},
    },
}


def _items(ledger: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = ledger.setdefault(key, [])
    if not isinstance(value, list):
        raise ValueError(f"ledger.{key} must be a list")
    if not all(isinstance(item, dict) for item in value):
        raise ValueError(f"ledger.{key} must contain only objects")
    return value


def _upsert_by_id(items: list[dict[str, Any]], item: dict[str, Any]) -> str:
    item_id = item["id"]
    for index, existing in enumerate(items):
        if existing.get("id") == item_id:
            items[index] = {**existing, **item, "updated_at": utc_now()}
            return "updated"
    item.setdefault("created_at", utc_now())
    items.append(item)
    return "created"


def _validate_entry(kind: str, entry: Mapping[str, Any], *, strict: bool = True) -> dict[str, Any]:
    if kind not in LEDGER_LISTS:
        raise ValueError(f"unsupported ledger entry kind: {kind}")
    if not isinstance(entry, Mapping):
        raise ValueError(f"{kind} entry must be an object")
    spec = LEDGER_LISTS[kind]
    missing = sorted(field for field in spec["required"] if not str(entry.get(field, "")).strip())
    if missing:
        raise ValueError(f"{kind} entry missing required fields: {', '.join(missing)}")
    unknown = sorted(set(entry) - spec["allowed"])
    if strict and unknown:
        raise ValueError(f"{kind} entry has unknown fields: {', '.join(unknown)}")

    normalized = {key: value for key, value in entry.items() if key in spec["allowed"]}
    normalized["id"] = str(normalized["id"]).strip()

    for field in BOOLEAN_FIELDS.get(kind, set()):
        if field in normalized and not isinstance(normalized[field], bool):
            raise ValueError(f"{kind}.{field} must be boolean")

    for field, allowed in ENUM_FIELDS.get(kind, {}).items():
        if field in normalized:
            value = str(normalized[field]).strip().lower()
            if value not in allowed:
                raise ValueError(f"{kind}.{field} must be one of: {', '.join(sorted(allowed))}")
            normalized[field] = value

    # Mark non-machine semantic updates as annotations. This is intentionally
    # not accepted as machine check evidence by the evaluator.
    normalized.setdefault("source", "annotation")
    return normalized


def apply_updates(
    ledger_path: str | Path,
    updates: Mapping[str, Any],
    *,
    strict: bool = True,
) -> dict[str, Any]:
    """Apply structured updates and return a deterministic summary."""
    ledger_file = Path(ledger_path)
    ledger = load_ledger(ledger_file)
    summary: dict[str, Any] = {"ledger": str(ledger_file), "updated": {}}

    for kind in LEDGER_LISTS:
        raw_entries = updates.get(kind, [])
        if raw_entries is None:
            raw_entries = []
        if not isinstance(raw_entries, list):
            raise ValueError(f"updates.{kind} must be a list")
        target = _items(ledger, kind)
        counts = {"created": 0, "updated": 0}
        for raw in raw_entries:
            entry = _validate_entry(kind, raw, strict=strict)
            action = _upsert_by_id(target, entry)
            counts[action] += 1
        if raw_entries:
            summary["updated"][kind] = counts

    if not isinstance(ledger.get("regressions", {}), dict):
        raise ValueError("ledger.regressions must be an object when present")
    ledger.setdefault("regressions", {"new_failures": 0})
    save_ledger(ledger_file, ledger)
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Apply structured requirements/tasks/findings/claims updates to an Evidence Ledger")
    parser.add_argument("--ledger", required=True, type=Path, help="Path to evidence-ledger.json")
    parser.add_argument("--updates", type=Path, help="JSON file with requirements/tasks/findings/claims arrays")
    parser.add_argument("--json", dest="json_text", help="Inline JSON updates")
    parser.add_argument("--no-strict", action="store_true", help="Ignore unknown fields instead of failing")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if bool(args.updates) == bool(args.json_text):
        raise SystemExit("pass exactly one of --updates or --json")
    payload = args.updates.read_text(encoding="utf-8") if args.updates else args.json_text
    updates = json.loads(payload)
    if not isinstance(updates, dict):
        raise SystemExit("updates JSON must be an object")
    summary = apply_updates(args.ledger, updates, strict=not args.no_strict)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
