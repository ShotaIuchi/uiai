# Environment Check Reference

テスト実行前の環境チェック定義。

## 事前チェック一覧

テスト開始前に以下の順序でチェックを実行する。

| # | チェック項目 | コマンド | 成功条件 |
|---|-------------|---------|---------|
| 1 | Xcode利用可能 | `xcode-select -p` | 終了コード 0 |
| 2 | simctl利用可能 | `xcrun simctl help` | 終了コード 0 |
| 3 | IDB利用可能 | `idb --help` | 終了コード 0 |
| 4 | シミュレータ一覧取得 | `xcrun simctl list devices available` | 出力あり |
| 5 | シミュレータ数確認 | - | 1台以上、または `simulator` パラメータ指定済み |
| 6 | シミュレータ状態確認 | `xcrun simctl list devices` | `Booted` 状態 |

## チェック詳細

### 1. Xcode利用可能チェック

```bash
# チェック方法
xcode-select -p

# 成功例
/Applications/Xcode.app/Contents/Developer

# 失敗例
xcode-select: error: unable to get active developer directory...
```

**失敗時の対応**:
- エラーメッセージ: `❌ Xcodeが見つかりません。App StoreからXcodeをインストールしてください。`
- 終了コード: 1

### 2. simctl利用可能チェック

```bash
# チェック方法
xcrun simctl help

# 成功例
（ヘルプテキストが表示される）

# 失敗例
xcrun: error: unable to find utility "simctl"
```

**失敗時の対応**:
- エラーメッセージ: `❌ simctlが利用できません。Xcodeのコマンドラインツールを確認してください。`
- 終了コード: 1

### 3. IDB利用可能チェック

```bash
# チェック方法
idb --help

# 成功例
（ヘルプテキストが表示される）

# 失敗例
command not found: idb
```

**失敗時の対応**:
- エラーメッセージ:
  ```
  ❌ Facebook IDB が見つかりません。

  インストール方法:
    brew tap facebook/fb
    brew install idb-companion
    pip3 install fb-idb
  ```
- 終了コード: 1

### 4. シミュレータ一覧取得

```bash
# チェック方法
xcrun simctl list devices available

# 成功例
== Devices ==
-- iOS 17.2 --
    iPhone 15 (XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX) (Shutdown)
    iPhone 15 Pro (YYYYYYYY-YYYY-YYYY-YYYY-YYYYYYYYYYYY) (Booted)

# 失敗例（デバイスなし）
== Devices ==
（空）
```

**失敗時の対応**:
- エラーメッセージ: `❌ 利用可能なシミュレータがありません。Xcode > Window > Devices and Simulators からシミュレータを追加してください。`
- 終了コード: 1

### 5. シミュレータ数確認

```bash
# チェック方法
xcrun simctl list devices available | grep -E "\((Booted|Shutdown)\)" | wc -l

# Bootedのシミュレータをカウント
xcrun simctl list devices | grep "(Booted)" | wc -l
```

**複数シミュレータ起動時（simulator パラメータ未指定）**:

`AskUserQuestion` ツールを使用してユーザーにシミュレータを選択させる。

```
ℹ️ 複数のシミュレータが起動しています。テストに使用するシミュレータを選択してください。
```

| シミュレータ | UDID | iOS | 状態 |
|------------|------|-----|------|
| iPhone 15 | XXXXXXXX... | 17.2 | Booted |
| iPhone 15 Pro | YYYYYYYY... | 17.2 | Booted |

**シミュレータが起動していない場合**:

```
ℹ️ 起動中のシミュレータがありません。シミュレータを起動しますか？
```

利用可能なシミュレータを一覧表示し、選択・起動を促す。

### 6. シミュレータ状態確認

```bash
# チェック方法
xcrun simctl list devices | grep "<udid>"

# 正常な状態
iPhone 15 (XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX) (Booted)

# 異常な状態
iPhone 15 (XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX) (Shutdown)
```

| 状態 | 意味 | 対応 |
|------|------|------|
| `Booted` | 起動中 | OK |
| `Shutdown` | 停止中 | 起動が必要 |
| `Creating` | 作成中 | 待機 |
| `Shutting Down` | 停止処理中 | 待機 |

**Shutdown の場合**:
- メッセージ:
  ```
  ℹ️ シミュレータ <name> が停止しています。起動しますか？

  起動コマンド: xcrun simctl boot <udid>
  ```
- 自動起動の選択肢を提示

## 指定シミュレータの検証

`simulator` パラメータが指定された場合の追加チェック。

### "booted" キーワードの場合

```bash
# 起動中のシミュレータを取得
xcrun simctl list devices | grep "(Booted)"

# 1台の場合: 自動選択
# 複数の場合: ユーザーに選択を促す
# 0台の場合: エラー
```

### UDID指定の場合

```bash
# 指定UDIDの存在確認
xcrun simctl list devices | grep "<udid>"

# 成功例
iPhone 15 (XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX) (Booted)

# 失敗例
（出力なし）
```

**指定シミュレータが見つからない場合**:
- エラーメッセージ:
  ```
  ❌ 指定されたシミュレータ <udid> が見つかりません。

  利用可能なシミュレータ:
    - iPhone 15 (XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX)
    - iPhone 15 Pro (YYYYYYYY-YYYY-YYYY-YYYY-YYYYYYYYYYYY)
  ```
- 終了コード: 1

## IDB接続確認

シミュレータ選択後、IDBの接続を確認。

```bash
# idb_companion が起動しているか確認
idb list-targets | grep "<udid>"

# 接続されていない場合は接続
idb connect <udid>

# 接続確認
idb list-targets
```

