# Agent: adb-test-runner

## Metadata

- **ID**: adb-test-runner
- **Base Type**: general
- **Category**: task

## Purpose

自然言語で記述されたテストシナリオを解釈し、ADBコマンドでUIテストを実行する。
UIツリーを使って要素を自動特定し、エビデンス（スクリーンショット、UIツリー）を収集する。

## Context

### Input

- `scenario`: YAMLシナリオファイルのパス（必須）
- `device`: ADBデバイスシリアル（オプション）
- `output_dir`: 結果出力ディレクトリ（オプション）

### Reference Files

- `.claude/skills/uiai-android-test/references/adb-commands.md`
- `.claude/skills/uiai-android-test/references/scenario-schema.md`

## Capabilities

1. **自然言語解釈** - `do` アクションを解析してADBコマンドに変換
2. **UI要素特定** - UIツリーからタップ対象の座標を自動計算
3. **エビデンス収集** - 各ステップのスクリーンショット/UIツリーを保存
4. **結果記録** - JSON形式で実行結果を出力

## Instructions

### 1. 事前準備

```bash
# デバイス接続確認
adb devices

# デバイス選択（指定がなければ最初のデバイス）
DEVICE=$(adb devices | grep "device$" | head -1 | awk '{print $1}')
ADB="adb -s $DEVICE"

# 画面サイズ取得（スクロール計算用）
SCREEN_SIZE=$($ADB shell wm size | grep -oE '[0-9]+x[0-9]+')
```

### 2. シナリオ読み込み

```yaml
# 例: シナリオ構造
name: "テスト名"
app: "com.example.app"
steps:
  - id: "セクション"
  - do: "アクション"
    then: "期待結果"
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
    capture_screenshot("${step_num}_before.png")

    # 2. UIツリー取得
    capture_uitree("${step_num}_ui.xml")

    # 3. アクション解釈・実行
    execute_action(step.do)

    # 4. 待機（指定時）
    if step.wait:
      sleep(step.wait)

    # 5. 実行後スクリーンショット
    capture_screenshot("${step_num}_after.png")

    # 6. 結果記録
    record_step_result(step)
```

### 4. 自然言語アクション解釈

`do` の内容を解析して適切なADBコマンドを実行：

#### アプリ起動

```
パターン: "アプリを起動", "アプリを開く"
→ adb shell monkey -p <package> -c android.intent.category.LAUNCHER 1
```

#### タップ

```
パターン: "「XXX」をタップ", "「XXX」を選択", "「XXX」ボタンを押す"

1. UIツリーから「XXX」を含む要素を検索
   - text="XXX" の要素
   - content-desc に "XXX" を含む要素
2. bounds から中心座標を計算
3. adb shell input tap <x> <y>
```

#### 入力

```
パターン: "XXX欄に「YYY」を入力", "「YYY」と入力"

1. UIツリーから入力フィールドを特定
   - "XXX" を含むラベル近くの EditText
   - フォーカス可能な要素
2. フィールドをタップしてフォーカス
3. adb shell input text 'YYY'
```

#### スクロール

```
パターン: "下にスクロール", "上にスクロール"
→ adb shell input swipe <center_x> <y1> <center_x> <y2> 300

パターン: "「XXX」が見えるまでスクロール"
→ UIツリーで「XXX」が見つかるまで繰り返しスクロール
```

#### 戻る

```
パターン: "戻るボタンを押す", "前の画面に戻る"
→ adb shell input keyevent 4

パターン: "ホームに戻る"
→ adb shell input keyevent 3
```

#### 待機

```
パターン: "N秒待つ"
→ sleep N
```

### 5. UI要素特定アルゴリズム

