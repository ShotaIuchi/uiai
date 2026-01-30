# uiai-video-to-scenario

画面録画動画からUIテストシナリオYAMLを自動生成するスキル。

## 概要

アプリの画面録画動画を入力として、UIテスト用のYAMLシナリオを自動生成します。ffmpegによるシーン検出でキーフレームを抽出し、Claude Visionで画像解析を行い、テストシナリオに変換します。

## 特徴

- **シーン検出**: ffmpegで画面変化のあるフレームのみを抽出（60秒→10-20フレーム程度）
- **バッチ解析**: Claude Visionで複数フレームを一括解析（8フレーム/バッチ）
- **ドラフト出力**: レビューが必要な箇所に `[REVIEW]` マーカーを付与
- **長尺動画対応**: 2分超の動画は自動分割して処理

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
| `video` | Yes | - | 入力動画ファイルパス（mp4, mov, webm等） |
| `platform` | No | `android` | 対象プラットフォーム（android, ios, web） |
| `output` | No | 自動生成 | 出力YAMLファイルパス |

## 処理フロー

1. **フレーム抽出**: ffmpegのシーン検出（閾値0.3）でキーフレームを抽出
2. **画像解析**: Claude Visionで各フレームを解析し、操作を識別
3. **シナリオ生成**: 解析結果をYAML形式のテストシナリオに変換

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

## [REVIEW] マーカー

以下の場合に `[REVIEW]` マーカーが自動付与されます：

- パスワード入力の検出
- 不明確な操作
- 推測されたUI要素名
- 不明確な画面遷移

## 前提条件

- ffmpegがインストールされていること

```bash
brew install ffmpeg
```

## 関連スキル

- `/uiai-scenario-check` - 生成されたシナリオの検証・修正
- `/uiai-android-test` - Androidでのシナリオ実行
- `/uiai-ios-test` - iOSでのシナリオ実行
- `/uiai-web-test` - Webでのシナリオ実行

## 出力ディレクトリ

```
.video-to-scenario/
└── <video-name>/
    ├── frames/           # 抽出フレーム
    ├── analysis.json     # 解析結果
    └── scenario.yaml     # 生成シナリオ
```
