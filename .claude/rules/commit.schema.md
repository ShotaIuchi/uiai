# Commit Schema

コミットメッセージの形式とルールを定義する。

## Format

```
<type>: <subject>

[body]

[footer]
```

## Type

| Type | 用途 |
|------|------|
| `feat` | 新機能追加 |
| `fix` | バグ修正 |
| `docs` | ドキュメントのみの変更 |
| `style` | コードの意味に影響しない変更（空白、フォーマット等） |
| `refactor` | バグ修正でも機能追加でもないコード変更 |
| `test` | テストの追加・修正 |
| `chore` | ビルドプロセスやツールの変更 |

## Rules

### Subject

- 50文字以内
- 命令形で記述（例: "Add feature" not "Added feature"）
- 文末にピリオドを付けない
- 先頭は大文字

### Body（オプション）

- 72文字で折り返し
- 変更の理由や背景を記述
- 空行でsubjectと区切る

### Footer（必須）

```
Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
```

## Examples

### 機能追加

```
feat: Add user authentication flow

Implement login, logout, and session management using JWT tokens.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
```

### バグ修正

```
fix: Resolve null pointer exception in user service

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
```

### ドキュメント

```
docs: Update API documentation for auth endpoints

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
```

## Validation

コミット前に以下を確認：

1. typeが有効な値であること
2. subjectが50文字以内であること
3. Co-Authored-Byが含まれていること
