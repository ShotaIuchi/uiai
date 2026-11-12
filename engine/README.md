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
uiai run <シナリオかフォルダ>... [--platform android|ios|web|all] [--model haiku]
         [--serial <adb シリアル>] [--browser-path <chromium>] [--headed]
         [--var NAME=VALUE]... [--webhook URL] [--run-id ID] [--fail-on-warning] [--dry-run]
```

- プラットフォームは `app` と接続中の対象から決まる。複数の候補が残ったら `--platform` を求める
- 値のない変数は、`--var`、`env:` の環境変数、対話入力の順に解決する。どれもなければ、そのシナリオは実行しない
- `--webhook`（または環境変数 `UIAI_WEBHOOK_URL`）を指定すると、失敗を `{"text": ...}` で POST する
- `--dry-run` は実行せずに、シナリオごとの実行先と値のない変数を表示する（実行できなければ終了コード 2）
- `--run-id` に既にある結果フォルダの名前を指定すると、実行せずに終了コード 2 になる

終了コード:

| コード | 意味 |
|---|---|
| 0 | すべて合格（警告付き合格を含む。`--fail-on-warning` なら警告付き合格も 1） |
| 1 | 不合格か未実行のステップがある |
| 2 | 最後まで実行できなかった（形式エラー、端末・ブラウザ・claude がない、変数の値がないなど） |

結果は `.uiai/results/<run id>/` に出る。

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
| `uiai/loop.py` | 実行ループ（`then` の判定・取り直し・観察・割り込みと逸脱の記録・失敗時の打ち切り） |
| `uiai/settle.py` | 画面の「変化待ち → 静止待ち」、否定形の `then` の観察、判断後の画面変化の検出 |
| `uiai/ai/protocol.py` | AI への指示と応答の読み取り |
| `uiai/ai/claude_code.py` | `claude -p` の持続セッション |
| `uiai/drivers/` | Android（adb）・Web（Playwright）。iOS は段階 3 |
| `uiai/events.py` / `notify.py` | イベント出力と Webhook |
| `uiai/redact.py` | 秘密の値を伏せる |
| `uiai/report.py` | `result.json`・`report.md`・`report.html`・`summary.md` |
