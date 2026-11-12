# ADB Commands Reference

Android Debug Bridge (ADB) コマンドリファレンス。
UIテスト自動化で使用する主要コマンドを記載。

## デバイス管理

### 接続確認

```bash
# 接続デバイス一覧
adb devices

# 詳細情報付き
adb devices -l
```

### デバイス指定

```bash
# 特定デバイスを指定してコマンド実行
adb -s <serial> <command>

# 例: emulator-5554 でシェルを開く
adb -s emulator-5554 shell
```

## 入力操作

### タップ

```bash
# 座標指定でタップ
adb shell input tap <x> <y>

# 例: 画面中央（540, 960）をタップ
adb shell input tap 540 960
```

### 長押し

```bash
# swipe コマンドで同一座標を指定して長押しを実現
adb shell input swipe <x> <y> <x> <y> <duration_ms>

# 例: 2秒間長押し
adb shell input swipe 540 960 540 960 2000
```

### スワイプ

```bash
# 開始点から終了点へスワイプ
adb shell input swipe <x1> <y1> <x2> <y2> [duration_ms]

# 例: 下から上へスワイプ（スクロールアップ）
adb shell input swipe 540 1500 540 500 300

# 例: 左から右へスワイプ
adb shell input swipe 100 960 900 960 300
```

### テキスト入力

```bash
# テキストを入力（空白はエスケープ必要）
adb shell input text '<text>'

# 例: メールアドレスを入力
adb shell input text 'test@example.com'

# 日本語入力（ADB Keyboard が必要）
adb shell am broadcast -a ADB_INPUT_TEXT --es msg '<日本語テキスト>'
```

### キーイベント

```bash
# キーコードを送信
adb shell input keyevent <keycode>

# よく使うキーコード
adb shell input keyevent 3    # HOME
adb shell input keyevent 4    # BACK
adb shell input keyevent 66   # ENTER
adb shell input keyevent 67   # DEL (Backspace)
adb shell input keyevent 82   # MENU
adb shell input keyevent 26   # POWER
adb shell input keyevent 187  # APP_SWITCH (Recent Apps)
adb shell input keyevent 111  # ESCAPE
```

### キーコード一覧（頻出）

| キーコード | 名称 | 説明 |
|-----------|------|------|
| 3 | HOME | ホーム画面へ |
| 4 | BACK | 戻る |
| 24 | VOLUME_UP | 音量上げ |
| 25 | VOLUME_DOWN | 音量下げ |
| 26 | POWER | 電源ボタン |
| 66 | ENTER | 決定/改行 |
| 67 | DEL | バックスペース |
| 82 | MENU | メニュー |
| 111 | ESCAPE | エスケープ |
| 187 | APP_SWITCH | アプリ切り替え |

## アプリ管理

### アプリ起動

```bash
# アクティビティを指定して起動
adb shell am start -n <package>/<activity>

# 例: MainActivity を起動
adb shell am start -n com.example.app/.MainActivity

# パッケージのメインアクティビティを起動
adb shell monkey -p <package> -c android.intent.category.LAUNCHER 1

# インテントでアクティビティ起動
adb shell am start -a android.intent.action.VIEW -d <uri>
```

### アプリ停止

```bash
# アプリを強制停止
adb shell am force-stop <package>

# 例
adb shell am force-stop com.example.app
```

### アプリデータ操作

```bash
# アプリデータをクリア（キャッシュ含む）
adb shell pm clear <package>

# 例
adb shell pm clear com.example.app
```

### アプリ情報

```bash
# インストール済みパッケージ一覧
adb shell pm list packages

# 特定パッケージの情報
adb shell dumpsys package <package>

# 実行中アクティビティ
adb shell dumpsys activity activities | grep -E 'mResumedActivity|mFocusedActivity'
```

## 画面キャプチャ

### スクリーンショット

```bash
# デバイス内に保存
adb shell screencap /sdcard/screenshot.png

# ローカルに取得
adb exec-out screencap -p > screenshot.png

# デバイス保存 → ローカル転送 → デバイス削除
adb shell screencap /sdcard/temp_screenshot.png && \
adb pull /sdcard/temp_screenshot.png ./screenshot.png && \
adb shell rm /sdcard/temp_screenshot.png
```

### 画面録画

