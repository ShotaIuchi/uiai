# Execution Flow

`/uiai-web-test` コマンドの内部実行フローの詳細。

## パラメータ解析

```bash
# $ARGUMENTS からパラメータを抽出
scenarios="${scenarios:-test/scenarios/**/*.yaml}"
browser="${browser:-chromium}"
headless="${headless:-true}"
strict="${strict:-false}"
```

## 前提条件確認

```bash
# Node.js 確認
if ! command -v node &> /dev/null; then
  echo "Error: node command not found"
  exit 1
fi

# バージョン確認
node_version=$(node --version | sed 's/v//' | cut -d. -f1)
if [ "$node_version" -lt 16 ]; then
  echo "Error: Node.js v16 or higher required"
  exit 1
fi

# Playwright 確認
if ! npx playwright --version &> /dev/null; then
  echo "Error: Playwright not installed"
  echo ""
  echo "Please install Playwright:"
  echo "  npm install -D playwright"
  echo "  npx playwright install"
  exit 1
fi

# ブラウザ確認
if ! npx playwright install "$browser" --dry-run 2>&1 | grep -q "already installed"; then
  echo "Error: Browser $browser not installed"
  echo ""
  echo "Please install the browser:"
  echo "  npx playwright install $browser"
  exit 1
fi

echo "Using browser: $browser (headless: $headless)"
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
BASE_OUTPUT_DIR=".web-test/results/$TIMESTAMP"
mkdir -p "$BASE_OUTPUT_DIR"
```

## Variable Collection Phase

Collect placeholder variables (undefined or null) before scenario execution.

### Flow Diagram

```
┌─────────────────────────────────────┐
│       Load Scenario YAML            │
└─────────────────────┬───────────────┘
                      │
                      ▼
┌─────────────────────────────────────┐
│      Parse variables section        │
└─────────────────────┬───────────────┘
                      │
                      ▼
          ┌───────────┴───────────┐
          │ Placeholder vars?     │
          │ (undefined or null)   │
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
│ Check environment   │          │
└──────────┬──────────┘          │
           │                     │
    ┌──────┼──────┐              │
    │             │              │
    ▼             ▼              │
┌───┴───┐   ┌─────┴─────┐        │
│  CI   │   │Interactive│        │
└───┬───┘   └─────┬─────┘        │
    │             │              │
    ▼             ▼              │
┌───┴──────┐ ┌────┴─────┐        │
│Skip test │ │  Display │        │
└──────────┘ │  prompts │        │
             └────┬─────┘        │
                  │              │
                  ▼              │
         ┌────────┴────────┐     │
         │ Wait for input  │     │
         └────────┬────────┘     │
                  │              │
                  ▼              │
         ┌────────┴────────┐     │
         │Store values in  │     │
         │memory           │     │
         └────────┬────────┘     │
                  │              │
                  └──────┬───────┘
                         │
                         ▼
              ┌──────────┴──────────┐
              │  Start test run     │
              └─────────────────────┘
```

### Variable Collection Implementation

```bash
# Extract variables from scenario
variables=$(parse_yaml_variables "$scenario_file")

# Detect placeholder variables (undefined or null)
placeholder_vars=()
for var_name in ${!variables[@]}; do
  var_value="${variables[$var_name]}"
  # Treat null or undefined (empty) as placeholder
  if [ "$var_value" = "null" ] || [ -z "$var_value" ]; then
    placeholder_vars+=("$var_name")
  fi
done

# If placeholder variables exist
if [ ${#placeholder_vars[@]} -gt 0 ]; then
  # Detect non-interactive environment
  if [ ! -t 0 ] || [ -n "$CI" ] || [ -n "$GITHUB_ACTIONS" ]; then
    echo "Skipped: variables [${placeholder_vars[*]}] require interactive input"
    skip_scenario
    continue
  fi

  # Interactive prompt
  echo "=== Variables require input ==="
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
  echo "=== Variable input complete ==="
  echo ""
fi
```

### Non-Interactive Environment Detection

Detected as non-interactive when:

| Condition | Description |
|-----------|-------------|
| `[ ! -t 0 ]` | stdin is not a terminal |
| `$CI` | CI environment variable is set |
| `$GITHUB_ACTIONS` | Running in GitHub Actions |
| `$JENKINS_URL` | Running in Jenkins |
| `$GITLAB_CI` | Running in GitLab CI |

