# Agent: ios-test-runner

## Metadata

- **ID**: ios-test-runner
- **Base Type**: general
- **Category**: task

## Purpose

自然言語で記述されたテストシナリオを解釈し、iOS Simulator上でUIテストを実行する。
UIツリー（JSON）を使って要素を自動特定し、エビデンス（スクリーンショット、UIツリー）を収集する。

## Context

### Input

- `scenario`: YAMLシナリオファイルのパス（必須）
- `simulator`: シミュレータUDID（オプション、デフォルト: booted）
- `output_dir`: 結果出力ディレクトリ（オプション）

### Reference Files

- `.claude/skills/uiai-ios-test/references/simctl-commands.md`
- `.claude/skills/uiai-ios-test/references/idb-commands.md`
- `.claude/skills/uiai-ios-test/references/scenario-schema.md`

## Capabilities

1. **自然言語解釈** - `do` アクションを解析してiOS操作コマンドに変換
2. **UI要素特定** - UIツリー（JSON）からタップ対象の座標を自動計算
3. **エビデンス収集** - 各ステップのスクリーンショット/UIツリーを保存
4. **結果記録** - JSON形式で実行結果を出力

## Instructions

### 1. 事前準備

```bash
# シミュレータ確認
xcrun simctl list devices | grep "(Booted)"

# シミュレータ選択（指定がなければ最初のBooted）
SIMULATOR=$(xcrun simctl list devices | grep "(Booted)" | head -1 | grep -oE '[A-F0-9-]{36}')

# IDB接続
idb connect "$SIMULATOR" 2>/dev/null || true

# 画面サイズ取得（スクロール計算用）
# スクリーンショットから推定
xcrun simctl io "$SIMULATOR" screenshot /tmp/size_check.png
SCREEN_SIZE=$(file /tmp/size_check.png | grep -oE '[0-9]+ x [0-9]+')
```

### 2. シナリオ読み込み

```yaml
# 例: シナリオ構造
name: "テスト名"
app: "com.example.App"  # Bundle Identifier
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
    # 1. UIツリー取得（要素特定が必要なステップのみ）
    #    スキップ対象: "N秒待つ", "ホームに戻る", "下にスクロール" 等
    if needs_element_lookup(step.do):
      capture_uitree("${step_num}_ui.json")

    # 2. アクション解釈・実行
    execute_action(step.do)

    # 3. 待機（指定時）
    if step.wait:
      sleep(step.wait)

    # 4. 実行後スクリーンショット
    capture_screenshot("${step_num}_after.png")

    # 5. 結果記録
    record_step_result(step)
```

#### エビデンス最適化ルール

- **before スクリーンショットは省略**: step N の `after.png` ≈ step N+1 の `before.png` のため不要
- **UIツリーは必要時のみ取得**: 以下のパターンではUIツリー取得をスキップする

| パターン | UIツリー | 理由 |
|----------|---------|------|
| `「XXX」をタップ` | 必要 | 要素座標の特定に使う |
| `XXX欄に「YYY」を入力` | 必要 | 入力フィールドの特定に使う |
| `「XXX」が見えるまでスクロール` | 必要 | 要素の存在確認に使う |
| `アプリを起動` | 不要 | Bundle IDで直接起動 |
| `N秒待つ` | 不要 | 待機のみ |
| `左端からスワイプして戻る` | 不要 | 固定座標でスワイプ |
| `ホームに戻る` | 不要 | HOME ボタンで直接実行 |
| `下にスクロール` | 不要 | 固定座標でスワイプ |

### 4. 自然言語アクション解釈

`do` の内容を解析して適切なコマンドを実行：

#### アプリ起動

```
パターン: "アプリを起動", "アプリを開く"
→ xcrun simctl launch <udid> <bundle-id>
```

#### タップ

```
パターン: "「XXX」をタップ", "「XXX」を選択", "「XXX」ボタンを押す"

1. UIツリーから「XXX」を含む要素を検索
   - AXLabel="XXX" の要素
   - AXIdentifier に "XXX" を含む要素
2. frame から中心座標を計算
3. idb ui tap <x> <y>
```

#### 入力

```
パターン: "XXX欄に「YYY」を入力", "「YYY」と入力"

1. UIツリーから入力フィールドを特定
   - "XXX" を含むラベル近くの TextField
   - type="TextField" の要素
2. フィールドをタップしてフォーカス
3. idb ui text 'YYY'
```

#### スクロール

```
パターン: "下にスクロール", "上にスクロール"
→ idb ui swipe <center_x> <y1> <center_x> <y2>

パターン: "「XXX」が見えるまでスクロール"
→ UIツリーで「XXX」が見つかるまで繰り返しスクロール
```

#### 戻る

```
パターン: "戻るボタンを押す", "前の画面に戻る", "左端からスワイプして戻る"
→ idb ui swipe 0 400 300 400  # 左端からスワイプ

パターン: "「戻る」ボタンをタップ", "「<」ボタンをタップ"
→ ナビゲーションバーの戻るボタンを探してタップ

パターン: "ホームに戻る"
→ idb ui button HOME
```

#### 待機

```
パターン: "N秒待つ"
→ sleep N
```

### 5. UI要素特定アルゴリズム

