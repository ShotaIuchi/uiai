---
name: uiai-scenario-check
description: シナリオYAMLファイルのスキーマ検証・修正提案・自動修正を行うスキル。
argument-hint: "scenarios=<path> [fix=true] [dry-run=true] [strict=true]"
arguments:
  - name: scenarios
    description: 検証対象YAMLファイル（glob対応）
    required: true
    placeholder: "sample/*.yaml"
  - name: fix
    description: 自動修正を実行
    required: false
    default: "false"
  - name: dry-run
    description: 修正内容表示のみ（fix=true時に有効）
    required: false
    default: "false"
  - name: strict
    description: 警告もエラー扱い
    required: false
    default: "false"
references:
  - path: ./references/validation-rules.md
  - path: ./references/auto-fix-rules.md
  - path: ./references/output-format.md
  - path: ../uiai-android-test/references/scenario-schema.md
---

# uiai Scenario Check

シナリオYAMLファイルをスキーマに基づいて検証し、エラーや警告を検出、自動修正を提案するスキル。

## 特徴

- **スキーマ検証** - 必須フィールド、型、形式の検証
- **参照整合性** - replay.from/to の存在・順序・循環参照チェック
- **自動修正** - 修正可能なエラーの自動修正
- **ドライラン** - 修正内容の事前確認

## 使用方法

```bash
# 基本検証
/uiai-scenario-check scenarios=test/scenarios/login.yaml

# 複数ファイル（glob対応）
/uiai-scenario-check scenarios=test/scenarios/*.yaml

# 自動修正
/uiai-scenario-check scenarios=test/scenarios/*.yaml fix=true

# ドライラン（修正内容表示のみ）
/uiai-scenario-check scenarios=test/scenarios/*.yaml fix=true dry-run=true

# 厳格モード（警告もエラー扱い）
/uiai-scenario-check scenarios=test/scenarios/*.yaml strict=true
```

## パラメータ

| パラメータ | 必須 | デフォルト | 説明 |
|-----------|------|-----------|------|
| `scenarios` | Yes | - | 検証対象YAMLファイル（glob対応） |
| `fix` | No | `false` | 自動修正を実行 |
| `dry-run` | No | `false` | 修正内容表示のみ（fix=true時） |
| `strict` | No | `false` | 警告もエラー扱い |

## 検証ルール概要

### エラー（修正必須）

| ID | 項目 | 自動修正 |
|----|------|---------|
| E001 | `name` 必須 | 不可 |
| E002 | `app` 必須 | 不可 |
| E003 | `steps` 必須 | 不可 |
| E004 | `steps` 非空 | 不可 |
| E005 | `id` 必須 | 可 |
| E006 | `actions` 必須 | 不可 |
| E010 | `app` 形式不正 | 不可 |
| E011 | `id` 重複 | 可 |
| E012 | `do`/`then` 混在 | 可 |
| E013 | `wait` 型不正 | 可 |
| E014 | `strict` 型不正 | 可 |
| E020 | `replay.from` 不存在 | 不可 |
| E021 | `replay.to` 不存在 | 不可 |
| E022 | `replay` 順序不正 | 不可 |
| E023 | `replay` 循環参照 | 不可 |

### 警告（推奨）

| ID | 項目 | 自動修正 |
|----|------|---------|
| W001 | 空 `actions` | 不可 |
| W002 | `then` なし | 不可 |
| W003 | 連続 `then` | 不可 |
| W004 | `config` 未知キー | 可 |

## 実行フロー

1. **ファイル読み込み** - glob パターンでファイルを展開
2. **YAML パース** - 構文エラーをチェック
3. **スキーマ検証** - 各ルールで検証
4. **結果出力** - エラー/警告をレポート
5. **自動修正**（fix=true時）- 修正可能項目を修正

## 出力

検証結果は以下の形式で出力される：

```
## シナリオ検証結果

### login.yaml

| ID | レベル | 行 | 内容 |
|----|--------|-----|------|
| E005 | ERROR | 8 | `id` が指定されていません |
| W002 | WARN | 8-12 | セクションに `then` がありません |

**エラー: 1, 警告: 1**
```

## 関連スキル

- `uiai-android-test` - 検証済みシナリオでテストを実行

## リファレンス

- [検証ルール](./references/validation-rules.md)
- [自動修正ルール](./references/auto-fix-rules.md)
- [出力フォーマット](./references/output-format.md)
- [シナリオスキーマ](../uiai-android-test/references/scenario-schema.md)
