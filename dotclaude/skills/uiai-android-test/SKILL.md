---
name: uiai-android-test
description: ADBを使用したAndroid UIテスト自動化スキル。自然言語でシナリオを記述し、スクリーンショットとUIツリーで結果を評価する。
argument-hint: "scenarios=<path> [device=<device-id>] [strict=true] [skip-ai=true] [force-ai=true]"
arguments:
  - name: scenarios
    description: テストシナリオYAMLファイル（glob対応）
    required: true
    placeholder: "test/scenarios/*.yaml"
  - name: device
    description: 対象デバイスID（adb devices で確認）
    required: false
    placeholder: "emulator-5554"
  - name: strict
    description: 全ステップで厳格モード（UIツリー完全一致検証）
    required: false
    default: "false"
  - name: skip-ai
    description: コンパイル実行時にAIチェックポイントをスキップ（最速モード）
    required: false
    default: "false"
  - name: force-ai
    description: コンパイル済みを無視してAIフル実行（再コンパイルも行う）
    required: false
    default: "false"
references:
  - path: ./references/adb-commands.md
  - path: ./references/scenario-schema.md
  - path: ./references/environment.md
  - path: ./references/execution-flow.md
  - path: ./references/compile-ir-schema.md
---

# uiai Android Test

自然言語でテストシナリオを記述し、ADBコマンドでAndroidアプリのUIテストを自動実行するスキル。

## 特徴

- **自然言語シナリオ** - リソースID不要、日本語でアクションを記述
- **自動要素特定** - UIツリーから自動的にタップ位置を判定
- **Vision検証** - Claude Visionで期待結果を自然言語で検証
- **厳格モード** - UIツリーのテキスト完全一致で厳密に検証可能

## シナリオ形式

```yaml
name: "拠点切り替えテスト"
app:
  android: "com.example.app"
  ios: "com.example.App"

steps:
  - id: "起動"
    actions:
      - do: "アプリを起動"
      - then: "ホーム画面が表示されていること"

  - id: "拠点切り替え"
    actions:
      - do: "メニューをタップ"
      - do: "「拠点切り替え」を選択"
      - then: "「拠点一覧から選択」画面が開いていること"

  - id: "拠点選択"
    actions:
      - do: "「東京本社」をタップ"
      - then: "拠点が「東京本社」に変更されていること"
        strict: true   # この検証のみ完全一致
```

## 使用方法

```bash
# テスト実行（compiled.json があれば自動で高速実行、なければ AI + コンパイル）
/uiai-android-test scenarios=test/scenarios/login.yaml

# 複数シナリオ
/uiai-android-test scenarios=test/scenarios/*.yaml

# デバイス指定
/uiai-android-test scenarios=test/scenarios/login.yaml device=emulator-5554

# 厳格モード（全ステップで完全一致検証）
/uiai-android-test scenarios=test/scenarios/login.yaml strict=true

# AIチェックポイントをスキップして最速実行
/uiai-android-test scenarios=test/scenarios/login.yaml skip-ai=true

# 強制AI実行（compiled.json を無視、再コンパイルも行う）
/uiai-android-test scenarios=test/scenarios/login.yaml force-ai=true
```

## Execution Requirement (MUST)

**各シナリオは必ずTaskツールでサブエージェントとして実行すること。**

### Default: Auto-Compiled Execution

デフォルトで compiled.json の存在を自動チェックし、あれば高速実行する。

```
for each scenario_file:
  1. compiled.json が存在 & source_hash 一致 & !force-ai?
     → Yes: python scripts/compiled_runner.py (高速実行)
            ai_required ステップがあれば evaluator で評価
     → No:  AI フル実行 → evaluator → scenario-compiler で compiled.json 生成
```

| Agent | Purpose |
|-------|---------|
| `adb-test-runner` | AI シナリオ実行、エビデンス収集 |
| `adb-test-evaluator` | 結果評価、レポート生成 |
| `scenario-compiler` | result.json → compiled.json 変換 |

複数シナリオがある場合、各シナリオを**独立したTaskとして実行**する。これにより：
- コンテキスト分離（シナリオ間の状態汚染を防止）
- エラー隔離（1シナリオの失敗が他に影響しない）
- 並列実行可能（独立したシナリオは同時実行可）

### Auto-Compilation Requirement (MUST)

**AI実行（adb-test-runner → adb-test-evaluator）を行った場合、必ず scenario-compiler を呼び出して compiled.json を自動生成すること。これはスキップ不可。**

以下のすべてのケースでコンパイルを実行する:

| ケース | コンパイル | 理由 |
|--------|-----------|------|
| compiled.json が存在しない（初回実行） | **MUST** | 次回以降の高速実行のため |
| source_hash 不一致（YAML変更後） | **MUST** | 最新のYAMLに対応するIRを生成 |
| `force-ai=true` 指定 | **MUST** | 明示的な再コンパイル要求 |
| compiled 実行が成功した場合 | 不要 | 既に最新のIRが存在 |

```
# AI実行後の必須フロー（省略禁止）
Task: adb-test-runner   → result.json 生成
Task: adb-test-evaluator → 結果評価
Task: scenario-compiler  → compiled.json 生成  ← これを絶対に省略しない
```

**注意**: evaluator でテストが失敗した場合でも、compiled.json は生成する。テスト結果とコンパイルは独立した処理である。

### Execution Modes

| Mode | Trigger | Speed | AI Calls | Cost |
|------|---------|-------|----------|------|
| Compiled (default) | compiled.json あり | 1-3s/step | UITree不足分のみ | $ |
| Compiled + skip-ai | `skip-ai=true` | 1-3s/step | None | $0 |
| AI full | compiled.json なし or `force-ai=true` | 5-15s/step | Every step | $$$ |

