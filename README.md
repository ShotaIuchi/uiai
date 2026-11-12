# uiai

AI駆動のクロスプラットフォームUIテスト自動化ツール。自然言語でテストシナリオを記述し、Claude Visionで結果を検証する。

## 特徴

- **自然言語シナリオ** - リソースID不要、日本語でアクションと期待結果を記述
- **自動要素特定** - UIツリーから自動的にタップ位置を判定
- **Vision検証** - スクリーンショットを解析して期待結果を自然言語で検証
- **厳格モード** - UIツリーのテキスト完全一致で厳密に検証可能

## 対応プラットフォーム

| プラットフォーム | ステータス | コマンド |
|-----------------|-----------|---------|
| Android | ✅ 対応 | `/uiai:android-test` |
| iOS | ✅ 対応 | `/uiai:ios-test` |
| Web | ✅ 対応 | `/uiai:web-test` |

## ユーティリティスキル

| コマンド | 説明 |
|---------|------|
| `/uiai:record-to-scenario` | 端末を操作しながら録画し、その録画からシナリオYAMLを自動生成（Android） |
| `/uiai:video-to-scenario` | 画面録画動画からシナリオYAMLを自動生成 |
| `/uiai:scenario-check` | シナリオYAMLの検証・自動修正 |
| `/uiai:create` | 対話形式で新しいスキルを作成 |

## インストール

uiai は Claude Code プラグインとして配布している。

```bash
# Claude Code 内で実行
/plugin marketplace add ShotaIuchi/uiai
/plugin install uiai@uiai
```

ローカルのチェックアウトをそのまま読み込む場合（開発時）:

```bash
claude --plugin-dir /path/to/uiai
```

> 旧方式（amu で `dotclaude/` を `~/.claude` にリンク）で導入済みの場合は、
> `~/.claude/skills/uiai-*` と `~/.claude/agents/task/` 配下の uiai エージェントのリンクを削除すること。
> 残したままだとスキルが二重に読み込まれる。

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
/uiai:android-test scenarios=test/scenarios/login.yaml

# 複数シナリオ
/uiai:android-test scenarios=test/scenarios/*.yaml

# デバイス指定
/uiai:android-test scenarios=test/scenarios/login.yaml device=emulator-5554
```

### iOS

```bash
# Claude Code内で実行
/uiai:ios-test scenarios=test/scenarios/login.yaml

# 複数シナリオ
/uiai:ios-test scenarios=test/scenarios/*.yaml

# シミュレータ指定
/uiai:ios-test scenarios=test/scenarios/login.yaml simulator=<UDID>

# 起動中のシミュレータを使用
/uiai:ios-test scenarios=test/scenarios/login.yaml simulator=booted
```

### Web

```bash
# Claude Code内で実行
/uiai:web-test scenarios=test/scenarios/login.yaml

# 複数シナリオ
/uiai:web-test scenarios=test/scenarios/*.yaml

# ブラウザ指定
/uiai:web-test scenarios=test/scenarios/login.yaml browser=firefox

# ヘッドレスモード無効（ブラウザ表示）
/uiai:web-test scenarios=test/scenarios/login.yaml headless=false
```

### シナリオ検証

```bash
# シナリオYAMLの検証
/uiai:scenario-check scenarios=test/scenarios/login.yaml

# 自動修正（ドライラン）
/uiai:scenario-check scenarios=test/scenarios/*.yaml fix=true dry-run=true

# 自動修正（実行）
/uiai:scenario-check scenarios=test/scenarios/*.yaml fix=true
```

### スキル作成

```bash
# 対話形式で新しいスキルを作成
/uiai:create

# スキル名を指定して開始
/uiai:create name=selenium-test
```

### 動画からシナリオ生成

```bash
# 画面録画からシナリオを自動生成
/uiai:video-to-scenario video=recordings/login.mp4

# プラットフォーム指定
/uiai:video-to-scenario video=recordings/ios-flow.mov platform=ios

# 出力先指定
/uiai:video-to-scenario video=recordings/test.mp4 output=scenarios/my-test.yaml
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

## ディレクトリ構造

```
.
├── .claude-plugin/
│   ├── plugin.json            # プラグインマニフェスト
│   └── marketplace.json       # マーケットプレイス定義（/plugin marketplace add 用）
├── skills/                    # /uiai:<skill-name> で呼び出し
│   ├── android-test/          # Androidテストスキル
│   ├── ios-test/              # iOSテストスキル
│   ├── web-test/              # Webテストスキル
│   ├── scenario-check/        # シナリオ検証スキル
│   ├── video-to-scenario/     # 動画→シナリオ生成
│   ├── record-to-scenario/    # 録画→シナリオ生成
│   └── create/                # スキル作成ウィザード
├── agents/                    # uiai:<agent-name> として登録されるサブエージェント
│   ├── adb-test-runner.md
│   ├── adb-test-evaluator.md
│   ├── ios-test-runner.md
│   ├── ios-test-evaluator.md
│   ├── web-test-runner.md
│   ├── web-test-evaluator.md
│   ├── scenario-compiler.md
│   ├── video-frame-extractor.md
│   ├── video-frame-analyzer.md
│   └── video-scenario-generator.md
└── scripts/                   # Compiled Runner（${CLAUDE_PLUGIN_ROOT}/scripts から参照）
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
