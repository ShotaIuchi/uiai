# IDB Commands Reference

Facebook IDB (iOS Development Bridge) コマンドリファレンス。
iOS Simulator のUIテスト自動化で使用する主要コマンドを記載。

## インストール

```bash
# Homebrew でインストール
brew tap facebook/fb
brew install idb-companion

# Python クライアントをインストール
pip3 install fb-idb
```

## 接続管理

### ターゲット一覧

```bash
# 接続可能なターゲット一覧
idb list-targets

# 出力例
# iPhone 15 | XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX | Booted | simulator | x86_64 | iOS 17.2
```

### ターゲット接続

```bash
# 特定のシミュレータに接続
idb connect <udid>

# 例
idb connect XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX
```

### companion 起動

```bash
# idb_companion を起動（バックグラウンド）
idb_companion --udid <udid> &

# ポート指定で起動
idb_companion --udid <udid> --grpc-port 10882
```

## UI操作

### タップ

```bash
# 座標指定でタップ
idb ui tap <x> <y>

# 例: 画面中央をタップ
idb ui tap 195 422

# 持続時間を指定（ミリ秒）
idb ui tap --duration 500 <x> <y>
```

### 長押し

```bash
# 長押し（持続時間をミリ秒で指定）
idb ui tap --duration 2000 <x> <y>
```

### スワイプ

```bash
# 開始点から終了点へスワイプ
idb ui swipe <x1> <y1> <x2> <y2>

# 例: 下から上へスワイプ（スクロールアップ）
idb ui swipe 195 700 195 200

# 例: 左端から右へスワイプ（戻るジェスチャー）
idb ui swipe 0 400 300 400

# 持続時間を指定（ミリ秒）
idb ui swipe --duration 300 <x1> <y1> <x2> <y2>

# デルタ値でスワイプ
idb ui swipe --delta 0 -500 <x> <y>
```

### テキスト入力

```bash
# テキストを入力
idb ui text '<text>'

# 例
idb ui text 'test@example.com'

# 日本語入力
idb ui text '東京'
```

### キー入力

```bash
# キーコードを送信
idb ui key <keycode>

# 例: Return キー
idb ui key 40

# 例: Delete キー
idb ui key 42
```

### キーコード一覧（頻出）

| キーコード | 名称 | 説明 |
|-----------|------|------|
| 40 | Return | 改行/決定 |
| 42 | Delete | バックスペース |
| 43 | Tab | タブ |
| 41 | Escape | エスケープ |
| 44 | Space | スペース |

**注意**: iOSには汎用的な「戻る」キーがないため、以下で代替：
- ナビゲーションバーの戻るボタンをタップ
- 左端からのスワイプジェスチャー: `idb ui swipe 0 400 300 400`

### ボタン操作

```bash
# ハードウェアボタンを押す
idb ui button <button>

# 利用可能なボタン
# - HOME
# - LOCK
# - SIDE_BUTTON
# - SIRI

# 例: ホームボタン
idb ui button HOME
```

## UIツリー取得

### describe-all

```bash
# 全UI要素をJSON形式で取得
idb ui describe-all

# ファイルに保存
idb ui describe-all > ui_tree.json
```

### JSON出力例

```json
[
  {
    "AXLabel": "ログイン",
    "AXIdentifier": "login_button",
    "AXValue": null,
    "type": "Button",
    "frame": {
      "x": 100,
      "y": 500,
      "width": 200,
      "height": 44
    },
    "AXEnabled": true,
    "AXUniqueId": "0x12345678"
  },
  {
    "AXLabel": "メールアドレス",
    "AXIdentifier": "email_field",
    "AXValue": "",
    "type": "TextField",
    "frame": {
      "x": 50,
      "y": 200,
      "width": 300,
      "height": 44
    },
    "AXEnabled": true,
    "AXUniqueId": "0x87654321"
  }
]
```

### 要素の属性

| 属性 | Android相当 | 説明 |
|------|------------|------|
| `AXLabel` | `text` | 表示テキスト/ラベル |
| `AXIdentifier` | `resource-id` | アクセシビリティ識別子 |
| `AXValue` | `content-desc` | 値（テキストフィールドの入力値等） |
| `type` | `class` | UI要素タイプ |
| `frame` | `bounds` | 位置とサイズ |
| `AXEnabled` | `enabled` | 有効/無効 |
| `AXUniqueId` | - | 一意識別子 |

