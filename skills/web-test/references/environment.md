# Environment Check Reference

テスト実行前の環境チェック定義。

## 事前チェック一覧

テスト開始前に以下の順序でチェックを実行する。

| # | チェック項目 | コマンド | 成功条件 |
|---|-------------|---------|---------|
| 1 | Node.js 利用可能 | `node --version` | 終了コード 0、v16以上 |
| 2 | npm/pnpm 利用可能 | `npm --version` または `pnpm --version` | 終了コード 0 |
| 3 | Playwright インストール確認 | `npx playwright --version` | 終了コード 0 |
| 4 | ブラウザインストール確認 | `npx playwright install --check` | 指定ブラウザがインストール済み |

## チェック詳細

### 1. Node.js 利用可能チェック

```bash
# チェック方法
node --version

# 成功例
v20.10.0

# 失敗例
command not found: node
```

**失敗時の対応**:
- エラーメッセージ: `❌ Node.jsが見つかりません。Node.js v16以上をインストールしてください。`
- 終了コード: 1

**バージョン確認**:
```bash
# バージョン番号を抽出して比較
node_version=$(node --version | sed 's/v//' | cut -d. -f1)
if [ "$node_version" -lt 16 ]; then
  echo "❌ Node.js v16以上が必要です。現在: $(node --version)"
  exit 1
fi
```

### 2. npm/pnpm 利用可能チェック

```bash
# チェック方法（npm）
npm --version

# 成功例
10.2.0

# pnpm の場合
pnpm --version

# 成功例
8.10.0
```

**失敗時の対応**:
- エラーメッセージ: `❌ npmまたはpnpmが見つかりません。パッケージマネージャをインストールしてください。`
- 終了コード: 1

### 3. Playwright インストール確認

```bash
# チェック方法
npx playwright --version

# 成功例
Version 1.40.0

# 失敗例
npm ERR! could not determine executable to run
```

**失敗時の対応**:
- エラーメッセージ:
  ```
  ❌ Playwrightがインストールされていません。

  以下のコマンドでインストールしてください:
    npm install -D playwright
  ```
- 終了コード: 1

### 4. ブラウザインストール確認

```bash
# チェック方法（全ブラウザ）
npx playwright install --check

# 特定ブラウザの確認
npx playwright install chromium --dry-run

# 成功例（インストール済み）
browser chromium version 120.0.6099.71 is already installed

# 失敗例（未インストール）
browser chromium is not installed
```

**失敗時の対応**:
- エラーメッセージ:
  ```
  ❌ ブラウザ <browser> がインストールされていません。

  以下のコマンドでインストールしてください:
    npx playwright install <browser>

  または全ブラウザをインストール:
    npx playwright install
  ```
- 終了コード: 1

## 指定ブラウザの検証

`browser` パラメータが指定された場合の追加チェック。

```bash
# 対応ブラウザの確認
case "$browser" in
  chromium|firefox|webkit)
    # 有効なブラウザ
    ;;
  *)
    echo "❌ 無効なブラウザ: $browser"
    echo "有効な値: chromium, firefox, webkit"
    exit 1
    ;;
esac

# ブラウザがインストールされているか確認
if ! npx playwright install "$browser" --dry-run 2>&1 | grep -q "already installed"; then
  echo "❌ ブラウザ $browser がインストールされていません。"
  echo "インストール: npx playwright install $browser"
  exit 1
fi
```

## チェックフロー

```
開始
  │
  ├─ Node.js利用可能？ ─ No ──→ エラー終了
  │       │
  │      Yes
  │       │
  ├─ Node.jsバージョン >= 16？ ─ No ──→ エラー終了
  │       │
  │      Yes
  │       │
  ├─ npm/pnpm利用可能？ ─ No ──→ エラー終了
  │       │
  │      Yes
  │       │
  ├─ Playwrightインストール済み？ ─ No ──→ エラー終了
  │       │
  │      Yes
  │       │
  ├─ 指定ブラウザ有効？ ─ No ──→ エラー終了
  │       │
  │      Yes
  │       │
  ├─ ブラウザインストール済み？ ─ No ──→ エラー終了
  │       │
  │      Yes
  │       │
  └─ テスト実行開始
```

## コンソール出力例

### 成功時

```
## 環境チェック

✅ Node.js: v20.10.0
✅ npm: 10.2.0
✅ Playwright: 1.40.0
✅ ブラウザ: chromium (120.0.6099.71)

テストを開始します...
```

### ブラウザ指定あり

```
## 環境チェック

✅ Node.js: v20.10.0
✅ npm: 10.2.0
✅ Playwright: 1.40.0
✅ 指定ブラウザ: firefox (121.0)

テストを開始します...
```

### 失敗時（Playwright未インストール）

```
## 環境チェック

✅ Node.js: v20.10.0
✅ npm: 10.2.0
❌ Playwrightがインストールされていません

以下のコマンドでインストールしてください:
  npm install -D playwright
  npx playwright install
```

### 失敗時（ブラウザ未インストール）

```
## 環境チェック

✅ Node.js: v20.10.0
✅ npm: 10.2.0
✅ Playwright: 1.40.0
❌ ブラウザ webkit がインストールされていません

以下のコマンドでインストールしてください:
  npx playwright install webkit
```

## 環境情報の記録

チェック成功後、以下の情報を result.json に記録する。

```json
{
  "environment": {
    "node_version": "20.10.0",
    "npm_version": "10.2.0",
    "playwright_version": "1.40.0",
    "browser": {
      "name": "chromium",
      "version": "120.0.6099.71",
      "headless": true
    },
    "os": {
      "platform": "darwin",
      "version": "14.1.2"
    },
    "check_timestamp": "2026-01-30T10:00:00Z"
  }
}
```

## 関連コマンド

```bash
# Node.js/npm バージョン
node --version
npm --version

# Playwright バージョン
npx playwright --version

# インストール済みブラウザ一覧
npx playwright install --list

# ブラウザのインストール状態
npx playwright install --check

# 特定ブラウザのインストール
npx playwright install chromium
npx playwright install firefox
npx playwright install webkit

# 全ブラウザのインストール
npx playwright install
```

## オプション環境変数

```bash
# ブラウザキャッシュ場所
PLAYWRIGHT_BROWSERS_PATH=/path/to/browsers

# プロキシ設定
HTTPS_PROXY=http://proxy.example.com:8080

# タイムアウト設定（ミリ秒）
PLAYWRIGHT_TIMEOUT=60000
```
