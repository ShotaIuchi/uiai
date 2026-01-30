# Environment Check Reference

テスト実行前の環境チェック定義。

## 事前チェック一覧

テスト開始前に以下の順序でチェックを実行する。

| # | チェック項目 | コマンド | 成功条件 |
|---|-------------|---------|---------|
| 1 | ADB利用可能 | `which adb` または `adb version` | 終了コード 0 |
| 2 | ADBサーバー起動 | `adb start-server` | 終了コード 0 |
| 3 | デバイス接続確認 | `adb devices` | 1台以上のデバイスがリスト |
| 4 | デバイス数確認 | `adb devices` | 1台、または `device` パラメータ指定済み |
| 5 | デバイス状態確認 | `adb devices` | `device` 状態（`offline`/`unauthorized` でない） |

## チェック詳細

### 1. ADB利用可能チェック

```bash
# チェック方法
adb version

# 成功例
Android Debug Bridge version 1.0.41
Version 34.0.5-10900879

# 失敗例
command not found: adb
```

**失敗時の対応**:
- エラーメッセージ: `❌ ADBが見つかりません。Android SDKをインストールし、PATHを設定してください。`
- 終了コード: 1

### 2. ADBサーバー起動

```bash
# チェック方法
adb start-server

# 成功例
* daemon not running; starting now at tcp:5037
* daemon started successfully

# または既に起動済み
（出力なし、終了コード0）
```

**失敗時の対応**:
- エラーメッセージ: `❌ ADBサーバーの起動に失敗しました。ポート5037が使用中の可能性があります。`
- 終了コード: 1

### 3. デバイス接続確認

```bash
# チェック方法
adb devices

# 成功例（デバイスあり）
List of devices attached
emulator-5554	device
XXXXXXXX	device

# 失敗例（デバイスなし）
List of devices attached
（空行のみ）
```

**失敗時の対応**:
- エラーメッセージ: `❌ 接続されたデバイスがありません。デバイスを接続するか、エミュレータを起動してください。`
- 終了コード: 1

### 4. デバイス数確認

```bash
# チェック方法
adb devices | grep -E "device$|emulator" | wc -l

# 1台の場合: 自動選択
# 2台以上の場合: ユーザーに選択を促す
```

**複数デバイス接続時（device パラメータ未指定）**:

`AskUserQuestion` ツールを使用してユーザーにデバイスを選択させる。

```
ℹ️ 複数のデバイスが接続されています。テストに使用するデバイスを選択してください。
```

| デバイス | モデル | Android | 状態 |
|----------|--------|---------|------|
| emulator-5554 | sdk_gphone64_arm64 | 14 | device |
| emulator-5556 | sdk_gphone64_arm64 | 13 | device |
| XXXXXXXX | Pixel 7 | 14 | device |

選択肢として各デバイスを提示し、ユーザーが選択したデバイスを使用する。

### 5. デバイス状態確認

```bash
# チェック方法
adb devices

# 正常な状態
emulator-5554	device

# 異常な状態
emulator-5554	offline
XXXXXXXX	unauthorized
```

| 状態 | 意味 | 対応 |
|------|------|------|
| `device` | 正常接続 | OK |
| `offline` | 接続切れ/応答なし | 再接続が必要 |
| `unauthorized` | USB デバッグ未許可 | デバイス側で許可が必要 |
| `no permissions` | 権限不足 | udev ルール設定が必要（Linux） |

**offline の場合**:
- エラーメッセージ: `❌ デバイス <serial> がオフラインです。USBを再接続するか、エミュレータを再起動してください。`
- 終了コード: 1

**unauthorized の場合**:
- エラーメッセージ:
  ```
  ❌ デバイス <serial> が未認証です。
  デバイス画面に「USBデバッグを許可しますか？」ダイアログが表示されている場合は「許可」をタップしてください。
  ```
- 終了コード: 1

## 指定デバイスの検証

`device` パラメータが指定された場合の追加チェック。

```bash
# 指定デバイスの存在確認
adb -s <device> get-state

# 成功例
device

# 失敗例
error: device '<device>' not found
```

**指定デバイスが見つからない場合**:
- エラーメッセージ:
  ```
  ❌ 指定されたデバイス <device> が見つかりません。

  接続中のデバイス:
    - emulator-5554
    - XXXXXXXX
  ```
- 終了コード: 1

## チェックフロー

```
開始
  │
  ├─ ADB利用可能？ ─ No ──→ エラー終了
  │       │
  │      Yes
  │       │
  ├─ ADBサーバー起動 ─ 失敗 ──→ エラー終了
  │       │
  │      成功
  │       │
  ├─ デバイス接続あり？ ─ No ──→ エラー終了
  │       │
  │      Yes
  │       │
  ├─ device パラメータ指定？
  │       │
  │      Yes ─────────────────────┐
  │       │                       │
  │      No                       │
  │       │                       │
  ├─ デバイス1台のみ？            │
  │       │                       │
  │      No                       │
  │       │                       │
  │       ▼                       │
  │  ユーザーに選択を促す         │
  │  (AskUserQuestion)            │
  │       │                       │
  │      選択                     │
  │       │                       │
  │      Yes（1台）               │
  │       │                       │
  │       └───────────────────────┘
  │                   │
  │       指定/選択デバイス確定
  │                   │
  ├─ デバイス状態 = device？ ─ No ──→ エラー終了
  │       │
  │      Yes
  │       │
  └─ テスト実行開始
```

## コンソール出力例

### 成功時

```
## 環境チェック

✅ ADB: version 34.0.5
✅ ADBサーバー: 起動済み
✅ デバイス: emulator-5554 (device)

テストを開始します...
```

### 複数デバイス（device指定あり）

```
## 環境チェック

✅ ADB: version 34.0.5
✅ ADBサーバー: 起動済み
ℹ️ 複数デバイスを検出: 3台
✅ 指定デバイス: emulator-5554 (device)

テストを開始します...
```

### 複数デバイス（ユーザー選択）

```
## 環境チェック

✅ ADB: version 34.0.5
✅ ADBサーバー: 起動済み
ℹ️ 複数デバイスを検出: 3台
```

→ AskUserQuestion で選択肢を表示:

```
テストに使用するデバイスを選択してください。

1. emulator-5554 (sdk_gphone64_arm64, Android 14)
2. emulator-5556 (sdk_gphone64_arm64, Android 13)
3. XXXXXXXX (Pixel 7, Android 14)
```

→ ユーザーが選択後:

```
✅ 選択デバイス: emulator-5554 (device)

テストを開始します...
```

### 失敗時

```
## 環境チェック

✅ ADB: version 34.0.5
✅ ADBサーバー: 起動済み
❌ デバイスが接続されていません

デバイスを接続するか、エミュレータを起動してください:
  - Android Studio > Device Manager > 起動
  - または: emulator -avd <avd_name>
```

## 環境情報の記録

チェック成功後、以下の情報を result.json に記録する。

```json
{
  "environment": {
    "adb_version": "34.0.5-10900879",
    "device": {
      "serial": "emulator-5554",
      "state": "device",
      "model": "sdk_gphone64_arm64",
      "android_version": "14",
      "api_level": "34",
      "screen_size": "1080x2400"
    },
    "check_timestamp": "2026-01-29T10:00:00Z"
  }
}
```

## 関連コマンド

```bash
# デバイス詳細情報
adb -s <serial> shell getprop ro.product.model
adb -s <serial> shell getprop ro.build.version.release
adb -s <serial> shell getprop ro.build.version.sdk
adb -s <serial> shell wm size
```
