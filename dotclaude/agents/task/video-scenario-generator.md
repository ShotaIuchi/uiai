# Agent: video-scenario-generator

## Metadata

- **ID**: video-scenario-generator
- **Base Type**: general
- **Category**: task

## Purpose

Vision解析結果からYAMLシナリオを生成する。適切なセクション分割、[REVIEW]マーカーの付与、プラットフォーム固有の調整を行う。

## Context

### Input

- `analysis_file`: 解析結果JSONファイル（必須）
- `platform`: 対象プラットフォーム（android, ios, web）
- `output`: 出力YAMLファイルパス（オプション）

### Reference Files

- `.claude/skills/uiai-video-to-scenario/references/scenario-generation.md`
- `.claude/skills/uiai-android-test/references/scenario-schema.md`

## Capabilities

1. **解析結果読み込み** - analysis.jsonの読み込みと検証
2. **セクション分割** - 論理的なセクションへの分割
3. **アクション変換** - action_typeからdo/thenへの変換
4. **[REVIEW]マーカー付与** - 要確認箇所のマーキング
5. **YAML出力** - スキーマ準拠のYAML生成

## Instructions

### 1. 解析結果の読み込み

```bash
# 解析結果ファイルの確認
if [ ! -f "$analysis_file" ]; then
  echo "Error: Analysis file not found: $analysis_file"
  exit 1
fi

# JSONの読み込み
analysis=$(cat "$analysis_file")
video_name=$(echo "$analysis" | jq -r '.video')
frame_count=$(echo "$analysis" | jq -r '.frame_count')
```

### 2. セクション分割

画面遷移と論理的な区切りに基づいてセクションを生成：

```python
# 擬似コード
sections = []
current_section = None
current_screen = None

for frame in analysis.frames:
    # 新しい画面に遷移した場合
    if frame.screen != current_screen:
        if current_section:
            sections.append(current_section)
        current_section = {
            "id": generate_section_id(frame.screen),
            "actions": []
        }
        current_screen = frame.screen

    # アクションを追加
    if frame.action:
        action = convert_to_action(frame)
        current_section["actions"].append(action)

# 最後のセクションを追加
if current_section:
    sections.append(current_section)
```

### 3. アクション変換

action_typeに応じてdo/thenを生成：

```python
def convert_to_action(frame):
    action_type = frame.action_type

    if action_type == "launch":
        return {"do": "アプリを起動"}

    elif action_type == "tap":
        target = frame.target_element
        return {"do": f"「{target}」をタップ"}

    elif action_type == "input":
        target = frame.target_element
        value = frame.input_value
        if value == "[OBSCURED]":
            return {
                "do": f"{target}に入力",
                "comment": "[REVIEW] password obscured"
            }
        return {"do": f"{target}に「{value}」を入力"}

    elif action_type == "scroll":
        return {"do": "下にスクロール"}

    elif action_type == "swipe":
        return {"do": "スワイプ"}

    elif action_type == "transition":
        screen = frame.screen
        return {"then": f"{screen}が表示されていること"}

    elif action_type == "wait":
        return None  # スキップまたはwaitプロパティとして追加

    return None
```

### 4. [REVIEW]マーカーの付与

notes フィールドに基づいてマーカーを追加：

```python
def add_review_markers(action, notes):
    if not notes:
        return action

    markers = []

    if "obscured" in notes.lower():
        markers.append("password obscured")
    if "unclear" in notes.lower():
        markers.append("unclear action")
    if "guessed" in notes.lower():
        markers.append("element name guessed")
    if "transition" in notes.lower() and "unclear" in notes.lower():
        markers.append("transition unclear")

    if markers:
        action["comment"] = f"[REVIEW] {', '.join(markers)}"

    return action
```

### 5. YAML生成

```yaml
name: "Generated - {video_name}"
app:
  android: "TODO: Set package name"
  ios: "TODO: Set bundle identifier"

steps:
  - id: "{section_id}"
    actions:
      - do: "{action}"
      - then: "{assertion}"
```

### 6. プラットフォーム固有の調整

#### Android

