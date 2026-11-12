# simctl Commands Reference

`xcrun simctl` コマンドリファレンス。
iOS Simulator のUIテスト自動化で使用する主要コマンドを記載。

## シミュレータ管理

### 一覧表示

```bash
# 全デバイス一覧
xcrun simctl list devices

# 利用可能なデバイスのみ
xcrun simctl list devices available

# JSON形式で出力
xcrun simctl list devices -j

# ブート済みデバイスのみ
xcrun simctl list devices | grep "(Booted)"
```

### 出力例

```
== Devices ==
-- iOS 17.2 --
    iPhone 15 (XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX) (Booted)
    iPhone 15 Pro (YYYYYYYY-YYYY-YYYY-YYYY-YYYYYYYYYYYY) (Shutdown)
-- iOS 16.4 --
    iPhone 14 (ZZZZZZZZ-ZZZZ-ZZZZ-ZZZZ-ZZZZZZZZZZZZ) (Shutdown)
```

### シミュレータ起動/停止

```bash
# 起動
xcrun simctl boot <udid>

# 停止
xcrun simctl shutdown <udid>

# 全て停止
xcrun simctl shutdown all

# 起動中のシミュレータを指定（"booted" キーワード）
xcrun simctl <command> booted <args>
```

### シミュレータ作成/削除

```bash
# 新規作成
xcrun simctl create "Test iPhone" "iPhone 15" "iOS17.2"

# 削除
xcrun simctl delete <udid>

# 利用不可なデバイスを削除
xcrun simctl delete unavailable
```

## アプリ管理

### アプリインストール

```bash
# .app バンドルをインストール
xcrun simctl install <udid> /path/to/MyApp.app

# 起動中シミュレータにインストール
xcrun simctl install booted /path/to/MyApp.app
```

### アプリ起動

```bash
# Bundle Identifier で起動
xcrun simctl launch <udid> <bundle-id>

# 例
xcrun simctl launch booted com.example.MyApp

# 引数付きで起動
xcrun simctl launch <udid> <bundle-id> --arg1 --arg2

# コンソール出力を表示（デバッグ用）
xcrun simctl launch --console <udid> <bundle-id>
```

### アプリ終了

```bash
# アプリを終了
xcrun simctl terminate <udid> <bundle-id>

# 例
xcrun simctl terminate booted com.example.MyApp
```

### アプリアンインストール

```bash
# アンインストール
xcrun simctl uninstall <udid> <bundle-id>

# 例
xcrun simctl uninstall booted com.example.MyApp
```

### アプリデータクリア

```bash
# iOSにはpm clearに相当するコマンドがないため、
# アンインストール → 再インストールで対応
xcrun simctl uninstall <udid> <bundle-id>
xcrun simctl install <udid> /path/to/MyApp.app
```

### アプリ情報

```bash
# インストール済みアプリ一覧
xcrun simctl listapps <udid>

# 特定アプリの情報
xcrun simctl get_app_container <udid> <bundle-id>

# データコンテナのパス
xcrun simctl get_app_container <udid> <bundle-id> data

# アプリバンドルのパス
xcrun simctl get_app_container <udid> <bundle-id> app
```

## 画面キャプチャ

### スクリーンショット

```bash
# PNG形式で保存
xcrun simctl io <udid> screenshot /path/to/screenshot.png

# 起動中シミュレータのスクリーンショット
xcrun simctl io booted screenshot ./screenshot.png

# マスクなし（ノッチ等も含む）
xcrun simctl io <udid> screenshot --type=png --mask=ignored /path/to/screenshot.png
```

### 画面録画

```bash
# 録画開始（Ctrl+C で停止）
xcrun simctl io <udid> recordVideo /path/to/recording.mp4

# コーデック指定
xcrun simctl io <udid> recordVideo --codec h264 /path/to/recording.mp4

# フォース終了時も保存
xcrun simctl io <udid> recordVideo --force /path/to/recording.mp4
```

## システム操作

### URL を開く

```bash
# URLスキームを開く
xcrun simctl openurl <udid> "myapp://path/to/screen"

# Webページを開く
xcrun simctl openurl <udid> "https://example.com"
```

