# uiai-ios-test

iOS Simulator UIテスト自動化スキル。

## Overview

自然言語でテストシナリオを記述し、iOS SimulatorでUIテストを自動実行する。
Android版（uiai-android-test）と同じYAML形式のシナリオを使用可能。

## Prerequisites

### Xcode

```bash
# Xcodeがインストールされていることを確認
xcode-select -p
```

### Facebook IDB

```bash
# IDBのインストール
brew tap facebook/fb
brew install idb-companion
pip3 install fb-idb
```

### iOS Simulator

```bash
# 利用可能なシミュレータを確認
xcrun simctl list devices available

# シミュレータを起動
xcrun simctl boot <udid>
# または Simulator.app を開く
```

## Usage

```bash
# 基本的な使い方
/uiai-ios-test scenarios=test/scenarios/login.yaml

# 複数シナリオ
/uiai-ios-test scenarios=test/scenarios/*.yaml

# シミュレータ指定
/uiai-ios-test scenarios=test/scenarios/login.yaml simulator=<UDID>

# 起動中のシミュレータを使用
/uiai-ios-test scenarios=test/scenarios/login.yaml simulator=booted

# 厳格モード
/uiai-ios-test scenarios=test/scenarios/login.yaml strict=true
```

## Scenario Format

Android版と同じYAML形式を使用：

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
```

## Tool Stack

| Tool | Purpose |
|------|---------|
| `xcrun simctl` | Simulator management, app install, screenshots |
| `idb` (Facebook IDB) | UI operations (tap, swipe, text), UI tree retrieval |

## iOS-Specific Notes

### Back Navigation

iOSには汎用的な戻るボタンがないため、以下で対応：

| Scenario | Command |
|----------|---------|
| `左端からスワイプして戻る` | `idb ui swipe 0 400 300 400` |
| `「戻る」ボタンをタップ` | Navigation bar back button tap |

### UI Tree Format

Android（XML）とiOS（JSON）の属性マッピング：

| Android | iOS | Description |
|---------|-----|-------------|
| `text` | `AXLabel` | Display text |
| `resource-id` | `AXIdentifier` | Identifier |
| `content-desc` | `AXValue` | Value |
| `bounds` | `frame` | Position and size |

## Output

```
.ios-test/
└── results/
    └── <timestamp>/
        ├── summary.md
        └── <scenario-name>/
            ├── report.md
            ├── result.json
            ├── step_01.png
            └── step_01_ui.json
```

## References

- [SKILL.md](./SKILL.md) - Full skill documentation
- [simctl-commands.md](./references/simctl-commands.md) - xcrun simctl reference
- [idb-commands.md](./references/idb-commands.md) - Facebook IDB reference
- [scenario-schema.md](./references/scenario-schema.md) - Scenario YAML schema
- [environment.md](./references/environment.md) - Environment checks
- [execution-flow.md](./references/execution-flow.md) - Internal execution flow

## Related

- [uiai-android-test](../uiai-android-test/) - Android version
