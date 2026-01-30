# Scenario YAML Schema (Web)

自然言語ベースのクロスプラットフォームUIテストシナリオ定義（Web拡張）。

## 基本構造

```yaml
name: "シナリオ名"
app:
  android: "com.example.app"      # Android パッケージ名
  ios: "com.example.App"          # iOS Bundle Identifier
  web: "https://example.com"      # Web ベースURL

steps:
  - id: "セクション名"
    actions:
      - do: "アクションの説明"
      - do: "アクションの説明"
        strict: true              # オプション: このアクションのみ厳格検証
      - then: "期待結果"
        strict: true              # オプション: この検証のみ厳格検証
```

## フィールド

| フィールド | 必須 | 説明 |
|-----------|------|------|
| `name` | ✅ | シナリオ名 |
| `app` | ✅ | アプリ識別子（オブジェクトまたは文字列） |
| `variables` | - | 変数定義（キー: 値のオブジェクト） |
| `steps` | ✅ | テストステップのリスト |

### app フィールド

プラットフォーム別にアプリ識別子を指定する。

**オブジェクト形式（推奨）**:

```yaml
app:
  android: "com.example.app"      # Android パッケージ名
  ios: "com.example.App"          # iOS Bundle Identifier
  web: "https://example.com"      # Web ベースURL
```

| サブフィールド | 説明 |
|---------------|------|
| `android` | Android パッケージ名（例: `com.example.app`） |
| `ios` | iOS Bundle Identifier（例: `com.example.App`） |
| `web` | WebアプリケーションのベースURL（例: `https://example.com`） |

**Web専用シナリオ**:

```yaml
app:
  web: "https://example.com"      # Webのみ
```

### variables フィールド

シナリオ内で再利用する値を変数として定義する。

```yaml
variables:
  email: "test@example.com"
  password: "password123"
  base_url: "https://example.com"
```

**変数名のルール**:
- 英字またはアンダースコアで始まる
- 英数字とアンダースコアのみ使用可能
- パターン: `[a-zA-Z_][a-zA-Z0-9_]*`

**変数の使用（補間）**:

`do` や `then` 内で `(variable_name)` 構文を使用して変数を参照する。

```yaml
variables:
  email: "test@example.com"
  password: "password123"

steps:
  - id: "Login"
    actions:
      - do: "Enter '(email)' in email field"
      - do: "Enter '(password)' in password field"
      - then: "User '(email)' is logged in"
```

**エスケープ**:

リテラルの括弧を使用する場合は `\(` と `\)` でエスケープする。

```yaml
steps:
  - id: "Math"
    actions:
      - do: "Enter '\(1+2\)' in formula field"   # → '(1+2)' として解釈
```

### steps 内の要素

| フィールド | 説明 |
|-----------|------|
| `id` | セクション/グループの識別子（任意の文字列） |
| `actions` | セクション内のアクションリスト |
| `replay` | 過去のセクションを再実行（`do`のみ実行、`then`はスキップ） |

### actions 内の要素

| フィールド | 説明 |
|-----------|------|
| `do` | 実行するアクション（自然言語） |
| `then` | 期待結果・検証内容（自然言語） |
| `wait` | 待機時間（秒）、オプション |
| `strict` | 厳格モード（この要素のみ完全一致検証、オプション）|

## 例

### Web基本テスト

```yaml
name: "ログインテスト"
app:
  web: "https://example.com"

steps:
  - id: "ログイン"
    actions:
      - do: "Open /login page"
      - do: "Enter 'test@example.com' in email field"
      - do: "Enter 'password123' in password field"
      - do: "Click 'Login' button"
      - then: "Dashboard is displayed"
```

### 変数を使ったWebテスト

```yaml
name: "ログインテスト（変数使用）"
app:
  web: "https://example.com"

variables:
  email: "test@example.com"
  password: "password123"
  welcome_message: "Welcome, Test User"

steps:
  - id: "Login"
    actions:
      - do: "Open /login page"
      - do: "Enter '(email)' in email field"
      - do: "Enter '(password)' in password field"
      - do: "Click 'Login' button"
      - then: "'(welcome_message)' is displayed"
```

変数を使うことで、テストデータを一箇所で管理し、複数のステップで再利用できる。

### クロスプラットフォームテスト

```yaml
name: "ログインテスト"
app:
  android: "com.example.app"
  ios: "com.example.App"
  web: "https://example.com"

steps:
  - id: "ログイン"
    actions:
      - do: "アプリを起動"           # モバイル: アプリ起動、Web: ベースURLに遷移
      - do: "「ログイン」をタップ"    # モバイル: タップ、Web: クリック
      - then: "ホーム画面が表示されていること"
```