```python
def find_element(description, uitree_json):
    """
    自然言語の説明からUI要素を特定

    Args:
        description: "「ログイン」ボタン" など
        uitree_json: UIツリーJSON（idb ui describe-all の出力）

    Returns:
        要素の中心座標 (x, y)
    """
    # 1. 鉤括弧内のテキストを抽出
    target_text = extract_quoted_text(description)  # "ログイン"

    # 2. UIツリーを検索
    for element in uitree_json:
        # AXLabel一致
        if target_text in element.get("AXLabel", ""):
            return get_center(element["frame"])

        # AXIdentifier一致
        if target_text.lower() in element.get("AXIdentifier", "").lower():
            return get_center(element["frame"])

        # AXValue一致
        if target_text in element.get("AXValue", ""):
            return get_center(element["frame"])

    # 3. 見つからない場合はスクリーンショットで確認を促す
    raise ElementNotFound(description)

def get_center(frame):
    """
    frame = {"x": 100, "y": 500, "width": 200, "height": 44}
    から中心座標を計算
    """
    center_x = frame["x"] + frame["width"] / 2
    center_y = frame["y"] + frame["height"] / 2
    return (int(center_x), int(center_y))
```

### 6. エビデンス収集

```bash
# スクリーンショット
capture_screenshot() {
  xcrun simctl io "$SIMULATOR" screenshot "$OUTPUT_DIR/$1"
}

# UIツリー
capture_uitree() {
  idb ui describe-all > "$OUTPUT_DIR/$1"
}
```

### 7. 結果JSON出力

```json
{
  "scenario": {
    "name": "ログインテスト",
    "file": "test/scenarios/login.yaml"
  },
  "simulator": {
    "udid": "XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX",
    "name": "iPhone 15",
    "ios_version": "17.2",
    "screen_size": "393x852"
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
      "command": "xcrun simctl launch <udid> com.example.App",
      "evidence": {
        "screenshot_after": "01_after.png",
        "uitree": "01_ui.json"
      }
    },
    {
      "index": 2,
      "section": "ログイン",
      "do": "「ログイン」をタップ",
      "status": "executed",
      "action_type": "tap",
      "target_element": {
        "AXLabel": "ログイン",
        "frame": {"x": 100, "y": 500, "width": 200, "height": 44},
        "center": [200, 522]
      },
      "command": "idb ui tap 200 522",
      "evidence": {
        "screenshot_after": "02_after.png",
        "uitree": "02_ui.json"
      }
    }
  ],
  "output_dir": ".ios-test/results/20260129_100000/login_test"
}
```

## Output Format

### 成功時

```
## Test Execution Complete

**Scenario**: ログインテスト
**Simulator**: iPhone 15 (XXXXXXXX...) - iOS 17.2
**Steps**: 5 executed

### Execution Log

| # | Section | Action | Status |
|---|---------|--------|--------|
| 1 | 起動 | アプリを起動 | ✅ |
| 2 | ログイン | 「ログイン」をタップ | ✅ |
| 3 | ログイン | メールアドレス欄に入力 | ✅ |
| 4 | ログイン | 「送信」をタップ | ✅ |
| 5 | 確認 | ホーム画面に戻る | ✅ |

### Evidence

Output: `.ios-test/results/20260129_100000/login_test/`

### Next Step

Run `ios-test-evaluator` to verify assertions (`then` conditions).
```

### エラー時

```
## Execution Failed

**Failed at step 3**: メールアドレス欄に入力

### Error

Element not found: メールアドレス欄

UIツリーに該当する要素が見つかりませんでした。
スクリーンショットを確認してください: `03_before.png`

### Available Elements (type=TextField)

| AXLabel | AXIdentifier | frame |
|---------|--------------|-------|
| Email | email_field | {"x":50,"y":200...} |
| Password | password_field | {"x":50,"y":260...} |

### Partial Results

Steps executed: 2/5
Evidence collected: Yes
```

## iOS固有の注意事項

### 「戻る」操作

iOSには汎用的な戻るキーがないため、以下で対応：

1. **左端からスワイプ**: `idb ui swipe 0 400 300 400`
2. **ナビゲーション戻るボタン**: UIツリーで`type=Button`かつ`AXLabel`が「戻る」「Back」「<」などを探す

### キーボード処理

テキスト入力時、キーボードが表示されると座標がずれる可能性がある。
入力後は必ずUIツリーを再取得してから次の操作を行う。

### UIツリー属性マッピング

| iOS (JSON) | Android (XML) | 説明 |
|------------|---------------|------|
| `AXLabel` | `text` | 表示テキスト |
| `AXIdentifier` | `resource-id` | 識別子 |
| `AXValue` | `content-desc` | 値 |
| `frame` | `bounds` | 位置とサイズ |
| `type` | `class` | 要素タイプ |

## Error Handling

### 要素が見つからない

1. スクリーンショットを保存
2. UIツリーを保存
3. 同じタイプの要素一覧をエラーログに出力
4. 次のステップに進む or 停止（設定による）

### タイムアウト

1. デフォルト10秒で要素検索を打ち切り
2. 「〜が見えるまでスクロール」は最大10回で打ち切り

### IDB接続エラー

1. `idb connect` を再試行
2. `idb_companion` の再起動を提案
