# Playwright Commands Reference

Playwright CLIおよびAPIコマンドリファレンス。
Web UIテスト自動化で使用する主要コマンドを記載。

## インストール

### Playwright インストール

```bash
# npm でインストール
npm install -D playwright

# または pnpm
pnpm add -D playwright

# または yarn
yarn add -D playwright
```

### ブラウザインストール

```bash
# 全ブラウザをインストール
npx playwright install

# 特定のブラウザのみ
npx playwright install chromium
npx playwright install firefox
npx playwright install webkit
```

## ナビゲーション

### ページ遷移

```javascript
// URLに遷移
await page.goto('https://example.com');

// 相対パスに遷移（baseURLが設定されている場合）
await page.goto('/dashboard');

// オプション付き
await page.goto('https://example.com', {
  waitUntil: 'networkidle',  // 'load' | 'domcontentloaded' | 'networkidle'
  timeout: 30000
});
```

### ページ操作

```javascript
// リロード
await page.reload();

// 戻る
await page.goBack();

// 進む
await page.goForward();
```

### URL取得

```javascript
// 現在のURL
const url = page.url();

// URLの確認
await expect(page).toHaveURL(/dashboard/);
await expect(page).toHaveURL('https://example.com/dashboard');
```

## 要素特定

### ロケーター（推奨）

```javascript
// ロール（アクセシビリティ）
page.getByRole('button', { name: 'Submit' })
page.getByRole('link', { name: 'Home' })
page.getByRole('textbox', { name: 'Email' })
page.getByRole('checkbox', { name: 'Agree' })

// ラベル
page.getByLabel('Email')
page.getByLabel('Password')

// プレースホルダー
page.getByPlaceholder('Enter your email')

// テキスト
page.getByText('Welcome')
page.getByText('Login', { exact: true })

// テストID
page.getByTestId('submit-button')

// Alt テキスト（画像）
page.getByAltText('Company logo')

// Title 属性
page.getByTitle('Close dialog')
```

### CSSセレクタ（フォールバック）

```javascript
// CSS セレクタ
page.locator('button.submit')
page.locator('#login-form input[type="email"]')
page.locator('[data-testid="submit"]')

// 複合
page.locator('form').getByRole('button', { name: 'Submit' })
```

### ロケーターフィルタリング

```javascript
// テキストでフィルタ
page.getByRole('listitem').filter({ hasText: 'Product 1' })

// 子要素でフィルタ
page.getByRole('listitem').filter({ has: page.getByRole('button') })

// n番目の要素
page.getByRole('listitem').nth(2)
page.getByRole('listitem').first()
page.getByRole('listitem').last()
```

## 入力操作

### クリック

```javascript
// シングルクリック
await page.getByRole('button', { name: 'Submit' }).click();

// ダブルクリック
await page.getByRole('button').dblclick();

// 右クリック
await page.getByRole('button').click({ button: 'right' });

// 座標指定クリック
await page.getByRole('button').click({ position: { x: 10, y: 10 } });

// 修飾キー付き
await page.getByRole('button').click({ modifiers: ['Shift'] });
```

### テキスト入力

```javascript
// テキスト入力（既存テキストをクリアして入力）
await page.getByLabel('Email').fill('test@example.com');

// 一文字ずつ入力（タイピングをシミュレート）
await page.getByLabel('Email').type('test@example.com');

// クリアのみ
await page.getByLabel('Email').clear();

// プレスキー
await page.getByLabel('Search').press('Enter');
```

### 選択・チェック

```javascript
// セレクトボックス
await page.getByLabel('Country').selectOption('Japan');
await page.getByLabel('Country').selectOption({ label: 'Japan' });
await page.getByLabel('Country').selectOption({ value: 'jp' });

// チェックボックス
await page.getByLabel('Agree to terms').check();
await page.getByLabel('Agree to terms').uncheck();

// ラジオボタン
await page.getByLabel('Option A').check();
```

### ファイルアップロード

```javascript
// 単一ファイル
await page.getByLabel('Upload').setInputFiles('path/to/file.pdf');

// 複数ファイル
await page.getByLabel('Upload').setInputFiles(['file1.pdf', 'file2.pdf']);

// クリア
await page.getByLabel('Upload').setInputFiles([]);
```

## スクロール

```javascript
// 要素までスクロール
await page.getByText('Contact').scrollIntoViewIfNeeded();

// ページ全体をスクロール
await page.evaluate(() => window.scrollBy(0, 500));

// 要素内スクロール
await page.locator('.scrollable-container').evaluate(
  el => el.scrollTop = 100
);
```

## 待機

### 自動待機

Playwrightは多くの操作で自動待機が組み込まれている：

```javascript
// これらは要素が actionable になるまで自動待機
await page.getByRole('button').click();  // visible, stable, enabled まで待機
await page.getByLabel('Email').fill('test');  // visible, editable まで待機
```

### 明示的待機

```javascript
// 固定時間待機（非推奨だが必要な場合）
await page.waitForTimeout(3000);

// 要素が表示されるまで待機
await page.getByText('Success').waitFor();
await page.getByText('Success').waitFor({ state: 'visible' });

// 要素が非表示/削除されるまで待機
await page.getByText('Loading').waitFor({ state: 'hidden' });
await page.getByText('Loading').waitFor({ state: 'detached' });

// ネットワークアイドルまで待機
await page.waitForLoadState('networkidle');

// 特定のURLへの遷移を待機
await page.waitForURL('**/dashboard');
```

