---
name: uiai-ios-test
description: iOS Simulator UIテスト自動化スキル。自然言語でシナリオを記述し、スクリーンショットとUIツリーで結果を評価する。
argument-hint: "scenarios=<path> [simulator=<udid>] [strict=true]"
arguments:
  - name: scenarios
    description: テストシナリオYAMLファイル（glob対応）
    required: true
    placeholder: "test/scenarios/*.yaml"
  - name: simulator
    description: 対象シミュレータUDID（xcrun simctl list で確認）
    required: false
    placeholder: "booted"
  - name: strict
    description: 全ステップで厳格モード（UIツリー完全一致検証）
    required: false
    default: "false"
references:
  - path: ./references/simctl-commands.md
  - path: ./references/idb-commands.md
  - path: ./references/scenario-schema.md
  - path: ./references/environment.md
  - path: ./references/execution-flow.md
---

# uiai iOS Test

自然言語でテストシナリオを記述し、iOS SimulatorでUIテストを自動実行するスキル。

## 特徴

- **自然言語シナリオ** - リソースID不要、日本語でアクションを記述
- **自動要素特定** - UIツリー（JSON）から自動的にタップ位置を判定
- **Vision検証** - Claude Visionで期待結果を自然言語で検証
- **厳格モード** - UIツリーのテキスト完全一致で厳密に検証可能
- **Android版と共通シナリオ** - 同じYAML形式を使用可能

## ツール構成

| ツール | 用途 |
|--------|------|
| `xcrun simctl` | シミュレータ起動、アプリインストール、スクリーンショット |
| `idb` (Facebook IDB) | タップ、スワイプ、テキスト入力、UI要素取得 |

## シナリオ形式

```yaml
name: "ログインテスト"
app:
  android: "com.example.app"
  ios: "com.example.App"

steps:
  - id: "起動"
    actions:
      - do: "アプリを起動"
      - then: "ホーム画面が表示されていること"

  - id: "ログイン"
    actions:
      - do: "「ログイン」をタップ"
      - do: "メールアドレス欄に「test@example.com」を入力"
      - do: "「送信」ボタンをタップ"
      - then: "ダッシュボード画面が表示されていること"
        strict: true   # この検証のみ完全一致
```

## 使用方法

```bash
# テスト実行
/uiai-ios-test scenarios=test/scenarios/login.yaml

# 複数シナリオ
/uiai-ios-test scenarios=test/scenarios/*.yaml

# シミュレータ指定
/uiai-ios-test scenarios=test/scenarios/login.yaml simulator=<UDID>

# 起動中のシミュレータを使用
/uiai-ios-test scenarios=test/scenarios/login.yaml simulator=booted

# 厳格モード（全ステップで完全一致検証）
/uiai-ios-test scenarios=test/scenarios/login.yaml strict=true
```

## ステップの書き方

### アクション（do）

| 種類 | 例 |
|------|-----|
| タップ | `「ログイン」ボタンをタップ`、`メニューを選択` |
| 入力 | `メールアドレス欄に「test@example.com」を入力` |
| スクロール | `下にスクロール`、`「Item 50」が見えるまでスクロール` |
| 戻る | `左端からスワイプして戻る`、`「戻る」ボタンをタップ` |
| 待機 | `3秒待つ` |
| アプリ | `アプリを起動`、`アプリを再起動` |

### 検証（then）

| 種類 | 例 |
|------|-----|
| 画面 | `ホーム画面が表示されていること` |
| 要素 | `「東京本社」と表示されていること` |
| 状態 | `スイッチがONになっていること` |
| 否定 | `エラーメッセージが表示されていないこと` |

### 厳格モード（strict）

通常はVision APIで「意味的に」検証するが、`strict: true` を指定するとUIツリーのテキスト完全一致で検証する。

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
| 通常（デフォルト） | Vision API | 画面全体の雰囲気、複雑なUI |
| 厳格 | UIツリー完全一致 | 正確な文字列表示の確認 |

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

## iOS固有の注意事項

### 「戻る」操作

iOSには汎用的な戻るボタンがないため、以下の方法で対応：

| シナリオ記述 | 実行される操作 |
|-------------|---------------|
| `左端からスワイプして戻る` | `idb ui swipe 0 400 300 400` |
| `「戻る」ボタンをタップ` | ナビゲーションバーの戻るボタンをタップ |
| `「<」ボタンをタップ` | 戻るボタンをタップ |

### Bundle Identifier

Android の package name と同じ形式（例: `com.example.App`）。
Xcode プロジェクトの Bundle Identifier を使用する。

## 内部処理

1. **UIツリー取得** - `idb ui describe-all` でJSON形式の画面要素を取得
2. **要素特定** - 自然言語の説明からUI要素を自動特定
   - AXLabel一致: 「ログイン」→ `AXLabel="ログイン"` の要素
   - AXIdentifier一致: 「メニュー」→ 識別子に "menu" を含む要素
3. **座標計算** - 要素の `frame` から中心座標を算出
4. **コマンド実行** - `idb ui tap x y` 等を実行
5. **検証** - スクリーンショット + Vision APIで期待結果を確認

## 出力

```
.ios-test/
└── results/
    └── <timestamp>/
        ├── summary.md           # 全体サマリー
        └── <scenario-name>/
            ├── report.md        # テストレポート
            ├── result.json      # 結果JSON
            ├── step_01.png      # スクリーンショット
            └── step_01_ui.json  # UIツリー
```

## 前提条件

- Xcode がインストールされていること
- iOS Simulator が利用可能であること
- Facebook IDB がインストールされていること

```bash
# IDBのインストール
brew tap facebook/fb
brew install idb-companion
pip3 install fb-idb
```

## 関連エージェント

- `ios-test-runner` - テスト実行とエビデンス収集
- `ios-test-evaluator` - 結果評価とレポート生成

## リファレンス

- [シナリオスキーマ](./references/scenario-schema.md)
- [simctlコマンド](./references/simctl-commands.md)
- [IDBコマンド](./references/idb-commands.md)
- [環境チェック](./references/environment.md)
- [実行フロー](./references/execution-flow.md)
