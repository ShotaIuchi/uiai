# Validation Rules

シナリオYAMLファイルの検証ルール定義。

## エラー（修正必須）

エラーはシナリオ実行を阻害する問題。修正が必須。

### E001: `name` 必須

シナリオ名が指定されていない。

```yaml
# NG
app: "com.example.app"
steps: [...]

# OK
name: "ログインテスト"
app: "com.example.app"
steps: [...]
```

**自動修正**: 不可（適切な名前は人間が決定すべき）

### E002: `app` 必須

アプリパッケージ名が指定されていない。

```yaml
# NG
name: "テスト"
steps: [...]

# OK
name: "テスト"
app: "com.example.app"
steps: [...]
```

**自動修正**: 不可（パッケージ名は特定できない）

### E003: `steps` 必須

steps フィールドが存在しない。

```yaml
# NG
name: "テスト"
app: "com.example.app"

# OK
name: "テスト"
app: "com.example.app"
steps: [...]
```

**自動修正**: 不可（テスト内容がない）

### E004: `steps` 非空

steps が空配列。

```yaml
# NG
steps: []

# OK
steps:
  - id: "step_1"
    actions:
      - do: "アプリを起動"
```

**自動修正**: 不可（テスト内容がない）

### E005: `id` 必須

ステップに id が指定されていない。

```yaml
# NG
steps:
  - actions:
      - do: "アプリを起動"

# OK
steps:
  - id: "起動"
    actions:
      - do: "アプリを起動"
```

**自動修正**: 可（`step_1`, `step_2` ... を自動生成）

### E006: `actions` 必須

ステップに actions が指定されていない（replay のみの場合は除く）。

```yaml
# NG
steps:
  - id: "起動"

# OK (actionsあり)
steps:
  - id: "起動"
    actions:
      - do: "アプリを起動"

# OK (replayのみ)
steps:
  - id: "リプレイ"
    replay:
      from: "起動"
      to: "起動"
```

**自動修正**: 不可（アクション内容は特定できない）

### E010: `app` 形式不正

パッケージ名が Android の形式（`com.xxx.xxx`）に従っていない。

```yaml
# NG
app: "example"
app: "com.example"
app: "com example app"

# OK
app: "com.example.app"
app: "jp.co.example.app"
```

**検証パターン**: `^[a-zA-Z][a-zA-Z0-9_]*(\.[a-zA-Z][a-zA-Z0-9_]*){2,}$`

**自動修正**: 不可（正しいパッケージ名は特定できない）

### E011: `id` 重複

同一シナリオ内で id が重複。

```yaml
# NG
steps:
  - id: "ログイン"
    actions: [...]
  - id: "ログイン"      # 重複
    actions: [...]

# OK
steps:
  - id: "ログイン"
    actions: [...]
  - id: "ログイン_2"
    actions: [...]
```

**自動修正**: 可（`_2`, `_3` ... サフィックスを追加）

### E012: `do`/`then` 同一行混在

actions 内で do と then が同一オブジェクトに存在。

```yaml
# NG
actions:
  - do: "ボタンをタップ"
    then: "画面が表示されること"

# OK
actions:
  - do: "ボタンをタップ"
  - then: "画面が表示されること"
```

**自動修正**: 可（2つの要素に分割）

### E013: `wait` 型不正

wait の値が数値でない。

```yaml
# NG
actions:
  - do: "ボタンをタップ"
    wait: "3秒"
  - do: "ボタンをタップ"
    wait: "three"

# OK
actions:
  - do: "ボタンをタップ"
    wait: 3
```

**自動修正**: 可（数値抽出を試みる。`"3秒"` → `3`）

### E014: `strict` 型不正

strict の値が boolean でない。

```yaml
# NG
actions:
  - do: "ボタンをタップ"
    strict: "true"
  - then: "表示されること"
    strict: 1

# OK
actions:
  - do: "ボタンをタップ"
    strict: true
  - then: "表示されること"
    strict: false
```

**自動修正**: 可（`"true"` → `true`, `1` → `true` 等）

### E020: `replay.from` 不存在

replay.from で参照している id が存在しない。

```yaml
# NG
steps:
  - id: "ログイン"
    actions: [...]
  - id: "確認"
    replay:
      from: "初期化"    # 存在しない
      to: "ログイン"

# OK
steps:
  - id: "初期化"
    actions: [...]
  - id: "ログイン"
    actions: [...]
  - id: "確認"
    replay:
      from: "初期化"
      to: "ログイン"
```

**自動修正**: 不可（参照先を特定できない）

### E021: `replay.to` 不存在

replay.to で参照している id が存在しない。

```yaml
# NG
steps:
  - id: "ログイン"
    actions: [...]
  - id: "確認"
    replay:
      from: "ログイン"
      to: "データ入力"   # 存在しない
```

**自動修正**: 不可（参照先を特定できない）

### E022: `replay` 順序不正

replay の from が to より後に定義されている。

