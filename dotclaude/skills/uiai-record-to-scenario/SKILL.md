---
name: uiai-record-to-scenario
description: 端末を操作しながら画面録画し、その録画からUIテストシナリオYAMLを自動生成する一体型スキル。録画開始→手動操作→停止→シナリオ生成までを一括実行する。現状はAndroid（adb）のみ対応。
argument-hint: "[platform=android] [output=<path>] [duration=<sec>] [device=<serial>]"
arguments:
  - name: platform
    description: 対象プラットフォーム（現状 android のみ対応。ios/web は今後対応予定）
    required: false
    default: "android"
  - name: output
    description: 出力YAMLファイルパス
    required: false
    placeholder: "scenarios/recorded.yaml"
  - name: duration
    description: 録画の上限秒数（screenrecord の上限は180秒）
    required: false
    default: "180"
  - name: device
    description: 対象デバイスのシリアル（複数デバイス接続時に指定）
    required: false
    placeholder: "emulator-5554"
references:
  - path: ./references/recording.md
  - path: ../uiai-video-to-scenario/references/ffmpeg-extraction.md
  - path: ../uiai-video-to-scenario/references/vision-analysis.md
  - path: ../uiai-video-to-scenario/references/scenario-generation.md
  - path: ../uiai-android-test/references/scenario-schema.md
  - path: ../uiai-android-test/references/adb-commands.md
---

# uiai Record to Scenario

端末を**実際に操作しながら画面録画**し、その録画から自動でUIテストシナリオYAMLを生成する一体型スキル。

`uiai-video-to-scenario` が「既に手元にある動画ファイル」を入力にするのに対し、本スキルは
**録画そのものをスキル内で開始・停止**し、生成された動画をそのまま解析フローへ流す。
「操作して見せれば、そのままテストシナリオになる」という record & generate 体験を提供する。

## 特徴

- **対話的な録画制御** - 録画を開始し、ユーザーの操作完了を待って停止
- **解析は既存資産を再利用** - フレーム抽出・Vision解析・YAML生成は `uiai-video-to-scenario` のエージェントを流用
- **ドラフト出力** - レビューが必要な箇所に `[REVIEW]` マーカーを付与
- **クリーンアップ** - 端末上の一時録画ファイルは自動削除

## 使用方法

```bash
# 基本使用（Android）
/uiai-record-to-scenario

# 出力先を指定
/uiai-record-to-scenario output=scenarios/login.yaml

# 録画上限を60秒に
/uiai-record-to-scenario duration=60

# 複数デバイス接続時はシリアルを指定
/uiai-record-to-scenario device=emulator-5554
```

## パラメータ

| パラメータ | 必須 | デフォルト | 説明 |
|-----------|------|-----------|------|
| `platform` | No | `android` | 対象プラットフォーム（現状 android のみ） |
| `output` | No | 自動生成 | 出力YAMLファイルパス |
| `duration` | No | `180` | 録画上限秒数（screenrecord の上限180秒） |
| `device` | No | - | デバイスシリアル（複数接続時） |

## 処理フロー

```
[前提確認] adb / 接続デバイス / platform=android
    ↓
[1. 録画開始] adb shell screenrecord（バックグラウンド）
    ↓ ユーザーが端末を手動操作
[2. 録画停止] 「停止」入力 → SIGINT → flush待ち
    ↓
[3. 動画取得] adb pull → ローカルmp4 / 端末側を削除
    ↓
[4. フレーム抽出] video-frame-extractor（ffmpeg scene detection）
    ↓
[5. 画像解析] video-frame-analyzer（Claude Vision）
    ↓
[6. シナリオ生成] video-scenario-generator（YAML + [REVIEW]）
    ↓
[出力: scenario.yaml]
```

## 実行手順

### 1. 前提確認

- `platform` が `android` 以外なら「現状 Android のみ対応」と伝えて終了する。
- `adb` が存在し、デバイスが接続されていることを確認する（詳細は `references/recording.md`）。
- 複数デバイス接続時に `device` 未指定ならシリアル一覧を提示して指定を促す。

### 2. 録画の開始と停止

`references/recording.md` の手順に従う。要点：

1. 録画を**バックグラウンドで開始**し、ユーザーに「操作を開始してください。終わったら『停止』と入力してください」と伝える。
2. ユーザーが「停止」と入力したら `SIGINT` を送って録画を止め、ファイルが書き出されるまで待つ。
3. `adb pull` でローカルに取得し、端末側の一時ファイルを削除する。

> 録画の開始・停止はユーザーとの対話が必要なため、**サブエージェントに委譲せずスキル本体（メインループ）で実行**すること。

### 3. 録画から先は video-to-scenario と同じ

取得したローカルmp4のパスを使い、以下のエージェントを順次 Task 実行する
（入出力規約は `uiai-video-to-scenario` と共通、出力は `.video-to-scenario/{name}/` 配下）：

1. `video-frame-extractor` — フレーム抽出
2. `video-frame-analyzer` — Vision解析
3. `video-scenario-generator` — YAML生成

### 4. 仕上げ

- 生成された `scenario.yaml` を `output` へコピー（未指定なら `.video-to-scenario/{name}/scenario.yaml` を案内）。
- `[REVIEW]` マーカーの箇所をユーザーに提示し、`uiai-scenario-check` での検証を案内する。

## 出力ディレクトリ

```
recordings/
└── uiai-record-<label>.mp4      # 取得した録画（ローカル）

.video-to-scenario/
└── uiai-record-<label>/         # 解析の中間生成物（既存規約を流用）
    ├── frames/
    ├── analysis.json
    └── scenario.yaml
```

## 制約・注意

- **録画上限は180秒**（`adb screenrecord` の仕様）。超える操作は分割録画するか、別途録画した動画を `uiai-video-to-scenario` に渡す。
- 録画には**音声は含まれない**（UIテスト用途のため不要）。
- ソフトキーボードやパスワード欄は黒塗り表示になることがあり、`[REVIEW]` が付与される。

## 前提条件

- `adb` がインストールされ、対象デバイス/エミュレータが接続済みであること。
- `ffmpeg` がインストールされていること（フレーム抽出に使用）。

```bash
brew install ffmpeg
```

## 関連エージェント

- `video-frame-extractor` - ffmpegによるフレーム抽出
- `video-frame-analyzer` - Claude Visionによる画像解析
- `video-scenario-generator` - YAMLシナリオ生成

## 関連スキル

- `uiai-video-to-scenario` - 既存の動画ファイルからシナリオ生成（本スキルの解析部の母体）
- `uiai-scenario-check` - 生成されたシナリオの検証・修正
- `uiai-android-test` - Androidでのシナリオ実行

## リファレンス

- [録画の開始・停止・取得](./references/recording.md)
- [ffmpeg抽出コマンド](../uiai-video-to-scenario/references/ffmpeg-extraction.md)
- [Vision解析プロンプト](../uiai-video-to-scenario/references/vision-analysis.md)
- [シナリオ生成ルール](../uiai-video-to-scenario/references/scenario-generation.md)
- [シナリオスキーマ](../uiai-android-test/references/scenario-schema.md)
- [adbコマンド](../uiai-android-test/references/adb-commands.md)
