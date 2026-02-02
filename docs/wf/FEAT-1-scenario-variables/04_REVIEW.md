# Review: FEAT-1-scenario-variables

> Plan: [03_PLAN.md](./03_PLAN.md)
> Created: 2026-02-02
> Type: Plan Review (Phase 2)

## Review Summary

Phase 2 の Plan（Step 7-10: Interactive Variable Input）をレビューした。Phase 1 は既に実装完了済み。

## Overall Assessment

| Criteria | Status | Notes |
|----------|--------|-------|
| Spec Alignment | PASS | Issue コメントの要求（対話式変数入力）を正確に反映 |
| Scope Clarity | PASS | null 値とプロンプトの挙動が明確に定義されている |
| Step Granularity | PASS | 各ステップが独立しており、適切なサイズ |
| Dependencies | PASS | Step 7 → 8 → 9 → 10 の依存関係が明確 |
| Risk Assessment | PASS | CI 環境でのハング回避策が記載されている |

## Issues Found

### Critical Issues

None.

### Major Issues

| ID | Step | Issue | Recommendation |
|----|------|-------|----------------|
| M-1 | 7 | iOS テストスキルに `scenario-schema.md` が存在しない | `uiai-ios-test` ディレクトリに `scenario-schema.md` を新規作成するか、既存の共通スキーマを参照する形式に変更 |

### Minor Issues

| ID | Step | Issue | Recommendation |
|----|------|-------|----------------|
| m-1 | 8 | `execution-flow.md` は iOS のみ存在し、Android/Web には未存在 | Phase 2 では iOS 用のみ更新し、Android/Web は既存ドキュメントの形式に従う（または必要に応じて作成） |
| m-2 | 10 | null 変数の例がコメントのみ | 実際に実行可能なサンプルファイル（例: `sample-interactive-login.yaml`）の追加を検討 |

## Recommendations

### 1. iOS スキーマドキュメントの対応（M-1 対応）

**Option A: 新規作成**
```
dotclaude/skills/uiai-ios-test/references/scenario-schema.md
```
- Android/Web と同等の内容を作成
- iOS 固有の `app.ios` 設定を追加

**Option B: 共通参照**
- 3 つのスキルで共通のスキーマリファレンスを参照
- `dotclaude/references/scenario-schema.md` に移動し、各スキルから参照

**推奨**: Option A（各スキルの独立性を維持）

### 2. Step 7 の修正案

現在の Plan:
```markdown
### Step 7: Update Schema for Null Variables

- **Files:**
  - `dotclaude/skills/uiai-android-test/references/scenario-schema.md`
  - `dotclaude/skills/uiai-web-test/references/scenario-schema.md`
  - `dotclaude/skills/uiai-ios-test/references/scenario-schema.md`
```

修正案:
```markdown
### Step 7: Update Schema for Null Variables

- **Files:**
  - `dotclaude/skills/uiai-android-test/references/scenario-schema.md` (UPDATE)
  - `dotclaude/skills/uiai-web-test/references/scenario-schema.md` (UPDATE)
  - `dotclaude/skills/uiai-ios-test/references/scenario-schema.md` (CREATE - based on Android schema)
```

### 3. 変数オブジェクト構文の明確化

Spec の変数オブジェクト構文:
```yaml
api_key:
  value: null
  prompt: "Enter your API key"
```

これが Step 7 で十分に説明されているか確認。実装時に以下を明記する必要あり:
- `prompt` フィールドはオプション
- `prompt` 未指定時はデフォルトメッセージを使用
- `value: null` と直接 `null` の等価性

## Approval Status

| Reviewer | Status | Date |
|----------|--------|------|
| Claude | APPROVED with minor revisions | 2026-02-02 |

## Action Items

1. [MUST] Step 7 の Files セクションに iOS スキーマ作成を明記
2. [SHOULD] Step 10 で実行可能なサンプルファイルの追加を検討
3. [NICE] Phase 2 完了後、execution-flow.md を Android/Web にも追加検討

## Notes

- Phase 1 の実装は高品質で、変数補間の基盤が整っている
- Phase 2 の追加機能は Spec の AC-6〜AC-9 に対応しており、要件を満たす
- CI 環境での skip 動作は重要なエッジケースであり、適切にカバーされている
- W006 警告コードの追加により、null 変数の存在を事前に把握可能
