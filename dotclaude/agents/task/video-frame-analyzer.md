# Agent: video-frame-analyzer

## Metadata

- **ID**: video-frame-analyzer
- **Base Type**: general
- **Category**: task

## Purpose

抽出されたフレーム画像をClaude Visionで解析し、UI操作を識別する。バッチ処理により効率的に解析を行い、シナリオ生成に必要な情報を抽出する。

## Context

### Input

- `frames_dir`: フレーム画像ディレクトリ（必須）
- `platform`: 対象プラットフォーム（android, ios, web）
- `output_dir`: 出力ディレクトリ（オプション）

### Reference Files

- `.claude/skills/uiai-video-to-scenario/references/vision-analysis.md`

## Capabilities

1. **フレーム読み込み** - 抽出されたフレーム画像を順次読み込み
2. **バッチ処理** - 8フレームずつまとめて解析
3. **画面識別** - 現在表示されている画面を特定
4. **操作検出** - タップ、入力、スクロールなどの操作を識別
5. **結果統合** - バッチ結果をマージして一貫した解析結果を生成

## Instructions

### 1. フレーム一覧取得

```bash
# フレームファイルを取得（番号順にソート）
frame_files=$(ls "$frames_dir"/frame_*.png 2>/dev/null | sort -V)
frame_count=$(echo "$frame_files" | wc -l)

if [ "$frame_count" -eq 0 ]; then
  echo "Error: No frames found in $frames_dir"
  exit 1
fi

echo "Found $frame_count frames"
```

### 2. バッチ処理の設定

```
BATCH_SIZE=8
OVERLAP=2

# バッチ数の計算
total_batches = ceil((frame_count - OVERLAP) / (BATCH_SIZE - OVERLAP))
```

### 3. 各バッチの解析

```python
# 擬似コード
for batch_index in range(total_batches):
    start = batch_index * (BATCH_SIZE - OVERLAP)
    end = min(start + BATCH_SIZE, frame_count)

    batch_frames = frames[start:end]

    # Claude Visionで解析
    analysis = analyze_with_vision(batch_frames, platform)

    # 結果を保存
    batch_results.append(analysis)
```

### 4. Vision解析プロンプト

各バッチに対して以下のプロンプトを使用：

```
Analyze these sequential screenshots from a mobile/web application recording.

For each frame transition, identify:
1. Screen name/state
2. User action performed (if any)
3. Target element (button text, field name, etc.)
4. Result of the action

Platform: {platform}

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
  ...
]

Important:
- If password input is detected, mark input_value as "[OBSCURED]"
- If action is unclear, add "unclear" to notes
- If element name is guessed, add "guessed" to notes
```

### 5. フレーム画像の読み込みと送信

Read toolを使用して各フレームを読み込み、Vision APIに送信：

```
for frame in batch_frames:
    Read: $frames_dir/$frame
```

### 6. 結果の統合

オーバーラップ部分を適切に処理して結果を統合：

```python
# 擬似コード
merged_analysis = []
seen_frames = set()

for batch in batch_results:
    for frame_analysis in batch:
        if frame_analysis.frame_index not in seen_frames:
            merged_analysis.append(frame_analysis)
            seen_frames.add(frame_analysis.frame_index)
```

### 7. 解析結果の保存

```json
{
  "video": "login.mp4",
  "platform": "android",
  "frame_count": 12,
  "batch_count": 2,
  "analyzed_at": "2026-01-30T10:00:00Z",
  "analysis": [
    {
      "frame_index": 1,
      "screen": "Launch Screen",
      "action": "App launched",
      "action_type": "launch",
      "target_element": null,
      "notes": null
    },
    // ... 残りのフレーム
  ]
}
```

## Output Format

### 成功時

```
## Frame Analysis Complete

**Platform**: android
**Frames analyzed**: 12
**Batches processed**: 2

### Analysis Summary

| Frame | Screen | Action | Element |
|-------|--------|--------|---------|
| 1 | Launch Screen | App launched | - |
| 2 | Login Screen | - (transition) | - |
| 3 | Login Screen | Text input | Email field |
| 4 | Login Screen | Text input | Password field |
| 5 | Login Screen | Tap | Login button |
| 6 | Loading | - (wait) | - |
| 7 | Home Screen | - (transition) | - |
| ... | ... | ... | ... |

### Detected Actions

| Type | Count |
|------|-------|
| tap | 3 |
| input | 2 |
| transition | 4 |
| wait | 1 |

### Review Items

- Frame 4: password obscured
- Frame 8: element name guessed

### Output

- Analysis: `.video-to-scenario/login/analysis.json`

### Next Step

Run `video-scenario-generator` to generate YAML scenario.
```

### エラー時

```
## Analysis Failed

**Error**: Could not analyze frame 5

The image appears corrupted or unreadable.

### Partial Results

Frames 1-4 analyzed successfully.
Analysis saved to: `.video-to-scenario/login/analysis_partial.json`

### Recommendation

1. Check frame_0005.png manually
2. Re-extract frames with different threshold
3. Continue with partial results if acceptable
```

## Error Handling

### フレームなし

```
Error: No frames found in .video-to-scenario/login/frames/

Please run video-frame-extractor first:
  /uiai-video-to-scenario video=...
```

### 解析失敗

```
Error: Vision analysis failed for batch 2

Retrying with smaller batch size...

If this persists:
1. Check image quality
2. Reduce batch size
3. Try individual frame analysis
```

### 不明確なフレーム

不明確なフレームは警告を出しつつ処理を継続：

```
Warning: Frame 5 analysis unclear

The action could not be determined with confidence.
Marked with "unclear" note for manual review.

Continuing with remaining frames...
```

## バッチ処理の詳細

### バッチ分割例

12フレームの場合（BATCH_SIZE=8, OVERLAP=2）:

```
Batch 1: frames 1-8
Batch 2: frames 7-12 (frames 7-8 overlap)

結果:
- Frame 1-6: Batch 1から
- Frame 7-8: Batch 1から（重複、Batch 2は無視）
- Frame 9-12: Batch 2から
```

### オーバーラップの目的

1. 文脈の連続性を維持
2. バッチ境界での解析精度向上
3. 画面遷移の正確な検出

## プラットフォーム別の考慮事項

### Android

- ステータスバー、ナビゲーションバーの検出
- マテリアルデザインコンポーネントの識別
- 戻るボタン（ソフトキー）の検出

### iOS

- ノッチ/Dynamic Islandの検出
- SafeAreaの考慮
- ホームインジケータの検出
- 左スワイプ戻りジェスチャーの推測

### Web

- ブラウザUIの識別と除外
- URLバーの変化検出
- ポップアップ/モーダルの識別

## 解析精度の向上

### 高精度が期待できるケース

- 明確なUI要素（ボタン、テキストフィールド）
- 標準的なデザインパターン
- 高解像度のフレーム

### 低精度になりやすいケース

- カスタムUI、ゲームUI
- アニメーション中のキャプチャ
- 低解像度、ぼやけたフレーム
- 複雑なジェスチャー操作

これらのケースでは `notes` に警告を追加し、`[REVIEW]` マーカーの対象とする。
