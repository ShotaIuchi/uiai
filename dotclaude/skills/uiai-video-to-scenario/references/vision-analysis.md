# Vision Analysis

Claude Visionを使用したフレーム画像の解析方法。

## 解析の目的

抽出されたフレーム画像から以下を識別する：

1. **現在の画面** - どの画面が表示されているか
2. **実行された操作** - 前のフレームから何が起きたか
3. **UI要素** - タップ対象、入力フィールド、ボタンなど

## バッチ処理

### バッチサイズ

| 設定 | 値 | 理由 |
|------|-----|------|
| バッチサイズ | 8フレーム | API効率とコンテキスト維持のバランス |
| オーバーラップ | 2フレーム | 文脈の連続性を確保 |

### バッチ処理の流れ

```
フレーム: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]

バッチ1: [1, 2, 3, 4, 5, 6, 7, 8]
バッチ2: [7, 8, 9, 10, 11, 12]  # 7,8がオーバーラップ
```

## 解析プロンプト

### システムプロンプト

```
You are a UI test scenario analyzer. Analyze mobile/web application screenshots to:
1. Identify the current screen/state
2. Detect user actions (tap, type, scroll, etc.)
3. Extract UI element information

Output in JSON format with the following structure for each frame transition.
```

### ユーザープロンプト

```
Analyze these sequential screenshots from a mobile/web application recording.

For each frame transition, identify:
1. Screen name/state
2. User action performed (if any)
3. Target element (button text, field name, etc.)
4. Result of the action

Platform: {platform}  # android, ios, or web

Output as JSON array:
[
  {
    "frame_index": 1,
    "screen": "Login Screen",
    "action": null,
    "action_type": null,
    "target_element": null,
    "notes": "Initial state"
  },
  {
    "frame_index": 2,
    "screen": "Login Screen",
    "action": "User entered email address",
    "action_type": "input",
    "target_element": "Email field",
    "input_value": "test@example.com",
    "notes": null
  },
  {
    "frame_index": 3,
    "screen": "Login Screen",
    "action": "User tapped login button",
    "action_type": "tap",
    "target_element": "Login button",
    "notes": null
  },
  {
    "frame_index": 4,
    "screen": "Home Screen",
    "action": null,
    "action_type": "transition",
    "target_element": null,
    "notes": "Screen changed after login"
  }
]

Important:
- If password input is detected, mark input_value as "[OBSCURED]"
- If action is unclear, add "unclear" to notes
- If element name is guessed, add "guessed" to notes
```

## 解析結果スキーマ

### フレーム解析結果

```json
{
  "frame_index": 1,
  "screen": "string",
  "action": "string | null",
  "action_type": "tap | input | scroll | swipe | wait | launch | transition | null",
  "target_element": "string | null",
  "input_value": "string | null",
  "notes": "string | null"
}
```

### フィールド説明

| フィールド | 型 | 説明 |
|-----------|-----|------|
| `frame_index` | number | フレーム番号（1始まり） |
| `screen` | string | 現在の画面名 |
| `action` | string? | 実行された操作の説明 |
| `action_type` | enum? | 操作タイプ |
| `target_element` | string? | 操作対象のUI要素 |
| `input_value` | string? | 入力された値 |
| `notes` | string? | 補足情報（unclear, guessedなど） |

### action_type 一覧

| タイプ | 説明 | 例 |
|--------|------|-----|
| `tap` | タップ操作 | ボタンタップ、選択 |
| `input` | テキスト入力 | フォーム入力 |
| `scroll` | スクロール | リストスクロール |
| `swipe` | スワイプ | ページ切り替え、戻る |
| `wait` | 待機/ローディング | ローディング表示 |
| `launch` | アプリ起動 | 最初のフレーム |
| `transition` | 画面遷移 | 画面が変わった |
| `null` | 操作なし | 初期状態 |

## 完全な解析結果例

```json
{
  "video": "login.mp4",
  "platform": "android",
  "frame_count": 7,
  "analysis": [
    {
      "frame_index": 1,
      "screen": "Launch Screen",
      "action": "App launched",
      "action_type": "launch",
      "target_element": null,
      "notes": null
    },
    {
      "frame_index": 2,
      "screen": "Login Screen",
      "action": null,
      "action_type": "transition",
      "target_element": null,
      "notes": "Splash finished"
    },
    {
      "frame_index": 3,
      "screen": "Login Screen",
      "action": "Entered email address",
      "action_type": "input",
      "target_element": "Email field",
      "input_value": "test@example.com",
      "notes": null
    },
    {
      "frame_index": 4,
      "screen": "Login Screen",
      "action": "Entered password",
      "action_type": "input",
      "target_element": "Password field",
      "input_value": "[OBSCURED]",
      "notes": "password obscured"
    },
    {
      "frame_index": 5,
      "screen": "Login Screen",
      "action": "Tapped login button",
      "action_type": "tap",
      "target_element": "Login button",
      "notes": null
    },
    {
      "frame_index": 6,
      "screen": "Loading Screen",
      "action": null,
      "action_type": "wait",
      "target_element": null,
      "notes": "Loading indicator visible"
    },
    {
      "frame_index": 7,
      "screen": "Home Screen",
      "action": null,
      "action_type": "transition",
      "target_element": null,
      "notes": "Login successful"
    }
  ]
}
```

## エラーハンドリング

### 不明確なフレーム

```json
{
  "frame_index": 5,
  "screen": "Unknown",
  "action": "Something happened",
  "action_type": null,
  "target_element": null,
  "notes": "unclear - frame too blurry or transition too fast"
}
```

### 解析できないフレーム

```json
{
  "frame_index": 3,
  "screen": "Error",
  "action": null,
  "action_type": null,
  "target_element": null,
  "notes": "Could not analyze - image appears corrupted"
}
```

## プラットフォーム固有の考慮事項

### Android

- ナビゲーションバー（戻る、ホーム、タスク）の検出
- マテリアルデザインコンポーネントの識別
- パッケージ名の推測は不要

### iOS

- ホームインジケータの検出
- iOSスタイルのナビゲーション（左スワイプ戻る）
- SafeAreaの考慮

### Web

- ブラウザUIの除外
- URL変更の検出
- レスポンシブデザインの考慮

## 最適化のヒント

### 画像サイズ

- 推奨: 1280x720以下にリサイズ
- 大きすぎる画像はトークンを消費

### バッチの連続性

- オーバーラップにより文脈を維持
- 長いセッションは複数バッチに分割

### 曖昧さの回避

- `notes`フィールドを活用して不確実性を明示
- シナリオ生成時に`[REVIEW]`マーカーに変換
