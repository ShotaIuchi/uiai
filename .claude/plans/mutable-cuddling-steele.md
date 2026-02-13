# Scenario Compilation: Feasibility Analysis & Implementation Plan

## Context

Currently, uiai's UI test execution requires **every step** to go through LLM inference:
- `do` action: AI reads natural language → dumps UITree → finds element → calculates coordinates → executes ADB command
- `then` assertion: AI takes screenshot → Vision API for semantic judgment (or UITree text search for strict mode)

This is **heavy** (5-15s/step, API cost per call). The user proposes: initial run uses AI as usual, but simultaneously generates a deterministic script. Subsequent runs use the compiled script without AI.

## Feasibility Summary

**Result: Highly feasible. 70-85% of typical scenario steps can be fully compiled.**

### Compilability Analysis (sample scenarios)

| Category | Example | Compilable? | Strategy |
|----------|---------|-------------|----------|
| App launch/stop | `"アプリを起動"` | **Yes** | Direct ADB command |
| Tap by quoted text | `"「ログイン」ボタンをタップ"` | **Yes** | UITree text search → bounds → tap |
| Text input | `"メールアドレス欄に「X」を入力"` | **Yes** | Find EditText → tap → input text |
| Fixed scroll | `"下にスクロール"` | **Yes** | Fixed swipe coordinates |
| Scroll-to-find | `"「Item 20」が見えるまでスクロール"` | **Yes** | Loop: UITree check + swipe |
| Back/Home | `"戻るボタンを押す"` | **Yes** | keyevent 4/3 |
| Wait | `wait: 2` | **Yes** | sleep |
| Strict `then` | `"「東京本社」と表示されていること" strict:true` | **Yes** | UITree text grep |
| `then` with quoted text | `"ヘッダーに「東京本社」と表示"` | **Partial** | Auto-promote to strict |
| Vision `then` | `"ホーム画面が表示されていること"` | **No** | AI checkpoint required |
| Ambiguous do | `"プロフィールアイコンをタップ"` | **No** | No quoted text, needs AI |

### sample-login.yaml の分析

| Step | Action | Compilable? |
|------|--------|-------------|
| `do: "アプリを起動"` | app_launch | **Yes** |
| `then: "ログイン画面が表示されていること"` | vision | **No** (AI checkpoint) |
| `do: "メールアドレス欄に「(email)」を入力"` | text_input | **Yes** |
| `do: "パスワード欄に「(password)」を入力"` | text_input | **Yes** |
| `do: "「ログイン」ボタンをタップ"` | tap_by_text | **Yes** |
| `then: "ホーム画面が表示されていること"` | vision | **No** (AI checkpoint) |
| `do: "プロフィールアイコンをタップ"` | ambiguous | **No** (AI required) |
| `then: "ユーザー名が表示されていること"` | vision | **No** (AI checkpoint) |

→ **do 5件中 4件 (80%) compilable, then 3件中 0件 compilable (strict化で改善可能)**

### sample-location-switch.yaml の分析

| Step | Action | Compilable? |
|------|--------|-------------|
| `do: "アプリを起動"` | app_launch | **Yes** |
| `then: "ホーム画面が表示..."` | vision | **No** |
| `do: "メニューをタップ"` | ambiguous (quoted text なし) | **No** |
| `do: "「拠点切り替え」を選択"` | tap_by_text | **Yes** |
| `then: "「拠点一覧から選択」画面が..."` | has quoted text → strict化可能 | **Partial** |
| `do: "「東京本社」をタップ"` | tap_by_text | **Yes** |
| `then: "拠点が「東京本社」に..."` | has quoted text → strict化可能 | **Partial** |
| `do: "ホーム画面に戻る"` | keyevent (BACK) | **Yes** |
| `then: "ヘッダーに「東京本社」..."` | has quoted text → strict化可能 | **Partial** |

→ quoted textを持つ`then`をstrict化すれば、大幅に改善

## Recommended Architecture

### Compiled Intermediate Representation (JSON IR)

初回AI実行時に、各ステップの解決結果をJSON IRとして保存する。

```json
{
  "version": "1.0",
  "compiled_at": "2026-02-13T10:00:00Z",
  "source": "sample/sample-login.yaml",
  "source_hash": "sha256:abc123...",
  "platform": "android",
  "app": { "android": "com.example.app" },
  "device": { "screen_size": "1080x2400" },
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
      "type": "do",
      "original": "「ログイン」ボタンをタップ",
      "compiled": {
        "strategy": "tap_by_text",
        "search_text": "ログイン",
        "match_type": "exact",
        "resource_id": "com.example.app:id/login_btn",
        "fallback_class": "android.widget.Button"
      }
    },
    {
      "index": 3,
      "type": "then",
      "original": "ホーム画面が表示されていること",
      "compiled": {
        "strategy": "ai_checkpoint"
      }
    },
    {
      "index": 4,
      "type": "then",
      "original": "ヘッダーに「東京本社」と表示されていること",
      "compiled": {
        "strategy": "strict_text_match",
        "search_text": "東京本社"
      }
    }
  ]
}
```

### Strategy Types

| Strategy | Description | AI Required |
|----------|-------------|-------------|
| `app_launch` | `monkey -p <pkg>` | No |
| `app_stop` | `am force-stop` | No |
| `tap_by_text` | UITree text search → center → tap | No |
| `tap_by_resource_id` | UITree resource-id search → tap | No |
| `text_input` | Find EditText → tap → input text | No |
| `scroll_fixed` | Fixed swipe | No |
| `scroll_to_find` | Loop: UITree search + swipe | No |
| `keyevent` | keyevent N | No |
| `wait` | sleep N | No |
| `strict_text_match` | UITree exact text search | No |
| `ai_checkpoint` | AI Vision or NLU required | **Yes** |

