from __future__ import annotations

import json

from hermes_cli.agent_loop_knowledge import KnowledgeEntry, record_knowledge_entry, slugify


def test_slugify_keeps_filename_safe() -> None:
    assert slugify("CI failure: npm test!!!") == "ci-failure-npm-test"


def test_record_knowledge_entry_writes_markdown_and_index(tmp_path) -> None:
    entry = KnowledgeEntry(
        title="Repeated CI failure",
        entry_type="failure",
        summary="A reusable lesson",
        symptom="CI failed",
        prevention="Run the same check locally first",
        evidence_references=["evidence-ledger.json"],
        tags=["ci"],
    )

    target = record_knowledge_entry(tmp_path, entry)

    assert target.exists()
    assert "Repeated CI failure" in target.read_text(encoding="utf-8")

    index = json.loads((tmp_path / ".agent-loop" / "knowledge" / "index.json").read_text(encoding="utf-8"))
    assert index["entries"][0]["title"] == "Repeated CI failure"
    assert index["entries"][0]["type"] == "failure"
    assert index["entries"][0]["status"] == "candidate"
