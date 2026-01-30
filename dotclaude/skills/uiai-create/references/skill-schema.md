# SKILL.md Schema

SKILL.mdファイルの構造とフィールド定義。

## ファイル構造

SKILL.mdは以下の2つのセクションで構成:

1. **Frontmatter** - YAMLメタデータ（`---`で囲む）
2. **Body** - Markdownドキュメント本文

## Frontmatter Schema

```yaml
---
name: string                    # 必須: スキル名
description: string             # 必須: スキルの説明
argument-hint: string           # 任意: 引数ヒント表示用
arguments:                      # 任意: 引数定義配列
  - name: string                # 必須: 引数名
    description: string         # 必須: 引数の説明
    required: boolean           # 必須: 必須フラグ
    placeholder: string         # 任意: 入力例
    default: string             # 任意: デフォルト値
references:                     # 任意: リファレンスファイル配列
  - path: string                # 必須: ファイルパス
---
```

## フィールド詳細

### name (必須)

スキルの一意識別子。

| 項目 | 値 |
|------|-----|
| 型 | string |
| 形式 | kebab-case |
| 制約 | `uiai-` prefix必須、8-50文字 |
| 例 | `uiai-android-test` |

### description (必須)

スキルの簡潔な説明。

| 項目 | 値 |
|------|-----|
| 型 | string |
| 制約 | 200文字以内 |
| 例 | `ADBを使用したAndroid UIテスト自動化スキル` |

### argument-hint (任意)

ヘルプ表示用の引数ヒント。

| 項目 | 値 |
|------|-----|
| 型 | string |
| 形式 | `key=<value>` 形式 |
| 例 | `scenarios=<path> [device=<device-id>]` |

### arguments (任意)

スキルが受け取る引数の配列。

#### arguments[].name (必須)

| 項目 | 値 |
|------|-----|
| 型 | string |
| 形式 | lowercase + hyphen |
| 制約 | 予約語禁止（help, version） |
| 例 | `scenarios`, `device-id` |

#### arguments[].description (必須)

| 項目 | 値 |
|------|-----|
| 型 | string |
| 例 | `テストシナリオYAMLファイル（glob対応）` |

#### arguments[].required (必須)

| 項目 | 値 |
|------|-----|
| 型 | boolean |
| 値 | `true` または `false` |

#### arguments[].placeholder (任意)

| 項目 | 値 |
|------|-----|
| 型 | string |
| 例 | `test/scenarios/*.yaml` |

#### arguments[].default (任意)

| 項目 | 値 |
|------|-----|
| 型 | string |
| 例 | `false` |

### references (任意)

参照するリファレンスファイルの配列。

#### references[].path (必須)

| 項目 | 値 |
|------|-----|
| 型 | string |
| 形式 | 相対パス |
| 例 | `./references/scenario-schema.md` |

## Body構造

Frontmatter以降のMarkdown本文の推奨構造:

```markdown
# {スキル名}

{説明文}

## 特徴

- **特徴1** - 説明
- **特徴2** - 説明

## 使用方法

\`\`\`bash
/{skill-name} {arguments}
\`\`\`

## パラメータ

| パラメータ | 必須 | デフォルト | 説明 |
|-----------|------|-----------|------|
| `name` | Yes | - | 説明 |

## 実行フロー

1. ステップ1
2. ステップ2

## 出力

出力形式の説明

## 注意事項

- 注意点1
- 注意点2

## リファレンス

- [リファレンス名](./references/file.md) - 説明
```

## 完全な例

```yaml
---
name: uiai-android-test
description: ADBを使用したAndroid UIテスト自動化スキル
argument-hint: "scenarios=<path> [device=<device-id>] [strict=true]"
arguments:
  - name: scenarios
    description: テストシナリオYAMLファイル（glob対応）
    required: true
    placeholder: "test/scenarios/*.yaml"
  - name: device
    description: 対象デバイスID
    required: false
    placeholder: "emulator-5554"
  - name: strict
    description: 厳格モード
    required: false
    default: "false"
references:
  - path: ./references/adb-commands.md
  - path: ./references/scenario-schema.md
---

# uiai Android Test

ADBを使用したAndroid UIテスト自動化スキル。

...
```

## バリデーションルール

### エラー（作成不可）

| ID | ルール |
|----|--------|
| E001 | `name` が未定義 |
| E002 | `description` が未定義 |
| E003 | `name` が `uiai-` で始まらない |
| E004 | `name` が kebab-case でない |
| E005 | `name` が 8-50 文字でない |
| E006 | `name` が既存スキルと重複 |
| E007 | 引数名が重複 |
| E008 | 引数名が予約語 |
| E009 | リファレンスパスが存在しない |

### 警告（作成可能）

| ID | ルール |
|----|--------|
| W001 | `argument-hint` が未定義 |
| W002 | 引数に `placeholder` がない |
| W003 | 任意引数に `default` がない |
