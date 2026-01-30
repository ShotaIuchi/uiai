# ffmpeg Frame Extraction

動画からUIテスト用フレームを抽出するffmpegコマンド集。

## シーン検出による抽出

画面変化のあるフレームのみを抽出する。静的なフレームは除外される。

### 基本コマンド

```bash
# シーン変化検出（閾値0.3 = 30%以上の変化があるフレームのみ）
ffmpeg -i input.mp4 -vf "select='gt(scene,0.3)'" -vsync vfr output/frame_%04d.png
```

### パラメータ

| パラメータ | 説明 |
|-----------|------|
| `-i input.mp4` | 入力動画ファイル |
| `-vf "select='gt(scene,0.3)'"` | シーン変化が30%以上のフレームを選択 |
| `-vsync vfr` | 可変フレームレート（重複フレーム防止） |
| `output/frame_%04d.png` | 出力ファイル名パターン |

### 閾値の調整

| 閾値 | 効果 | 用途 |
|------|------|------|
| `0.1` | 小さな変化も検出 | 細かいアニメーションをキャプチャ |
| `0.3` | 中程度の変化を検出（推奨） | 画面遷移、ボタンタップ |
| `0.5` | 大きな変化のみ検出 | 画面遷移のみ |

```bash
# より敏感な検出（小さな変化も捕捉）
ffmpeg -i input.mp4 -vf "select='gt(scene,0.1)'" -vsync vfr output/frame_%04d.png

# より鈍感な検出（大きな変化のみ）
ffmpeg -i input.mp4 -vf "select='gt(scene,0.5)'" -vsync vfr output/frame_%04d.png
```

## 重複フレーム除去

シーン検出と併用して、より効率的にフレームを抽出する。

```bash
# 重複フレームを除去
ffmpeg -i input.mp4 -vf "mpdecimate" -vsync vfr output/dedup_%04d.png
```

### シーン検出と組み合わせ

```bash
# シーン検出 + 重複除去
ffmpeg -i input.mp4 -vf "mpdecimate,select='gt(scene,0.3)'" -vsync vfr output/frame_%04d.png
```

## 動画分割

長尺動画を分割して処理する。

### 指定時間で分割

```bash
# 2分（120秒）ごとに分割
ffmpeg -i input.mp4 -c copy -map 0 -segment_time 120 -f segment output/segment_%03d.mp4
```

### 分割してフレーム抽出（ワンライナー）

```bash
# 分割 → 各セグメントからフレーム抽出
for seg in output/segment_*.mp4; do
  base=$(basename "$seg" .mp4)
  ffmpeg -i "$seg" -vf "select='gt(scene,0.3)'" -vsync vfr "output/${base}_frame_%04d.png"
done
```

## タイムスタンプ付き抽出

フレームにタイムスタンプ情報を付加する。

### ファイル名にタイムスタンプ

```bash
# タイムスタンプをファイル名に含める
ffmpeg -i input.mp4 -vf "select='gt(scene,0.3)',showinfo" -vsync vfr output/frame_%04d.png 2>&1 | \
  grep "pts_time" | awk -F'pts_time:' '{print $2}' | cut -d' ' -f1 > output/timestamps.txt
```

### メタデータとして保存

```bash
# フレーム情報をJSON形式で出力
ffmpeg -i input.mp4 -vf "select='gt(scene,0.3)',showinfo" -vsync vfr output/frame_%04d.png 2>&1 | \
  grep "pts_time" | \
  awk -F'pts_time:' '{
    n++;
    gsub(/[^0-9.]/, "", $2);
    printf "{\"frame\": %d, \"timestamp\": %.3f}\n", n, $2
  }' > output/frame_info.jsonl
```

## 動画情報の取得

抽出前に動画の情報を確認する。

```bash
# 動画の長さを取得（秒）
ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 input.mp4

# フレームレートを取得
ffprobe -v error -select_streams v:0 -show_entries stream=r_frame_rate -of default=noprint_wrappers=1:nokey=1 input.mp4

# 解像度を取得
ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=s=x:p=0 input.mp4
```

## 解像度の調整

フレームサイズを調整してAPI呼び出しを最適化する。

```bash
# 幅1280pxにリサイズ（アスペクト比維持）
ffmpeg -i input.mp4 -vf "select='gt(scene,0.3)',scale=1280:-1" -vsync vfr output/frame_%04d.png

# 最大1920x1080に収める
ffmpeg -i input.mp4 -vf "select='gt(scene,0.3)',scale='min(1920,iw):min(1080,ih)':force_original_aspect_ratio=decrease" -vsync vfr output/frame_%04d.png
```

## エラーハンドリング

### よくあるエラー

| エラー | 原因 | 対処 |
|--------|------|------|
| `No such filter: 'select'` | ffmpegバージョンが古い | ffmpegを更新 |
| `Output file is empty` | 閾値が高すぎる | 閾値を下げる |
| `Permission denied` | 出力ディレクトリがない | `mkdir -p output` |

### 前提条件チェック

```bash
# ffmpegの存在確認
if ! command -v ffmpeg &> /dev/null; then
  echo "Error: ffmpeg not found"
  echo "Install: brew install ffmpeg"
  exit 1
fi

# 出力ディレクトリ作成
mkdir -p output/frames
```

## 推奨ワークフロー

```bash
# 1. 動画情報を確認
duration=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 input.mp4)
echo "Duration: ${duration}s"

# 2. 長尺動画の場合は分割
if (( $(echo "$duration > 120" | bc -l) )); then
  ffmpeg -i input.mp4 -c copy -map 0 -segment_time 120 -f segment output/segment_%03d.mp4
  input_files=(output/segment_*.mp4)
else
  input_files=(input.mp4)
fi

# 3. フレーム抽出
frame_index=1
for file in "${input_files[@]}"; do
  ffmpeg -i "$file" -vf "select='gt(scene,0.3)'" -vsync vfr -start_number $frame_index output/frames/frame_%04d.png
  frame_index=$((frame_index + $(ls output/frames/ | wc -l)))
done

# 4. 抽出結果を確認
echo "Extracted $(ls output/frames/ | wc -l) frames"
```

## 出力例

60秒のログイン操作動画から抽出した場合：

```
output/frames/
├── frame_0001.png  # アプリ起動直後
├── frame_0002.png  # ログイン画面表示
├── frame_0003.png  # メールアドレス入力中
├── frame_0004.png  # パスワード入力中
├── frame_0005.png  # ログインボタンタップ
├── frame_0006.png  # ローディング表示
└── frame_0007.png  # ホーム画面表示
```

典型的には60秒の動画から10-20フレーム程度が抽出される。
