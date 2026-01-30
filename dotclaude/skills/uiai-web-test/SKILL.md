---
name: uiai-web-test
description: Playwrightを使用したWeb UIテスト自動化スキル。自然言語でシナリオを記述し、スクリーンショットとDOM解析で結果を評価する。
argument-hint: "scenarios=<path> [browser=chromium] [headless=true] [strict=true]"
arguments:
  - name: scenarios
    description: テストシナリオYAMLファイル（glob対応）
    required: true
    placeholder: "test/scenarios/*.yaml"
  - name: browser
    description: 使用ブラウザ（chromium, firefox, webkit）
    required: false
    default: "chromium"
  - name: headless
    description: ヘッドレスモードで実行
    required: false
    default: "true"
  - name: strict
    description: 全ステップで厳格モード（DOM完全一致検証）
    required: false
    default: "false"
references:
  - path: ./references/playwright-commands.md
  - path: ./references/scenario-schema.md
  - path: ./references/environment.md
  - path: ./references/execution-flow.md
---

# uiai Web Test

自然言語でテストシナリオを記述し、PlaywrightでWebアプリケーションのUIテストを自動実行するスキル。

## 特徴

- **自然言語シナリオ** - セレクタ不要、日本語でアクションを記述
- **自動要素特定** - アクセシビリティツリーから自動的にクリック位置を判定
- **Vision検証** - Claude Visionで期待結果を自然言語で検証
- **厳格モード** - DOMのテキスト完全一致で厳密に検証可能
- **マルチブラウザ** - Chromium, Firefox, WebKit対応

## シナリオ形式

```yaml
name: "ログインテスト"
app:
  android: "com.example.app"
  ios: "com.example.App"
  web: "https://example.com"

steps:
  - id: "ログイン"
    actions:
      - do: "Open /login page"
      - do: "Enter 'test@example.com' in email field"
      - do: "Enter 'password123' in password field"
      - do: "Click 'Login' button"
      - then: "Dashboard is displayed"
        strict: true
```

## 使用方法

```bash
# テスト実行
/uiai-web-test scenarios=test/scenarios/login.yaml

# 複数シナリオ
/uiai-web-test scenarios=test/scenarios/*.yaml

# ブラウザ指定
/uiai-web-test scenarios=test/scenarios/login.yaml browser=firefox

# ヘッドレスモード無効（ブラウザ表示）
/uiai-web-test scenarios=test/scenarios/login.yaml headless=false

# 厳格モード（全ステップで完全一致検証）
/uiai-web-test scenarios=test/scenarios/login.yaml strict=true
```

## ステップの書き方

### アクション（do）

| 種類 | 例 |
|------|-----|
| ナビゲーション | `Open https://example.com`、`Go to /dashboard` |
| クリック | `Click 'Login' button`、`Click the submit link` |
| 入力 | `Enter 'test@example.com' in email field` |
| 選択 | `Select 'Japan' from country dropdown` |
| スクロール | `Scroll down`、`Scroll to 'Contact' section` |
| 待機 | `Wait 3 seconds` |
| リフレッシュ | `Refresh the page` |

### 検証（then）

| 種類 | 例 |
|------|-----|
| 画面 | `Dashboard is displayed` |
| 要素 | `'Welcome, John' is visible` |
| URL | `URL contains '/dashboard'` |
| 状態 | `Checkbox is checked` |
| 否定 | `Error message is not displayed` |

### 厳格モード（strict）

通常はVision APIで「意味的に」検証するが、`strict: true` を指定するとDOMのテキスト完全一致で検証する。

```yaml
# シナリオ全体に適用
config:
  strict: true

# または do/then 個別に適用
steps:
  - id: "確認"
    actions:
      - do: "Click 'Submit' button"
        strict: true  # このdoのみ厳格に要素特定
      - then: "'Order confirmed' is displayed"
        strict: true  # このthenのみ完全一致検証
```

| モード | 検証方法 | 用途 |
|--------|----------|------|
| 通常（デフォルト） | Vision API | 画面全体の雰囲気、複雑なUI |
| 厳格 | DOM完全一致 | 正確な文字列表示の確認 |

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
      - do: "Open /login"
      - do: "Click 'Login' button"
      - then: "Dashboard is displayed"

  - id: "リプレイ確認"
    replay:
      from: "ログイン"
      to: "ログイン"
    actions:
      - then: "再実行後も正常に動作すること"
```

| フィールド | 説明 |
|-----------|------|
| `from` | 開始セクションのID |
| `to` | 終了セクションのID（`from`と同じなら単一セクション） |

**注意**: リプレイ先に `replay` がある場合は再帰的に実行される。

## Web固有の注意事項

### ナビゲーション

| シナリオ記述 | 実行される操作 |
|-------------|---------------|
| `Open https://example.com` | `page.goto('https://example.com')` |
| `Go to /dashboard` | `page.goto(baseUrl + '/dashboard')` |
| `Refresh the page` | `page.reload()` |
| `Go back` | `page.goBack()` |

### 要素特定

PlaywrightはアクセシビリティツリーとDOMを使用して要素を特定：

| 優先順位 | 特定方法 | 例 |
|----------|----------|-----|
| 1 | ロール + テキスト | `getByRole('button', { name: 'Submit' })` |
| 2 | ラベル | `getByLabel('Email')` |
| 3 | プレースホルダー | `getByPlaceholder('Enter email')` |
| 4 | テキスト | `getByText('Login')` |
| 5 | テストID | `getByTestId('submit-btn')` |

### 待機処理

Playwrightは自動待機が組み込まれているため、多くの場合明示的な待機は不要：

```yaml
# 自動待機される操作
- do: "Click 'Submit' button"  # 要素が表示されるまで自動待機

# 明示的な待機が必要な場合
- do: "Wait 3 seconds"         # 固定時間待機
- do: "Wait for loading to finish"  # ローディング完了を待機
```

## 内部処理

1. **ページ取得** - `page.goto(url)` でページを開く
2. **要素特定** - 自然言語の説明からUI要素を自動特定
   - テキスト一致: 「Login」→ `getByText('Login')` または `getByRole('button', { name: 'Login' })`
   - ラベル一致: 「email field」→ `getByLabel('email')` または `getByPlaceholder('email')`
3. **アクション実行** - `click()`, `fill()`, `selectOption()` 等を実行
4. **検証** - スクリーンショット + Vision APIで期待結果を確認

## 出力

```
.web-test/
└── results/
    └── <timestamp>/
        ├── summary.md           # 全体サマリー
        └── <scenario-name>/
            ├── report.md        # テストレポート
            ├── result.json      # 結果JSON
            ├── step_01_before.png  # スクリーンショット（実行前）
            ├── step_01_after.png   # スクリーンショット（実行後）
            ├── step_01_dom.html    # DOM スナップショット
            └── step_01_a11y.json   # アクセシビリティツリー
```

## 前提条件

- Node.js がインストールされていること（v16以上推奨）
- Playwright がインストールされていること

```bash
# Playwrightのインストール
npm install -D playwright

# ブラウザのインストール
npx playwright install
```

## 関連エージェント

- `web-test-runner` - テスト実行とエビデンス収集
- `web-test-evaluator` - 結果評価とレポート生成

## リファレンス

- [シナリオスキーマ](./references/scenario-schema.md)
- [Playwrightコマンド](./references/playwright-commands.md)
- [環境チェック](./references/environment.md)
- [実行フロー](./references/execution-flow.md)
