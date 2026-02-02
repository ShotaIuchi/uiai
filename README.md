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
| `uiai-video-to-scenario` | 画面録画動画からシナリオYAMLを自動生成 |
| `uiai-scenario-check` | シナリオYAMLの検証・自動修正 |
| `uiai-create` | 対話形式で新しいスキルを作成 |

## シナリオ例

### 基本的なシナリオ

```yaml
name: "ログインテスト"
app:
  android: "com.example.app"
  ios: "com.example.App"
  web: "https://example.com"

variables:
  email: "test@example.com"
  password: "password123"

steps:
  - id: "起動"
    actions:
      - do: "アプリを起動"
      - then: "ログイン画面が表示されていること"

  - id: "ログイン"
    actions:
      - do: "メールアドレス欄に「(email)」を入力"
      - do: "パスワード欄に「(password)」を入力"
      - do: "「ログイン」ボタンをタップ"
      - then: "ホーム画面が表示されていること"
```

### 高度なシナリオ

```yaml
name: "拠点切り替えテスト"
app:
  android: "com.example.app"
  ios: "com.example.App"

variables:
  # 通常の変数
  office: "東京本社"
  # プレースホルダー変数（実行時に入力）
  password:

config:
  strict: true  # 全体で厳格モードを有効化

steps:
  - id: "ログイン"
    actions:
      - do: "アプリを起動"
      - do: "パスワード欄に「(password)」を入力"
      - do: "「ログイン」ボタンをタップ"
      - then: "ホーム画面が表示されていること"

  - id: "拠点選択"
    actions:
      - do: "メニューをタップ"
      - do: "「拠点切り替え」を選択"
      - do: "「(office)」をタップ"
      - then: "「(office)」と表示されていること"

  - id: "再ログイン確認"
    replay:
      from: "ログイン"
      to: "ログイン"
    actions:
      - then: "ホーム画面が表示されていること"
        strict: false  # この検証のみ通常モード
```

## シナリオ機能

### variables（変数）

シナリオ内で再利用する値を定義する。`(variable_name)` 構文で参照可能。

```yaml
variables:
  email: "test@example.com"
  password: "password123"

steps:
  - id: "ログイン"
    actions:
      - do: "メールアドレス欄に「(email)」を入力"
```

### 対話式入力（プレースホルダー変数）

変数の値を省略または `null` にすると、テスト実行前に対話式で入力を求められる。

```yaml
variables:
  email: "test@example.com"  # 固定値
  password:                  # 実行時に入力
  api_key: null              # 実行時に入力（明示的）
  secret:
    prompt: "シークレットを入力"  # カスタムプロンプト
```

CI環境などの非対話式環境では、プレースホルダー変数を含むテストはスキップされる。

### strict（厳格モード）

`strict: true` を指定すると、UIツリー/DOMのテキストで完全一致検証を行う。

```yaml
config:
  strict: true  # シナリオ全体に適用

steps:
  - id: "確認"
    actions:
      - then: "「東京本社」と表示されていること"
        strict: true  # この検証のみ厳格モード
```

- 通常モード: Vision APIで意味的に判定（柔軟）
- 厳格モード: テキスト完全一致で判定（厳密）

### replay（再実行）

過去のセクションの `do` アクションを再実行する。`then` はスキップされる。

```yaml
steps:
  - id: "ログイン"
    actions:
      - do: "ログインボタンをタップ"
      - then: "ホーム画面が表示されていること"

  - id: "再確認"
    replay:
      from: "ログイン"
      to: "ログイン"
    actions:
      - then: "画面が正しく表示されていること"
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

### 動画からシナリオ生成

```bash
# 画面録画からシナリオを自動生成
/uiai-video-to-scenario video=recordings/login.mp4

# プラットフォーム指定
/uiai-video-to-scenario video=recordings/ios-flow.mov platform=ios

# 出力先指定
/uiai-video-to-scenario video=recordings/test.mp4 output=scenarios/my-test.yaml
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

### 動画からシナリオ生成

- ffmpegがインストールされていること

```bash
# ffmpegのインストール
brew install ffmpeg
```

## 推奨ツール

### amu（シンボリックリンク管理）

[amu](https://github.com/ShotaIuchi/amu)を使用すると、`dotclaude/`ディレクトリの管理が容易になります。

```bash
# インストール
brew install ShotaIuchi/tap/amu

# dotclaudeを~/.claudeにリンク
amu add dotclaude ~/.claude
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
│   ├── uiai-video-to-scenario/  # 動画→シナリオ生成
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
│       ├── web-test-evaluator.md
│       ├── video-frame-extractor.md
│       ├── video-frame-analyzer.md
│       └── video-scenario-generator.md
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

### 動画→シナリオ生成

```
.video-to-scenario/
└── <video-name>/
    ├── frames/              # 抽出フレーム
    │   ├── frame_0001.png
    │   ├── frame_0002.png
    │   └── ...
    ├── extraction_info.json # 抽出情報
    ├── timestamps.jsonl     # タイムスタンプ
    ├── analysis.json        # 解析結果
    └── scenario.yaml        # 生成シナリオ
```

## ライセンス

MIT