### Web固有の操作

```yaml
name: "Webフォームテスト"
app:
  web: "https://example.com"

steps:
  - id: "フォーム入力"
    actions:
      - do: "Open /contact page"
      - do: "Enter 'John Doe' in name field"
      - do: "Enter 'john@example.com' in email field"
      - do: "Select 'Support' from category dropdown"
      - do: "Enter 'Hello, I need help with...' in message textarea"
      - do: "Check 'I agree to terms' checkbox"
      - do: "Click 'Submit' button"
      - then: "'Thank you for your message' is displayed"

  - id: "バリデーションエラー"
    actions:
      - do: "Open /contact page"
      - do: "Click 'Submit' button"
      - then: "'Email is required' error is displayed"
```

## 自然言語アクションの書き方（Web）

### ナビゲーション系

```
Open https://example.com
Open /login page
Go to /dashboard
Refresh the page
Go back
Go forward
```

### クリック系

```
Click 'Login' button
Click the submit link
Click 'Continue' link
Click on the logo
Double-click the item
Right-click the element
```

### 入力系

```
Enter 'test@example.com' in email field
Type 'Hello' in search box
Clear the input field
Press Enter key
Press Tab key
```

### 選択系

```
Select 'Japan' from country dropdown
Check 'Remember me' checkbox
Uncheck 'Newsletter' checkbox
Select 'Option A' radio button
```

### スクロール系

```
Scroll down
Scroll up
Scroll to 'Contact' section
Scroll to the bottom of the page
Scroll to the top
```

### 待機系

```
Wait 3 seconds
Wait for loading to finish
Wait for 'Success' message to appear
Wait for the spinner to disappear
```

### ファイル系

```
Upload 'document.pdf' to file input
Upload multiple files: 'file1.png', 'file2.png'
```

### ホバー/フォーカス系

```
Hover over 'Menu' item
Focus on email input
```

## 期待結果（then）の書き方（Web）

### 画面確認

```
Dashboard is displayed
Login page is shown
Error page is not displayed
```

### 要素確認

```
'Welcome, John' is visible
'Submit' button is enabled
'Delete' button is disabled
'Remember me' checkbox is checked
```

### URL確認

```
URL contains '/dashboard'
URL is 'https://example.com/success'
URL matches '/users/[0-9]+'
```

### テキスト確認

```
Page contains 'Welcome'
'Error: Invalid email' is displayed
'Success' message appears
```

### 状態確認

```
Form is submitted successfully
User is logged in
Cart has 3 items
```

## 日本語と英語の混在

シナリオは日本語でも英語でも記述可能。Web向けには英語が推奨されるが、チームの好みに合わせて選択可能。

```yaml
# 日本語
steps:
  - id: "ログイン"
    actions:
      - do: "/loginページを開く"
      - do: "メールフィールドに「test@example.com」を入力"
      - do: "「ログイン」ボタンをクリック"
      - then: "ダッシュボードが表示されていること"

# 英語
steps:
  - id: "Login"
    actions:
      - do: "Open /login page"
      - do: "Enter 'test@example.com' in email field"
      - do: "Click 'Login' button"
      - then: "Dashboard is displayed"
```

## 厳格モード（Strict Mode）

`strict: true` を指定すると、検証が**DOM完全一致**で行われる。

### 通常モード（デフォルト）

- Vision APIで意味的に判定
- 柔軟だが、厳密な判定が必要な場合に不向き

### 厳格モード

- DOMのテキストで**完全一致**検証
- `then` 内の引用符で囲まれた文字列がDOMのテキストに**そのまま存在**するかをチェック

```yaml
steps:
  - id: "確認"
    actions:
      - do: "Click 'Submit' button"
      - then: "'Order #12345 confirmed' is displayed"
        strict: true              # DOM完全一致検証
```

## オプション設定

```yaml
name: "テスト名"
app:
  web: "https://example.com"

config:
  timeout: 60                     # 全体タイムアウト（秒）
  strict: true                    # 厳格モード（全do/thenで完全一致検証）
  viewport:
    width: 1280
    height: 720
  locale: "ja-JP"
  timezone: "Asia/Tokyo"

steps:
  - id: "テスト"
    actions:
      - do: "..."
```

## 注意事項

- `app.web` はベースURLとして使用される（`/` で始まるパスはこれに連結される）
- モバイルとWebで同じシナリオを共有する場合、プラットフォーム固有のアクションに注意
  - モバイル: `タップ`、`スワイプ`、`戻るボタン`
  - Web: `クリック`、`スクロール`、`Go back`
- Playwrightの自動待機機能により、明示的な `wait` は多くの場合不要
