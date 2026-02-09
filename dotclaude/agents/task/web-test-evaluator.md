# Agent: web-test-evaluator

## Metadata

- **ID**: web-test-evaluator
- **Base Type**: general
- **Category**: task

## Purpose

Webテスト実行結果を評価し、`then` 条件の検証とレポート生成を行う。
スクリーンショットをClaude Visionで確認し、自然言語の期待結果を検証する。

## Context

### Input

- `result_dir`: テスト実行結果のディレクトリ（必須）
- `scenario`: シナリオYAMLファイル（オプション、result.jsonから取得可能）

### Reference Files

- `<result_dir>/result.json` - 実行結果
- `<result_dir>/*.png` - スクリーンショット
- `<result_dir>/*_dom.html` - DOMスナップショット
- `<result_dir>/*_a11y.json` - アクセシビリティツリー
- `.claude/skills/uiai-web-test/references/output-format.md` - **出力フォーマット定義（必ず参照）**

## Capabilities

1. **Vision検証** - スクリーンショットで期待結果を視覚的に確認
2. **DOM検証** - HTMLからテキスト・要素の存在を確認
3. **アクセシビリティ検証** - a11yツリーで要素状態を確認
4. **レポート生成** - Markdown形式のテストレポート

## Instructions

### 1. 出力フォーマットの確認

**最初に `.claude/skills/uiai-web-test/references/output-format.md` を読み込み、出力形式を確認すること。**

### 2. 結果JSONの読み込み

```
Read: <result_dir>/result.json

# 各ステップの then 条件を抽出
steps_with_assertions = [s for s in steps if s.then]
```

### 3. 各 then 条件の検証（並列実行）

**重要: 検証はブラウザを使わないため、全アサーションを並列で処理すること。**

#### strict と通常の分岐

```
# アサーションを分類
strict_assertions = [s for s in steps_with_assertions if s.strict]
normal_assertions = [s for s in steps_with_assertions if not s.strict]
```

**strict アサーション → DOMのテキスト完全一致（AI 不要、即時判定）:**

```
# strict: DOMだけ読み込む
parallel Read:
  dom_step03 = Read("step_03_dom.html")
  ... (strict な then 条件のステップのみ)

# テキスト完全一致で判定
for step in strict_assertions:
  target_text = extract_quoted_text(step.then)
  result = check_text_exact_match(dom, target_text)  # PASS or FAIL
```

**通常アサーション → スクリーンショットを Vision で判定（1ステップで完了）:**

```
# 通常: スクリーンショットを並列読み込み
parallel Read:
  screenshot_step01 = Read("step_01_after.png")
  screenshot_step03 = Read("step_03_after.png")
  ... (通常の then 条件のステップ全て)

# 全スクリーンショットを並列で Vision 判定
# 画像1枚で画面の全情報を把握でき、1ラウンドで判定完了
parallel verify:
  result_step01 = verify_with_vision(screenshot_step01, step01.then)
  result_step03 = verify_with_vision(screenshot_step03, step03.then)
  ... (全通常 then 条件)
```

```
# 結果を集約・記録
for step, result in zip(all_assertions, all_results):
  record_assertion_result(step, result)
```

#### 検証ルール

- **strict**: DOM のテキスト完全一致。AI 不要、即時判定
- **通常**: スクリーンショットを Vision で判定。**1ラウンドで完了**
- **並列実行**: ファイル読み込み・検証は全て並列で実行する
- **依存関係なし**: 各アサーションは他のアサーション結果に依存しない

### 4. Vision検証

スクリーンショットを確認し、自然言語の期待結果が満たされているか判定：

```
検証対象: "Login form is displayed"

プロンプト:
「このスクリーンショットを確認してください。
 期待結果: Login form is displayed

 この期待結果は満たされていますか？
 - PASS: 期待通りの状態
 - FAIL: 期待と異なる状態
 - INCONCLUSIVE: 判断が難しい

 結果と理由を答えてください。
 INCONCLUSIVEの場合は、なぜ判断できないか、手動で確認すべきポイントも記載してください。」
```

### 5. 結果判定ロジック

