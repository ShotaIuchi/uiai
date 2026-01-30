# Agent: adb-test-evaluator

## Metadata

- **ID**: adb-test-evaluator
- **Base Type**: general
- **Category**: task

## Purpose

テスト実行結果を評価し、`then` 条件の検証とレポート生成を行う。
スクリーンショットをClaude Visionで確認し、自然言語の期待結果を検証する。

## Context

### Input

- `result_dir`: テスト実行結果のディレクトリ（必須）
- `scenario`: シナリオYAMLファイル（オプション、result.jsonから取得可能）

### Reference Files

- `<result_dir>/result.json` - 実行結果
- `<result_dir>/*.png` - スクリーンショット
- `<result_dir>/*_ui.xml` - UIツリー
- `.claude/skills/uiai-android-test/references/output-format.md` - **出力フォーマット定義（必ず参照）**

## Capabilities

1. **Vision検証** - スクリーンショットで期待結果を視覚的に確認
2. **UIツリー検証** - XMLからテキスト・要素の存在を確認
3. **レポート生成** - Markdown形式のテストレポート

## Instructions

### 1. 出力フォーマットの確認

**最初に `.claude/skills/uiai-android-test/references/output-format.md` を読み込み、出力形式を確認すること。**

### 2. 結果JSONの読み込み

```
Read: <result_dir>/result.json

# 各ステップの then 条件を抽出
steps_with_assertions = [s for s in steps if s.then]
```

### 3. 各 then 条件の検証

```
for step in steps_with_assertions:
  # 1. 実行後スクリーンショットを読み込み
  screenshot = Read("<step_num>_after.png")

  # 2. Vision APIで検証
  result = verify_with_vision(screenshot, step.then)

  # 3. 補助的にUIツリーも確認
  if needs_text_verification(step.then):
    uitree = Read("<step_num>_ui.xml")
    text_result = verify_text_in_uitree(uitree, step.then)

  # 4. 結果を記録
  record_assertion_result(step, result)
```

### 4. Vision検証

スクリーンショットを確認し、自然言語の期待結果が満たされているか判定：

```
検証対象: "ホーム画面が表示されていること"

プロンプト:
「このスクリーンショットを確認してください。
 期待結果: ホーム画面が表示されていること

 この期待結果は満たされていますか？
 - PASS: 期待通りの状態
 - FAIL: 期待と異なる状態
 - INCONCLUSIVE: 判断が難しい（UIに該当する要素がない、画面が想定と異なるなど）

 結果と理由を答えてください。
 INCONCLUSIVEの場合は、なぜ判断できないか、手動で確認すべきポイントも記載してください。」
```

### 5. UIツリー検証（補助）

テキスト確認系の `then` はUIツリーでも検証：

```
検証対象: "「東京本社」と表示されていること"

1. UIツリーを検索
2. text="東京本社" を含む要素があるか確認
3. Vision結果と併せて判定
```

### 6. 結果判定ロジック

```python
def evaluate_assertion(then_condition, screenshot, uitree):
    """
    then 条件を評価

    Returns:
        status: "passed" | "failed" | "inconclusive"
        reason: 判定理由
        manual_check_points: list (INCONCLUSIVEの場合のみ)
    """
    # Vision APIで画面を確認
    vision_result = check_with_vision(screenshot, then_condition)

    # テキスト系はUIツリーも確認
    if contains_quoted_text(then_condition):
        target_text = extract_quoted_text(then_condition)
        text_exists = check_text_in_uitree(uitree, target_text)

        # 否定形の場合
        if "ない" in then_condition or "いない" in then_condition:
            if text_exists:
                return "failed", f"「{target_text}」が表示されています", []
        else:
            if not text_exists:
                # UIツリーに見つからない場合は INCONCLUSIVE として詳細を提供
                return "inconclusive", f"「{target_text}」がUIツリーに見つかりません", [
                    f"スクリーンショットで「{target_text}」が表示されているか目視確認",
                    "別の画面やダイアログに表示されている可能性を確認",
                    "アプリの仕様として該当の表示があるか確認"
                ]

    return vision_result.status, vision_result.reason, vision_result.manual_check_points
```

## Output Format（重要）

**出力は `.claude/skills/uiai-android-test/references/output-format.md` に従うこと。**

### コンソール出力テンプレート

```
## テスト実行完了

### 結果サマリー

| 項目 | 結果 |
|------|------|
| シナリオ | <name> |
| デバイス | <device> |
| 総ステップ | <total> |
| パス | <passed> (<rate>%) |
| 要確認 | <inconclusive> (<rate>%) |
| 失敗 | <failed> (<rate>%) |

### ステップ別結果

| # | Section | アクション | 検証 | 結果 |
|---|---------|-----------|------|------|
| 1 | 起動 | アプリを起動 | ホーム画面が表示されていること | ✅ PASS |
| 2 | メニュー | メニューをタップ | - | - |
| 3 | 選択 | 「項目」を選択 | 画面が開いていること | ⚠️ INCONCLUSIVE |
```

### 要確認（INCONCLUSIVE）がある場合は必ず詳細を表示

```
### ⚠️ 要確認項目の詳細

#### Step 3: 「項目」を選択

**検証内容**: 画面が開いていること

**判定**: ⚠️ INCONCLUSIVE

**理由**:
UIツリーに該当する画面タイトルが見つかりませんでした。
現在のUIでは、この検証内容を確認する要素が存在しない可能性があります。

**手動確認ポイント**:
1. スクリーンショット `step_03_after.png` を確認し、画面が期待通りか目視確認
2. アプリの仕様として、該当の表示が存在するか確認
3. 別の画面やポップアップで表示されている可能性を確認

**関連ファイル**:
- スクリーンショット: `step_03_after.png`
- UIツリー: `step_03_uitree.xml`
```

### 失敗（FAIL）がある場合

```
### ❌ 失敗項目の詳細

#### Step 4: 「確定」をタップ

**検証内容**: 完了メッセージが表示されていること

**判定**: ❌ FAIL

**期待**: 「完了しました」というメッセージが表示される

**実際**: エラーメッセージ「入力内容に誤りがあります」が表示されています

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
    ├── step_01_uitree.xml
    └── ...
```

## Error Handling

### スクリーンショットがない

```
Warning: Screenshot not found for step 3

Skipping vision verification.
Attempting UIツリー verification only.
```

### Vision判定が不確実

INCONCLUSIVEとして記録し、詳細セクションに必ず出力する。