### Execution Flow

```
scenario.yaml exists
  ├── compiled.json exists?
  │   ├── Yes → source_hash matches?
  │   │   ├── Yes → Compiled Runner (fast)
  │   │   │   └── ai_checkpoint steps → invoke evaluator for those only
  │   │   └── No → Recompile (AI full run + emit IR)
  │   └── No → First Run (AI full run + emit IR)
  └── compiled.json generated
```

### Compiled Runner (Python)

軽量Pythonスクリプトで、JSON IRを読み込んでADBコマンドを実行する。

```
scripts/
├── compiled_runner.py        # Main runner
├── backends/
│   ├── adb_backend.py        # Android: UITree(XML) + ADB commands
│   ├── idb_backend.py        # iOS: UITree(JSON) + IDB commands (future)
│   └── playwright_backend.py # Web: DOM + Playwright API (future)
└── utils/
    └── uitree_parser.py      # UITree XML/JSON parser, element finder
```

Core logic:
1. Parse `compiled.json`
2. For each step:
   - `tap_by_text`: dump UITree → `xml.etree` で `text="X"` 検索 → bounds → center → `input tap`
   - `tap_by_resource_id`: dump UITree → `resource-id` 検索 → bounds → center
   - `text_input`: EditText検索 → tap → `input text`
   - `strict_text_match`: dump UITree → text grep → pass/fail
   - `ai_checkpoint`: screenshot保存 + skip (or invoke AI evaluator)
3. Output: same `result.json` format as current system

### Element Resolution Priority (Compiled)

初回実行時にAIが見つけた要素のメタデータを全て記録し、replay時は以下の優先順位で探索:

1. **resource-id** (最も安定、UI変更に強い)
2. **text exact match** (表示テキストが変わらなければ有効)
3. **content-desc** (アクセシビリティ属性)
4. **class + index** (最終手段)

### Staleness Detection

| Signal | Detection | Action |
|--------|-----------|--------|
| YAML変更 | `source_hash` mismatch | Recompile |
| Element not found | UITree検索失敗 | Fallback to AI for that step |
| App version change | `dumpsys package` version比較 | Warn |
| Compiled file age | TTL (configurable) | Warn |

要素が見つからない場合、**そのステップだけ** AI fallbackする (全体を再実行しない)。

## Expected Performance

| Metric | Current (All AI) | Compiled (Hybrid) | Compiled (Skip AI) |
|--------|-------------------|--------------------|--------------------|
| AI calls per 10-step scenario | 10+ | 2-3 (ai_checkpoints only) | 0 |
| Time per `do` step | 5-15s | 1-3s | 1-3s |
| Time per `then` step | 5-15s | 5-15s (ai) / <1s (strict) | <1s |
| 10-step scenario total | 50-150s | 15-40s | 10-30s |
| Speed improvement | - | **3-5x** | **5-10x** |
| API cost | $$$ | $ | $0 |

## Implementation Phases

### Phase 1: IR Format & Compilation (core)

1. **`dotclaude/skills/uiai-android-test/references/compile-ir-schema.md`** (new)
   - JSON IR format definition

2. **`dotclaude/agents/task/adb-test-runner.md`** (modify)
   - Add element metadata capture: 各`do`ステップ実行時に `resource-id`, `bounds`, `class`, `content-desc` を `result.json` に追記
   - (現在の `target_element` フィールドを拡充)

3. **`dotclaude/agents/task/scenario-compiler.md`** (new)
   - `result.json` → `compiled.json` 変換エージェント
   - NLU pattern matching rules for deterministic action classification

### Phase 2: Compiled Runner

4. **`scripts/compiled_runner.py`** (new)
   - JSON IR interpreter + ADB execution
   - UITree XML parser (element finder)
   - Result output in same format

5. **`scripts/backends/adb_backend.py`** (new)
   - ADB command wrapper

### Phase 3: Integration

6. **`dotclaude/skills/uiai-android-test/SKILL.md`** (modify)
   - Add `compiled=true/false` parameter
   - Add execution flow branch for compiled mode

7. **`dotclaude/skills/uiai-android-test/references/execution-flow.md`** (modify)
   - Add compiled execution path diagram

### Phase 4: Polish & Cross-Platform (future)

8. iOS/Web backend support
9. `--recompile` flag
10. CI integration guide

## Decisions

- **Runner形式**: Python Runner (`scripts/compiled_runner.py`) — Claude session不要で独立実行
- **AI checkpoint**: Hybrid — vision-based `then` はAI checkpoint、quoted textありの `then` はstrict化
- **Platform**: Android (ADB) のみ先行実装、iOS/Webは後回し

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| UI layout changes → element not found | Medium | Graceful fallback to AI per-step |
| Multiple elements with same text | Medium | Store parent hierarchy + index during compilation |
| Dynamic content (timestamps etc) | Low | Support regex in `search_text` |
| Python dependency | Low | Most dev environments have Python |
| Variable interpolation timing | Low | Resolve at runtime, not at compile time |

## Verification

1. Sample scenario `sample-login.yaml` を通常実行 → `result.json` が拡張されたメタデータを含むことを確認
2. `result.json` → `compiled.json` 変換を実行 → IR format validation
3. `compiled_runner.py` で `compiled.json` を実行 → 同じ操作が再現されることを確認
4. UIが変わった場合のfallback動作を確認 (要素名を変えて再実行)
