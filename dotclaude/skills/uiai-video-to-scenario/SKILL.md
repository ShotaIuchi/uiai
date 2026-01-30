---
name: uiai-video-to-scenario
description: 画面録画動画からUIテストシナリオYAMLを自動生成するスキル。
argument-hint: "video=<path> [platform=android|ios|web] [output=<path>]"
arguments:
  - name: video
    description: 入力動画ファイル（mp4, mov, webm対応）
    required: true
    placeholder: "recordings/login.mp4"
  - name: platform
    description: 対象プラットフォーム
    required: false
    default: "android"
  - name: output
    description: 出力YAMLファイルパス
    required: false
    placeholder: "scenarios/generated.yaml"
references:
  - path: ./references/ffmpeg-extraction.md
  - path: ./references/vision-analysis.md
  - path: ./references/scenario-generation.md
  - path: ../uiai-android-test/references/scenario-schema.md
---

# uiai Video to Scenario

画面録画動画からUIテストシナリオYAMLを自動生成するスキル。

## 特徴

- **シーン検出** - ffmpegで画面変化のあるフレームのみを抽出
- **バッチ解析** - Claude Visionで複数フレームを一括解析
- **ドラフト出力** - レビューが必要な箇所に `[REVIEW]` マーカーを付与
- **長尺動画対応** - 2分超の動画は自動分割して処理

## 使用方法

```bash
# 基本使用
/uiai-video-to-scenario video=recordings/login.mp4

# プラットフォーム指定
/uiai-video-to-scenario video=recordings/ios-flow.mov platform=ios

# 出力先指定
/uiai-video-to-scenario video=recordings/test.mp4 output=scenarios/my-test.yaml
```

## パラメータ

| パラメータ | 必須 | デフォルト | 説明 |
|-----------|------|-----------|------|
| `video` | Yes | - | 入力動画ファイルパス |
| `platform` | No | `android` | 対象プラットフォーム（android, ios, web） |
| `output` | No | 自動生成 | 出力YAMLファイルパス |

## 対応形式

| 拡張子 | 対応 |
|--------|------|
| `.mp4` | ✅ |
| `.mov` | ✅ |
| `.webm` | ✅ |
| `.avi` | ✅ |
| `.mkv` | ✅ |

## 処理フロー

```
[動画入力]
    ↓
[1. フレーム抽出] ffmpeg scene detection (閾値0.3)
    ↓ frames/*.png (10-20枚程度)
[2. 画像解析] Claude Vision API (8フレーム/バッチ)
    ↓ analysis.json
[3. シナリオ生成] YAML出力 + [REVIEW]マーカー
    ↓
[出力: scenario.yaml]
```

## 出力例

```yaml
name: "Generated - login.mp4"
app:
  android: "TODO: Set package name"
  ios: "TODO: Set bundle identifier"

steps:
  - id: "起動"
    actions:
      - do: "アプリを起動"
      - then: "ログイン画面が表示されていること"

  - id: "ログイン"
    actions:
      - do: "メールアドレス欄に「test@example.com」を入力"
      - do: "パスワード欄に入力"  # [REVIEW] password obscured
      - do: "「ログイン」ボタンをタップ"
      - then: "ホーム画面が表示されていること"
```

## 出力ディレクトリ

```
.video-to-scenario/
└── <video-name>/
    ├── frames/           # 抽出フレーム
    │   ├── frame_0001.png
    │   ├── frame_0002.png
    │   └── ...
    ├── analysis.json     # 解析結果
    └── scenario.yaml     # 生成シナリオ
```

## [REVIEW] マーカー

以下の場合に `[REVIEW]` マーカーが付与される：

| 状況 | 例 |
|------|-----|
| パスワード入力 | `# [REVIEW] password obscured` |
| 不明確な操作 | `# [REVIEW] unclear action` |
| 推測要素 | `# [REVIEW] element name guessed` |
| 画面遷移不明 | `# [REVIEW] transition unclear` |

## 長尺動画の処理

2分を超える動画は自動的に分割処理される：

1. 2分ごとにセグメント分割
2. 各セグメントを個別に処理
3. 最後に結果を結合

## 前提条件

- ffmpegがインストールされていること

```bash
# ffmpegのインストール
brew install ffmpeg
```

## 関連エージェント

- `video-frame-extractor` - ffmpegによるフレーム抽出
- `video-frame-analyzer` - Claude Visionによる画像解析
- `video-scenario-generator` - YAMLシナリオ生成

## 関連スキル

- `uiai-scenario-check` - 生成されたシナリオの検証・修正
- `uiai-android-test` - Androidでのシナリオ実行
- `uiai-ios-test` - iOSでのシナリオ実行
- `uiai-web-test` - Webでのシナリオ実行

## リファレンス

- [ffmpeg抽出コマンド](./references/ffmpeg-extraction.md)
- [Vision解析プロンプト](./references/vision-analysis.md)
- [シナリオ生成ルール](./references/scenario-generation.md)
- [シナリオスキーマ](../uiai-android-test/references/scenario-schema.md)
