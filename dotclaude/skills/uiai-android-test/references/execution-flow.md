# Execution Flow

`/uiai-android-test` コマンドの内部実行フローの詳細。

## パラメータ解析

```bash
# $ARGUMENTS からパラメータを抽出
scenarios="${scenarios:-test/scenarios/**/*.yaml}"
device="${device:-}"
skip_ai="${skip_ai:-false}"
force_ai="${force_ai:-false}"
```

## 前提条件確認

```bash
# ADB 接続確認
if ! command -v adb &> /dev/null; then
  echo "Error: adb command not found"
  exit 1
fi

# デバイス接続確認
device_count=$(adb devices | grep -c "device$")
if [ "$device_count" -eq 0 ]; then
  echo "Error: No device connected"
  echo ""
  echo "Please ensure:"
  echo "1. Device/emulator is running"
  echo "2. USB debugging is enabled"
  echo "3. Run 'adb devices' to verify"
  exit 1
fi

# デバイス指定がない場合は最初のデバイスを使用
if [ -z "$device" ]; then
  device=$(adb devices | grep "device$" | head -1 | awk '{print $1}')
fi

echo "Using device: $device"
```

## シナリオファイル検出

```bash
# glob パターンでシナリオファイルを検索
Glob: pattern="$scenarios"

# ファイルが見つからない場合
if [ ${#scenario_files[@]} -eq 0 ]; then
  echo "Error: No scenario files found matching: $scenarios"
  exit 1
fi

echo "Found ${#scenario_files[@]} scenario(s)"
```

## 出力ディレクトリ準備

```bash
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BASE_OUTPUT_DIR=".adb-test/results/$TIMESTAMP"
mkdir -p "$BASE_OUTPUT_DIR"
```

## 変数収集フェーズ

シナリオ実行前にプレースホルダー変数（値省略またはnull）の収集を行う。

### フロー図

```
┌─────────────────────────────────────┐
│        シナリオ YAML 読み込み         │
└─────────────────────┬───────────────┘
                      │
                      ▼
┌─────────────────────────────────────┐
│       variables セクション解析        │
└─────────────────────┬───────────────┘
                      │
                      ▼
          ┌───────────┴───────────┐
          │ プレースホルダー変数あり? │
          │ (値省略 or null)       │
          └───────────┬───────────┘
                      │
           ┌──────────┼──────────┐
           │                     │
           ▼                     ▼
    ┌──────┴──────┐       ┌──────┴──────┐
    │     Yes     │       │     No      │
    └──────┬──────┘       └──────┬──────┘
           │                     │
           ▼                     │
┌──────────┴──────────┐          │
│  非対話式環境か確認  │          │
└──────────┬──────────┘          │
           │                     │
    ┌──────┼──────┐              │
    │             │              │
    ▼             ▼              │
┌───┴───┐   ┌─────┴─────┐        │
│  CI   │   │ 対話式OK  │        │
└───┬───┘   └─────┬─────┘        │
    │             │              │
    ▼             ▼              │
┌───┴──────┐ ┌────┴─────┐        │
│テストスキップ│ │ プロンプト│        │
└──────────┘ │ 表示     │        │
             └────┬─────┘        │
                  │              │
                  ▼              │
         ┌────────┴────────┐     │
         │  ユーザー入力待ち │     │
         └────────┬────────┘     │
                  │              │
                  ▼              │
         ┌────────┴────────┐     │
         │  変数値をメモリに │     │
         │  保存            │     │
         └────────┬────────┘     │
                  │              │
                  └──────┬───────┘
                         │
                         ▼
              ┌──────────┴──────────┐
              │   テスト実行開始     │
              └─────────────────────┘
```

### 変数収集の実装

```bash
# シナリオから変数を抽出
variables=$(parse_yaml_variables "$scenario_file")

# プレースホルダー変数を検出（値省略またはnull）
placeholder_vars=()
for var_name in ${!variables[@]}; do
  var_value="${variables[$var_name]}"
  # null または undefined（空）をプレースホルダーとして扱う
  if [ "$var_value" = "null" ] || [ -z "$var_value" ]; then
    placeholder_vars+=("$var_name")
  fi
done

# プレースホルダー変数がある場合
if [ ${#placeholder_vars[@]} -gt 0 ]; then
  # 非対話式環境の検出
  if [ ! -t 0 ] || [ -n "$CI" ] || [ -n "$GITHUB_ACTIONS" ]; then
    echo "Skipped: variables [${placeholder_vars[*]}] require interactive input"
    skip_scenario
    continue
  fi

  # 対話式プロンプト
  echo "=== 変数入力が必要です ==="
  echo ""
  for var_name in "${placeholder_vars[@]}"; do
    prompt_msg=$(get_custom_prompt "$var_name" "$scenario_file")
    if [ -n "$prompt_msg" ]; then
      echo "Variable '$var_name' is not set."
      read -p "$prompt_msg: " var_value
    else
      echo "Variable '$var_name' is not set."
      read -p "Enter value for $var_name: " var_value
    fi
    variables[$var_name]="$var_value"
    echo ""
  done
  echo "=== 変数入力完了 ==="
  echo ""
fi
```

