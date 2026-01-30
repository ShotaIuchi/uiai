# Auto-Fix Rules

自動修正可能なエラーの修正ルール定義。

## 自動修正可能なエラー

### E005: `id` 必須 → 自動生成

id が指定されていないステップに `step_N` 形式の id を自動生成。

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
3. wait, strict などのオプションは do 側に残す

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

文字列や数値の strict を boolean に変換。

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

### W004: `config` 未知キー → 削除

config 内の未知のキーを削除。

**修正ルール**:
1. 既知のキー以外を削除
2. 既知のキー: `timeout`, `clear_data_before`, `stop_app_after`, `strict`

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

---

## 自動修正不可のエラー

以下のエラーは自動修正不可。人間による判断が必要。

| ID | 理由 |
|----|------|
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
| W001 | 意図的な場合がある |
| W002 | 検証内容は人間が決定すべき |
| W003 | 意図的な場合がある |

---

## 修正実行モード

### 通常モード（fix=true）

修正を実行してファイルを上書き保存。

```bash
/uiai-scenario-check scenarios=test/*.yaml fix=true
```

### ドライランモード（fix=true dry-run=true）

修正内容を表示するが、ファイルは変更しない。

```bash
/uiai-scenario-check scenarios=test/*.yaml fix=true dry-run=true
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
