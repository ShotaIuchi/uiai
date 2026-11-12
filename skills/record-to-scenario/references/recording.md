# 録画の開始・停止・取得（Android / adb）

`record-to-scenario` の録画パートの手順。録画は**ユーザーとの対話が必要**なため、
サブエージェントではなくスキル本体（メインループ）で実行する。

## 1. 前提確認

```bash
# adb の存在確認
command -v adb >/dev/null || echo "Error: adb not found"

# 接続デバイス一覧
adb devices
```

- `List of devices attached` に `device` 状態の端末が1台あればOK。
- 複数台ある場合は、以降のコマンドすべてに `-s <serial>` を付ける（`device` 引数）。
- 0台、または `unauthorized` / `offline` の場合は接続を促して中断する。

> 以降の例では複数デバイス対応のため `ADB="adb -s <serial>"`（単一台なら `ADB="adb"`）とする。

## 2. 録画開始（バックグラウンド）

端末側の一時パスに録画する。`run_in_background` でバックグラウンド実行し、操作の間も走らせ続ける。

```bash
# label は任意の識別子（例: ユーザー入力 or 連番）。Date 依存を避けるため固定 or 引数由来にする。
REMOTE="/sdcard/uiai-record.mp4"

# duration は引数（デフォルト180、上限180）
$ADB shell screenrecord --time-limit 180 --bit-rate 8000000 "$REMOTE"
```

開始したら、ユーザーに次を伝える：

> 録画を開始しました。**端末を操作してテストしたい流れを実演**してください。
> 終わったら「**停止**」と入力してください（最大180秒で自動停止します）。

- `--bit-rate 8000000`（8Mbps）は解析に十分な画質の目安。端末性能に応じて調整可。
- 解像度を落として軽くしたい場合は `--size 720x1280` などを付ける。

## 3. 録画停止

ユーザーが「停止」と入力したら、`SIGINT` を送って正常終了させる。
**強制終了（SIGKILL）は使わない** — ファイルが壊れる。

```bash
# 録画プロセスに割り込み
$ADB shell pkill -SIGINT screenrecord

# ファイルの書き出し（flush / moov atom 書き込み）を待つ
# プロセスが消えるまでポーリングする
until ! $ADB shell pidof screenrecord >/dev/null 2>&1; do : ; done
```

> 自動停止（`--time-limit` 到達）の場合は `pkill` 不要。プロセス消滅を待つだけでよい。

## 4. ローカルへ取得 → 端末側を削除

```bash
mkdir -p recordings
LOCAL="recordings/uiai-record-<label>.mp4"

$ADB pull "$REMOTE" "$LOCAL"
$ADB shell rm -f "$REMOTE"
```

- `adb pull` が成功し、`$LOCAL` のサイズが 0 でないことを確認する。
- 取得した `$LOCAL` を `uiai:video-frame-extractor` の `video` 引数に渡す。

## 5. エラーハンドリング

| 状況 | 対処 |
|------|------|
| `adb` なし | インストールを案内して中断 |
| デバイス0台 / unauthorized | 接続・認証を促して中断 |
| 複数台で serial 未指定 | `adb devices` を提示し `device=` を促す |
| screenrecord が即終了 | 端末が screenrecord 非対応（古い/一部端末）の可能性。別録画手段→`video-to-scenario` を案内 |
| pull したファイルが 0 byte | flush 待ちが不足。SIGINT 後にプロセス消滅を待ってから再 pull |
| 180秒を超えたい | 一度停止して生成、続きを再録画。または外部録画→`video-to-scenario` |

## 補足

- 録画に**音声は含まれない**（UIテスト用途のため不要）。
- ソフトキーボード操作やパスワード欄は黒塗りになることがあり、解析側で `[REVIEW]` が付与される。
- 一時ファイル名 `<label>` は、`Date` 依存を避けるため引数由来の文字列か固定名を用いる
  （固定名の場合、前回の録画を上書きする前に既存ファイルの有無を確認する）。
