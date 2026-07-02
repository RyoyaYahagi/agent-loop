# agent-loop

エビデンスに基づく自律開発ループツールキット。決定論的なエージェントループ評価器の実行、機械エビデンスの収集、CI上での有界LLM修復ループの起動、そして無限ループではなく人間へのハンドオフで停止するために必要なファイルをまとめたリポジトリです。

## 含まれるもの

- `hermes_cli/agent_loop_capture.py` — 台帳の初期化、コマンドエビデンス、gitスナップショット、PRスナップショット、修復ステータスのヘルパー
- `hermes_cli/agent_loop_evaluator.py` — 決定論的評価器とハードゲート
- `hermes_cli/agent_loop_controller.py` — 最大試行回数・繰り返し失敗停止・実行時間制限・ハンドオフレポートを備えた有界修復コントローラー
- `hermes_cli/agent_loop_ledger_update.py` — 要件/タスク/発見事項/クレームの決定論的セマンティック台帳アップデーター
- `hermes_cli/agent_loop_knowledge.py` — 失敗・パターン・決定・ハンドオフのナレッジキャプチャ（教訓をリポジトリ資産として蓄積）
- `hermes_cli/agent_loop_pr_guard.py` — CI/チェックが失敗・保留・未設定のときにAI PRのマージをブロックするフェイルクローズドガード
- `hermes_cli/agent_loop_pr_ci_loop.py` — CIがグリーンになるまでAI PRを修復し、許可されたベースブランチに安全にマージする有界ループ
- `hermes_cli/agent_loop_regression.py` — JUnit XML / git worktree から新規失敗を機械計算する回帰検出
- `hermes_cli/agent_loop_decision_log.py` — AI/Controllerの判断理由・前提・リスクを台帳に監査ログとして残すヘルパー
- `scripts/setup.sh` — マシンに一度だけ実行するセットアップ（`uv tool install` で `agent-loop-*` を導入、前提を検出・警告）
- `scripts/*.py` — 上記のCLIラッパー（dev/legacy。セットアップ後は `agent-loop-*` コマンドの使用を推奨）
- `templates/evidence-ledger.json` — スターター台帳
- `templates/knowledge-entry.md` — レビュー可能なナレッジエントリテンプレート
- `templates/pr-body-human-review-ja.md` — 人間がレビューすべき観点に絞った日本語PRボディ
- `docs/knowledge-asset-design.md` — 失敗と教訓を永続的なプロジェクトナレッジに変換するための設計
- `docs/pr-human-review-ja.md` — 日本語PRレビューサマリーとCIマージゲートポリシー
- `docs/ai-decision-log.md` — 問題発生時にAI/Controllerの判断を追跡するための監査ログ設計
- `docs/non-functional-requirements-ja.md` — 非機能要件チェックリスト（保守性・性能・可用性・セキュリティ・運用性・統制・拡張性ほか）
- `skills/software-development/agent-loop-evaluation/` — エビデンス台帳・決定論的評価・有界修復・ハンドオフルール
- `skills/software-development/subagent-driven-development/` — 自律実装ループ: 計画 → サブエージェント実装 → 仕様レビュー → 品質レビュー → 最終検証
- `skills/github/github-pr-workflow/` — ブランチ → コミット → ドラフトPR → CI → AIレビュー → マージ/クリーンアップのループ
- `skills/github/github-issues/`, `github-code-review`, `github-auth`, `github-repo-management` — ループで使用するissue/PR/レビュー/認証/リポジトリ操作
- `skills/autonomous-ai-agents/{codex,claude-code,opencode}/` — オプションの外部コーディングエージェント委譲バックエンド
- `.github/workflows/agent-loop.yml` — PR / workflow_dispatch / workflow_call のCIゲート
- `.github/workflows/pr-ci-repair-merge.yml` — CIがグリーンになるまでPRを修復してから安全にマージする手動ワークフロー
- `tests/cli/` — Hermes Agentからコピーしたコアユニットテスト

## 前提条件 (Prerequisites)

- **uv** — パッケージ管理・インストールに使用（https://docs.astral.sh/uv/）
- **git** — 台帳スナップショットとPRワークフローに必要
- **gh** (GitHub CLI) + `gh auth login` — PRガード／CI修復マージに必要

`setup.sh` はこれらを**検出して不足を警告する**だけで、自動インストールはしません（gh認証も同様）。

## セットアップ（マシンに一度）

`agent-loop-*` コマンドをこのマシンのPATHに導入します。一度実行すれば、任意のリポジトリに
`cd` して使えます（リポジトリごとの再インストールは不要）。

```bash
# クローンしたディレクトリで
./scripts/setup.sh

# uv 自体が未導入なら自動導入も任せる場合
./scripts/setup.sh --bootstrap-uv

# ローカルの変更を反映して再インストール
./scripts/setup.sh --upgrade
```

