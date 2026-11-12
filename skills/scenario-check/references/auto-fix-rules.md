# Auto-Fix Rules

`fix=true` のときに自動で直してよい問題と、その直し方。ここにない問題は修正案を示すだけにする。
直したあとは必ず `uiai check` で確かめ直す。

## 自動修正可能なエラー

### E005: `id` 必須 → 自動生成

`id` がないセクションに（セクションがマッピングでない場合は修正不可） `step_N` 形式の id を自動生成。

**修正ルール**:
1. ステップの出現順に番号を付与（1から開始）
2. 既存の id と重複しないように採番
3. 形式: `step_1`, `step_2`, ...

**例**:

```yaml
# Before
steps:
  - actions:
      - do: "アプリを起動"
  - id: "ログイン"
    actions:
      - do: "ログインする"
  - actions:
      - do: "確認する"

# After
steps:
  - id: "step_1"
    actions:
      - do: "アプリを起動"
  - id: "ログイン"
    actions:
      - do: "ログインする"
  - id: "step_3"
    actions:
      - do: "確認する"
```

### E011: `id` 重複 → サフィックス追加

重複した id に `_2`, `_3` ... のサフィックスを追加。

**修正ルール**:
1. 最初の出現はそのまま維持
2. 2回目以降の出現に `_N` サフィックスを追加
3. 既存の id と重複しないように採番

**例**:

```yaml
# Before
steps:
  - id: "ログイン"
    actions: [...]
  - id: "ログイン"
    actions: [...]
  - id: "ログイン"
    actions: [...]

# After
steps:
  - id: "ログイン"
    actions: [...]
  - id: "ログイン_2"
    actions: [...]
  - id: "ログイン_3"
    actions: [...]
```

### E012: `do`/`then` 混在 → 分割

do と then が同一オブジェクトに存在する場合、2つの要素に分割。

**修正ルール**:
1. do を含むオブジェクトを先に配置
2. then を含むオブジェクトを後に配置
3. `wait`・`strict` は do 側に、`timeout`・`observe`（`then` にだけ有効）は then 側に置く

**例**:

```yaml
# Before
actions:
  - do: "ボタンをタップ"
    then: "画面が表示されること"
    wait: 3

# After
actions:
  - do: "ボタンをタップ"
    wait: 3
  - then: "画面が表示されること"
```

### E013: `wait` 型不正 → 数値変換

文字列の wait を数値に変換。

**修正ルール**:
1. 数値部分を抽出
2. 抽出できない場合は修正不可

**例**:

```yaml
# Before → After
wait: "3"       → wait: 3
wait: "3秒"     → wait: 3
wait: "3.5"     → wait: 3.5
wait: "3 sec"   → wait: 3
wait: "three"   → 修正不可（エラーのまま）
```

**抽出パターン**: `^\s*(\d+(?:\.\d+)?)`

### E014: `strict` 型不正 → boolean 変換

文字列や数値の `strict`（`config.strict`・`config.clear_data_before`・`config.stop_app_after` も同じ）を boolean に変換。

**修正ルール**:
| 入力値 | 変換後 |
|--------|--------|
| `"true"`, `"True"`, `"TRUE"` | `true` |
| `"false"`, `"False"`, `"FALSE"` | `false` |
| `1`, `"1"` | `true` |
| `0`, `"0"` | `false` |
| `"yes"`, `"Yes"`, `"YES"` | `true` |
| `"no"`, `"No"`, `"NO"` | `false` |
| その他 | 修正不可 |

**例**:

```yaml
# Before → After
strict: "true"   → strict: true
strict: 1        → strict: true
strict: "yes"    → strict: true
strict: "false"  → strict: false
strict: 0        → strict: false
strict: "maybe"  → 修正不可（エラーのまま）
```

### W004: `config` 未知キー → 綴りの修正か削除

config 内の未知のキーを直す。

