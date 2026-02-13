# Compiled IR Schema

Compiled Intermediate Representation (IR) format for deterministic scenario replay.

## Overview

Initial AI execution produces a `compiled.json` alongside `result.json`. Subsequent runs use the compiled IR to execute deterministically without AI inference, falling back to AI only for `ai_checkpoint` steps.

## File Location

Compiled IR is placed next to the source YAML file with `.compiled.json` suffix.

```
sample/
├── sample-login.yaml                  # Source scenario
├── sample-login.yaml.compiled.json    # Compiled IR
├── sample-location-switch.yaml
└── sample-location-switch.yaml.compiled.json
```

This convention ensures:
- Compiled files travel with the source (portable across PCs, git)
- No collision between multiple scenarios
- Easy to find: just append `.compiled.json` to the YAML path

## Top-Level Structure

```json
{
  "version": "1.0",
  "compiled_at": "2026-02-13T10:00:00Z",
  "source": "sample/sample-login.yaml",
  "source_hash": "sha256:abc123...",
  "platform": "android",
  "app": {
    "android": "com.example.app"
  },
  "device": {
    "screen_size": "1080x2400"
  },
  "variables": {
    "email": "test@example.com",
    "password": "password123"
  },
  "steps": []
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `version` | string | Yes | IR format version (`"1.0"`) |
| `compiled_at` | string | Yes | ISO8601 compilation timestamp |
| `source` | string | Yes | Source YAML file path (relative to project root) |
| `source_hash` | string | Yes | SHA-256 hash of source YAML for staleness detection |
| `platform` | string | Yes | Target platform (`"android"`) |
| `app` | object | Yes | App identifiers (mirrors YAML `app` field) |
| `device` | object | Yes | Device info captured during compilation |
| `variables` | object | No | Variable definitions from YAML (runtime-resolved for placeholders) |
| `steps` | array | Yes | Compiled step array |

## Step Structure

Each step in the `steps` array:

```json
{
  "index": 1,
  "section": "起動",
  "type": "do",
  "original": "アプリを起動",
  "wait": 0,
  "strict": false,
  "compiled": {
    "strategy": "app_launch",
    "package": "com.example.app"
  }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `index` | number | Yes | 1-based step index |
| `section` | string | Yes | Section ID from YAML |
| `type` | string | Yes | `"do"`, `"then"`, or `"replay"` |
| `original` | string | Yes | Original natural language text |
| `wait` | number | No | Wait time in seconds after execution (default: 0) |
| `strict` | boolean | No | Strict mode flag (default: false) |
| `compiled` | object | Yes | Compiled strategy and parameters |

## Strategy Types

### `app_launch` - App Launch

```json
{
  "strategy": "app_launch",
  "package": "com.example.app"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `package` | string | Android package name |

**ADB Command**: `adb shell monkey -p <package> -c android.intent.category.LAUNCHER 1`

**Patterns**: `アプリを起動`, `アプリを開く`

### `app_stop` - App Stop

```json
{
  "strategy": "app_stop",
  "package": "com.example.app"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `package` | string | Android package name |

**ADB Command**: `adb shell am force-stop <package>`

**Patterns**: `アプリを終了`, `アプリを停止`

### `app_restart` - App Restart

```json
{
  "strategy": "app_restart",
  "package": "com.example.app"
}
```

Executes `app_stop` then `app_launch` sequentially.

**Patterns**: `アプリを再起動`

### `tap_by_text` - Tap by Text Search

```json
{
  "strategy": "tap_by_text",
  "search_text": "ログイン",
  "match_type": "exact",
  "element_metadata": {
    "resource_id": "com.example.app:id/login_btn",
    "class": "android.widget.Button",
    "content_desc": "",
    "bounds": "[100,500][980,600]",
    "parent_hierarchy": ["android.widget.LinearLayout", "android.widget.FrameLayout"]
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `search_text` | string | Text to find in UITree |
| `match_type` | string | `"exact"` or `"contains"` |
| `element_metadata` | object | Element hints from first run (optional) |

**Element Resolution Priority** (at replay):
1. `resource_id` - Most stable across UI changes
2. `search_text` exact match on `text` attribute
3. `content_desc` match
4. `class` + parent hierarchy (last resort)

**ADB Command**: UITree dump -> find element -> `adb shell input tap <center_x> <center_y>`

**Patterns**: `「XXX」をタップ`, `「XXX」を選択`, `「XXX」ボタンを押す`, `「XXX」を押す`

### `tap_by_resource_id` - Tap by Resource ID

```json
{
  "strategy": "tap_by_resource_id",
  "resource_id": "com.example.app:id/menu_btn",
  "fallback_text": "メニュー",
  "element_metadata": {
    "class": "android.widget.ImageButton",
    "content_desc": "menu",
    "bounds": "[0,100][100,200]"
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `resource_id` | string | Android resource ID |
| `fallback_text` | string | Fallback text search if resource-id not found |
| `element_metadata` | object | Additional element hints |

Used when AI identified an element by resource-id during first run (no quoted text in original action).

### `text_input` - Text Input

```json
{
  "strategy": "text_input",
  "input_text": "test@example.com",
  "field_hint": "メールアドレス",
  "element_metadata": {
    "resource_id": "com.example.app:id/email_input",
    "class": "android.widget.EditText",
    "bounds": "[50,300][1030,380]"
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `input_text` | string | Text to input (variable-interpolated) |
| `field_hint` | string | Field description for UITree search |
| `element_metadata` | object | Element hints from first run |

**ADB Commands**: Find EditText -> `input tap` to focus -> `input text '<text>'`

**Patterns**: `XXX欄に「YYY」を入力`, `「YYY」と入力`

### `scroll_fixed` - Fixed Scroll

```json
{
  "strategy": "scroll_fixed",
  "direction": "down",
  "distance": 500,
  "duration_ms": 300
}
```

| Field | Type | Description |
|-------|------|-------------|
| `direction` | string | `"up"`, `"down"`, `"left"`, `"right"` |
| `distance` | number | Scroll distance in pixels |
| `duration_ms` | number | Swipe duration (default: 300) |

**ADB Command**: `adb shell input swipe <x1> <y1> <x2> <y2> <duration>`

**Patterns**: `下にスクロール`, `上にスクロール`, `左にスワイプ`, `右にスワイプ`

### `scroll_to_find` - Scroll Until Element Found

```json
{
  "strategy": "scroll_to_find",
  "search_text": "Item 20",
  "direction": "down",
  "max_scrolls": 10,
  "distance": 500,
  "duration_ms": 300
}
```

| Field | Type | Description |
|-------|------|-------------|
| `search_text` | string | Text to find in UITree |
| `direction` | string | Scroll direction |
| `max_scrolls` | number | Maximum scroll attempts (default: 10) |
| `distance` | number | Scroll distance per attempt |
| `duration_ms` | number | Swipe duration per attempt |

**Logic**: Loop: dump UITree -> check for `search_text` -> if not found, swipe -> repeat

**Patterns**: `「XXX」が見えるまでスクロール`

### `keyevent` - Key Event

```json
{
  "strategy": "keyevent",
  "keycode": 4,
  "key_name": "BACK"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `keycode` | number | Android keycode |
| `key_name` | string | Human-readable key name |

**Common Keycodes**:

| Key Name | Keycode | Pattern |
|----------|---------|---------|
| `BACK` | 4 | `戻るボタンを押す`, `前の画面に戻る` |
| `HOME` | 3 | `ホームに戻る`, `ホーム画面に戻る` |
| `ENTER` | 66 | `エンターを押す`, `確定` |
| `MENU` | 82 | `メニューキーを押す` |

**ADB Command**: `adb shell input keyevent <keycode>`

### `wait` - Wait/Sleep

```json
{
  "strategy": "wait",
  "duration_sec": 3
}
```

| Field | Type | Description |
|-------|------|-------------|
| `duration_sec` | number | Wait time in seconds |

**Patterns**: `N秒待つ`, `wait: N` (YAML field)

### `strict_text_match` - Strict Text Assertion

```json
{
  "strategy": "strict_text_match",
  "search_text": "東京本社",
  "match_type": "exact",
  "negate": false
}
```

| Field | Type | Description |
|-------|------|-------------|
| `search_text` | string | Text to find in UITree |
| `match_type` | string | `"exact"` or `"contains"` |
| `negate` | boolean | If true, assert text is NOT present |

Used for `then` steps with quoted text (auto-promoted to strict) or explicit `strict: true`.

**Logic**: Dump UITree -> search for `search_text` in all `text` attributes -> pass/fail

**Patterns** (then):
- `「XXX」と表示されていること` -> exact match
- `「XXX」が含まれていること` -> contains match
- `「XXX」が表示されていないこと` -> negate=true

### `uitree_verify` - UITree Fingerprint Verification

```json
{
  "strategy": "uitree_verify",
  "assertion": "ホーム画面が表示されていること",
  "fallback_to_ai": false,
  "checks": [
    {"type": "text_visible", "value": "ホーム", "match_type": "exact"},
    {"type": "resource_id_exists", "value": "com.example.app:id/bottom_nav"},
    {"type": "class_exists", "value": "androidx.recyclerview.widget.RecyclerView"},
    {"type": "text_not_visible", "value": "エラー", "match_type": "contains"},
    {"type": "element_count_gte", "selector": {"class": "android.widget.TextView"}, "min_count": 3}
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `assertion` | string | Original `then` text |
| `fallback_to_ai` | boolean | If true, fall back to AI on check failure (default: false) |
| `checks` | array | List of programmatic checks to execute |

#### Check Types

| Type | Fields | Description |
|------|--------|-------------|
| `text_visible` | `value`, `match_type` | Assert text exists in UITree |
| `text_not_visible` | `value`, `match_type` | Assert text does NOT exist in UITree |
| `resource_id_exists` | `value` | Assert resource-id exists |
| `class_exists` | `value` | Assert widget class exists |
| `element_count_gte` | `selector`, `min_count` | Assert element count >= min_count |

- `match_type`: `"exact"` (default) or `"contains"`
- `selector`: Object with optional keys `class`, `resource_id`, `text`

Used for `then` steps without quoted text where the UITree from the first AI run provides sufficient structural data for deterministic verification. Generated automatically by the scenario compiler when UITree fingerprint data is available.

**Failure behavior**:
- `fallback_to_ai: false` (default) -> check failure = `failed`
- `fallback_to_ai: true` -> check failure = `ai_required` (falls back to AI)

**Execution**: Dump UITree -> run all checks -> pass if all succeed

### `screenshot_only` - Screenshot Evidence Only

```json
{
  "strategy": "screenshot_only",
  "assertion": "ホーム画面が表示されていること"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `assertion` | string | Original `then` text (for documentation only) |

Used as fallback when UITree fingerprint data is insufficient for `uitree_verify`, or when explicitly requested via `verify: screenshot` in the YAML. Always passes — captures screenshot and UITree as evidence without programmatic or AI verification.

**Execution**: Capture screenshot + UITree as evidence -> always pass

### `ai_checkpoint` - AI Vision Checkpoint

```json
{
  "strategy": "ai_checkpoint",
  "assertion": "ホーム画面が表示されていること",
  "hint": "Look for main navigation bar and content feed"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `assertion` | string | Original `then` text for AI evaluation |
| `hint` | string | Optional hint from first run (AI's reasoning) |

Used when UITree fingerprint data is insufficient for `uitree_verify`, or when explicitly requested via `verify: ai` in the YAML.

**Execution**: Take screenshot -> invoke AI evaluator (or skip in `--skip-ai` mode)

## Replay Steps

Replay steps are expanded into individual compiled steps at compilation time:

```json
{
  "index": 5,
  "section": "リプレイ確認",
  "type": "replay",
  "original": "replay: ログイン -> ログイン",
  "replay_source": {
    "from": "ログイン",
    "to": "ログイン"
  },
  "compiled": {
    "strategy": "replay",
    "expanded_steps": [
      {
        "section": "ログイン",
        "type": "do",
        "original": "アプリを起動",
        "compiled": { "strategy": "app_launch", "package": "com.example.app" }
      },
      {
        "section": "ログイン",
        "type": "do",
        "original": "ログインボタンをタップ",
        "compiled": { "strategy": "tap_by_text", "search_text": "ログイン" }
      }
    ]
  }
}
```

## Variable Interpolation

Variables in `compiled.json` use the same `(variable_name)` syntax as YAML.
The compiled runner resolves variables at runtime (not at compile time) to support:

- Placeholder variables (interactive input)
- Environment-specific values

```json
{
  "strategy": "text_input",
  "input_text": "(email)",
  "field_hint": "メールアドレス"
}
```

At runtime, `(email)` is replaced with the resolved variable value.

## Staleness Detection

| Signal | Detection Method | Action |
|--------|-----------------|--------|
| YAML changed | `source_hash` mismatch | Recompile |
| Element not found | UITree search failure at runtime | Mark step as failed (or fallback to AI if `fallback_to_ai: true`) |
| Screen size changed | `device.screen_size` mismatch | Warn (scroll distances may differ) |
| Compiled file age | Configurable TTL | Warn |

Per-step fallback: When an element is not found during compiled execution, only that step falls back to AI. The rest continue in compiled mode.

## Complete Example

```json
{
  "version": "1.0",
  "compiled_at": "2026-02-13T10:00:00Z",
  "source": "sample/sample-login.yaml",
  "source_hash": "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "platform": "android",
  "app": {
    "android": "com.example.app"
  },
  "device": {
    "screen_size": "1080x2400"
  },
  "variables": {
    "email": "test@example.com",
    "password": "password123"
  },
  "steps": [
    {
      "index": 1,
      "section": "起動",
      "type": "do",
      "original": "アプリを起動",
      "compiled": {
        "strategy": "app_launch",
        "package": "com.example.app"
      }
    },
    {
      "index": 2,
      "section": "起動",
      "type": "then",
      "original": "ログイン画面が表示されていること",
      "compiled": {
        "strategy": "uitree_verify",
        "assertion": "ログイン画面が表示されていること",
        "fallback_to_ai": false,
        "checks": [
          {"type": "text_visible", "value": "ログイン", "match_type": "exact"},
          {"type": "resource_id_exists", "value": "com.example.app:id/email_input"}
        ]
      }
    },
    {
      "index": 3,
      "section": "入力",
      "type": "do",
      "original": "メールアドレス欄に「(email)」を入力",
      "compiled": {
        "strategy": "text_input",
        "input_text": "(email)",
        "field_hint": "メールアドレス",
        "element_metadata": {
          "resource_id": "com.example.app:id/email_input",
          "class": "android.widget.EditText",
          "bounds": "[50,300][1030,380]"
        }
      }
    },
    {
      "index": 4,
      "section": "入力",
      "type": "do",
      "original": "パスワード欄に「(password)」を入力",
      "compiled": {
        "strategy": "text_input",
        "input_text": "(password)",
        "field_hint": "パスワード",
        "element_metadata": {
          "resource_id": "com.example.app:id/password_input",
          "class": "android.widget.EditText",
          "bounds": "[50,420][1030,500]"
        }
      }
    },
    {
      "index": 5,
      "section": "ログイン実行",
      "type": "do",
      "original": "「ログイン」ボタンをタップ",
      "wait": 2,
      "compiled": {
        "strategy": "tap_by_text",
        "search_text": "ログイン",
        "match_type": "exact",
        "element_metadata": {
          "resource_id": "com.example.app:id/login_btn",
          "class": "android.widget.Button",
          "content_desc": "",
          "bounds": "[100,550][980,630]"
        }
      }
    },
    {
      "index": 6,
      "section": "ログイン実行",
      "type": "then",
      "original": "ホーム画面が表示されていること",
      "compiled": {
        "strategy": "uitree_verify",
        "assertion": "ホーム画面が表示されていること",
        "fallback_to_ai": false,
        "checks": [
          {"type": "text_visible", "value": "ホーム", "match_type": "exact"},
          {"type": "resource_id_exists", "value": "com.example.app:id/bottom_nav"},
          {"type": "class_exists", "value": "androidx.recyclerview.widget.RecyclerView"}
        ]
      }
    },
    {
      "index": 7,
      "section": "ログイン確認",
      "type": "do",
      "original": "プロフィールアイコンをタップ",
      "compiled": {
        "strategy": "ai_checkpoint",
        "assertion": "プロフィールアイコンをタップ"
      }
    },
    {
      "index": 8,
      "section": "ログイン確認",
      "type": "then",
      "original": "ユーザー名が表示されていること",
      "compiled": {
        "strategy": "screenshot_only",
        "assertion": "ユーザー名が表示されていること"
      }
    }
  ]
}
```