### 非対話式環境の検出

以下の条件で非対話式環境と判定：

| 条件 | 説明 |
|------|------|
| `[ ! -t 0 ]` | 標準入力がターミナルでない |
| `$CI` | CI 環境変数が設定されている |
| `$GITHUB_ACTIONS` | GitHub Actions で実行中 |
| `$JENKINS_URL` | Jenkins で実行中 |
| `$GITLAB_CI` | GitLab CI で実行中 |

### 非対話式環境での動作

```
=== Test Skipped ===

Scenario: ログインテスト (test/login-flow.yaml)
Reason: Variables require interactive input

The following variables have null values and require user input:
  - password
  - api_key

To run this test:
  1. Run in interactive terminal
  2. Or provide values in the YAML file

=== End ===
```

## シナリオ順次実行

### 実行モード判定（デフォルト: Auto-Compiled）

デフォルトで compiled.json を自動チェックする。`force-ai=true` の場合のみ AI 強制実行。

```
┌─────────────────────────────────────┐
│       パラメータ確認                 │
│   force-ai=true ?                   │
└─────────────────┬───────────────────┘
                  │
       ┌──────────┼──────────┐
       │                     │
       ▼                     ▼
┌──────┴──────┐       ┌──────┴──────────┐
│ force-ai    │       │ Auto (default)  │
│ → AI実行    │       │ compiled.json   │
│ + 再コンパイル│       │ 存在チェック     │
└─────────────┘       └────────┬────────┘
                               │
                    ┌──────────┼──────────┐
                    │                     │
                    ▼                     ▼
             ┌──────┴──────┐       ┌──────┴──────┐
             │ あり & hash  │       │ なし or     │
             │ 一致         │       │ hash 不一致  │
             └──────┬──────┘       └──────┬──────┘
                    │                     │
                    ▼                     ▼
             ┌──────────────┐      ┌──────────────┐
             │ Compiled     │      │ AI実行       │
             │ Runner       │      │ + コンパイル   │
             │ (高速実行)    │      │ (初回 or 更新) │
             └──────┬───────┘      └──────────────┘
                    │
            ┌───────┼───────┐
            │               │
            ▼               ▼
     ┌──────┴──────┐ ┌─────┴──────┐
     │ skip-ai?    │ │ AI steps   │
     │ → SKIP      │ │ → evaluator│
     └─────────────┘ └────────────┘
```

### Default Flow (Auto-Compiled)

各シナリオに対して以下を実行:

```
for scenario_file in scenario_files:
  scenario_name=$(grep "^name:" $scenario_file | cut -d'"' -f2)
  compiled_path="${scenario_file}.compiled.json"

  echo "=========================================="
  echo "Running: $scenario_name"
  echo "File: $scenario_file"
  echo "=========================================="

  # --- force-ai: AI強制実行 + 再コンパイル ---
  if [ "$force_ai" = "true" ]; then
    Task: adb-test-runner
      scenario=$scenario_file
      device=$device
      output_dir=$BASE_OUTPUT_DIR/$scenario_name

    Task: adb-test-evaluator
      result_dir=$BASE_OUTPUT_DIR/$scenario_name
      scenario=$scenario_file

    Task: scenario-compiler
      result_dir=$BASE_OUTPUT_DIR/$scenario_name
      scenario=$scenario_file
      output_dir=.adb-test/compiled/

    collect_result($scenario_name, $result_dir)
    continue
  fi

  # --- Auto: compiled.json の存在 & 鮮度チェック ---
  if [ -f "$compiled_path" ]; then
    source_hash=$(shasum -a 256 "$scenario_file" | awk '{print $1}')
    compiled_hash=$(jq -r '.source_hash' "$compiled_path" | sed 's/sha256://')

    if [ "$source_hash" = "$compiled_hash" ]; then
      # Compiled Runner で高速実行
      echo "Running compiled: $scenario_name"
      python scripts/compiled_runner.py "$compiled_path" \
        --device "$device" \
        --output-dir "$BASE_OUTPUT_DIR/$scenario_name" \
        ${skip_ai:+--skip-ai}

      # AI checkpoints があれば evaluator を実行
      if [ "$skip_ai" != "true" ]; then
        ai_required=$(jq '[.steps[] | select(.status == "ai_required")] | length' \
          "$BASE_OUTPUT_DIR/$scenario_name/result.json")

        if [ "$ai_required" -gt 0 ]; then
          Task: adb-test-evaluator
            result_dir=$BASE_OUTPUT_DIR/$scenario_name
            scenario=$scenario_file
        fi
      fi

      collect_result($scenario_name, $result_dir)
      continue
    fi
  fi

  # --- compiled.json が無い or stale → AI実行 + コンパイル ---
  echo "First run: $scenario_name (AI execution + compile)"

  Task: adb-test-runner
    scenario=$scenario_file
    device=$device
    output_dir=$BASE_OUTPUT_DIR/$scenario_name

  Task: adb-test-evaluator
    result_dir=$BASE_OUTPUT_DIR/$scenario_name
    scenario=$scenario_file

  Task: scenario-compiler
    result_dir=$BASE_OUTPUT_DIR/$scenario_name
    scenario=$scenario_file

  collect_result($scenario_name, $result_dir)
```