```bash
# 画面録画開始（最大3分）
adb shell screenrecord /sdcard/recording.mp4

# 時間指定（秒）
adb shell screenrecord --time-limit 30 /sdcard/recording.mp4

# 録画停止は Ctrl+C または別ターミナルから
adb shell pkill -SIGINT screenrecord
```

## UIツリー取得

### UI Automator

```bash
# UIツリーをXMLでダンプ
adb shell uiautomator dump /sdcard/ui.xml

# ローカルに取得
adb shell uiautomator dump /sdcard/ui.xml && adb pull /sdcard/ui.xml

# 圧縮形式で取得
adb exec-out uiautomator dump /dev/tty
```

### UIツリー XML 例

```xml
<?xml version="1.0" encoding="UTF-8"?>
<hierarchy rotation="0">
  <node index="0" text="" resource-id="" class="android.widget.FrameLayout"
        package="com.example.app" content-desc="" checkable="false" checked="false"
        clickable="false" enabled="true" focusable="false" focused="false"
        scrollable="false" long-clickable="false" password="false" selected="false"
        bounds="[0,0][1080,1920]">
    <node index="0" text="Login" resource-id="com.example.app:id/login_button"
          class="android.widget.Button" bounds="[100,500][980,600]" ... />
  </node>
</hierarchy>
```

### 要素の特定方法

| 属性 | 用途 | 例 |
|------|------|-----|
| `resource-id` | 一意のID（推奨） | `com.example.app:id/login_button` |
| `text` | 表示テキスト | `Login` |
| `content-desc` | アクセシビリティ説明 | `Submit form` |
| `class` | ウィジェットタイプ | `android.widget.Button` |
| `bounds` | 座標範囲 | `[100,500][980,600]` |

## ファイル操作

### ファイル転送

```bash
# デバイス → ローカル
adb pull /sdcard/file.txt ./local_file.txt

# ローカル → デバイス
adb push ./local_file.txt /sdcard/file.txt
```

### ファイル操作

```bash
# ファイル一覧
adb shell ls /sdcard/

# ファイル削除
adb shell rm /sdcard/file.txt

# ディレクトリ作成
adb shell mkdir /sdcard/test_output/
```

## システム情報

### 画面情報

```bash
# 画面サイズ取得
adb shell wm size

# 画面密度取得
adb shell wm density

# 画面の向き
adb shell dumpsys input | grep SurfaceOrientation
```

### デバイス情報

```bash
# Android バージョン
adb shell getprop ro.build.version.release

# API レベル
adb shell getprop ro.build.version.sdk

# デバイスモデル
adb shell getprop ro.product.model
```

## 待機処理

### 画面遷移待機

```bash
# アクティビティの変化を監視
adb shell am monitor

# 特定のアクティビティが表示されるまで待機（シェルスクリプト例）
while true; do
  activity=$(adb shell dumpsys activity activities | grep mResumedActivity)
  if echo "$activity" | grep -q "TargetActivity"; then
    break
  fi
  sleep 0.5
done
```

### 要素の出現待機

```bash
# UIツリーで特定要素の出現を待機（シェルスクリプト例）
timeout=10
interval=0.5
elapsed=0
while [ $(echo "$elapsed < $timeout" | bc) -eq 1 ]; do
  adb shell uiautomator dump /sdcard/ui.xml 2>/dev/null
  if adb shell cat /sdcard/ui.xml | grep -q 'resource-id="target_id"'; then
    break
  fi
  sleep $interval
  elapsed=$(echo "$elapsed + $interval" | bc)
done
```

## トラブルシューティング

### 接続問題

```bash
# ADB サーバー再起動
adb kill-server && adb start-server

# USB 接続リセット
adb usb

# Wi-Fi 接続
adb tcpip 5555
adb connect <device_ip>:5555
```

### 権限問題

```bash
# ルート権限で実行（ルート化端末のみ）
adb root

# SELinux を permissive に（デバッグ用）
adb shell setenforce 0
```

## ベストプラクティス

1. **要素特定は `resource-id` を優先** - テキストは変わる可能性がある
2. **待機処理を適切に入れる** - 画面遷移後は要素の出現を確認
3. **エラーハンドリング** - コマンド失敗時の終了コードを確認
4. **スクリーンショットは操作前後に取得** - デバッグ用エビデンス
5. **UIツリーはアサーション前に取得** - 要素の存在確認に使用