#### Verification Strategies (then) — Compiled Execution

| Strategy | Method | When | skip-ai | AI |
|----------|--------|------|---------|----|
| `strict_text_match` | UITreeテキスト検索 | 引用テキスト `「XX」` あり | Runs | No |
| `uitree_verify` | UITree指紋照合 | **コンパイル時デフォルト** | Runs | No |
| `screenshot_only` | スクショのみ | `verify: screenshot` 指定時 | Runs | No |
| `ai_checkpoint` | AI Vision | UITreeデータ不足 or `verify: ai` 指定時 | Skipped | Yes |

#### verify オプション（then ステップ用）

```yaml
# デフォルト: uitree_verify（コンパイル時にUITreeデータから自動生成）
# UITreeデータ不足の場合は ai_checkpoint にフォールバック

steps:
  - id: "確認"
    actions:
      - then: "ホーム画面が表示されていること"            # uitree_verify（デフォルト）
      - then: "複雑なUIが正しいこと"
        verify: ai                                        # 明示的にAI Vision検証
      - then: "画面遷移したこと"
        verify: screenshot                                # スクショのみ（検証なし）
```

詳細は [execution-flow.md](./references/execution-flow.md) を参照。

## ステップの書き方

### アクション（do）

| 種類 | 例 |
|------|-----|
| タップ | `「ログイン」ボタンをタップ`、`メニューを選択` |
| 入力 | `メールアドレス欄に「test@example.com」を入力` |
| スクロール | `下にスクロール`、`「Item 50」が見えるまでスクロール` |
| 戻る | `戻るボタンを押す`、`ホームに戻る` |
| 待機 | `3秒待つ` |
| アプリ | `アプリを起動`、`アプリを再起動` |

### 検証（then）

| 種類 | 例 |
|------|-----|
| 画面 | `ホーム画面が表示されていること` |
| 要素 | `「東京本社」と表示されていること` |
| 状態 | `チェックボックスがONになっていること` |
| 否定 | `エラーメッセージが表示されていないこと` |

### 厳格モード（strict）

通常はUITree指紋照合で検証するが、`strict: true` を指定するとUIツリーのテキスト完全一致で検証する。AI検証が必要な場合は `verify: ai` を指定する。

```yaml
# シナリオ全体に適用
config:
  strict: true

# または do/then 個別に適用
steps:
  - id: "拠点確認"
    actions:
      - do: "メニューを開く"
        strict: true  # このdoのみ厳格に要素特定
      - then: "「東京本社」と表示されていること"
        strict: true  # このthenのみ完全一致検証
```

| モード | 検証方法 | 用途 |
|--------|----------|------|
| 通常（デフォルト） | UITree指紋照合 | 画面状態のプログラム的検証 |
| 厳格 | UIツリー完全一致 | 正確な文字列表示の確認 |
| AI (`verify: ai`) | Vision API | 画面全体の雰囲気、複雑なUI |
| スクショ (`verify: screenshot`) | スクリーンショットのみ | エビデンス記録のみ |

**strictの優先順位**: 個別指定 > config.strict > false（デフォルト）

### セクションID（id）

テストをグループ化するための識別子。各セクションは `actions` リストを持つ：

```yaml
steps:
  - id: "ログイン"
    actions:
      - do: "..."
      - then: "..."

  - id: "データ確認"
    actions:
      - do: "..."
      - then: "..."
```

### リプレイ（replay）

過去のセクションの `do` アクションを再実行する。`then` はスキップされる。

```yaml
steps:
  - id: "ログイン"
    actions:
      - do: "アプリを起動"
      - do: "ログインボタンをタップ"
      - then: "ホーム画面が表示されていること"

  - id: "リプレイ確認"
    replay:
      from: "ログイン"
      to: "ログイン"    # 単一セクションの場合は同じID
    actions:
      - then: "再実行後も正常に動作すること"
```

| フィールド | 説明 |
|-----------|------|
| `from` | 開始セクションのID |
| `to` | 終了セクションのID（`from`と同じなら単一セクション） |

**注意**: リプレイ先に `replay` がある場合は再帰的に実行される。

## 内部処理

1. **UIツリー取得** - `adb shell uiautomator dump` で画面要素を取得
2. **要素特定** - 自然言語の説明からUI要素を自動特定
   - テキスト一致: 「ログイン」→ `text="ログイン"` の要素
   - content-desc一致: 「メニュー」→ 説明に "menu" を含む要素
3. **座標計算** - 要素の `bounds` から中心座標を算出
4. **コマンド実行** - `adb shell input tap x y` 等を実行
5. **検証** - スクリーンショット + Vision APIで期待結果を確認

## 出力

```
.adb-test/
└── results/
    └── <timestamp>/
        ├── summary.md           # 全体サマリー
        └── <scenario-name>/
            ├── report.md        # テストレポート
            ├── result.json      # 結果JSON
            ├── step_01.png      # スクリーンショット
            └── step_01_ui.xml   # UIツリー
```

## 前提条件

- ADBがインストールされていること
- Androidデバイス/エミュレータが接続されていること
- USBデバッグが有効であること

## 関連エージェント

- `adb-test-runner` - テスト実行とエビデンス収集
- `adb-test-evaluator` - 結果評価とレポート生成
- `scenario-compiler` - result.json → compiled.json 変換

## リファレンス

- [シナリオスキーマ](./references/scenario-schema.md)
- [ADBコマンド](./references/adb-commands.md)
- [出力フォーマット](./references/output-format.md)
- [環境チェック](./references/environment.md)
- [コンパイルIRスキーマ](./references/compile-ir-schema.md)