```yaml
# NG
steps:
  - id: "ログイン"
    actions: [...]
  - id: "データ入力"
    actions: [...]
  - id: "確認"
    replay:
      from: "データ入力"
      to: "ログイン"     # fromより前に定義されている

# OK
steps:
  - id: "ログイン"
    actions: [...]
  - id: "データ入力"
    actions: [...]
  - id: "確認"
    replay:
      from: "ログイン"
      to: "データ入力"
```

**自動修正**: 不可（意図が不明）

### E023: `replay` 循環参照

replay が循環参照を形成。

```yaml
# NG
steps:
  - id: "A"
    replay:
      from: "B"
      to: "B"
    actions: [...]
  - id: "B"
    replay:
      from: "A"
      to: "A"         # A → B → A の循環
    actions: [...]
```

**自動修正**: 不可（構造的な問題）

### E030: 未定義変数参照

`do` または `then` で参照している変数が `variables` に定義されていない。

```yaml
# NG
variables:
  email: "test@example.com"

steps:
  - id: "ログイン"
    actions:
      - do: "メールに「(email)」を入力"
      - do: "パスワードに「(password)」を入力"  # password は未定義

# OK
variables:
  email: "test@example.com"
  password: "password123"

steps:
  - id: "ログイン"
    actions:
      - do: "メールに「(email)」を入力"
      - do: "パスワードに「(password)」を入力"
```

**検出パターン**: `(?<!\\)\(([a-zA-Z_][a-zA-Z0-9_]*)\)` で変数参照を検出

**自動修正**: 不可（変数の値は特定できない）

### E031: 無効な変数名

変数名が命名規則に従っていない。

```yaml
# NG
variables:
  123email: "test@example.com"     # 数字で始まる
  my-var: "value"                  # ハイフン不可
  "user name": "john"              # スペース不可

# OK
variables:
  email: "test@example.com"
  my_var: "value"
  user_name: "john"
  _private: "value"
```

**命名規則**: `^[a-zA-Z_][a-zA-Z0-9_]*$`

**自動修正**: 不可（適切な名前は人間が決定すべき）

### E032: 変数名重複

同一シナリオ内で変数名が重複定義されている。

```yaml
# NG
variables:
  email: "test@example.com"
  email: "another@example.com"     # 重複

# OK
variables:
  email: "test@example.com"
  email_alt: "another@example.com"
```

**自動修正**: 可（最初の定義を維持、後続を削除）

---

## 警告（推奨）

警告は実行可能だが推奨されない問題。

### W001: 空 `actions`

actions が空配列。

```yaml
# 警告
steps:
  - id: "空ステップ"
    actions: []

# OK
steps:
  - id: "ステップ"
    actions:
      - do: "アプリを起動"
```

**自動修正**: 不可（意図的な場合がある）

### W002: `then` なし

セクションに then（検証）がない。

```yaml
# 警告
steps:
  - id: "ログイン"
    actions:
      - do: "ボタンをタップ"
      - do: "入力する"
      # thenがない

# OK
steps:
  - id: "ログイン"
    actions:
      - do: "ボタンをタップ"
      - do: "入力する"
      - then: "ログインできること"
```

**自動修正**: 不可（検証内容は人間が決定すべき）

### W003: 連続 `then`

do なしで then が連続。

```yaml
# 警告
steps:
  - id: "確認"
    actions:
      - then: "画面Aが表示されること"
      - then: "画面Bも表示されること"  # 連続then

# OK（通常は1つのthenにまとめる）
steps:
  - id: "確認"
    actions:
      - then: "画面Aと画面Bが表示されること"
```

**自動修正**: 不可（意図的な場合がある）

### W004: `config` 未知キー

config に未知のキーが含まれている。

```yaml
# 警告
config:
  timeout: 60
  unknown_key: "value"    # 未知のキー
  strict: true

# OK
config:
  timeout: 60
  clear_data_before: true
  stop_app_after: true
  strict: true
```

**既知のキー**: `timeout`, `clear_data_before`, `stop_app_after`, `strict`

**自動修正**: 可（未知キーを削除）

### W005: 未使用変数

`variables` に定義されているが、どの `do` や `then` でも使用されていない。

```yaml
# 警告
variables:
  email: "test@example.com"
  password: "password123"      # 未使用
  office: "東京本社"           # 未使用

steps:
  - id: "ログイン"
    actions:
      - do: "メールに「(email)」を入力"   # email のみ使用
      - then: "ログインできること"

# OK（すべての変数を使用）
variables:
  email: "test@example.com"

steps:
  - id: "ログイン"
    actions:
      - do: "メールに「(email)」を入力"
      - then: "ログインできること"
```

**自動修正**: 不可（意図的な場合がある。将来使う予定の変数かもしれない）

---

## 検証順序

1. YAML構文チェック
2. 必須フィールド（E001-E006）
3. 形式チェック（E010-E014）
4. 参照整合性（E020-E023）
5. 変数チェック（E030-E032）
6. 警告チェック（W001-W005）

## 終了条件

| strict オプション | 終了条件 |
|------------------|---------|
| false（デフォルト） | エラーが1件以上 |
| true | エラーまたは警告が1件以上 |
