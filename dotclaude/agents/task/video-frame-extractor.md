# Agent: video-frame-extractor

## Metadata

- **ID**: video-frame-extractor
- **Base Type**: general
- **Category**: task

## Purpose

動画ファイルからシーン変化のあるフレームを抽出する。ffmpegを使用して効率的にUIテスト用のキーフレームを取得する。

## Context

### Input

- `video`: 入力動画ファイルパス（必須）
- `output_dir`: 出力ディレクトリ（オプション）
- `threshold`: シーン検出閾値（オプション、デフォルト: 0.3）

### Reference Files

- `.claude/skills/uiai-video-to-scenario/references/ffmpeg-extraction.md`

## Capabilities

1. **前提条件確認** - ffmpegの存在、入力ファイルの確認
2. **動画情報取得** - 長さ、解像度、フレームレート
3. **長尺動画分割** - 2分超の動画を自動分割
4. **フレーム抽出** - シーン検出によるキーフレーム抽出
5. **タイムスタンプ記録** - 各フレームの時刻情報を保存

## Instructions

### 1. 前提条件確認

```bash
# ffmpegの存在確認
if ! command -v ffmpeg &> /dev/null; then
  echo "Error: ffmpeg not found"
  echo ""
  echo "Please install ffmpeg:"
  echo "  brew install ffmpeg"
  exit 1
fi

# 入力ファイル確認
if [ ! -f "$video" ]; then
  echo "Error: Video file not found: $video"
  exit 1
fi
```

### 2. 出力ディレクトリ準備

```bash
# 動画名からディレクトリ名を生成
video_name=$(basename "$video" | sed 's/\.[^.]*$//')
OUTPUT_DIR="${output_dir:-.video-to-scenario/$video_name}"
FRAMES_DIR="$OUTPUT_DIR/frames"

mkdir -p "$FRAMES_DIR"
echo "Output directory: $OUTPUT_DIR"
```

### 3. 動画情報取得

```bash
# 動画の長さを取得（秒）
duration=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$video")
echo "Duration: ${duration}s"

# 解像度を取得
resolution=$(ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=s=x:p=0 "$video")
echo "Resolution: $resolution"

# フレームレートを取得
framerate=$(ffprobe -v error -select_streams v:0 -show_entries stream=r_frame_rate -of default=noprint_wrappers=1:nokey=1 "$video")
echo "Frame rate: $framerate"
```

### 4. 長尺動画の分割

2分（120秒）を超える動画は分割して処理：

```bash
threshold=${threshold:-0.3}

if (( $(echo "$duration > 120" | bc -l) )); then
  echo "Long video detected. Splitting into segments..."

  # 2分ごとに分割
  ffmpeg -i "$video" -c copy -map 0 -segment_time 120 -f segment "$OUTPUT_DIR/segment_%03d.mp4" -y 2>/dev/null

  input_files=("$OUTPUT_DIR"/segment_*.mp4)
  echo "Created ${#input_files[@]} segments"
else
  input_files=("$video")
fi
```

### 5. フレーム抽出

```bash
frame_count=0
start_number=1

for file in "${input_files[@]}"; do
  segment_name=$(basename "$file" .mp4)
  echo "Processing: $segment_name"

  # シーン検出によるフレーム抽出
  ffmpeg -i "$file" \
    -vf "select='gt(scene,$threshold)'" \
    -vsync vfr \
    -start_number $start_number \
    "$FRAMES_DIR/frame_%04d.png" \
    -y 2>/dev/null

  # 抽出されたフレーム数をカウント
  new_frames=$(ls "$FRAMES_DIR"/frame_*.png 2>/dev/null | wc -l)
  start_number=$((new_frames + 1))

  echo "  Extracted frames: $new_frames total"
done

# 最終フレーム数
total_frames=$(ls "$FRAMES_DIR"/frame_*.png 2>/dev/null | wc -l)
echo ""
echo "Total frames extracted: $total_frames"
```

### 6. タイムスタンプ記録

```bash
# 各フレームのタイムスタンプを記録
echo "Extracting timestamps..."

ffmpeg -i "$video" \
  -vf "select='gt(scene,$threshold)',showinfo" \
  -vsync vfr \
  -f null - 2>&1 | \
  grep "pts_time" | \
  awk -F'pts_time:' '{
    n++;
    gsub(/[^0-9.]/, "", $2);
    printf "{\"frame\": %d, \"timestamp\": %.3f}\n", n, $2
  }' > "$OUTPUT_DIR/timestamps.jsonl"

echo "Timestamps saved to: $OUTPUT_DIR/timestamps.jsonl"
```

### 7. 情報ファイル生成

```bash
# 抽出情報をJSON形式で保存
cat > "$OUTPUT_DIR/extraction_info.json" << EOF
{
  "video": "$video",
  "duration": $duration,
  "resolution": "$resolution",
  "framerate": "$framerate",
  "threshold": $threshold,
  "frame_count": $total_frames,
  "frames_dir": "$FRAMES_DIR",
  "extracted_at": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
}
EOF

echo "Extraction info saved to: $OUTPUT_DIR/extraction_info.json"
```

## Output Format

### 成功時

```
## Frame Extraction Complete

**Video**: recordings/login.mp4
**Duration**: 45.2s
**Resolution**: 1080x1920
**Threshold**: 0.3

### Extracted Frames

Total: 12 frames

| Frame | Timestamp |
|-------|-----------|
| frame_0001.png | 0.000s |
| frame_0002.png | 2.345s |
| frame_0003.png | 5.678s |
| ... | ... |

### Output

- Frames: `.video-to-scenario/login/frames/`
- Info: `.video-to-scenario/login/extraction_info.json`
- Timestamps: `.video-to-scenario/login/timestamps.jsonl`

### Next Step

Run `video-frame-analyzer` to analyze extracted frames.
```

### エラー時

```
## Extraction Failed

**Error**: ffmpeg not found

Please install ffmpeg:
  brew install ffmpeg
```

## Error Handling

### ffmpeg未インストール

```
Error: ffmpeg not found

Please install ffmpeg:
  macOS:   brew install ffmpeg
  Ubuntu:  sudo apt install ffmpeg
  Windows: choco install ffmpeg
```

### 入力ファイルなし

```
Error: Video file not found: recordings/test.mp4

Please check the file path and try again.
```

### フレーム抽出失敗

```
Error: No frames extracted

Possible causes:
1. Video has no scene changes (try lower threshold)
2. Video format not supported
3. Video file is corrupted

Try: /uiai-video-to-scenario video=... threshold=0.1
```

### ディスク容量不足

```
Error: Not enough disk space

Required: ~{estimated_size}MB
Available: {available_size}MB

Please free up disk space and try again.
```

## 出力ディレクトリ構造

```
.video-to-scenario/
└── {video_name}/
    ├── extraction_info.json  # 抽出情報
    ├── timestamps.jsonl      # タイムスタンプ
    └── frames/
        ├── frame_0001.png
        ├── frame_0002.png
        └── ...
```

## 閾値の調整ガイド

| 閾値 | フレーム数 | 用途 |
|------|-----------|------|
| 0.1 | 多い | 細かいアニメーションも捕捉 |
| 0.3 | 中程度（推奨） | 画面遷移、主要な操作 |
| 0.5 | 少ない | 大きな画面遷移のみ |

フレームが少なすぎる場合は閾値を下げ、多すぎる場合は上げる。