**IDB接続失敗時**:
- エラーメッセージ:
  ```
  ❌ IDBがシミュレータに接続できません。

  以下を試してください:
  1. idb_companion を再起動: pkill idb_companion && idb_companion --udid <udid> &
  2. シミュレータを再起動: xcrun simctl shutdown <udid> && xcrun simctl boot <udid>
  3. IDBを再インストール: pip3 install --upgrade fb-idb
  ```

## チェックフロー

```
開始
  │
  ├─ Xcode利用可能？ ─ No ──→ エラー終了
  │       │
  │      Yes
  │       │
  ├─ simctl利用可能？ ─ No ──→ エラー終了
  │       │
  │      Yes
  │       │
  ├─ IDB利用可能？ ─ No ──→ エラー終了
  │       │
  │      Yes
  │       │
  ├─ シミュレータあり？ ─ No ──→ エラー終了
  │       │
  │      Yes
  │       │
  ├─ simulator パラメータ指定？
  │       │
  │      Yes ─── "booted"？ ────────────────┐
  │       │          │                      │
  │       │         Yes                     │
  │       │          │                      │
  │       │    起動中シミュレータ取得        │
  │       │          │                      │
  │       │       ┌──┴──┐                   │
  │       │       │     │                   │
  │       │     1台  複数                   │
  │       │       │     │                   │
  │       │       │  ユーザー選択           │
  │       │       │     │                   │
  │       │       └──┬──┘                   │
  │       │          │                      │
  │      No          │                    UDID指定
  │       │          │                      │
  │       ▼          │                      │
  │  起動中シミュレータ取得                 │
  │       │          │                      │
  │    ┌──┴──┐       │                      │
  │    │     │       │                      │
  │   0台  1台以上    │                      │
  │    │     │       │                      │
  │    │  ┌──┴──┐    │                      │
  │    │  │     │    │                      │
  │    │ 1台  複数   │                      │
  │    │  │     │    │                      │
  │    │  │  ユーザー選択                   │
  │    │  │     │    │                      │
  │    │  └──┬──┘    │                      │
  │    │     │       │                      │
  │ シミュレータ起動を提案                  │
  │    │     │       │                      │
  │    └─────┴───────┴──────────────────────┘
  │                   │
  │       シミュレータ確定
  │                   │
  ├─ シミュレータ状態 = Booted？
  │       │
  │      No ─── 起動を提案 ─── 拒否 ──→ エラー終了
  │       │                     │
  │       │               承認（起動）
  │       │                     │
  │      Yes ──────────────────┘
  │       │
  ├─ IDB接続確認 ─ 失敗 ──→ エラー終了
  │       │
  │      成功
  │       │
  └─ テスト実行開始
```

## コンソール出力例

### 成功時

```
## 環境チェック

✅ Xcode: /Applications/Xcode.app/Contents/Developer
✅ simctl: 利用可能
✅ IDB: 利用可能
✅ シミュレータ: iPhone 15 (XXXXXXXX...) - iOS 17.2 (Booted)
✅ IDB接続: 確立済み

テストを開始します...
```

### 複数シミュレータ（simulator指定あり）

```
## 環境チェック

✅ Xcode: /Applications/Xcode.app/Contents/Developer
✅ simctl: 利用可能
✅ IDB: 利用可能
ℹ️ 複数シミュレータを検出: 3台
✅ 指定シミュレータ: iPhone 15 (XXXXXXXX...) - iOS 17.2 (Booted)
✅ IDB接続: 確立済み

テストを開始します...
```

### 複数シミュレータ（ユーザー選択）

```
## 環境チェック

✅ Xcode: /Applications/Xcode.app/Contents/Developer
✅ simctl: 利用可能
✅ IDB: 利用可能
ℹ️ 複数シミュレータを検出: 3台
```

→ AskUserQuestion で選択肢を表示:

```
テストに使用するシミュレータを選択してください。

1. iPhone 15 (XXXXXXXX..., iOS 17.2, Booted)
2. iPhone 15 Pro (YYYYYYYY..., iOS 17.2, Booted)
3. iPhone 14 (ZZZZZZZZ..., iOS 16.4, Shutdown)
```

→ ユーザーが選択後:

```
✅ 選択シミュレータ: iPhone 15 (Booted)
✅ IDB接続: 確立済み

テストを開始します...
```

### 失敗時

```
## 環境チェック

✅ Xcode: /Applications/Xcode.app/Contents/Developer
✅ simctl: 利用可能
❌ IDBが見つかりません

Facebook IDB をインストールしてください:

  brew tap facebook/fb
  brew install idb-companion
  pip3 install fb-idb
```

## 環境情報の記録

チェック成功後、以下の情報を result.json に記録する。

```json
{
  "environment": {
    "xcode_path": "/Applications/Xcode.app/Contents/Developer",
    "idb_version": "1.1.8",
    "simulator": {
      "udid": "XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX",
      "name": "iPhone 15",
      "state": "Booted",
      "ios_version": "17.2",
      "device_type": "iPhone15,2",
      "screen_size": "393x852"
    },
    "check_timestamp": "2026-01-29T10:00:00Z"
  }
}
```

## 関連コマンド

```bash
# シミュレータ詳細情報
xcrun simctl list devices -j | jq '.devices[][] | select(.udid == "<udid>")'

# iOS バージョン
xcrun simctl list runtimes

# 画面サイズ（おおよその取得）
xcrun simctl io <udid> screenshot /tmp/test.png && file /tmp/test.png
```