### プッシュ通知

```bash
# プッシュ通知を送信
xcrun simctl push <udid> <bundle-id> /path/to/payload.json

# ペイロード例
cat > payload.json << 'EOF'
{
  "aps": {
    "alert": {
      "title": "Test Notification",
      "body": "This is a test message"
    }
  }
}
EOF
```

### 位置情報

```bash
# 位置情報を設定
xcrun simctl location <udid> set <lat>,<lon>

# 例: 東京駅
xcrun simctl location booted set 35.6812,139.7671

# 位置情報をクリア
xcrun simctl location <udid> clear
```

### プライバシー権限

```bash
# 権限を付与
xcrun simctl privacy <udid> grant <permission> <bundle-id>

# 権限を取り消し
xcrun simctl privacy <udid> revoke <permission> <bundle-id>

# 権限をリセット
xcrun simctl privacy <udid> reset <permission> <bundle-id>

# 全権限をリセット
xcrun simctl privacy <udid> reset all <bundle-id>
```

### 権限一覧

| 権限 | 説明 |
|------|------|
| `all` | 全て |
| `calendar` | カレンダー |
| `contacts-limited` | 連絡先（制限付き） |
| `contacts` | 連絡先 |
| `location` | 位置情報 |
| `location-always` | 常に位置情報 |
| `photos-add` | 写真（追加のみ） |
| `photos` | 写真 |
| `media-library` | メディアライブラリ |
| `microphone` | マイク |
| `motion` | モーション |
| `reminders` | リマインダー |
| `siri` | Siri |

## デバイス情報

### デバイス状態

```bash
# 起動状態を確認
xcrun simctl list devices | grep <udid>

# JSON形式で詳細取得
xcrun simctl list devices -j | jq '.devices[][] | select(.udid == "<udid>")'
```

### ランタイム情報

```bash
# 利用可能なランタイム一覧
xcrun simctl list runtimes

# 出力例
# iOS 17.2 (17.2 - 21C62) - com.apple.CoreSimulator.SimRuntime.iOS-17-2
```

## ステータスバー

### ステータスバーのオーバーライド

```bash
# 時刻を固定
xcrun simctl status_bar <udid> override --time "9:41"

# バッテリー状態を変更
xcrun simctl status_bar <udid> override --batteryState charged --batteryLevel 100

# キャリア名を変更
xcrun simctl status_bar <udid> override --operatorName "Test Carrier"

# 全てのオーバーライドをクリア
xcrun simctl status_bar <udid> clear
```

### オーバーライドオプション

| オプション | 説明 | 例 |
|-----------|------|-----|
| `--time` | 時刻 | `9:41` |
| `--dataNetwork` | データネットワーク | `wifi`, `4g`, `lte`, `5g` |
| `--wifiMode` | Wi-Fiモード | `active`, `searching`, `failed` |
| `--wifiBars` | Wi-Fiバー | `0-3` |
| `--cellularMode` | セルラーモード | `active`, `searching`, `failed` |
| `--cellularBars` | セルラーバー | `0-4` |
| `--operatorName` | キャリア名 | `Test Carrier` |
| `--batteryState` | バッテリー状態 | `charging`, `charged`, `discharging` |
| `--batteryLevel` | バッテリーレベル | `0-100` |

## キーチェーン

```bash
# キーチェーンをリセット
xcrun simctl keychain <udid> reset
```

## ログ

```bash
# システムログを取得
xcrun simctl spawn <udid> log stream --predicate 'subsystem == "com.example.MyApp"'

# クラッシュログの場所
~/Library/Logs/DiagnosticReports/
```

## 診断

```bash
# 診断情報を収集
xcrun simctl diagnose

# 出力先を指定
xcrun simctl diagnose --output /path/to/output
```

## ベストプラクティス

1. **UDID vs "booted"** - 複数シミュレータを扱う場合は明示的にUDIDを指定
2. **アプリ終了** - 状態をリセットしたい場合は terminate → launch
3. **データクリア** - uninstall → install のペアで実現
4. **スクリーンショット** - 操作前後に取得してエビデンスとする
5. **権限** - テスト前に必要な権限を grant しておく
