# Plan: `uitree_verify` strategy の追加

## Context

コンパイル済みシナリオの `then`（検証）ステップには現在2パターンしかない:

| 現状 | strategy | 動作 |
|------|----------|------|
| 引用テキストあり `「XX」` | `strict_text_match` | UITreeテキスト検索（プログラム的） |
| それ以外 | `ai_checkpoint` | AI Vision or スキップ（検証なし） |

**問題**: `ホーム画面が表示されていること` のような引用なしアサーションは、AI呼ぶか検証スキップの二択。UITreeから画面状態を判定できるケースでも無駄にAIを使うか、検証を諦めている。

**解決**: 初回AI実行時のUITreeデータから「画面の指紋」を抽出し、再実行時にプログラム的に検証する `uitree_verify` strategy を追加する。

## 変更後の検証モード

| strategy | 検証方法 | skip-ai時 | AI依存 |
|----------|---------|-----------|--------|
| `strict_text_match` | UITreeテキスト検索 | 実行される | なし |
| **`uitree_verify`** (NEW) | **UITree指紋照合** | **実行される** | **なし** |
| `ai_checkpoint` | AI Vision | スキップ | あり |

## `uitree_verify` JSON Schema

```json
{
  "strategy": "uitree_verify",
  "assertion": "ホーム画面が表示されていること",
  "fallback_to_ai": false,
  "checks": [
    {"type": "text_visible", "value": "ホーム", "match_type": "exact"},
    {"type": "resource_id_exists", "value": "com.example.app:id/bottom_nav"},
    {"type": "class_exists", "value": "androidx.recyclerview.widget.RecyclerView"},
    {"type": "text_not_visible", "value": "エラー", "match_type": "contains"},
    {"type": "element_count_gte", "selector": {"class": "android.widget.TextView"}, "min_count": 3}
  ]
}
```

### Check Types

| type | 用途 | 例 |
|------|------|-----|
| `text_visible` | テキストが存在する | `"ホーム"` が画面にある |
| `text_not_visible` | テキストが存在しない | `"エラー"` が画面にない |
| `resource_id_exists` | リソースIDが存在する | `bottom_nav` が存在 |
| `class_exists` | ウィジェットクラスが存在する | RecyclerView がある |
| `element_count_gte` | 要素がN個以上ある | TextViewが3個以上 |

### 失敗時の動作

- `fallback_to_ai: false`（デフォルト）→ チェック失敗 = `failed`
- `fallback_to_ai: true` → チェック失敗 = `ai_required`（AIにフォールバック）

## 変更ファイル

### 1. `scripts/utils/uitree_parser.py` — ユーティリティ関数追加

新規関数:
- `resource_id_exists(root, resource_id)` → bool
- `class_exists(root, class_name)` → bool
- `count_elements(root, selector)` → int
- `extract_fingerprint(root)` → dict（全テキスト・リソースID・構造クラスを抽出）

### 2. `scripts/compiled_runner.py` — `uitree_verify` ハンドラ追加

- `_execute_then()` に `uitree_verify` 分岐を追加
- 各チェックを実行し、全パスで `passed`、失敗で `failed` or `ai_required`
- `verification.checks` に個別チェック結果を記録
- import に新関数を追加

### 3. `dotclaude/agents/task/scenario-compiler.md` — コンパイル時のUITree解析

`classify_then` を拡張:
```
1. 引用テキストあり → strict_text_match（従来通り）
2. (NEW) UITree XMLを読み、指紋チェックを生成 → uitree_verify
3. UITreeデータ不十分 or strict指定 → ai_checkpoint（従来通り）
```

コンパイラが初回実行のUITree XMLを読み取り、以下を抽出:
- 目立つテキスト（2文字以上、動的でないもの）を2-3個選択
- アプリ固有のリソースID（`android:id/` を除外）を1-2個選択
- 構造的ウィジェット（RecyclerView, TabLayout等）があれば追加

### 4. `dotclaude/skills/uiai-android-test/references/compile-ir-schema.md` — スキーマ文書

`strict_text_match` と `ai_checkpoint` の間に `uitree_verify` セクションを追加。

### 5. `dotclaude/skills/uiai-android-test/SKILL.md` — 検証モード一覧更新

Execution Modes テーブルに `uitree_verify` の説明を追加。

## 実装順序

1. `uitree_parser.py` — ユーティリティ関数追加（テスト可能な単体）
2. `compiled_runner.py` — ランタイムハンドラ追加
3. `scenario-compiler.md` — コンパイル時ロジック更新
4. `compile-ir-schema.md` — スキーマ文書追加
5. `SKILL.md` — 概要文書更新

## 検証方法

1. 既存テストが壊れないことを確認（`strict_text_match` と `ai_checkpoint` の動作は変更なし）
2. 手動で `uitree_verify` を含む compiled.json を作成し、compiled_runner.py で実行
3. シナリオをAI実行 → 生成された compiled.json に `uitree_verify` が含まれることを確認