### Staleness Detection

| Signal | Detection | Action |
|--------|-----------|--------|
| YAML changed | `source_hash` mismatch | AI run + recompile |
| Element not found | UITree search failure at runtime | Fallback to AI for that step only |
| Screen size changed | `device.screen_size` mismatch | Warn (scroll coordinates may differ) |
| `force-ai=true` | Always | AI run + recompile |

### Per-Step AI Fallback

When compiled runner marks a step as `ai_required`:

```
compiled_runner.py 実行
  ├── step 1: app_launch → OK (compiled)
  ├── step 2: tap_by_text → OK (compiled)
  ├── step 3: ai_checkpoint → ai_required
  ├── step 4: text_input → OK (compiled)
  └── step 5: tap_by_text → ai_required (element not found)

→ skip-ai=false: adb-test-evaluator が ai_required ステップのみ評価
→ skip-ai=true:  ai_required ステップは SKIP 扱い
```

## 結果集約

```bash
# 全シナリオの結果を集約
total_scenarios=0
passed_scenarios=0
failed_scenarios=0
total_assertions=0
passed_assertions=0

for result in results:
  total_scenarios++
  if result.all_passed:
    passed_scenarios++
  else:
    failed_scenarios++
  total_assertions += result.assertion_count
  passed_assertions += result.passed_count
```

## サマリーレポート生成

```markdown
# uiai Android Test Summary

## Execution Info

| Item | Value |
|------|-------|
| Timestamp | 2026-01-29 10:00:00 |
| Device | emulator-5554 |
| Scenarios | 5 |
| Duration | 5m 30s |

## Results

### Scenarios

| Scenario | Status | Assertions | Pass Rate |
|----------|--------|------------|-----------|
| ログインフロー | PASSED | 15/15 | 100% |
| 商品検索 | PASSED | 12/12 | 100% |
| カート追加 | FAILED | 8/10 | 80% |
| 決済フロー | SKIPPED | - | - |
| ログアウト | PASSED | 5/5 | 100% |

### Summary

| Metric | Value |
|--------|-------|
| Total Scenarios | 5 |
| Passed | 3 (60%) |
| Failed | 1 (20%) |
| Skipped | 1 (20%) |
| Total Assertions | 40 |
| Passed Assertions | 35 (87.5%) |
```

## サマリー出力

```bash
# サマリーレポートをファイルに保存
Write: $BASE_OUTPUT_DIR/summary.md

# コンソール出力
echo ""
echo "=========================================="
echo "Test Execution Complete"
echo "=========================================="
echo ""
echo "Results: $passed_scenarios/$total_scenarios scenarios passed"
echo "Assertions: $passed_assertions/$total_assertions passed"
echo ""
echo "Output: $BASE_OUTPUT_DIR/"
echo "Summary: $BASE_OUTPUT_DIR/summary.md"
```

## エラーハンドリング

### ADB未インストール

```
Error: adb command not found

Please install Android SDK Platform Tools:
- macOS: brew install android-platform-tools
- Linux: sudo apt install android-tools-adb
- Windows: Download from https://developer.android.com/studio/releases/platform-tools
```

### デバイス未接続

```
Error: No device connected

Please ensure:
1. Device/emulator is running
2. USB debugging is enabled
3. ADB connection is authorized

Run 'adb devices' to verify connection.
```

### シナリオファイルなし

```
Error: No scenario files found matching: test/scenarios/**/*.yaml

Please create scenario files or specify a different path:
  /uiai-android-test scenarios=path/to/scenarios/*.yaml

See SKILL.md for scenario format documentation.
```

### シナリオパースエラー

```
Error: Failed to parse scenario file

File: test/scenarios/login-flow.yaml
Error: Missing required field: 'app'

Required fields: name, app, steps
```