### Non-Interactive Environment Behavior

```
=== Test Skipped ===

Scenario: Login Flow (test/login-flow.yaml)
Reason: Variables require interactive input

The following variables are placeholders and require user input:
  - password
  - api_key

To run this test:
  1. Run in interactive terminal
  2. Or provide values in the YAML file

=== End ===
```

## シナリオ順次実行

各シナリオに対して以下を実行:

```
for scenario_file in scenario_files:
  # シナリオ名を抽出
  scenario_name=$(grep "^name:" $scenario_file | cut -d'"' -f2)

  # Base URL を抽出
  base_url=$(grep "web:" $scenario_file | cut -d'"' -f2)

  echo "=========================================="
  echo "Running: $scenario_name"
  echo "File: $scenario_file"
  echo "URL: $base_url"
  echo "=========================================="

  # 1. テスト実行（web-test-runner エージェント起動）
  Task: web-test-runner
    scenario=$scenario_file
    browser=$browser
    headless=$headless
    output_dir=$BASE_OUTPUT_DIR/$scenario_name

  # 2. 結果評価（web-test-evaluator エージェント起動）
  Task: web-test-evaluator
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
# uiai Web Test Summary

## Execution Info

| Item | Value |
|------|-------|
| Timestamp | 2026-01-30 10:00:00 |
| Browser | chromium (120.0.6099.71) |
| Headless | true |
| Scenarios | 5 |
| Duration | 2m 30s |

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

### Node.js未インストール

```
Error: node command not found

Please install Node.js v16 or higher:
- macOS: brew install node
- Linux: See https://nodejs.org/
- Windows: Download from https://nodejs.org/
```

### Playwright未インストール

```
Error: Playwright not installed

Please install Playwright:
  npm install -D playwright
  npx playwright install

See https://playwright.dev/docs/intro for details.
```

### ブラウザ未インストール

```
Error: Browser webkit not installed

Please install the browser:
  npx playwright install webkit

Or install all browsers:
  npx playwright install
```

### シナリオファイルなし

```
Error: No scenario files found matching: test/scenarios/**/*.yaml

Please create scenario files or specify a different path:
  /uiai-web-test scenarios=path/to/scenarios/*.yaml

See SKILL.md for scenario format documentation.
```

### シナリオパースエラー

```
Error: Failed to parse scenario file

File: test/scenarios/login-flow.yaml
Error: Missing required field: 'app.web'

Required fields: name, app.web, steps
```

### ページロードエラー

```
Error: Failed to load page

URL: https://example.com/login
Error: net::ERR_CONNECTION_REFUSED

Please check:
1. The URL is correct and accessible
2. The server is running
3. Network connectivity
```

### 要素特定エラー

```
Error: Element not found

Action: Click 'Submit' button
Timeout: 30000ms

The element could not be found on the page.
Screenshot saved: step_03_before.png

Suggestions:
1. Check if the element text is correct
2. Check if the element is visible on the page
3. The element may be in an iframe
```

## Web固有の考慮事項

### ネットワーク待機

```
# ページロード後、ネットワークが安定するまで待機
await page.waitForLoadState('networkidle');

# または DOM が完全に構築されるまで
await page.waitForLoadState('domcontentloaded');
```

### iframe対応

```
# iframe 内の要素を操作する場合
const frame = page.frameLocator('#iframe-id');
await frame.getByRole('button', { name: 'Submit' }).click();
```

### シャドウDOM対応

```
# シャドウDOM内の要素
// Playwright は自動的にシャドウDOMを透過して検索
await page.getByRole('button', { name: 'Submit' }).click();
```

### Cookie/認証

```
# 認証状態を保持する場合
const context = await browser.newContext({
  storageState: 'auth.json'
});

# 認証状態を保存
await context.storageState({ path: 'auth.json' });
```

## パフォーマンス最適化

### 並列実行

```bash
# 複数シナリオを並列実行する場合（将来の拡張）
# 各シナリオを別のブラウザコンテキストで実行
```

### リソースブロック

```javascript
// 不要なリソースをブロックしてテスト高速化
await page.route('**/*.{png,jpg,jpeg,gif,svg}', route => route.abort());
await page.route('**/analytics/**', route => route.abort());
```

### キャッシュ活用

```javascript
// ブラウザキャッシュを有効化
const context = await browser.newContext({
  // キャッシュを維持
});
```
