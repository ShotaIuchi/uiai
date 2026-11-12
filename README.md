# uiai

自然言語で書いたシナリオで UI テストを実行する Claude Code プラグイン。
プログラムがループを回し、AI（既定は haiku）が 1 ステップごとにスクリーンショットを見て、操作と判定をする。

## 特徴

- **自然言語シナリオ** — 日本語で「やること（`do`）」と「期待する画面（`then`）」を書く
- **画面だけで判断** — UI ツリー・DOM・リソース ID を使わない。事前のコンパイルもない
- **AI の判断は 1 ステップ 1 回** — 1 回あたり約 1 秒。10 ステップのシナリオで 30〜60 秒が目安
- **失敗をその場で知らせる** — Claude Code のチャット（使える環境ならデスクトップ通知も）や Webhook に
- **不具合を隠さない** — 想定外のダイアログを閉じた、何もしなかった、遠回りした、などを警告として残す
- **誤った不合格を減らす** — 不合格を確定する前に、別のモデル（既定 sonnet）が同じ画像で判定し直す。判定が分かれたら警告に残す
- **並列実行** — `--parallel` で、複数の端末・シミュレータ・ブラウザにシナリオを割り振る
- **秘密の値を AI に渡さない** — `secret: true` の変数は AI に見せず、記録からも伏せる
- **証拠を残す** — AI に送った画像・タップ位置・判断の理由・読み取った文字をレポートに

## 対応状況

| プラットフォーム | 状況 |
|---|---|
| Android | ✅（ASCII 以外の文字はクリップボード経由で入力する） |
| Web | ✅（Chromium） |
| iOS | ✅（Mac のシミュレータのみ。ASCII 以外の文字入力は未対応） |

## コマンド

| コマンド | 説明 |
|---|---|
| `/uiai:test` | シナリオを実行する |
| `/uiai:scenario-check` | シナリオの形式を検査し、直す |
| `/uiai:record-to-scenario` | 端末を操作しながら録画し、シナリオを作る（Android） |
| `/uiai:video-to-scenario` | 画面録画の動画からシナリオを作る |

## インストール

```bash
# Claude Code 内で実行
/plugin marketplace add ShotaIuchi/uiai
/plugin install uiai@uiai
```

ローカルのチェックアウトをそのまま読み込む場合（開発時）:

```bash
claude --plugin-dir /path/to/uiai
```

> 旧方式（amu で `dotclaude/` を `~/.claude` にリンク）で導入済みの場合は、
> `~/.claude/skills/uiai-*` と `~/.claude/agents/task/` 配下の uiai エージェントのリンクを削除すること。
> 残したままだとスキルが二重に読み込まれる。

### 前提

| もの | 用途 |
|---|---|
| [uv](https://docs.astral.sh/uv/) | 実行エンジンの起動。Python 本体と依存は uv が自動で用意する |
| Claude Code | AI の呼び出し（ログイン済みであること） |
| adb | Android（端末かエミュレータを接続しておく） |
| Xcode と [AXe](https://github.com/cameroncooke/AXe) | iOS（Mac のみ。シミュレータを起動しておく）。AXe は `brew install cameroncooke/axe/axe` |
| Chromium | Web。初回に `uiai setup` で取得する（`/uiai:test` が必要に応じて実行する） |
| ffmpeg | 動画からのシナリオ作成 |

## 使い方

```text
/uiai:test test/scenarios/login.yaml
/uiai:test test/scenarios/                    # フォルダ内の全シナリオ
/uiai:test login.yaml --platform web          # app に複数のプラットフォームがあるとき
/uiai:test login.yaml --var office=大阪支社    # 変数の値を渡す
```

実行はバックグラウンドで進み、失敗が起きるたびにチャットに届く。終わると結果のまとめと、レポート（`report.html`）の場所が返る。

## シナリオ

```yaml
name: "ログインテスト"
app:
  android: "com.example.app"
  web: "https://example.com/login"

variables:
  email: "test@example.com"
  password:
    env: TEST_PASSWORD    # 環境変数から読む
    secret: true          # AI に渡さず、記録からも伏せる

steps:
  - id: "ログイン"
    actions:
      - do: "アプリを起動する"
      - then: "ログイン画面が表示されていること"
      - do: "メールアドレス「(email)」、パスワード「(password)」でログインする"
      - then: "ホーム画面が表示されていること"
      - then: "エラーが表示されていないこと"

  - id: "拠点"
    actions:
      - do: "メニューから「拠点切り替え」を開き、「東京本社」を選ぶ"
      - then: "「東京本社」と表示されていること"
        strict: true      # 一字一句の完全一致で判定
```

書き方の全体は [シナリオ仕様](skills/test/references/scenario-schema.md)。
走らせられる例は [examples/](examples/)。旧形式のシナリオはそのまま読める（`strict` の判定方法の変更と `verify` の廃止は仕様の「旧形式からの変更」を参照）。

## 結果

```
.uiai/results/<run id>/
  summary.md            全シナリオの結果
  events.jsonl          失敗・警告などのイベント
  <シナリオ>-<プラットフォーム>/
    report.html         画像・タップ位置・AI の理由・判定を時系列で
    report.md
    result.json
    call_NN.jpg         AI に送った画像
```

作業フォルダの `.gitignore` に `.uiai/` を足しておくとよい。

## コマンドラインから使う

プラグインが有効な間、Claude Code のシェルでは `uiai` コマンドが使える（`bin/uiai`。Windows の PowerShell からは `bin/uiai.cmd`）。

```sh
uiai run login.yaml --platform web     # 実行（終了コード 0: 合格 / 1: 不合格・未実行あり / 2: 実行できなかった）
uiai run login.yaml --dry-run          # 実行せずに、対象と値のない変数を確かめる
uiai run scenarios/ --parallel         # 接続中の全端末（Web は 2 ブラウザ）に割り振って並列に実行
uiai run scenarios/ --notify           # 失敗と終了を OS のデスクトップ通知でも知らせる（Claude Code の外で使うとき）
uiai check scenarios/                  # 形式の検査
uiai watch --run latest                # 実行中の失敗を 1 行ずつ表示
uiai setup                             # 実行環境の確認と Chromium の取得
```

CI で使う方法は [docs/ci/](docs/ci/README.md)、エンジンの詳細は [engine/README.md](engine/README.md)。

## 注意

- スクリーンショットは Anthropic の API に送られる。秘密の値（`secret: true`）は AI に渡さないが、画面に平文で表示された内容は送られる。機密情報を表示するアプリでは注意する。
- 実行中は、対象の端末・シミュレータ・ブラウザを操作しない。
- Android で ASCII 以外の文字を入力すると、端末のクリップボードの中身が上書きされる。

## ディレクトリ構造

```
.
├── .claude-plugin/        # プラグインのマニフェストとマーケットプレイス定義
├── bin/                   # uiai コマンド（プラグインが有効な間 PATH に入る）
├── engine/                # 実行エンジン（Python。uv で起動）
├── skills/
│   ├── test/              # /uiai:test と、シナリオ仕様（references/scenario-schema.md）
│   ├── scenario-check/
│   ├── record-to-scenario/
│   └── video-to-scenario/
├── agents/                # 動画からのシナリオ作成用のサブエージェント
├── examples/              # 走らせられるシナリオと、受け入れ確認用のシナリオ
├── sample/                # 書式の例（実在しないアプリ向け）
├── template/              # シナリオのひな形
└── docs/                  # 設計・CI
```

## ライセンス

MIT