## スクリーンショット

### ページ全体

```javascript
// ページ全体
await page.screenshot({ path: 'screenshot.png' });

// フルページ（スクロール含む）
await page.screenshot({ path: 'fullpage.png', fullPage: true });

// PNG/JPEG形式
await page.screenshot({ path: 'screenshot.jpeg', type: 'jpeg', quality: 80 });
```

### 要素スクリーンショット

```javascript
// 特定要素のみ
await page.getByRole('dialog').screenshot({ path: 'dialog.png' });
```

### オプション

```javascript
await page.screenshot({
  path: 'screenshot.png',
  fullPage: true,
  omitBackground: true,  // 透過背景
  clip: { x: 0, y: 0, width: 800, height: 600 }  // 範囲指定
});
```

## DOM/HTML取得

### HTML取得

```javascript
// ページ全体のHTML
const html = await page.content();

// 要素のHTML
const elementHtml = await page.getByRole('main').innerHTML();
const outerHtml = await page.getByRole('main').evaluate(el => el.outerHTML);
```

### テキスト取得

```javascript
// 要素のテキスト
const text = await page.getByRole('heading').textContent();

// 入力値
const value = await page.getByLabel('Email').inputValue();
```

### 属性取得

```javascript
// 属性値
const href = await page.getByRole('link').getAttribute('href');

// 複数の属性
const attrs = await page.getByRole('button').evaluate(el => ({
  id: el.id,
  class: el.className,
  disabled: el.disabled
}));
```

## アクセシビリティツリー

```javascript
// アクセシビリティスナップショット取得
const snapshot = await page.accessibility.snapshot();

// 特定要素のアクセシビリティ情報
const snapshot = await page.accessibility.snapshot({ root: page.getByRole('main') });

// JSON出力例
{
  "role": "WebArea",
  "name": "Example Page",
  "children": [
    { "role": "heading", "name": "Welcome", "level": 1 },
    { "role": "button", "name": "Login" }
  ]
}
```

## アサーション

### 要素アサーション

```javascript
// 可視性
await expect(page.getByRole('button')).toBeVisible();
await expect(page.getByRole('button')).toBeHidden();

// 有効/無効
await expect(page.getByRole('button')).toBeEnabled();
await expect(page.getByRole('button')).toBeDisabled();

// チェック状態
await expect(page.getByRole('checkbox')).toBeChecked();

// テキスト
await expect(page.getByRole('heading')).toHaveText('Welcome');
await expect(page.getByRole('heading')).toContainText('Welcome');

// 値
await expect(page.getByLabel('Email')).toHaveValue('test@example.com');

// 属性
await expect(page.getByRole('link')).toHaveAttribute('href', '/home');

// カウント
await expect(page.getByRole('listitem')).toHaveCount(5);
```

### ページアサーション

```javascript
// URL
await expect(page).toHaveURL('https://example.com/dashboard');
await expect(page).toHaveURL(/dashboard/);

// タイトル
await expect(page).toHaveTitle('Dashboard');
await expect(page).toHaveTitle(/Dashboard/);
```

## ブラウザコンテキスト

### ブラウザ起動

```javascript
// Chromium
const browser = await chromium.launch();

// Firefox
const browser = await firefox.launch();

// WebKit (Safari)
const browser = await webkit.launch();

// オプション
const browser = await chromium.launch({
  headless: false,     // ブラウザ表示
  slowMo: 100,        // 操作を遅くする（デバッグ用）
  devtools: true      // DevTools を開く
});
```

### ページ作成

```javascript
// 新規ブラウザコンテキスト
const context = await browser.newContext({
  viewport: { width: 1280, height: 720 },
  locale: 'ja-JP',
  timezoneId: 'Asia/Tokyo'
});

// 新規ページ
const page = await context.newPage();
```

### クリーンアップ

```javascript
await page.close();
await context.close();
await browser.close();
```

## CLI コマンド

### テスト実行

```bash
# 全テスト実行
npx playwright test

# 特定ファイル
npx playwright test tests/login.spec.ts

# ヘッドレス無効
npx playwright test --headed

# 特定ブラウザ
npx playwright test --project=chromium
npx playwright test --project=firefox

# デバッグモード
npx playwright test --debug
```

### コード生成

```bash
# コードジェネレーター起動
npx playwright codegen https://example.com

# 特定デバイスをエミュレート
npx playwright codegen --device="iPhone 13" https://example.com
```

### スクリーンショット

```bash
# URLのスクリーンショット取得
npx playwright screenshot https://example.com screenshot.png

# フルページ
npx playwright screenshot --full-page https://example.com fullpage.png
```

### PDF生成

```bash
npx playwright pdf https://example.com page.pdf
```

## ベストプラクティス

1. **ロケーターはアクセシビリティ優先** - `getByRole`, `getByLabel` を優先使用
2. **CSSセレクタは最終手段** - テストIDやロールで特定できない場合のみ
3. **明示的待機は避ける** - Playwrightの自動待機を活用
4. **スクリーンショットは操作前後に取得** - デバッグ用エビデンス
5. **アクセシビリティツリーを活用** - 要素特定のデバッグに有効