```yaml
app:
  android: "TODO: Set package name"

steps:
  - id: "ナビゲーション"
    actions:
      - do: "戻るボタンを押す"  # 戻るキー
```

#### iOS

```yaml
app:
  ios: "TODO: Set bundle identifier"

steps:
  - id: "ナビゲーション"
    actions:
      - do: "左端からスワイプして戻る"  # iOSの戻り操作
```

#### Web

```yaml
app:
  web: "TODO: Set URL"

steps:
  - id: "ナビゲーション"
    actions:
      - do: "ブラウザの戻るボタンをクリック"
```

### 7. 出力ファイルの書き込み

```bash
# 出力先の決定
output_file="${output:-${analysis_dir}/scenario.yaml}"

# YAMLを書き込み
Write: $output_file
```

## Output Format

### 成功時

```
## Scenario Generation Complete

**Video**: login.mp4
**Platform**: android
**Sections**: 3
**Actions**: 8

### Generated Scenario

```yaml
name: "Generated - login.mp4"
app:
  android: "TODO: Set package name"
  ios: "TODO: Set bundle identifier"

steps:
  - id: "起動"
    actions:
      - do: "アプリを起動"
      - then: "ログイン画面が表示されていること"
  ...
```

### Review Items (3)

| Line | Issue |
|------|-------|
| 12 | [REVIEW] password obscured |
| 18 | [REVIEW] element name guessed |
| 25 | [REVIEW] transition unclear |

### Output

- Scenario: `.video-to-scenario/login/scenario.yaml`

### Next Steps

1. Review and edit [REVIEW] items
2. Set app package/bundle identifier
3. Validate with `/uiai-scenario-check scenarios=...`
4. Test with `/uiai-android-test scenarios=...`
```

### エラー時

```
## Generation Failed

**Error**: Invalid analysis file format

The analysis file does not contain required fields.

Required:
- video: string
- frame_count: number
- analysis: array

Please run video-frame-analyzer first.
```

## Error Handling

### 解析結果なし

```
Error: Analysis file not found

Please run the analysis first:
  1. video-frame-extractor
  2. video-frame-analyzer
```

### 不正なJSON形式

```
Error: Invalid JSON in analysis file

Please check the file format or re-run video-frame-analyzer.
```

### アクションなし

```
Warning: No actions detected in video

The analysis did not identify any user actions.
Possible causes:
1. Video contains only static screens
2. Scene detection threshold too high
3. Analysis failed to recognize actions

Generated minimal scenario with transitions only.
```

## セクション命名ルール

| 画面名 | セクションID |
|--------|-------------|
| Login Screen | `ログイン` |
| Home Screen | `ホーム` |
| Settings Screen | `設定` |
| Search Screen | `検索` |
| Detail Screen | `詳細` |
| List Screen | `一覧` |
| Form Screen | `入力` |
| Confirmation Screen | `確認` |
| Loading Screen | (スキップ) |
| Error Screen | `エラー` |

## 生成されるYAML例

### 完全な例

```yaml
name: "Generated - login.mp4"
app:
  android: "TODO: Set package name"
  ios: "TODO: Set bundle identifier"

steps:
  - id: "起動"
    actions:
      - do: "アプリを起動"
      - then: "ログイン画面が表示されていること"

  - id: "ログイン"
    actions:
      - do: "メールアドレス欄に「test@example.com」を入力"
      - do: "パスワード欄に入力"  # [REVIEW] password obscured
      - do: "「ログイン」ボタンをタップ"
      - then: "ホーム画面が表示されていること"

  - id: "メニュー操作"
    actions:
      - do: "メニューアイコンをタップ"  # [REVIEW] element name guessed
      - do: "「設定」をタップ"
      - then: "設定画面が表示されていること"
```

## 検証チェックリスト

生成後に確認すべき項目：

- [ ] `name` が設定されている
- [ ] `app` にプラットフォーム識別子がある（TODOを置換）
- [ ] 各セクションに `id` がある
- [ ] `do` と `then` が適切に分離されている
- [ ] `[REVIEW]` マーカーが付いた箇所を人間が確認
- [ ] `/uiai-scenario-check` で構文検証を実行
