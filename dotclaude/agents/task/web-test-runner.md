# Agent: web-test-runner

## Metadata

- **ID**: web-test-runner
- **Base Type**: general
- **Category**: task

## Purpose

自然言語で記述されたテストシナリオを解釈し、PlaywrightでWebアプリケーションのUIテストを実行する。
アクセシビリティツリーとDOMを使って要素を自動特定し、エビデンス（スクリーンショット、DOM、アクセシビリティツリー）を収集する。

## Context

### Input

- `scenario`: YAMLシナリオファイルのパス（必須）
- `browser`: 使用ブラウザ（chromium, firefox, webkit）（オプション、デフォルト: chromium）
- `headless`: ヘッドレスモードで実行（オプション、デフォルト: true）
- `output_dir`: 結果出力ディレクトリ（オプション）

### Reference Files

- `.claude/skills/uiai-web-test/references/playwright-commands.md`
- `.claude/skills/uiai-web-test/references/scenario-schema.md`

## Capabilities

1. **自然言語解釈** - `do` アクションを解析してPlaywright操作に変換
2. **UI要素特定** - アクセシビリティツリー/DOMから要素を自動特定
3. **エビデンス収集** - 各ステップのスクリーンショット/DOM/a11yツリーを保存
4. **結果記録** - JSON形式で実行結果を出力

## Instructions

### 1. 事前準備

```javascript
const { chromium, firefox, webkit } = require('playwright');

// ブラウザ選択
const browserType = browser === 'firefox' ? firefox
                  : browser === 'webkit' ? webkit
                  : chromium;

// ブラウザ起動
const browserInstance = await browserType.launch({
  headless: headless === 'true'
});

// コンテキスト作成
const context = await browserInstance.newContext({
  viewport: { width: 1280, height: 720 },
  locale: 'ja-JP'
});

// ページ作成
const page = await context.newPage();
```

### 2. シナリオ読み込み

```yaml
# 例: シナリオ構造
name: "テスト名"
app:
  web: "https://example.com"
steps:
  - id: "セクション"
    actions:
      - do: "アクション"
      - then: "期待結果"
```

### 3. ステップ実行ループ

各ステップを順次処理：

```
for step in steps:
  if step.id:
    # セクション開始（ログのみ）
    log("=== Section: ${step.id} ===")
    continue

  if step.do:
    # 1. 実行前スクリーンショット
    await page.screenshot({ path: "${step_num}_before.png" })

    # 2. DOM取得
    const html = await page.content()
    writeFile("${step_num}_dom.html", html)

    # 3. アクセシビリティツリー取得
    const a11y = await page.accessibility.snapshot()
    writeFile("${step_num}_a11y.json", JSON.stringify(a11y, null, 2))

    # 4. アクション解釈・実行
    await execute_action(step.do)

    # 5. 待機（指定時）
    if step.wait:
      await page.waitForTimeout(step.wait * 1000)

    # 6. 実行後スクリーンショット
    await page.screenshot({ path: "${step_num}_after.png" })

    # 7. 結果記録
    record_step_result(step)
```

### 4. 自然言語アクション解釈

`do` の内容を解析して適切なPlaywright操作を実行：

#### ナビゲーション

```
パターン: "Open https://...", "Open /path"
→ await page.goto(url)

パターン: "Go to /path"
→ await page.goto(baseUrl + path)

パターン: "Refresh the page"
→ await page.reload()

パターン: "Go back"
→ await page.goBack()
```

#### クリック

```
パターン: "Click 'XXX' button", "Click 'XXX' link"

1. ロケーターで要素を検索
   - getByRole('button', { name: 'XXX' })
   - getByRole('link', { name: 'XXX' })
   - getByText('XXX')
2. await locator.click()
```

#### 入力

```
パターン: "Enter 'YYY' in XXX field"

1. 入力フィールドを特定
   - getByLabel('XXX')
   - getByPlaceholder('XXX')
   - getByRole('textbox', { name: 'XXX' })
2. await locator.fill('YYY')
```

#### 選択

```
パターン: "Select 'YYY' from XXX dropdown"

1. セレクトボックスを特定
   - getByLabel('XXX')
   - getByRole('combobox', { name: 'XXX' })
2. await locator.selectOption('YYY')
```

#### チェックボックス

```
パターン: "Check 'XXX' checkbox"
→ await page.getByLabel('XXX').check()

パターン: "Uncheck 'XXX' checkbox"
→ await page.getByLabel('XXX').uncheck()
```

#### スクロール

```
パターン: "Scroll down", "Scroll up"
→ await page.evaluate(() => window.scrollBy(0, 500))

パターン: "Scroll to 'XXX'"
→ await page.getByText('XXX').scrollIntoViewIfNeeded()
```

#### 待機

```
パターン: "Wait N seconds"
→ await page.waitForTimeout(N * 1000)

パターン: "Wait for loading to finish"
→ await page.waitForLoadState('networkidle')
```

### 5. UI要素特定アルゴリズム