### describe-point

```bash
# 特定の座標にある要素を取得
idb ui describe-point <x> <y>
```

## アプリ管理

### インストール

```bash
# .app または .ipa をインストール
idb install /path/to/MyApp.app
```

### 起動

```bash
# アプリを起動
idb launch <bundle-id>

# 例
idb launch com.example.MyApp

# 引数付きで起動
idb launch <bundle-id> -- --arg1 --arg2

# フォアグラウンドで起動（ログ出力あり）
idb launch --foreground-if-running <bundle-id>
```

### 終了

```bash
# アプリを終了
idb terminate <bundle-id>
```

### アンインストール

```bash
# アンインストール
idb uninstall <bundle-id>
```

### アプリ一覧

```bash
# インストール済みアプリ一覧
idb list-apps
```

## クラッシュログ

```bash
# クラッシュログ一覧
idb crash list

# クラッシュログを取得
idb crash show <crash-name>

# クラッシュログを削除
idb crash delete <crash-name>
```

## ファイル操作

```bash
# ファイルをシミュレータにプッシュ
idb file push /local/path /app-container/path --bundle-id <bundle-id>

# ファイルをシミュレータからプル
idb file pull /app-container/path /local/path --bundle-id <bundle-id>

# ファイル一覧
idb file ls /path --bundle-id <bundle-id>

# ファイル削除
idb file rm /path --bundle-id <bundle-id>
```

## その他

### スクリーンショット（simctl推奨）

```bash
# IDBでもスクリーンショット可能だが、simctl推奨
idb screenshot /path/to/screenshot.png
```

### 録画

```bash
# 画面録画
idb record /path/to/recording.mp4
```

### URL を開く

```bash
# URLスキームを開く
idb open <url>

# 例
idb open "myapp://path/to/screen"
```

### アクセシビリティ情報

```bash
# アクセシビリティ情報を取得
idb accessibility info
```

## 座標計算

### frame から中心座標を計算

```python
def get_center(frame):
    """
    frame = {"x": 100, "y": 500, "width": 200, "height": 44}
    から中心座標を計算
    """
    center_x = frame["x"] + frame["width"] / 2
    center_y = frame["y"] + frame["height"] / 2
    return (int(center_x), int(center_y))

# 例
# frame = {"x": 100, "y": 500, "width": 200, "height": 44}
# center = (200, 522)
```

## Android ADB との対応

| 操作 | ADB | IDB |
|------|-----|-----|
| タップ | `adb shell input tap x y` | `idb ui tap x y` |
| スワイプ | `adb shell input swipe x1 y1 x2 y2` | `idb ui swipe x1 y1 x2 y2` |
| テキスト入力 | `adb shell input text 'text'` | `idb ui text 'text'` |
| 戻る | `adb shell input keyevent 4` | `idb ui swipe 0 400 300 400` |
| ホーム | `adb shell input keyevent 3` | `idb ui button HOME` |
| UIツリー | `adb shell uiautomator dump` | `idb ui describe-all` |
| UIツリー形式 | XML | JSON |

## トラブルシューティング

### idb_companion が接続できない

```bash
# companion を再起動
pkill idb_companion
idb_companion --udid <udid> &

# 接続を再試行
idb connect <udid>
```

### describe-all が空を返す

```bash
# アプリがフォアグラウンドにあることを確認
xcrun simctl launch booted <bundle-id>

# 少し待ってから再試行
sleep 2
idb ui describe-all
```

### タップが反応しない

1. 座標が正しいか確認（frame から計算）
2. 要素が AXEnabled=true か確認
3. キーボードが表示されていて座標がずれていないか確認

## ベストプラクティス

1. **simctl と IDB の使い分け**
   - シミュレータ管理、アプリインストール、スクリーンショット → simctl
   - UI操作、UIツリー取得 → IDB

2. **要素特定は AXLabel を優先** - AXIdentifier がない場合も多い

3. **待機処理を適切に入れる** - 画面遷移後は describe-all で要素の出現を確認

4. **戻るジェスチャー** - 左端からスワイプ: `idb ui swipe 0 400 300 400`

5. **キーボード表示時** - 座標がずれる可能性があるため、UIツリーを再取得
