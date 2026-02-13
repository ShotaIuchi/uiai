# Agent: scenario-compiler

## Metadata

- **ID**: scenario-compiler
- **Base Type**: general
- **Category**: task

## Purpose

AI実行済みの `result.json` を読み取り、決定論的に再実行可能な `compiled.json` (Compiled IR) に変換する。
自然言語パターンマッチングとAI実行時に収集した要素メタデータを組み合わせて、各ステップの最適な実行戦略を判定する。

## Context

### Input

- `result_dir`: result.json が存在するディレクトリ（必須）
- `scenario`: 元のYAMLシナリオファイルのパス（必須）

### Output Location

`<scenario>.compiled.json` （元の YAML と同じディレクトリ）

例: `sample/sample-login.yaml` → `sample/sample-login.yaml.compiled.json`

### Reference Files

- `.claude/skills/uiai-android-test/references/compile-ir-schema.md`
- `.claude/skills/uiai-android-test/references/scenario-schema.md`

## Capabilities

1. **NLU Pattern Matching** - 自然言語アクションの決定論的分類
2. **Element Metadata Extraction** - result.json から要素メタデータを抽出
3. **Strategy Selection** - 各ステップに最適な compiled strategy を割当て
4. **IR Generation** - compile-ir-schema.md に準拠した compiled.json を出力

## Instructions

### 1. Input Reading

```bash
# result.json を読み込み
result=$(cat "$result_dir/result.json")

# 元の YAML シナリオを読み込み
scenario=$(cat "$scenario")

# YAML の SHA-256 ハッシュを計算
source_hash=$(shasum -a 256 "$scenario" | awk '{print $1}')
```

### 2. NLU Pattern Classification

各 `do` アクションの自然言語テキストをパターンマッチングで分類する。

#### Pattern Rules (Priority Order)

```python
def classify_action(text, step_result):
    """
    Classify a natural language action into a compiled strategy.

    Args:
        text: Original action text (e.g. "アプリを起動")
        step_result: Step result from result.json (with target_element)

    Returns:
        Compiled strategy dict
    """

    # 1. App operations
    if matches(text, ["アプリを起動", "アプリを開く"]):
        return {"strategy": "app_launch", "package": app_package}

    if matches(text, ["アプリを終了", "アプリを停止"]):
        return {"strategy": "app_stop", "package": app_package}

    if matches(text, ["アプリを再起動"]):
        return {"strategy": "app_restart", "package": app_package}

    # 2. Text input (must check before tap - both contain quoted text)
    input_match = re.search(r'[にへ]「(.+?)」[をと]入力', text)
    if input_match:
        field_hint = extract_field_hint(text)
        return {
            "strategy": "text_input",
            "input_text": input_match.group(1),
            "field_hint": field_hint,
            "element_metadata": extract_metadata(step_result)
        }

    # 3. Scroll to find
    scroll_find_match = re.search(r'「(.+?)」が見えるまでスクロール', text)
    if scroll_find_match:
        return {
            "strategy": "scroll_to_find",
            "search_text": scroll_find_match.group(1),
            "direction": "down",
            "max_scrolls": 10,
            "distance": 500,
            "duration_ms": 300
        }

    # 4. Fixed scroll
    scroll_match = re.search(r'(上|下|左|右)に(スクロール|スワイプ)', text)
    if scroll_match:
        direction_map = {"上": "up", "下": "down", "左": "left", "右": "right"}
        return {
            "strategy": "scroll_fixed",
            "direction": direction_map[scroll_match.group(1)],
            "distance": 500,
            "duration_ms": 300
        }

    # 5. Tap by quoted text
    tap_match = re.search(r'「(.+?)」', text)
    if tap_match and any(kw in text for kw in ["タップ", "押す", "選択", "クリック"]):
        return {
            "strategy": "tap_by_text",
            "search_text": tap_match.group(1),
            "match_type": "exact",
            "element_metadata": extract_metadata(step_result)
        }

    # 6. Back/Home navigation
    if matches(text, ["戻るボタンを押す", "前の画面に戻る", "戻る"]):
        return {"strategy": "keyevent", "keycode": 4, "key_name": "BACK"}

    if matches(text, ["ホームに戻る", "ホーム画面に戻る"]):
        return {"strategy": "keyevent", "keycode": 3, "key_name": "HOME"}

    # 7. Wait
    wait_match = re.search(r'(\d+)秒待つ', text)
    if wait_match:
        return {"strategy": "wait", "duration_sec": int(wait_match.group(1))}

    # 8. Ambiguous action - needs AI at runtime
    # If step_result has resource_id, use tap_by_resource_id
    metadata = extract_metadata(step_result)
    if metadata and metadata.get("resource_id"):
        return {
            "strategy": "tap_by_resource_id",
            "resource_id": metadata["resource_id"],
            "fallback_text": extract_any_text(text),
            "element_metadata": metadata
        }

    # 9. Truly ambiguous - AI checkpoint required
    return {"strategy": "ai_checkpoint", "assertion": text}
```

#### Pattern Match Helper

```python
def matches(text, patterns):
    """Check if text matches any of the patterns (substring match)."""
    return any(p in text for p in patterns)

def extract_field_hint(text):
    """Extract field description from input action text."""
    # "メールアドレス欄に「xxx」を入力" -> "メールアドレス"
    match = re.match(r'(.+?)[欄フィールド]?[にへ]「', text)
    return match.group(1).strip() if match else ""

def extract_metadata(step_result):
    """Extract element metadata from result.json step."""
    if not step_result or "target_element" not in step_result:
        return None
    te = step_result["target_element"]
    return {
        "resource_id": te.get("resource_id", ""),
        "class": te.get("class", ""),
        "content_desc": te.get("content_desc", ""),
        "bounds": te.get("bounds", ""),
        "parent_hierarchy": te.get("parent_hierarchy", [])
    }
```

