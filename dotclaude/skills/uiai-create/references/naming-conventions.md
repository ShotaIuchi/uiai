# Naming Conventions

uiaiスキルの命名規則定義。

## スキル名

### 形式

```
uiai-{category}-{name}
uiai-{name}
```

| 項目 | ルール |
|------|--------|
| Prefix | `uiai-` 必須 |
| 形式 | kebab-case（小文字とハイフンのみ） |
| 文字数 | 8-50文字（prefix含む） |
| 一意性 | `dotclaude/skills/` 内で一意 |

### 有効な例

```
uiai-android-test      # OK: カテゴリ+名前
uiai-scenario-check    # OK: カテゴリ+名前
uiai-create            # OK: 名前のみ
uiai-web-api-test      # OK: 複数ハイフン
```

### 無効な例

```
android-test           # NG: uiai- prefix なし
uiai_android_test      # NG: アンダースコア使用
uiai-AndroidTest       # NG: 大文字使用
uiai-test              # NG: 8文字未満
uiai-very-long-skill-name-that-exceeds-fifty-characters  # NG: 50文字超過
```

### 推奨カテゴリ

| カテゴリ | 用途 | 例 |
|---------|------|-----|
| `android-` | Android関連 | `uiai-android-test` |
| `ios-` | iOS関連 | `uiai-ios-test` |
| `web-` | Web関連 | `uiai-web-test` |
| `scenario-` | シナリオ関連 | `uiai-scenario-check` |
| `api-` | API関連 | `uiai-api-test` |
| なし | ユーティリティ | `uiai-create` |

## 引数名

### 形式

```
{name}
{category}-{name}
```

| 項目 | ルール |
|------|--------|
| 形式 | lowercase + hyphen |
| 予約語 | `help`, `version` は使用禁止 |
| 一意性 | 同一スキル内で一意 |

### 有効な例

```
scenarios              # OK: 単語
device-id              # OK: ハイフン区切り
dry-run                # OK: ハイフン区切り
strict                 # OK: 単語
```

### 無効な例

```
Scenarios              # NG: 大文字
device_id              # NG: アンダースコア
deviceId               # NG: camelCase
help                   # NG: 予約語
version                # NG: 予約語
```

### 推奨パターン

| パターン | 用途 | 例 |
|---------|------|-----|
| 単数名詞 | 単一値 | `device`, `timeout` |
| 複数名詞 | 複数値/glob | `scenarios`, `files` |
| 形容詞 | フラグ | `strict`, `verbose` |
| 動詞-名詞 | 動作指定 | `dry-run`, `skip-validation` |

## リファレンスファイル名

### 形式

```
{name}.md
{category}-{name}.md
```

| 項目 | ルール |
|------|--------|
| 形式 | kebab-case + `.md` |
| 配置 | `./references/` ディレクトリ |

### 有効な例

```
scenario-schema.md     # OK
adb-commands.md        # OK
validation-rules.md    # OK
output-format.md       # OK
```

### 無効な例

```
ScenarioSchema.md      # NG: PascalCase
scenario_schema.md     # NG: アンダースコア
schema.yaml            # NG: 拡張子が .md でない
```

### 推奨サフィックス

| サフィックス | 用途 | 例 |
|-------------|------|-----|
| `-schema` | データ構造定義 | `scenario-schema.md` |
| `-rules` | ルール定義 | `validation-rules.md` |
| `-format` | フォーマット定義 | `output-format.md` |
| `-commands` | コマンド定義 | `adb-commands.md` |
| `-patterns` | パターン定義 | `error-patterns.md` |

## ディレクトリ構造

```
dotclaude/skills/
└── {skill-name}/           # スキル名（kebab-case）
    ├── SKILL.md            # 固定ファイル名
    └── references/         # 固定ディレクトリ名
        └── {ref-name}.md   # リファレンス名（kebab-case）
```

## バリデーション正規表現

### スキル名

```regex
^uiai-[a-z][a-z0-9]*(-[a-z][a-z0-9]*)*$
```

長さ: 8-50文字

### 引数名

```regex
^[a-z][a-z0-9]*(-[a-z][a-z0-9]*)*$
```

禁止: `help`, `version`

### リファレンスファイル名

```regex
^[a-z][a-z0-9]*(-[a-z][a-z0-9]*)*\.md$
```

## チェックリスト

スキル作成時の命名チェックリスト:

- [ ] スキル名が `uiai-` で始まる
- [ ] スキル名が kebab-case
- [ ] スキル名が 8-50 文字
- [ ] スキル名が既存スキルと重複しない
- [ ] 引数名が lowercase + hyphen
- [ ] 引数名が予約語でない
- [ ] 引数名がスキル内で一意
- [ ] リファレンスファイル名が kebab-case
- [ ] リファレンスファイルが `.md` 拡張子
