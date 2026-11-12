# uiai engine

シナリオ（YAML）を、AI がスクリーンショットを見て 1 ステップずつ操作・判定しながら実行するエンジン。
設計は [docs/design/ai-loop-redesign.md](../docs/design/ai-loop-redesign.md)。

- プログラムがループを回し、AI には 1 ステップにつき 1 回だけ判断させる（前の `then` の判定と次の操作を同時に返す）
- 画面の入力はスクリーンショットだけ（UI ツリーは使わない）
- AI は Claude Code（`claude -p`）経由。手元では Claude Code のログインで動く

## 前提

| もの | 用途 |
|---|---|
| [uv](https://docs.astral.sh/uv/) | 唯一の前提。Python 本体と依存（版は `main.py` の先頭で固定）を自動で用意する |
| Claude Code CLI（`claude`） | AI の呼び出し |
| adb | Android を動かすとき |
| Xcode と [AXe](https://github.com/cameroncooke/AXe) | iOS シミュレータを動かすとき（Mac のみ）。AXe は `brew install cameroncooke/axe/axe`（v2.0.3 で確認） |
| Chromium | Web を動かすとき。`uiai setup` で取得する |

起動はプラグインの `bin/uiai`（Windows の PowerShell からは `bin/uiai.cmd`）から行う。プラグインが有効な間は、Claude Code のシェルの PATH に入っている。中身は `uv run --script engine/main.py` を呼ぶだけ。

```sh
uiai setup                             # 実行環境の確認とブラウザの取得（Linux の CI では --with-deps）
uiai check sample/                     # シナリオの形式を検査
uiai run examples/web-demo.yaml
uiai watch --run latest                # 実行中の失敗を 1 行ずつ表示
```

このリポジトリの中では `bin/uiai ...` と書けば同じことができる。

## run

```
uiai run <シナリオかフォルダ>... [--platform android|ios|web|all] [--model haiku] [--rejudge-model sonnet|none]
         [--serial <adb シリアル>]... [--udid <シミュレータ>]... [--parallel] [--browsers N]
         [--browser-path <chromium>] [--headed] [--var NAME=VALUE]... [--webhook URL] [--notify]
         [--run-id ID] [--results-dir DIR] [--fail-on-warning] [--dry-run]
```

- プラットフォームは `app` と接続中の対象（Android 端末・起動中の iOS シミュレータ）から決まる。複数の候補が残ったら `--platform` を求める
- Android 端末が複数つながっていれば `--serial`、iOS シミュレータが複数起動していれば `--udid` で選ぶ
- 値のない変数は、`--var`、`env:` の環境変数、対話入力の順に解決する。どれもなければ、そのシナリオは実行しない。実行の前に、全シナリオの分をまとめて解決する
- `then` が待ち時間を過ぎても不合格のときは、確定する前に `--rejudge-model`（既定 sonnet）が同じ画像で判定し直す。sonnet が合格とすれば合格にするが、判定が分かれたことを警告に残す。`none` で無効
- `--parallel` は端末ごとに並列で実行する。Android は接続中の全端末、iOS は起動中の全シミュレータ（`--serial`・`--udid` を繰り返して絞れる）、Web は `--browsers` 個（既定 2）のブラウザ。シナリオは空いた端末から順に割り当てる（同じシナリオを全端末で回すのではない）。表示の各行には端末名が付く
- `--webhook`（または環境変数 `UIAI_WEBHOOK_URL`）を指定すると、失敗を `{"text": ...}` で POST する
- `--notify`（または環境変数 `UIAI_NOTIFY=1`）を指定すると、失敗（1 回の実行で 5 件まで）と終了を OS のデスクトップ通知でも知らせる。Claude Code を使わずに手元で実行するとき用（mac は osascript、Linux は notify-send、Windows は PowerShell。Windows は未検証）
- `--dry-run` は実行せずに、シナリオごとの実行先と値のない変数を表示する（実行できなければ終了コード 2）
- `--run-id` に既にある結果フォルダの名前を指定すると、実行せずに終了コード 2 になる

終了コード:

| コード | 意味 |
|---|---|
| 0 | すべて合格（警告付き合格を含む。`--fail-on-warning` なら警告付き合格も 1） |
| 1 | 不合格か未実行のステップがある |
| 2 | 最後まで実行できなかった（形式エラー、端末・ブラウザ・claude がない、変数の値がないなど） |

結果は `.uiai/results/<run id>/` に出る（置き場所は `--results-dir` で変えられる）。

```
summary.md            全シナリオの結果
events.jsonl          失敗・警告などのイベント（uiai watch が読む）
<シナリオ>-<対象>/
  result.json         呼び出しごとの操作・座標・AI の理由・読み取った文字・判定・時間・トークン
  report.md / report.html
  call_NN.jpg         AI に送った画像
```

秘密の変数（`secret: true`）の値は AI に渡さず、上の記録・通知からも `****` に伏せる。

## watch

`uiai watch --run <run id|latest>` は、失敗（`then` の不合格・`do` の失敗・実行エラー）を起きた順に 1 行ずつ出し、実行が終わると終了する（終了コード 0）。Claude Code の Monitor ツールで見張る用途を想定している。`--all` を付けると警告とシナリオごとの結果も出す。

`--timeout` 秒で見張りをやめる（実行は止めない）。そのときは続きを見るためのコマンド（`--skip <読んだイベント数>` 付き）を出して、終了コード 3 で終わる。Monitor の時間切れより少し短くしておけば、取りこぼさずに張り直せる。

## テスト

実機を使わない単体テスト（偽の AI と偽のドライバでループの制御を確かめる）:

```sh
cd engine && uv run --no-project --with pyyaml==6.0.3 --with pillow==13.0.0 --with pytest pytest -q tests
```

実画面での受け入れ確認は [examples/README.md](../examples/README.md)。

## 構成

| ファイル | 役割 |
|---|---|
| `main.py` | 入口。依存の宣言（PEP 723） |
| `uiai/cli.py` | `run` / `check` / `setup` / `watch` |
| `uiai/scenario.py` | YAML の読み込み・検査（E0xx/W0xx）・変数・replay の展開 |
| `uiai/platform.py` | 実行するプラットフォームの決定 |
| `uiai/loop.py` | 実行ループ（`then` の判定・取り直し・観察・割り込みと逸脱の記録・失敗時の打ち切り）。会話が大きくなったら作り直す（直前の入力が 5 万トークンを超えたら次のセクションの境目で、10 万トークンを超えたら次の `do` の前で）。待ち時間を過ぎた `then` の不合格は、別のモデルで判定し直す |
| `uiai/settle.py` | 画面の「変化待ち → 静止待ち」、否定形の `then` の観察、判断後の画面変化の検出 |
| `uiai/ai/protocol.py` | AI への指示と応答の読み取り |
| `uiai/ai/claude_code.py` | `claude -p` の持続セッション（stream-json で画像とテキストを送る。ツール・MCP・ユーザー設定は無効にする） |
| `uiai/drivers/` | Android（adb。ASCII 以外の文字は uiautomator2 でクリップボードから貼り付ける）・iOS（`xcrun simctl` と AXe）・Web（Playwright） |
| `uiai/events.py` / `notify.py` / `desktop.py` | イベント出力、Webhook、デスクトップ通知 |
| `uiai/redact.py` | 秘密の値を伏せる |
| `uiai/report.py` | `result.json`・`report.md`・`report.html`・`summary.md` |