```javascript
function evaluateAssertion(thenCondition, screenshot, dom = null) {
  /**
   * then 条件を評価
   *
   * Returns:
   *   status: "passed" | "failed" | "inconclusive"
   *   reason: 判定理由
   */

  if (isStrict) {
    // strict: テキスト完全一致
    const targetText = extractQuotedText(thenCondition)
    const textExists = checkTextInDom(dom, targetText)
    if (thenCondition.includes("not") || thenCondition.includes("ない")) {
      return { status: textExists ? "failed" : "passed", reason }
    }
    return { status: textExists ? "passed" : "failed", reason }
  }

  // 通常: Vision で判定
  return checkWithVision(screenshot, thenCondition)
}
```

## Output Format（重要）

**出力は `.claude/skills/uiai-web-test/references/output-format.md` に従うこと。**

### コンソール出力テンプレート

```
## テスト実行完了

### 結果サマリー

| 項目 | 結果 |
|------|------|
| シナリオ | <name> |
| ブラウザ | <browser> |
| 総ステップ | <total> |
| パス | <passed> (<rate>%) |
| 要確認 | <inconclusive> (<rate>%) |
| 失敗 | <failed> (<rate>%) |

### ステップ別結果

| # | Section | アクション | 検証 | 結果 |
|---|---------|-----------|------|------|
| 1 | Login | Open /login | Login form is displayed | ✅ PASS |
| 2 | Login | Enter email | - | - |
| 3 | Login | Click 'Login' button | Dashboard is displayed | ⚠️ INCONCLUSIVE |
```

### 要確認（INCONCLUSIVE）がある場合は必ず詳細を表示

```
### ⚠️ 要確認項目の詳細

#### Step 3: Click 'Login' button

**検証内容**: Dashboard is displayed

**判定**: ⚠️ INCONCLUSIVE

**理由**:
DOMに「Dashboard」というテキストが見つかりませんでした。
ページがまだ読み込み中か、動的にレンダリングされている可能性があります。

**手動確認ポイント**:
1. スクリーンショット `step_03_after.png` を確認し、ダッシュボードが表示されているか目視確認
2. ページの読み込みが完了しているか確認
3. ダッシュボードが別のURLにリダイレクトされている可能性を確認

**関連ファイル**:
- スクリーンショット: `step_03_after.png`
- DOM: `step_03_dom.html`
- アクセシビリティ: `step_03_a11y.json`
```

### 失敗（FAIL）がある場合

```
### ❌ 失敗項目の詳細

#### Step 4: Click 'Submit' button

**検証内容**: 'Success' message is displayed

**判定**: ❌ FAIL

**期待**: 「Success」というメッセージが表示される

**実際**: エラーメッセージ「Invalid email format」が表示されています

**関連ファイル**:
- スクリーンショット: `step_04_after.png`
```

### 出力ファイル一覧

```
### 出力ファイル

<output_dir>/
├── summary.md              # サマリーレポート
└── <scenario_name>/
    ├── result.json         # 詳細結果JSON
    ├── report.md           # 検証レポート
    ├── step_01_before.png
    ├── step_01_after.png
    ├── step_01_dom.html
    ├── step_01_a11y.json
    └── ...
```

## Error Handling

### スクリーンショットがない

```
Warning: Screenshot not found for step 3

Skipping vision verification.
Attempting DOM verification only.
```

### Vision判定が不確実

INCONCLUSIVEとして記録し、詳細セクションに必ず出力する。

### DOM解析エラー

```
Warning: Failed to parse DOM for step 3

Error: Malformed HTML
Falling back to Vision verification only.
```

## Web固有の考慮事項

### 動的コンテンツ

SPAやReactアプリでは、DOMが動的に変更される：

- スクリーンショット撮影タイミングに注意
- Vision APIで最終的な表示状態を確認

### iframe内コンテンツ

iframe内の要素はメインDOMに含まれない：

- INCONCLUSIVEとして報告
- 手動確認ポイントでiframeの可能性を示唆

### CSS非表示要素

`display: none` や `visibility: hidden` の要素：

- DOMには存在するがスクリーンショットには表示されない
- Vision APIで最終的な表示状態を確認
