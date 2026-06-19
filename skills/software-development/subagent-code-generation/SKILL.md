---
title: Subagent Code Generation
name: subagent-code-generation
version: 1.0.0
description: delegate_taskでsubagentにコード生成・レビュー・テストを依頼する方法と注意点
trigger: delegate_task, subagent, code generation, model override
---

# Subagent Code Generation

## 目的

`delegate_task` を使ってsubagentにコード生成・レビュー・テストを依頼し、司令塔（親エージェント）は統合・判断・報告に専念する。

## 方法

### 1. delegate_task の基本

```yaml
delegate_task:
  goal: "Implement feature X: create DB migration, service layer, and API routes"
  context: |
    - Working directory: /root/Ruletrade-AI
    - Follow existing portfolio MVP pattern
    - Use createServerClient (not createClient)
    - Handle errors with AppError and toErrorResponse
  toolsets: [terminal, file, web]
  role: leaf
```

### 2. Model Override（パッチ適用済み / Gateway キャッシュ注意）

delegate_task は `model` パラメータでモデルを上書きできる。

```yaml
delegate_task:
  model:
    model: "deepseek-v4-flash"
    provider: "opencode-go"
```

**重要**: delegate_tool.py に model/provider パラメータのパッチは適用済みだが、**反映されるかは実行環境のプロセス構成に依存する**。2つのケースがある：

#### ケース A: Gateway が同一プロセス内で動作（通常の CLI 使用）
- **セッション内**では即座に反映されない（ツール定義はセッション起動時にキャッシュされる）
- **セッションリセット後**（`/reset` または新規チャット）から反映される

#### ケース B: Gateway が Docker sandbox の外で動作（ヘッドレス/サーバー環境）
- sandbox 内の `delegate_tool.py` を修正しても、**gateway プロセスは sandbox 外で別プロセスとして動作しているため、変更が反映されない**
- `/reset` や新規チャットでも gateway プロセスが再起動しない限り反映されない
- この場合、delegate_task の model override は**事実上使用不可**となる

検証結果:
- セッション内で `deepseek-v4-flash` を指定 → subagent 実行ログで `model: "kimi-k2.6"` と表示された
- 原因: gateway プロセスが sandbox の外で動作し、パッチされたファイルを読み込んでいない

### 3. cronjob での Model Override

cronjob は gateway 経由でスケジュールされるため、**gateway プロセスがパッチを認識していれば** model override が有効になる。しかし gateway プロセス自身が古いコードをキャッシュしている場合（ケース B）、cronjob でも override は機能しない。

```yaml
cronjob:
  action: create
  name: my-task
  model:
    model: "deepseek-v4-flash"
    provider: "opencode-go"
  prompt: "コード生成タスク..."
  schedule: "every 6h"
```

**用途**: 自動実装ループで軽量モデル（deepseek-v4-flash）をサブエージェントに使う想定だが、**実際に動作するかは gateway プロセスの状態を確認してから使うこと**。

### 4. タスク分割（重要）

subagent も tool call limit（約40-50回/ターン）を持つ。1つの subagent に大量ファイルを一度に書かせると limit に達する。

推奨分割単位：
- DB Migration + Zod Schema（1 subagent）
- Service層（1-2 subagent、機能ごと）
- API Routes（1 subagent、ルートごと）
- UI Components（1 subagent、ページごと）
- テスト・レビュー（1 subagent）

### 5. レビュー・テスト依頼

コード生成後、別の subagent にレビューを依頼する。

```yaml
delegate_task:
  goal: "Review the watchlist implementation for type safety, error handling, and lint issues"
  context: |
    - Check all new files under src/features/watchlist/
    - Ensure no 'any' types remain
    - Verify AppError usage pattern matches portfolio
    - Run npm run lint and npm run typecheck
    - Run npm run test and report failures
  toolsets: [terminal, file]
  role: leaf
```

## 司令塔が直接実装するパターン（セッション内の model override 制限）

セッション内では delegate_task の model override がキャッシュのため即座に反映されないため、**司令塔（kimi-k2.6）が直接実装する**パターンが有効だ。

### 実装ストラテジー
1. **Issue 内容を読み込み**、実装パターン（Portfolio MVP など既存パターン）を推定
2. **既存コードを読み込み**、パターンを確認（サービス層、API route、コンポーネント構造）
3. **ファイルを一括生成**。同じカテゴリのファイルをまとめて1回の write_file で生成
4. **lint / typecheck / test** を実行
5. **エラーがあれば patch** で修正（any 使用、型エラー等）
6. **branch 作成 → commit → push → PR 作成**

### バックエンド・フロントエンド分離
大規模イシュー（例: #85 Deployment Operations MVP）では、UIを後回しにしてバックエンドのみ先に PR 化することで tool call limit を避けられる。
- Phase 1: DB + Schema + Service + API + Scripts + Docs（バックエンド PR）
- Phase 2: Admin UI（後続 PR）

### スクリプトの typecheck 対策
`scripts/` 内のファイルが `@/` エイリアスを使用すると、`tsc` がモジュール解決に失敗する。
- 対策: `tsconfig.json` の `exclude` に `"scripts"` を追加
- または、スクリプトは `.mts` で書き、`tsx` で実行する

## 制約

- subagent は親のメモリを持たない。すべての文脈（ファイルパス、エラーメッセージ、制約）は context に明示的に書くこと
- subagent は `clarify`（ユーザーへの質問）が使えない。判断が必要な場合は親に戻す
- subagent は 1ターンで完結する。長時間タスクは cronjob にする
- **delegate_task の model override はパッチ適用済みだが、実行環境のプロセス構成に依存する**：
  - Gateway が同一プロセスの場合: セッションキャッシュのため `/reset` が必要
  - Gateway が sandbox 外で動作する場合: **model override は事実上使用不可**。親エージェントが直接実装するか、`callAi` 経由で別モデルを使うようにする

## opencode CLI との使い分け

- delegate_task：リポジトリ内の既存コードパターンを参照しながら、ファイル操作・コマンド実行・テストを含む実装に最適
- opencode CLI：単純なコード生成（1ファイル〜数ファイル）で、モデル選択・高速な文章生成が必要な場合に最適
- 現状 opencode CLI はログイン未完了（goプランの `/connect` 相当の認証が必要）
