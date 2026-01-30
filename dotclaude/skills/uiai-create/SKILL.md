---
name: uiai-create
description: 対話形式で新しいスキルを作成するウィザード
argument-hint: "[name=<skill-name>]"
arguments:
  - name: name
    description: 作成するスキル名（省略時は対話で入力）
    required: false
    placeholder: "uiai-my-skill"
references:
  - path: ./references/skill-schema.md
  - path: ./references/naming-conventions.md
---

# uiai-create

対話形式で新しいスキルを作成するウィザード。質問に回答してSKILL.mdとリファレンスファイルを自動生成する。

## 特徴

- **対話形式** - 段階的に質問に回答してスキルを定義
- **バリデーション** - 入力値をリアルタイムで検証
- **自動生成** - SKILL.mdとリファレンスファイルを自動生成
- **プレビュー** - 作成前に内容を確認可能

## 使用方法

```bash
# 対話形式で開始
/uiai-create

# スキル名を指定して開始
/uiai-create name=uiai-web-test
```

## 対話フロー

### Step 1: スキル名

スキル名を入力する。`name` 引数で指定した場合はスキップ。

**バリデーション**:
- `uiai-` prefix必須
- kebab-case形式（小文字とハイフンのみ）
- 8-50文字
- `dotclaude/skills/` 内で重複禁止

### Step 2: 説明

スキルの説明を入力する。

**バリデーション**:
- 空文字禁止
- 200文字以内

### Step 3: 引数

引数を追加するかどうかを選択。追加する場合はループで複数追加可能。

各引数で入力する項目:
| 項目 | 必須 | 説明 |
|------|------|------|
| name | Yes | 引数名（lowercase + hyphen） |
| description | Yes | 引数の説明 |
| required | Yes | 必須かどうか（yes/no） |
| placeholder | No | 入力例 |
| default | No | デフォルト値（required=noの場合のみ） |

**バリデーション**:
- 引数名: lowercase + hyphen、予約語禁止（help, version）、重複禁止
- 説明: 空文字禁止

### Step 4: リファレンス

リファレンスファイルを追加するかどうかを選択。追加する場合はループで複数追加可能。

各リファレンスで入力する項目:
| 項目 | 必須 | 説明 |
|------|------|------|
| name | Yes | ファイル名（拡張子なし、kebab-case） |
| purpose | Yes | ファイルの用途説明 |

### Step 5: 確認

設定内容をプレビュー表示し、作成するか確認する。

**選択肢**:
- `yes` - 作成実行
- `no` - キャンセル
- `edit` - 編集（対象項目を選択して再入力）

## 出力構造

```
dotclaude/skills/{skill-name}/
├── SKILL.md
└── references/          # リファレンス追加時のみ
    └── {ref-name}.md
```

## 生成されるSKILL.md

```yaml
---
name: {skill-name}
description: {説明}
argument-hint: "{引数ヒント}"
arguments:
  - name: {arg-name}
    description: {arg-description}
    required: {true/false}
    placeholder: "{placeholder}"
    default: "{default}"
references:
  - path: ./references/{ref-name}.md
---

# {Skill Title}

{説明}

## 使用方法

\`\`\`bash
/{skill-name} {argument-hint}
\`\`\`

## パラメータ

| パラメータ | 必須 | デフォルト | 説明 |
|-----------|------|-----------|------|
| {arg-name} | {Yes/No} | {default} | {description} |

## リファレンス

- [{ref-name}](./references/{ref-name}.md) - {purpose}
```

## 生成されるリファレンスファイル

各リファレンスファイルは以下のテンプレートで生成:

```markdown
# {Ref Title}

{purpose}の定義。

## 概要

TODO: 概要を記述

## 詳細

TODO: 詳細を記述
```

## 実行例

```
=== uiai-create: スキル作成ウィザード ===

[1/5] スキル名を入力してください:
> uiai-web-test

[2/5] スキルの説明を入力してください:
> Seleniumを使用したWebテスト自動化

[3/5] 引数を追加しますか？ (yes/no)
> yes

  引数名: scenarios
  説明: テストシナリオファイル
  必須 (yes/no): yes
  プレースホルダー: tests/*.yaml

引数を追加しますか？ (yes/no)
> no

[4/5] リファレンスを追加しますか？ (yes/no)
> no

[5/5] 確認

  スキル名: uiai-web-test
  説明: Seleniumを使用したWebテスト自動化
  引数:
    - scenarios (必須): テストシナリオファイル
  リファレンス: なし

作成しますか？ (yes/no/edit): yes

✓ dotclaude/skills/uiai-web-test/SKILL.md 作成完了
```

## エラーメッセージ

| エラー | 原因 | 対処 |
|--------|------|------|
| `スキル名は uiai- で始まる必要があります` | prefix不正 | `uiai-` を付ける |
| `スキル名は kebab-case で指定してください` | 形式不正 | 小文字とハイフンのみ使用 |
| `スキル名は 8-50 文字で指定してください` | 文字数不正 | 適切な長さに調整 |
| `スキル '{name}' は既に存在します` | 重複 | 別の名前を指定 |
| `'{name}' は予約語のため使用できません` | 予約語 | 別の名前を指定 |
| `引数名 '{name}' は既に定義されています` | 引数重複 | 別の名前を指定 |

## 注意事項

- 作成後のスキルは `/{skill-name}` で呼び出し可能
- リファレンスファイルのTODOは手動で記述が必要
- 既存スキルの上書きは不可（先に手動削除が必要）

## リファレンス

- [SKILL.mdスキーマ](./references/skill-schema.md)
- [命名規則](./references/naming-conventions.md)
