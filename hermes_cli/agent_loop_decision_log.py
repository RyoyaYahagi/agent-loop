"""AI decision logging for agent-loop ledgers.

Machine evidence answers "what happened". Decision logs answer "why did the AI
or controller choose this action". They are intentionally stored as annotation,
not proof: a decision log helps humans debug the loop after an incident, but it
must never make evaluator gates pass.

Do not store private chain-of-thought. Store concise, reviewable rationales:
inputs considered, options, selected option, assumptions, risks, and evidence
references.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from hermes_cli.agent_loop_capture import load_ledger, save_ledger, utc_now


@dataclass(frozen=True)
class AIDecisionLog:
    """A concise audit record for an AI/controller decision.

    This object is for traceability, not truth. The evaluator should continue to
    rely on machine evidence for pass/fail decisions. Humans can inspect these
    records later to understand why a repair command ran, why a merge was
    blocked, why an escalation happened, or which assumptions were active.
    """

    id: str
    phase: str
    actor: str
    decision: str
    rationale: str
    options_considered: Sequence[str] = ()
    selected_option: str | None = None
    assumptions: Sequence[str] = ()
    risks: Sequence[str] = ()
    evidence_refs: Sequence[str] = ()
    related_requirements: Sequence[str] = ()
    related_tasks: Sequence[str] = ()
    related_findings: Sequence[str] = ()
    confidence: str | None = None
    timestamp: str = ""
    source: str = "annotation"

    def normalized(self) -> "AIDecisionLog":
        """Fill defaults and validate fields without mutating the log."""

        if not self.id:
            raise ValueError("decision id is required")
        if not self.phase:
            raise ValueError("phase is required")
        if not self.actor:
            raise ValueError("actor is required")
        if not self.decision:
            raise ValueError("decision is required")
        if self.source != "annotation":
            raise ValueError("AI decision logs must use source='annotation'")
        return AIDecisionLog(**{**asdict(self), "timestamp": self.timestamp or utc_now()})


def _next_decision_id(existing: Sequence[Mapping[str, Any]]) -> str:
    """Generate a stable DECISION-### id for append-only decision logs."""

    return f"DECISION-{len(existing) + 1:03d}"


def record_ai_decision(
    *,
    ledger_path: str | Path,
    phase: str,
    actor: str,
    decision: str,
    rationale: str,
    decision_id: str | None = None,
    options_considered: Sequence[str] = (),
    selected_option: str | None = None,
    assumptions: Sequence[str] = (),
    risks: Sequence[str] = (),
    evidence_refs: Sequence[str] = (),
    related_requirements: Sequence[str] = (),
    related_tasks: Sequence[str] = (),
    related_findings: Sequence[str] = (),
    confidence: str | None = None,
) -> dict[str, Any]:
    """Append one AI/controller decision log to the ledger.

    The ledger key is `ai_decision_logs` to make the trust level explicit. These
    entries are durable audit context and can be shown in dashboards/MCP tools.
    """

    path = Path(ledger_path)
    ledger = load_ledger(path)
    logs = ledger.setdefault("ai_decision_logs", [])
    if not isinstance(logs, list):
        raise ValueError("ledger.ai_decision_logs must be a list")

    entry = AIDecisionLog(
        id=decision_id or _next_decision_id([item for item in logs if isinstance(item, Mapping)]),
        phase=phase,
        actor=actor,
        decision=decision,
        rationale=rationale,
        options_considered=tuple(options_considered),
        selected_option=selected_option,
        assumptions=tuple(assumptions),
        risks=tuple(risks),
        evidence_refs=tuple(evidence_refs),
        related_requirements=tuple(related_requirements),
        related_tasks=tuple(related_tasks),
        related_findings=tuple(related_findings),
        confidence=confidence,
    ).normalized()
    payload = asdict(entry)
    logs.append(payload)
    save_ledger(path, ledger)
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Append an AI/controller decision log to an Evidence Ledger")
    parser.add_argument("--ledger", required=True, help="Path to evidence-ledger.json")
    parser.add_argument("--id", dest="decision_id", help="Decision id. Defaults to DECISION-###")
    parser.add_argument("--phase", required=True, help="Loop phase, e.g. plan, repair_attempt_1, merge_guard")
    parser.add_argument("--actor", required=True, help="Actor making the decision, e.g. ai, controller, ci-loop")
    parser.add_argument("--decision", required=True, help="Concise decision statement")
    parser.add_argument("--rationale", required=True, help="Concise rationale. Do not include private chain-of-thought.")
    parser.add_argument("--option", action="append", default=[], help="Option considered. Repeatable.")
    parser.add_argument("--selected-option")
    parser.add_argument("--assumption", action="append", default=[])
    parser.add_argument("--risk", action="append", default=[])
    parser.add_argument("--evidence-ref", action="append", default=[])
    parser.add_argument("--related-requirement", action="append", default=[])
    parser.add_argument("--related-task", action="append", default=[])
    parser.add_argument("--related-finding", action="append", default=[])
    parser.add_argument("--confidence", choices=["low", "medium", "high"])
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    entry = record_ai_decision(
        ledger_path=args.ledger,
        phase=args.phase,
        actor=args.actor,
        decision=args.decision,
        rationale=args.rationale,
        decision_id=args.decision_id,
        options_considered=args.option,
        selected_option=args.selected_option,
        assumptions=args.assumption,
        risks=args.risk,
        evidence_refs=args.evidence_ref,
        related_requirements=args.related_requirement,
        related_tasks=args.related_task,
        related_findings=args.related_finding,
        confidence=args.confidence,
    )
    print(json.dumps(entry, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
