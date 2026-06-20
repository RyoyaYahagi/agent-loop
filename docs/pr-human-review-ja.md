# 日本語PRレビューサマリー設計

AI が作る PR は、実装者向けの英語コメントや網羅的な説明が多くなりやすい。人間レビューでは、すべてを読むのではなく「人間が判断すべきポイント」だけを日本語で確認できるようにする。

## 方針

1. **PR本文は日本語を標準にする**
   - AI が作成した PR でも、レビュー観点・リスク・CI状態は日本語で書く。
   - 実装詳細の長文説明より、人間判断が必要な点を優先する。

2. **AIに任せたことと人間が見ることを分離する**
   - AI の作業報告をそのまま信じない。
   - 人間は設計判断、スコープ、責務分離、高リスク差分、テスト観点、運用影響を見る。

3. **CI未通過・未実行はマージ禁止として明示する**
   - `CI failed` だけでなく `checks missing` も禁止扱い。
   - AI が「テストした」と書いていても、machine evidence がなければ未確認扱い。

4. **PR本文は短く、詳細はリンクに逃がす**
   - ledger、CI run、diff、handoff report、knowledge entry へのリンクを貼る。
   - diff全文や長いログはPR本文に貼らない。

## 人間が見るべきポイント表

| 開発ステップ | AIに任せやすい | 人間が見るべきポイント |
| --- | --- | --- |
| 要件整理 | 論点洗い出し、質問作成、仕様ドラフト | 本当に解くべき課題、スコープ、優先順位 |
| 設計 | 代替案、影響範囲調査、ADR下書き | アーキテクチャ判断、将来の変更耐性 |
| 実装 | 小さな関数、テスト、リファクタ、ドキュメント | 責務分離、既存設計との整合性 |
| テスト | 単体/E2E生成、境界値追加 | テスト観点の妥当性、重要シナリオ漏れ |
| レビュー | 差分要約、リスク分類、レビュー観点提示 | 高リスク差分、仕様逸脱、非機能要件 |
| 運用 | ログ分析、障害仮説、修正案 | 本番影響、顧客影響、リリース判断 |

## PR作成時の必須セクション

テンプレート: `templates/pr-body-human-review-ja.md`

必須:

- このPRで解く課題
- 設計判断
- 実装内容
- テスト・CI
- リスク分類
- AIに任せたこと / 人間が判断すること
- マージ前チェック
- 最終判断欄

## CI gate 方針

PR merge の前に次を満たすこと:

1. PR が Draft ではない
2. required checks がすべて success
3. agent-loop evaluator が PASS、または人間が FAIL 理由を明示的に許容
4. 未解決の blocker/security/CI failure コメントがない
5. branch protection がある場合は GitHub 側で required status checks を必須化

agent-loop 側では `scripts/pr_merge_guard.py` を使い、GitHub の PR 状態・check 状態を機械的に確認する。

## CIが通るまで修正してからマージするループ

`pr_merge_guard.py` は単発の安全確認。AI が CI failure を直し切ってから merge する運用には `scripts/pr_ci_repair_merge.py` を使う。

```bash
python scripts/pr_ci_repair_merge.py <PR_NUMBER> \
  --repair-command 'hermes chat -q "Fix PR {pr} CI failure. Attempt {attempt}. Check CI logs, patch only the needed files, run local checks, commit, and push."' \
  --max-attempts 3 \
  --allowed-base develop
```

動作:

1. `gh pr view` で PR/check 状態を取得
2. checks が pending なら bounded wait
3. checks が failing/missing なら repair command を1回実行
4. repair command が commit/push した後、再度 PR/check 状態を確認
5. green になったら `gh pr merge --squash --delete-branch`
6. 最大試行回数で green にならなければ停止して人間にバトンタッチ

安全条件:

- checks missing は green ではないため merge しない
- CI/check が1つでも failure/pending なら merge しない
- default では `develop` / `staging` だけ自動 merge 可能
- `main` への自動 merge は default 禁止。明示的に `--allow-main` が必要
- `--require-review-approval` を付けると reviewDecision=APPROVED も必須

## PR本文の書き方

悪い例:

```md
Implemented feature X. Tests passed.
```

良い例:

```md
## テスト・CI

- ローカル: `npm run lint`, `npm run typecheck`, `npm test`
- CI: required checks success
- agent-loop evaluator: PASS

### 人間に見てほしいポイント

- RLS policy の責務分離が既存設計と合っているか
- 重要シナリオとして「他ユーザーのデータが見えないこと」が十分か
```

## 運用上の注意

- AIがPR本文を更新するときは、日本語レビューセクションを消さない。
- CIが通っていないPRをmergeしない。`gh pr merge --auto` を優先し、手動 merge は人間判断に限定する。
- checks が存在しない repo は「CI green」ではなく「CI missing」と扱う。
- PR本文のチェック欄はレビュー負荷を下げるためのUIであり、evaluator の代替ではない。