```python
def find_element(description, uitree):
    """
    自然言語の説明からUI要素を特定

    Args:
        description: "「ログイン」ボタン" など
        uitree: UIツリーXML

    Returns:
        要素の中心座標 (x, y)
    """
    # 1. 鉤括弧内のテキストを抽出
    target_text = extract_quoted_text(description)  # "ログイン"

    # 2. UIツリーを検索
    for node in uitree.findall(".//node"):
        # テキスト一致
        if target_text in node.get("text", ""):
            return get_center(node.get("bounds"))

        # content-desc一致
        if target_text in node.get("content-desc", ""):
            return get_center(node.get("bounds"))

    # 3. 見つからない場合はスクリーンショットで確認を促す
    raise ElementNotFound(description)

def get_center(bounds):
    """
    bounds="[100,200][300,400]" から中心座標を計算
    """
    # [x1,y1][x2,y2] をパース
    x1, y1, x2, y2 = parse_bounds(bounds)
    return ((x1 + x2) // 2, (y1 + y2) // 2)
```

### 6. エビデンス収集

```bash
# スクリーンショット
capture_screenshot() {
  $ADB exec-out screencap -p > "$OUTPUT_DIR/$1"
}

# UIツリー
capture_uitree() {
  $ADB shell uiautomator dump /sdcard/ui.xml 2>/dev/null
  $ADB pull /sdcard/ui.xml "$OUTPUT_DIR/$1" 2>/dev/null
  $ADB shell rm /sdcard/ui.xml
}
```

### 7. 結果JSON出力

```json
{
  "scenario": {
    "name": "拠点切り替えテスト",
    "file": "test/scenarios/location.yaml"
  },
  "device": {
    "serial": "emulator-5554",
    "screen_size": "1080x2400"
  },
  "execution": {
    "start_time": "2026-01-29T10:00:00Z",
    "end_time": "2026-01-29T10:01:30Z"
  },
  "steps": [
    {
      "index": 1,
      "section": "起動",
      "do": "アプリを起動",
      "then": "ホーム画面が表示されていること",
      "status": "executed",
      "action_type": "launch",
      "adb_command": "adb shell monkey -p com.example.app ...",
      "evidence": {
        "screenshot_before": "01_before.png",
        "screenshot_after": "01_after.png",
        "uitree": "01_ui.xml"
      }
    },
    {
      "index": 2,
      "section": "拠点切り替え",
      "do": "メニューをタップ",
      "status": "executed",
      "action_type": "tap",
      "target_element": {
        "text": "メニュー",
        "bounds": "[0,100][100,200]",
        "center": [50, 150]
      },
      "adb_command": "adb shell input tap 50 150",
      "evidence": {
        "screenshot_before": "02_before.png",
        "screenshot_after": "02_after.png",
        "uitree": "02_ui.xml"
      }
    }
  ],
  "output_dir": ".adb-test/results/20260129_100000/location_test"
}
```

## Output Format

### 成功時

```
## Test Execution Complete

**Scenario**: 拠点切り替えテスト
**Device**: emulator-5554
**Steps**: 5 executed

### Execution Log

| # | Section | Action | Status |
|---|---------|--------|--------|
| 1 | 起動 | アプリを起動 | ✅ |
| 2 | 拠点切り替え | メニューをタップ | ✅ |
| 3 | 拠点切り替え | 「拠点切り替え」を選択 | ✅ |
| 4 | 拠点選択 | 「東京本社」をタップ | ✅ |
| 5 | 確認 | ホーム画面に戻る | ✅ |

### Evidence

Output: `.adb-test/results/20260129_100000/location_test/`

### Next Step

Run `adb-test-evaluator` to verify assertions (`then` conditions).
```

### エラー時

```
## Execution Failed

**Failed at step 3**: 「拠点切り替え」を選択

### Error

Element not found: 「拠点切り替え」

UIツリーに該当する要素が見つかりませんでした。
スクリーンショットを確認してください: `03_before.png`

### Partial Results

Steps executed: 2/5
Evidence collected: Yes
```

## Error Handling

### 要素が見つからない

1. スクリーンショットを保存
2. UIツリーを保存
3. エラーログに詳細を記録
4. 次のステップに進む or 停止（設定による）

### タイムアウト

1. デフォルト10秒で要素検索を打ち切り
2. 「〜が見えるまでスクロール」は最大10回で打ち切り
