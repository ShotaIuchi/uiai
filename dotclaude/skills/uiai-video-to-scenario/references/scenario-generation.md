# Scenario Generation Rules

Vision解析結果からYAMLシナリオを生成するルール。

## 変換ルール

### action_type → do/then

| action_type | 生成 | 例 |
|-------------|------|-----|
| `launch` | `do: "アプリを起動"` | - |
| `tap` | `do: "「{target}」をタップ"` | `do: "「ログイン」ボタンをタップ"` |
| `input` | `do: "{target}に「{value}」を入力"` | `do: "メールアドレス欄に「test@example.com」を入力"` |
| `scroll` | `do: "下にスクロール"` | - |
| `swipe` | `do: "左にスワイプ"` | - |
| `wait` | (スキップまたは `wait: N`) | - |
| `transition` | `then: "{screen}が表示されていること"` | `then: "ホーム画面が表示されていること"` |

### 画面遷移の処理

画面遷移（`transition`）は直前の操作の結果として `then` に変換する：

```
Frame 3: tap -> "Login button"
Frame 4: transition -> "Home Screen"
```

↓

```yaml
- do: "「ログイン」ボタンをタップ"
- then: "ホーム画面が表示されていること"
```

## セクション（id）の生成

### セクション分割ルール

以下の場合に新しいセクションを開始：

1. **画面遷移後** - 新しい画面に入った時
2. **論理的な区切り** - ログイン完了、フォーム送信など
3. **3アクション以上連続** - 長いシーケンスを分割

### セクション命名

| 画面/状態 | セクション名 |
|----------|-------------|
| Login Screen | `ログイン` |
| Home Screen | `ホーム` |
| Settings | `設定` |
| Form submission | `{form名}入力` |
| Search | `検索` |

## [REVIEW] マーカー

以下の場合にマーカーを付与：

### パスワード入力

```yaml
- do: "パスワード欄に入力"  # [REVIEW] password obscured
```

### 不明確な操作

```yaml
- do: "画面をタップ"  # [REVIEW] unclear action
```

### 推測された要素名

```yaml
- do: "「送信」ボタンをタップ"  # [REVIEW] element name guessed
```

### 画面遷移が不明確

```yaml
- then: "次の画面が表示されていること"  # [REVIEW] transition unclear
```

## 出力テンプレート

### 基本構造

```yaml
name: "Generated - {video_filename}"
app:
  android: "TODO: Set package name"
  ios: "TODO: Set bundle identifier"

steps:
  - id: "{section_name}"
    actions:
      - do: "{action}"
      - then: "{assertion}"
```

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

## プラットフォーム別の調整

### Android

```yaml
app:
  android: "TODO: Set package name"  # 必須
  ios: "com.example.App"  # オプション

steps:
  - id: "ナビゲーション"
    actions:
      - do: "戻るボタンを押す"  # Androidの戻るキー
```

### iOS

```yaml
app:
  android: "com.example.app"  # オプション
  ios: "TODO: Set bundle identifier"  # 必須

steps:
  - id: "ナビゲーション"
    actions:
      - do: "左端からスワイプして戻る"  # iOSの戻る操作
```

### Web

```yaml
app:
  web: "TODO: Set URL"

steps:
  - id: "ナビゲーション"
    actions:
      - do: "ブラウザの戻るボタンをクリック"
```

## 待機の処理

### ローディング画面

ローディング画面が検出された場合：

```yaml
- do: "「送信」ボタンをタップ"
  wait: 3  # ローディング待機
- then: "完了画面が表示されていること"
```

### 明示的な待機

長いアニメーションや遷移の場合：

```yaml
- do: "「更新」ボタンをタップ"
- do: "3秒待つ"
- then: "データが更新されていること"
```

## 重複の削除

### 連続する同一画面

同じ画面が続く場合は統合：

```
Frame 2: Login Screen (typing)
Frame 3: Login Screen (typing)
Frame 4: Login Screen (button tap)
```

↓

```yaml
- do: "メールアドレス欄に「...」を入力"
- do: "「ログイン」ボタンをタップ"
```

### 冗長な遷移

中間遷移は省略：

```
Frame 5: Loading
Frame 6: Loading
Frame 7: Home Screen
```

↓

```yaml
- do: "「ログイン」ボタンをタップ"
- then: "ホーム画面が表示されていること"  # ローディングは省略
```

## エラーケース

### 解析失敗フレーム

```yaml
# [REVIEW] frames 5-7 could not be analyzed
- do: "不明な操作"  # [REVIEW] unclear
```

### 画面認識失敗

```yaml
- then: "画面が変更されていること"  # [REVIEW] screen not recognized
```

## 検証チェックリスト

生成後、以下を確認：

- [ ] `name` が設定されている
- [ ] `app` にプラットフォーム識別子がある
- [ ] 各セクションに `id` がある
- [ ] `do` と `then` が適切に分離されている
- [ ] `[REVIEW]` マーカーが付いた箇所を人間が確認
- [ ] `/uiai-scenario-check` で構文検証