**修正ルール**:
1. 既知のキーの綴り誤りと明らかに分かるもの（`then_timout` → `then_timeout` など）は、キー名を直す
2. それ以外は削除する（エンジンは無視しているため、動きは変わらない）
3. 既知のキー: `timeout`, `then_timeout`, `max_actions`, `strict`, `clear_data_before`, `stop_app_after`, `reset`, `on_failure`, `interrupts`, `model`（`verify` は W007）

**例**:

```yaml
# Before
config:
  timeout: 60
  unknown_key: "value"
  another_unknown: 123
  strict: true

# After
config:
  timeout: 60
  strict: true
```

### E032: 変数名重複 → 最初を維持

重複した変数定義のうち、最初の定義を維持し、後続を削除。

**修正ルール**:
1. 最初の出現をそのまま維持
2. 2回目以降の出現を削除
3. YAMLの重複キーは通常パーサーで後勝ちになるが、修正では最初を採用

**例**:

```yaml
# Before
variables:
  email: "test@example.com"
  password: "password123"
  email: "another@example.com"     # 重複

# After
variables:
  email: "test@example.com"
  password: "password123"
```

`uiai check` は重複キーを行番号つきで検出する。

### W007: `verify` → 削除

`verify`・`config.verify` を削除する。判定は AI の画像判定に一本化されており、エンジンは無視しているため、動きは変わらない。

```yaml
# Before
config:
  verify: uitree
steps:
  - id: "確認"
    actions:
      - then: "ホーム画面が表示されていること"
        verify: ai

# After
steps:
  - id: "確認"
    actions:
      - then: "ホーム画面が表示されていること"
```

`config` が空になったら `config` ごと削除する。

---

## 自動修正不可のエラー

以下のエラーは自動修正不可。人間による判断が必要。

| ID | 理由 |
|----|------|
| E000 | YAML の構文の直し方は一意に決まらない |
| E001 | 適切なシナリオ名は人間が決定すべき |
| E002 | パッケージ名は特定できない |
| E003 | テスト内容がない |
| E004 | テスト内容がない |
| E006 | アクション内容は特定できない |
| E010 | 正しいパッケージ名は特定できない |
| E020 | 参照先を特定できない |
| E021 | 参照先を特定できない |
| E022 | 意図が不明 |
| E023 | 構造的な問題 |
| E030 | 変数の値は特定できない |
| E031 | 適切な変数名は人間が決定すべき |
| E015 | 正しい値は人間が決定すべき |
| E016 | どの動きにするかは人間が決定すべき |
| E033 | `then` で何を確かめたいかは人間が決定すべき |
| E034 | アクションの内容は特定できない |
| W001 | 意図的な場合がある |
| W002 | 検証内容は人間が決定すべき |
| W003 | 意図的な場合がある |
| W005 | 意図的な場合がある（将来使う予定かもしれない） |
| W006 | 実行時に入力させる意図の場合がある |
| W008 | 適切な上限は人間が決定すべき（目安は `do` の数 × 10 秒以上） |
| W009 | `then` に移すべきか、消すべきかは意図による |

---

## 修正実行モード

### 通常モード（fix=true）

修正を実行してファイルを上書き保存。

```bash
/uiai:scenario-check scenarios=test/*.yaml fix=true
```

### ドライランモード（fix=true dry-run=true）

修正内容を表示するが、ファイルは変更しない。

```bash
/uiai:scenario-check scenarios=test/*.yaml fix=true dry-run=true
```

---

## 修正の安全性

### 修正前のバックアップ

自動修正を実行する前に、以下を推奨：

1. git で変更管理されていることを確認
2. 未コミットの変更がないことを確認
3. ドライランで修正内容を確認

### 修正の原則

1. **最小限の変更**: 必要な修正のみ行う
2. **既存の構造維持**: YAML のフォーマット・インデント・コメントを可能な限り維持
3. **順序維持**: 要素の順序は変更しない（E012 の分割を除く）

### 修正失敗時

以下の場合、該当項目の修正をスキップ：

1. 型変換ができない場合（E013, E014）
2. 修正により新たなエラーが発生する場合

スキップされた項目はエラーとして残り、レポートに表示される。