```javascript
async function findElement(description, page) {
  /**
   * 自然言語の説明からUI要素を特定
   *
   * Args:
   *   description: "'Login' button" など
   *   page: Playwright Page オブジェクト
   *
   * Returns:
   *   Locator オブジェクト
   */

  // 1. 引用符内のテキストを抽出
  const targetText = extractQuotedText(description) // "Login"

  // 2. 要素タイプを推定
  const elementType = inferElementType(description) // "button", "link", "textbox" など

  // 3. ロケーターを試行（優先順位順）
  const strategies = [
    // ロール + テキスト
    () => page.getByRole(elementType, { name: targetText }),
    // ラベル
    () => page.getByLabel(targetText),
    // プレースホルダー
    () => page.getByPlaceholder(targetText),
    // テキスト
    () => page.getByText(targetText, { exact: true }),
    // 部分一致テキスト
    () => page.getByText(targetText)
  ]

  for (const strategy of strategies) {
    const locator = strategy()
    if (await locator.count() > 0) {
      return locator.first()
    }
  }

  throw new ElementNotFoundError(description)
}

function inferElementType(description) {
  if (/button/i.test(description)) return 'button'
  if (/link/i.test(description)) return 'link'
  if (/field|input|textbox/i.test(description)) return 'textbox'
  if (/checkbox/i.test(description)) return 'checkbox'
  if (/dropdown|select/i.test(description)) return 'combobox'
  return 'generic'
}
```

### 6. エビデンス収集

```javascript
// スクリーンショット
async function captureScreenshot(page, filename) {
  await page.screenshot({ path: `${OUTPUT_DIR}/${filename}`, fullPage: false })
}

// DOM
async function captureDOM(page, filename) {
  const html = await page.content()
  fs.writeFileSync(`${OUTPUT_DIR}/${filename}`, html)
}

// アクセシビリティツリー
async function captureA11y(page, filename) {
  const snapshot = await page.accessibility.snapshot()
  fs.writeFileSync(`${OUTPUT_DIR}/${filename}`, JSON.stringify(snapshot, null, 2))
}
```

### 7. 結果JSON出力

```json
{
  "scenario": {
    "name": "ログインテスト",
    "file": "test/scenarios/login.yaml"
  },
  "browser": {
    "name": "chromium",
    "version": "120.0.6099.71",
    "headless": true
  },
  "execution": {
    "start_time": "2026-01-30T10:00:00Z",
    "end_time": "2026-01-30T10:01:30Z"
  },
  "steps": [
    {
      "index": 1,
      "section": "ログイン",
      "do": "Open /login page",
      "then": "Login form is displayed",
      "status": "executed",
      "action_type": "navigate",
      "playwright_action": "page.goto('https://example.com/login')",
      "evidence": {
        "screenshot_before": "01_before.png",
        "screenshot_after": "01_after.png",
        "dom": "01_dom.html",
        "a11y": "01_a11y.json"
      }
    },
    {
      "index": 2,
      "section": "ログイン",
      "do": "Click 'Login' button",
      "status": "executed",
      "action_type": "click",
      "target_element": {
        "role": "button",
        "name": "Login",
        "locator": "getByRole('button', { name: 'Login' })"
      },
      "playwright_action": "page.getByRole('button', { name: 'Login' }).click()",
      "evidence": {
        "screenshot_before": "02_before.png",
        "screenshot_after": "02_after.png",
        "dom": "02_dom.html",
        "a11y": "02_a11y.json"
      }
    }
  ],
  "output_dir": ".web-test/results/20260130_100000/login_test"
}
```

## Output Format

### 成功時

```
## Test Execution Complete

**Scenario**: ログインテスト
**Browser**: chromium (headless)
**Steps**: 5 executed

### Execution Log

| # | Section | Action | Status |
|---|---------|--------|--------|
| 1 | ログイン | Open /login page | ✅ |
| 2 | ログイン | Enter email | ✅ |
| 3 | ログイン | Enter password | ✅ |
| 4 | ログイン | Click 'Login' button | ✅ |
| 5 | 確認 | Dashboard is displayed | ✅ |

### Evidence

Output: `.web-test/results/20260130_100000/login_test/`

### Next Step

Run `web-test-evaluator` to verify assertions (`then` conditions).
```

### エラー時

```
## Execution Failed

**Failed at step 3**: Click 'Submit' button

### Error

Element not found: 'Submit' button

The element could not be found on the page.

Tried locators:
- getByRole('button', { name: 'Submit' })
- getByText('Submit')

Screenshot saved: `03_before.png`

### Partial Results

Steps executed: 2/5
Evidence collected: Yes
```

## Error Handling

### 要素が見つからない

1. スクリーンショットを保存
2. DOMを保存
3. エラーログに詳細を記録
4. 次のステップに進む or 停止（設定による）

### タイムアウト

1. デフォルト30秒で要素検索を打ち切り
2. ネットワークアイドル待機は60秒でタイムアウト

### ナビゲーションエラー

1. ページロード失敗時はエラーをログ
2. ネットワークエラーの詳細を記録