クローンせずに直接導入することもできます:

```bash
uv tool install --from git+https://github.com/RyoyaYahagi/agent-loop agent-loop
```

開発・CI向けの editable インストール（venv + テスト依存）:

```bash
./scripts/setup.sh --dev
source .venv/bin/activate
```

## クイックスタート（リポジトリごと）

セットアップ後、評価したいリポジトリ内で実行します:

```bash
cd /path/to/your/repo

agent-loop-ledger-init \
  --ledger evidence-ledger.json \
  --loop-run-id issue-123 \
  --repo "owner/repo" \
  --issue 123 \
  --branch "feature/issue-123" \
  --base-ref main \
  --required-check "CHECK-test:pytest -q" \
  --required-check "CHECK-lint:ruff check ." \
  --required-status-check test

agent-loop-controller evidence-ledger.json --max-attempts 1 --output-report agent-loop-handoff.md
```

`evidence-ledger.json` と `.agent-loop/` は実行状態なので、コミットしたくなければ
対象リポジトリの `.gitignore` に追加してください。

`--required-check` は `ID:command` 形式です。`--required-check-json '{"id":"CHECK-test","command_argv":["pytest","-q"],"timeout":600,"type":"unit-tests"}'` も使えます。文字列IDだけの旧形式は宣言のみとして扱われ、コントローラーでは実行できないため評価はFAILします。

## CIモード

### 評価のみゲート

決定論的評価器が `FAIL` を返した場合、ワークフローはPRを失敗させます。LLMがpass/failを判断することはありません。

### 有界修復モード

手動またはreusableワークフローで `repair=true` を設定して実行します。コントローラーの動作:

1. `scope.required_checks` をコントローラー自身が実行する
2. 直後に git snapshot を取得する
3. 台帳を評価する
4. 決定論的な `repair_tasks` から修復プロンプトを生成する
5. 設定した修復コマンドを1回実行する
6. 再びコントローラー所有の検証パスから始める
5. 成功したら停止、いずれかの上限に達したら人間にエスカレーション

修復エージェントは機械エビデンスを書きません。コード修正とセマンティックな台帳アノテーションだけを行い、チェック再実行・ログ保存・snapshot はコントローラー/CIが所有します。

デフォルトの上限:

- `AGENT_LOOP_MAX_ATTEMPTS=3`
- `AGENT_LOOP_MAX_SAME_FAILURE_COUNT=2`
- `AGENT_LOOP_MAX_RUNTIME_MINUTES=30`

`AGENT_LOOP_REPAIR_COMMAND` に生成されたプロンプトを受け取るコマンドを設定します。コントローラーが公開する環境変数:

- `HERMES_LEDGER_PATH`
- `HERMES_AGENT_LOOP_REPAIR_PROMPT_FILE`
- `HERMES_AGENT_LOOP_REPAIR_ATTEMPT`
- `HERMES_AGENT_LOOP_PHASE`

実行例:

```bash
AGENT_LOOP_REPAIR_COMMAND='hermes chat -q "$(cat $HERMES_AGENT_LOOP_REPAIR_PROMPT_FILE)"' \
agent-loop-controller evidence-ledger.json --comment-pr
```

試行回数が尽きた場合、同じ失敗が繰り返された場合、実行時間が切れた場合、権限/シークレットが不足している場合、または修復コマンドがない場合、コントローラーはエスカレーションで終了し `agent-loop-handoff.md` を書き出します。PR CI内では `gh` と `GH_TOKEN` が利用可能な場合、PRにハンドオフをコメントすることもできます。

## 日本語PRレビューサマリー

AI作成のPRには、人間が判断すべき観点（問題/スコープ、アーキテクチャ決定、責任境界、テストの妥当性、高リスクdiff、本番/顧客への影響）のみを示した日本語レビューサマリーを含める必要があります。使い方:

```bash
cp templates/pr-body-human-review-ja.md /tmp/pr-body.md
gh pr create --draft --body-file /tmp/pr-body.md
```

自動マージの前に、フェイルクローズドPRガードを実行してください:

```bash
agent-loop-pr-merge-guard <PR_NUMBER>
```

PRがドラフト状態の場合、チェックが失敗/保留/未設定の場合、必須チェックがrollupに存在しない場合、必須チェックが `SKIPPED`/`NEUTRAL` の場合、GitHubが `mergeable=false` または未確定を報告する場合、またはオプションのレビュー承認が必要だが未取得の場合にブロックします。`--required-check NAME` または台帳の `scope.required_status_checks` で必須GitHubチェック名を指定できます。完全なポリシーは `docs/pr-human-review-ja.md` を参照してください。

CIがグリーンになるまで修復を続けてからマージするには、有界CI修復ループを実行します:

```bash
agent-loop-pr-ci-repair-merge <PR_NUMBER> \
  --repair-command 'hermes chat -q "Fix PR {pr} CI failure. Attempt {attempt}. Check CI logs, patch only the needed files, run local checks, commit, and push."' \
  --max-attempts 3 \
  --allowed-base develop
```

安全のデフォルト設定:

- `pr_merge_guard` がチェックのグリーンを確認するまでマージしない
- チェック未設定は成功ではなく失敗として扱う
- 必須チェックの `SKIPPED` / `NEUTRAL` は失敗として扱う
- merge時はガード確認時のhead SHAを `--match-head-commit` で固定する
- 有界試行回数の後に停止し、人間にハンドオフする
- デフォルトでは `develop` または `staging` へのみ自動マージ
- `--allow-main` を明示的に設定しない限り `main` への自動マージは行わない

## 台帳の更新

証明として信頼せずに構造化アノテーションを適用する:

```bash
agent-loop-ledger-update --ledger evidence-ledger.json --updates examples/semantic-updates.json
```

アップデーターはセマンティックエントリをアノテーションとしてマークします。機械エビデンスは引き続きラッパー/CI/ツールから取得する必要があります。

`accepted_risk` / `deferred` の findings は、非AIの `approved_by` と `reason` が必要です。`ai`, `agent`, `assistant`, `llm`, `claude`, `controller`, `bot` は承認者として無効です。

## 回帰検出

JUnit XML同士の差分:

```bash
agent-loop-regression \
  --ledger evidence-ledger.json \
  --base-junit /tmp/base.xml \
  --head-junit /tmp/head.xml
```

git worktreeでbase/headを実行して差分:

```bash
agent-loop-regression \
  --ledger evidence-ledger.json \
  --base-ref origin/main \
  --test-command 'pytest -q --junitxml {junit}'
```

評価器は `regressions.source == "machine"` かつ `head_commit` が最新 git snapshot と一致する場合だけ回帰エビデンスとして認めます。

## AI判断ログ

問題発生時に「なぜAI/Controllerがその行動を選んだか」を追えるように、`ai_decision_logs` を台帳に残せます。これは監査用アノテーションであり、evaluator のPASS/FAIL証拠にはなりません。

```bash
agent-loop-ledger-decision \
  --ledger evidence-ledger.json \
  --phase repair_attempt_1 \
  --actor ai \
  --decision "Fix failing typecheck before requesting review" \
  --rationale "CI reported a type error and merge guard blocks non-green checks." \
  --evidence-ref "checks[CHECK-typecheck]" \
  --confidence high
```

Controller と CI修復マージループは、PASS停止・修復実行・マージ・エスカレーションなどの主要判断を自動で記録します。詳細は `docs/ai-decision-log.md` を参照してください。

## ナレッジ資産

失敗と永続的な教訓は `.agent-loop/knowledge/` にMarkdownファイルと小さな `index.json` として昇格できます。これらのナレッジ資産は評価器エビデンスとは意図的に分離されています: 将来のエージェントを導くことはできますが、現在の実行をpassにすることはできません。

人間が書いた教訓を記録する:

```bash
agent-loop-knowledge-record \
  --repo-root . \
  --type pattern \
  --title "認証済みNext.jsページはforce-dynamicが必要" \
  --summary "getCurrentUser()を呼ぶページはdynamic = force-dynamicをエクスポートする必要がある。" \
  --prevention "プッシュ前に新しい認証済みページを確認する。" \
  --tag nextjs --tag ci
```

最新の台帳評価から失敗候補を作成する:

```bash
agent-loop-knowledge-record --repo-root . --ledger evidence-ledger.json
```

昇格ルール、ストレージレイアウト、コメントポリシーについては `docs/knowledge-asset-design.md` を参照してください。

## コードコメントポリシー

オーケストレーションコードは重要な箇所でコメントを充実させるべきです。クラスや関数が存在する理由、持つ権限、防ぐ障害モード、信頼してはいけないものを説明するdocstring/コメントを追加してください。次のコード行を言い換えるだけのコメントは避けてください。

## ハードルール

- AIの自己申告はエビデンスではない
- 必須チェックはコマンド・cwd・コミット・終了コード・stdout/stderrログ・`source: machine` とともに機械的に収集する必要がある
- 台帳は `schema_version: 2` 必須。不正な構造や空台帳はFAIL
- 必須チェック証拠は最新git snapshotのHEADと一致し、snapshotがcleanでなければならない
- 完了クレームにはエビデンスが必要。根拠のない、または矛盾する完了クレームは失敗する
- 修正済み発見事項には再チェックエビデンスが必要
- `accepted_risk` / `deferred` は人間承認者と理由がなければ未解決扱い
- 回帰データは機械計算のみ有効
- 修復コントローラーは有界であり、無限ループではなく人間にハンドオフする
