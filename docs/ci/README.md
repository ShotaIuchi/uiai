# CI で使う

> **未検証**: この手順は CI 上ではまだ試していない（手元の mac でのみ確認済み）。特に、CI での `claude` の認証と、CI 上のエミュレータの速さは確かめていない。

Claude Code の中では `uiai` コマンドに PATH が通るが、CI では通らない。CI では、このリポジトリを版を固定して取得し、`<取得先>/bin/uiai` をパスで直接呼ぶ。

## 必要なもの

| もの | 入れ方 |
|---|---|
| uv | `astral-sh/setup-uv` など |
| Claude Code CLI | `curl -fsSL https://claude.ai/install.sh \| bash` |
| Claude の認証 | 次のどちらか一方を CI のシークレットに入れる。`claude setup-token` で発行した長期トークン（環境変数 `CLAUDE_CODE_OAUTH_TOKEN`）か、API キー（`ANTHROPIC_API_KEY`） |
| Chromium（Web） | `uiai setup --with-deps`（Linux では OS のライブラリも入れる。sudo が要る） |
| エミュレータ（Android） | `reactivecircus/android-emulator-runner` など。速さは未計測 |

## 結果の受け取り方

| 何を | どこで |
|---|---|
| 合否 | `uiai run` の終了コード。0: 合格（警告付き合格を含む）、1: 不合格か未実行あり、2: 最後まで実行できなかった。警告付き合格も落としたいなら `--fail-on-warning` |
| 失敗の通知 | Webhook。`UIAI_WEBHOOK_URL`（Slack の Incoming Webhook など）に `{"text": ...}` を POST する。1 回の実行で 10 件を超えたら、残りは終了時にまとめて 1 回で送る |
| 詳細 | `.uiai/results/` を成果物として保存する（`report.html` に画像と判定が並ぶ） |

CI ではバックグラウンド実行もチャットへの通知もないので、`/uiai:test` ではなく `uiai run` を直接使う。

## 秘密の値

シナリオでは `env:` と `secret: true` で受け取り、値は CI のシークレットから環境変数で渡す。

```yaml
variables:
  password:
    env: TEST_PASSWORD
    secret: true
```

値の決まらない変数（値も `env:` もない変数）があるシナリオは、CI では対話入力ができないため実行されない（終了コード 2）。`uiai run --dry-run` で事前に確かめられる。

成果物の画像には画面がそのまま写る。画面に平文で表示される秘密の値は伏せられない。

## GitHub Actions の例

[github-actions-web.yml](github-actions-web.yml)（Web のシナリオを Linux で実行する）。

- `ref` は、タグかコミットの SHA で固定する（`main` のままだと、uiai の更新で挙動が変わる）。
- `--run-id` を付けると、結果フォルダの名前が CI の実行と対応する。
- Windows のランナーでは `bin\uiai.cmd` を使う（未検証）。
