# AI判断ログ / Decision Log

agent-loop は、問題発生時に「何が起きたか」だけでなく「なぜAI/Controllerがその判断をしたか」を後から追えるようにする。

## 結論

- `checks`, `machine_evidence`, `evaluations` は **何が起きたか / PASS・FAILの根拠** を記録する。
- `ai_decision_logs` は **なぜその判断・次アクションを選んだか** を記録する。
- ただし `ai_decision_logs` は `source: "annotation"` であり、evaluator を PASS させる証拠にはならない。

## 記録する判断

最低限、以下の判断は記録する。

1. 計画判断
   - なぜこのスコープにしたか
   - 代替案
   - 捨てた案
   - 前提・リスク
2. 実装修正判断
   - なぜそのファイル/責務を変更したか
   - 既存設計との整合性
3. CI修正判断
   - なぜ repair command を実行したか
   - どの check failure を見たか
   - 何回目の修正か
4. merge判断
   - CI/check が green であること
   - base branch safety policy が通ったこと
   - review approval が必要なら満たしたこと
5. escalation判断
   - なぜ人間にバトンタッチしたか
   - 何回試したか
   - 同じ失敗が繰り返されたか

## 記録しないもの

- private chain-of-thought
- secrets / tokens / credentials
- 生ログ全文
- diff全文
- 一週間で古くなる一時情報だけの記録

必要なのは詳細な思考過程ではなく、後からレビュー可能な監査ログ。

## Ledger schema

```json
{
  "ai_decision_logs": [
    {
      "id": "DECISION-001",
      "phase": "repair_attempt_1",
      "actor": "controller",
      "decision": "Run bounded repair command for evaluator failures",
      "rationale": "Evaluator returned FAIL, limits were not exceeded, and a repair command is configured.",
      "options_considered": ["handoff now", "run repair command"],
      "selected_option": "run repair command",
      "assumptions": [],
      "risks": ["Repair command may fail or require human interpretation."],
      "evidence_refs": ["evaluations[0]", "logs/CHECK-test.stderr.log"],
      "related_requirements": [],
      "related_tasks": [],
      "related_findings": [],
      "confidence": "high",
      "timestamp": "2026-06-20T00:00:00Z",
      "source": "annotation"
    }
  ]
}
```

## CLI

```bash
python scripts/ledger_decision.py \
  --ledger evidence-ledger.json \
  --phase repair_attempt_1 \
  --actor ai \
  --decision "Fix failing typecheck before requesting review" \
  --rationale "CI reported a type error and merge guard blocks non-green checks." \
  --option "handoff immediately" \
  --option "fix type error and rerun checks" \
  --selected-option "fix type error and rerun checks" \
  --evidence-ref "checks[CHECK-typecheck]" \
  --risk "Fix may reveal additional type errors" \
  --confidence high
```

## Trust boundary

`ai_decision_logs` は監査・説明・改善のための情報であり、evaluator の PASS/FAIL には使わない。

悪い使い方:

```text
AI判断ログに「テストは通った」と書いてあるのでPASS
```

正しい使い方:

```text
AI判断ログに「typecheck修正を選んだ理由」があり、checks[] に machine evidence として typecheck success があるので追跡可能
```

## Dashboard / MCP

Dashboard では PR / CI / evaluator の横に decision log timeline を表示する。
MCP では read-only tool として以下を提供する想定。

- `get_decision_timeline`
- `get_decisions_by_phase`
- `get_escalation_context`

副作用のある判断記録は `record_decision_log` のように明示名にする。
