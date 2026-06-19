# CI 失敗パターンと修正手順（Ruletrade-AI 実績）

実際のプロジェクトで発生した CI 失敗とその修正方法を記録する。

---

## パターン1: `npm ci` lockfile sync エラー

### 症状
```
npm error `npm ci` can only install packages when your package.json and package-lock.json or npm-shrinkwrap.json are in sync.
npm error Missing: <package-name> from lock file
```

### 原因
`package.json` が変更されたが `package-lock.json` が再生成されていない。

### 修正
```bash
npm install --package-lock-only
# または npm install（完全再インストールが必要な場合）
git add package-lock.json
git commit -m "chore: sync package-lock.json"
```

---

## パターン2: Prettier `format:check` 失敗

### 症状
ローカルでは `npx prettier --write .` で通ったが、CI で失敗する。

### 原因
- Prettier のバージョン差異（ローカルと CI で異なる）
- 他のツール（patch、subagent 等）が prettier 実行後にファイルを変更した
- `package-lock.json` が同期されていない

### 修正
```bash
# 完全クリーンアップ
rm -rf node_modules package-lock.json
npm install
npx prettier --write .
git add -A
git commit -m "style: apply prettier formatting"
```

### 個別ファイル修正（bulk run 後も残る場合）
```bash
# CI ログからファイル名を確認
gh run view <run-id> --job <job-id> --log | grep "warn\]"

# 該当ファイルだけ修正
npx prettier --write <file1> <file2>
git add -A
git commit -m "style: fix remaining prettier formatting in N files"
```

---

## パターン3: Gitleaks secret scan 失敗

### 症状
```
WRN leaks found: 22
```

### 原因
外部パッケージ（例: `.agents/skills/notebooklm/`）が誤って git 追跡対象になっている。テスト用のモック認証情報が secret scan に引っかかる。

### 修正
```bash
# 1. .gitignore に追加
echo ".agents/skills/notebooklm/" >> .gitignore

# 2. git 追跡から除外（ローカルファイルは保持）
git rm -r --cached .agents/skills/notebooklm/

# 3. .gitleaksignore に追加（テスト用の偽キーが引っかかる場合）
echo "path/to/test-file.ts" >> .gitleaksignore

# 4. コミット
git add .gitignore .gitleaksignore
git commit -m "chore: ignore external package and fix secret scan"
```

### 偽キーの注意事項
テスト用の偽キーは、実際のキーに似たパターン（`sk-proj-...`）を避け、マッチしない文字列（`sk-test-fake`）を使う。

---

## パターン4: `dorny/paths-filter` "Resource not accessible by integration"

### 症状
CI ジョブ `detect-changes` で失敗。

### 原因
これは workflow の token permission の問題であり、コードの問題ではない。

### 対応
他のジョブがすべて通過していれば無視してよい。workflow 設定で `permissions: pull-requests: read` を追加すれば解決する可能性がある。

---

## パターン5: 大きな外部パッケージの誤追跡

### 症状
PR に意図しない数百ファイルが含まれる。

### 原因
外部スキル・パッケージが `.gitignore` に入っていない。

### 修正
```bash
# 追跡解除
git rm -r --cached <directory>/

# .gitignore 追加
echo "<directory>/" >> .gitignore

# コミット
git add -A
git commit -m "chore: remove accidentally tracked files

- <directory> contains <N> files that should not be tracked"
```

---

## 予防策（Push 前チェックリスト）

```bash
# 1. 意図しないファイルが含まれていないか確認
git diff --stat --cached

# 2. 外部ディレクトリが混入していないか確認
git diff --cached --name-only | grep -E '^\.(agents|claude|next|venv)/' && echo "WARNING"

# 3. 品質チェックを実行
npm run lint
npm run typecheck
npm test
npm run format:check

# 4. 問題なければ push
git push origin HEAD
```
