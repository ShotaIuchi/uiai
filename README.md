# uiai

AI駆動のクロスプラットフォームUIテスト自動化ツール。自然言語でテストシナリオを記述し、Claude Visionで結果を検証する。

## 特徴

- **自然言語シナリオ** - リソースID不要、日本語でアクションと期待結果を記述
- **自動要素特定** - UIツリーから自動的にタップ位置を判定
- **Vision検証** - スクリーンショットを解析して期待結果を自然言語で検証
- **厳格モード** - UIツリーのテキスト完全一致で厳密に検証可能

## 対応プラットフォーム

| プラットフォーム | ステータス | スキル名 |
|-----------------|-----------|---------|
| Android | ✅ 対応 | `uiai-android-test` |
| iOS | ✅ 対応 | `uiai-ios-test` |
| Web | ✅ 対応 | `uiai-web-test` |

## ユーティリティスキル

| スキル名 | 説明 |
|---------|------|
| `uiai-scenario-check` | シナリオYAMLの検証・自動修正 |
| `uiai-create` | 対話形式で新しいスキルを作成 |

## シナリオ例

```yaml
name: "ログインテスト"
app:
  android: "com.example.app"
  ios: "com.example.App"
  web: "https://example.com"

steps:
  - id: "起動"
    actions:
      - do: "アプリを起動"
      - then: "ログイン画面が表示されていること"

  - id: "ログイン"
    actions:
      - do: "メールアドレス欄に「test@example.com」を入力"
      - do: "パスワード欄に「password123」を入力"
      - do: "「ログイン」ボタンをタップ"
      - then: "ホーム画面が表示されていること"
```

## 使用方法

### Android

```bash
# Claude Code内で実行
/uiai-android-test scenarios=test/scenarios/login.yaml

# 複数シナリオ
/uiai-android-test scenarios=test/scenarios/*.yaml

# デバイス指定
/uiai-android-test scenarios=test/scenarios/login.yaml device=emulator-5554
```

### iOS

```bash
# Claude Code内で実行
/uiai-ios-test scenarios=test/scenarios/login.yaml

# 複数シナリオ
/uiai-ios-test scenarios=test/scenarios/*.yaml

# シミュレータ指定
/uiai-ios-test scenarios=test/scenarios/login.yaml simulator=<UDID>

# 起動中のシミュレータを使用
/uiai-ios-test scenarios=test/scenarios/login.yaml simulator=booted
```

### Web

```bash
# Claude Code内で実行
/uiai-web-test scenarios=test/scenarios/login.yaml

# 複数シナリオ
/uiai-web-test scenarios=test/scenarios/*.yaml

# ブラウザ指定
/uiai-web-test scenarios=test/scenarios/login.yaml browser=firefox

# ヘッドレスモード無効（ブラウザ表示）
/uiai-web-test scenarios=test/scenarios/login.yaml headless=false
```

### シナリオ検証

```bash
# シナリオYAMLの検証
/uiai-scenario-check scenarios=test/scenarios/login.yaml

# 自動修正（ドライラン）
/uiai-scenario-check scenarios=test/scenarios/*.yaml fix=true dry-run=true

# 自動修正（実行）
/uiai-scenario-check scenarios=test/scenarios/*.yaml fix=true
```

### スキル作成

```bash
# 対話形式で新しいスキルを作成
/uiai-create

# スキル名を指定して開始
/uiai-create name=uiai-web-test
```

## 前提条件

### Android

- ADBがインストールされていること
- Androidデバイス/エミュレータが接続されていること
- USBデバッグが有効であること

### iOS

- Xcodeがインストールされていること
- iOS Simulatorが利用可能であること
- Facebook IDBがインストールされていること

```bash
# IDBのインストール
brew tap facebook/fb
brew install idb-companion
pip3 install fb-idb
```

### Web

- Node.js v16以上がインストールされていること
- Playwrightがインストールされていること

```bash
# Playwrightのインストール
npm install -D playwright
npx playwright install
```

## ディレクトリ構造

```
dotclaude/
├── skills/
│   ├── uiai-android-test/     # Androidテストスキル
│   │   ├── SKILL.md
│   │   └── references/
│   ├── uiai-ios-test/         # iOSテストスキル
│   │   ├── SKILL.md
│   │   └── references/
│   ├── uiai-web-test/         # Webテストスキル
│   │   ├── SKILL.md
│   │   └── references/
│   ├── uiai-scenario-check/   # シナリオ検証スキル
│   │   ├── SKILL.md
│   │   └── references/
│   └── uiai-create/           # スキル作成ウィザード
│       ├── SKILL.md
│       └── references/
├── agents/
│   └── task/
│       ├── adb-test-runner.md
│       ├── adb-test-evaluator.md
│       ├── ios-test-runner.md
│       ├── ios-test-evaluator.md
│       ├── web-test-runner.md
│       └── web-test-evaluator.md
└── rules/
```

## 出力

### Android

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

### iOS

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

### Web

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
            ├── step_01_dom.html    # DOMスナップショット
            └── step_01_a11y.json   # アクセシビリティツリー
```

## ライセンス

MIT
