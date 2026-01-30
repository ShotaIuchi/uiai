# Execution Flow

`/uiai-ios-test` コマンドの内部実行フローの詳細。

## パラメータ解析

```bash
# $ARGUMENTS からパラメータを抽出
scenarios="${scenarios:-test/scenarios/**/*.yaml}"
simulator="${simulator:-booted}"
strict="${strict:-false}"
```

## 前提条件確認

```bash
# Xcode 確認
if ! xcode-select -p &> /dev/null; then
  echo "Error: Xcode not found"
  exit 1
fi

# simctl 確認
if ! xcrun simctl help &> /dev/null; then
  echo "Error: simctl not available"
  exit 1
fi

# IDB 確認
if ! command -v idb &> /dev/null; then
  echo "Error: Facebook IDB not found"
  echo ""
  echo "Please install IDB:"
  echo "  brew tap facebook/fb"
  echo "  brew install idb-companion"
  echo "  pip3 install fb-idb"
  exit 1
fi

# シミュレータ確認
booted_sims=$(xcrun simctl list devices | grep "(Booted)" | wc -l)
if [ "$booted_sims" -eq 0 ]; then
  echo "Error: No simulator is running"
  echo ""
  echo "Please boot a simulator:"
  echo "  xcrun simctl boot <udid>"
  echo ""
  echo "Or open Simulator.app"
  exit 1
fi

# シミュレータ指定がない/booted場合は最初の起動中シミュレータを使用
if [ "$simulator" = "booted" ]; then
  simulator=$(xcrun simctl list devices | grep "(Booted)" | head -1 | grep -oE '[A-F0-9-]{36}')
fi

echo "Using simulator: $simulator"

# IDB接続
idb connect "$simulator" 2>/dev/null || true
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
BASE_OUTPUT_DIR=".ios-test/results/$TIMESTAMP"
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

  # 1. テスト実行（ios-test-runner エージェント起動）
  Task: ios-test-runner
    scenario=$scenario_file
    simulator=$simulator
    output_dir=$BASE_OUTPUT_DIR/$scenario_name

  # 2. 結果評価（ios-test-evaluator エージェント起動）
  Task: ios-test-evaluator
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
# uiai iOS Test Summary

## Execution Info

| Item | Value |
|------|-------|
| Timestamp | 2026-01-29 10:00:00 |
| Simulator | iPhone 15 (XXXXXXXX...) |
| iOS Version | 17.2 |
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

### Xcode未インストール

```
Error: Xcode not found

Please install Xcode from the App Store:
  https://apps.apple.com/app/xcode/id497799835

After installation, run:
  xcode-select --install
```

### IDB未インストール

```
Error: Facebook IDB not found

Please install IDB:
  brew tap facebook/fb
  brew install idb-companion
  pip3 install fb-idb

After installation, start idb_companion:
  idb_companion --udid <simulator-udid> &
```

### シミュレータ未起動

```
Error: No simulator is running

Please boot a simulator:
  1. Open Simulator.app
  2. Or run: xcrun simctl boot <udid>

Available simulators:
  - iPhone 15 (XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX) - iOS 17.2
  - iPhone 15 Pro (YYYYYYYY-YYYY-YYYY-YYYY-YYYYYYYYYYYY) - iOS 17.2
```

### シナリオファイルなし

```
Error: No scenario files found matching: test/scenarios/**/*.yaml

Please create scenario files or specify a different path:
  /uiai-ios-test scenarios=path/to/scenarios/*.yaml

See SKILL.md for scenario format documentation.
```

### シナリオパースエラー

```
Error: Failed to parse scenario file

File: test/scenarios/login-flow.yaml
Error: Missing required field: 'app'

Required fields: name, app, steps
```

### IDB接続失敗

```
Error: Failed to connect IDB to simulator

Simulator: iPhone 15 (XXXXXXXX...)

Please try:
  1. Restart idb_companion:
     pkill idb_companion
     idb_companion --udid <udid> &

  2. Restart the simulator:
     xcrun simctl shutdown <udid>
     xcrun simctl boot <udid>

  3. Check IDB installation:
     pip3 install --upgrade fb-idb
```

## iOS固有の処理

### 「戻る」操作の変換

iOSには汎用的な戻るキーがないため、シナリオの「戻る」を変換：

| シナリオ記述 | 変換後のコマンド |
|-------------|-----------------|
| `戻るボタンを押す` | `idb ui swipe 0 400 300 400` (左端からスワイプ) |
| `前の画面に戻る` | `idb ui swipe 0 400 300 400` |
| `ホームに戻る` | `idb ui button HOME` |
| `「戻る」ボタンをタップ` | ナビゲーションバーの戻るボタンを探してタップ |

### UIツリーの属性マッピング

Android XMLからiOS JSONへの属性変換：

| Android (XML) | iOS (JSON) | 用途 |
|---------------|------------|------|
| `text` | `AXLabel` | 表示テキスト |
| `resource-id` | `AXIdentifier` | 識別子 |
| `content-desc` | `AXValue` | 値/説明 |
| `bounds` | `frame` | 位置とサイズ |
| `class` | `type` | 要素タイプ |

### 座標計算の違い

Android:
```
bounds="[100,200][300,400]"
center = ((100+300)/2, (200+400)/2) = (200, 300)
```

iOS:
```json
"frame": {"x": 100, "y": 200, "width": 200, "height": 200}
center = (100 + 200/2, 200 + 200/2) = (200, 300)
```

## 出力ディレクトリ構造

```
.ios-test/
└── results/
    └── 20260129_100000/
        ├── summary.md           # 全体サマリー
        ├── login_test/
        │   ├── result.json      # 実行結果JSON
        │   ├── report.md        # 評価レポート
        │   ├── step_01_before.png
        │   ├── step_01_after.png
        │   ├── step_01_ui.json  # UIツリー（JSON形式）
        │   └── ...
        └── search_test/
            ├── result.json
            ├── report.md
            └── ...
```
