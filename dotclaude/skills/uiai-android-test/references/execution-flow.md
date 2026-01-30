# Execution Flow

`/uiai-android-test` コマンドの内部実行フローの詳細。

## パラメータ解析

```bash
# $ARGUMENTS からパラメータを抽出
scenarios="${scenarios:-test/scenarios/**/*.yaml}"
device="${device:-}"
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

## シナリオ順次実行

各シナリオに対して以下を実行:

```
for scenario_file in scenario_files:
  # シナリオ名を抽出
  scenario_name=$(grep "^name:" $scenario_file | cut -d'"' -f2)

  echo "=========================================="
  echo "Running: $scenario_name"
  echo "File: $scenario_file"
  echo "=========================================="

  # 1. テスト実行（adb-test-runner エージェント起動）
  Task: adb-test-runner
    scenario=$scenario_file
    device=$device
    output_dir=$BASE_OUTPUT_DIR/$scenario_name

  # 2. 結果評価（adb-test-evaluator エージェント起動）
  Task: adb-test-evaluator
    result_dir=$BASE_OUTPUT_DIR/$scenario_name
    scenario=$scenario_file

  # 3. 結果を収集
  collect_result($scenario_name, $result_dir)
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