### 3. Then Classification

```python
def classify_then(text, strict):
    """
    Classify a 'then' assertion.

    Args:
        text: Original assertion text
        strict: Whether strict mode is enabled

    Returns:
        Compiled strategy dict
    """

    # 1. Quoted text present - can be auto-promoted to strict
    quoted_match = re.search(r'「(.+?)」', text)
    if quoted_match:
        search_text = quoted_match.group(1)

        # Check for negation
        negate = "ないこと" in text or "されていないこと" in text

        # Check for contains vs exact
        match_type = "contains" if "含まれ" in text else "exact"

        return {
            "strategy": "strict_text_match",
            "search_text": search_text,
            "match_type": match_type,
            "negate": negate
        }

    # 2. Explicit strict mode but no quoted text
    if strict:
        # Cannot do strict match without quoted text
        return {
            "strategy": "ai_checkpoint",
            "assertion": text,
            "hint": "strict mode requested but no quoted text available"
        }

    # 3. Vision-based assertion (default)
    return {
        "strategy": "ai_checkpoint",
        "assertion": text
    }
```

### 4. Compilation Process

```python
def compile_scenario(scenario_yaml, result_json):
    """
    Main compilation function.

    Args:
        scenario_yaml: Parsed YAML scenario
        result_json: Parsed result.json from first AI run

    Returns:
        compiled.json dict
    """
    compiled = {
        "version": "1.0",
        "compiled_at": now_iso8601(),
        "source": scenario_yaml["_file_path"],
        "source_hash": sha256(scenario_yaml["_file_path"]),
        "platform": "android",
        "app": scenario_yaml["app"],
        "device": result_json["device"],
        "variables": scenario_yaml.get("variables", {}),
        "steps": []
    }

    global_strict = scenario_yaml.get("config", {}).get("strict", False)
    step_index = 0
    result_steps = {s["index"]: s for s in result_json["steps"]}

    for section in scenario_yaml["steps"]:
        section_id = section["id"]

        # Handle replay
        if "replay" in section:
            step_index += 1
            replay_step = compile_replay(
                section, scenario_yaml["steps"], step_index, result_steps
            )
            compiled["steps"].append(replay_step)

        # Handle actions
        for action in section.get("actions", []):
            step_index += 1
            result_step = result_steps.get(step_index, {})

            if "do" in action:
                strict = action.get("strict", global_strict)
                strategy = classify_action(action["do"], result_step)
                compiled_step = {
                    "index": step_index,
                    "section": section_id,
                    "type": "do",
                    "original": action["do"],
                    "compiled": strategy
                }
                if action.get("wait"):
                    compiled_step["wait"] = action["wait"]
                if strict:
                    compiled_step["strict"] = strict

            elif "then" in action:
                strict = action.get("strict", global_strict)
                strategy = classify_then(action["then"], strict)
                compiled_step = {
                    "index": step_index,
                    "section": section_id,
                    "type": "then",
                    "original": action["then"],
                    "strict": strict,
                    "compiled": strategy
                }

            compiled["steps"].append(compiled_step)

    return compiled
```

### 5. Output

```bash
# compiled.json を元の YAML ファイルと同じディレクトリに出力
# 例: sample/sample-login.yaml → sample/sample-login.yaml.compiled.json
output_path="${scenario}.compiled.json"
write_json(compiled, output_path)
```

## Output Format

### Success

```
## Scenario Compilation Complete

**Source**: sample/sample-login.yaml
**Output**: .adb-test/compiled/sample-login.compiled.json

### Compilation Summary

| Metric | Value |
|--------|-------|
| Total Steps | 8 |
| Fully Compiled | 5 (62.5%) |
| AI Checkpoints | 3 (37.5%) |

### Step Details

| # | Type | Strategy | Original |
|---|------|----------|----------|
| 1 | do | app_launch | アプリを起動 |
| 2 | then | ai_checkpoint | ログイン画面が表示されていること |
| 3 | do | text_input | メールアドレス欄に「(email)」を入力 |
| 4 | do | text_input | パスワード欄に「(password)」を入力 |
| 5 | do | tap_by_text | 「ログイン」ボタンをタップ |
| 6 | then | ai_checkpoint | ホーム画面が表示されていること |
| 7 | do | ai_checkpoint | プロフィールアイコンをタップ |
| 8 | then | ai_checkpoint | ユーザー名が表示されていること |

### Expected Performance

- **Without AI**: Steps 1, 3, 4, 5 execute without AI (1-3s each)
- **With AI**: Steps 2, 6, 7, 8 require AI evaluation (5-15s each)
- **Estimated speedup**: ~2-3x vs full AI execution
```

### Error

```
## Compilation Failed

**Source**: sample/sample-login.yaml
**Error**: result.json not found at <path>

Please run the scenario with AI first:
  /uiai-android-test scenarios=sample/sample-login.yaml
```

## Notes

- The compiler NEVER executes ADB commands. It only reads result.json and generates compiled.json.
- Variable references like `(email)` are preserved as-is in compiled.json (resolved at runtime).
- Replay sections are expanded inline with references to the original compiled steps.
- If result.json step indices don't match the YAML structure, the compiler logs a warning and falls back to pattern-only classification (without element metadata).
