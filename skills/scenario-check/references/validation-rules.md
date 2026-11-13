# 検査ルール

`uiai check` が出す問題の一覧。判定の正はエンジン（`engine/uiai/scenario.py` の `check_data`）。
このファイルは、各ルールの意味と直し方の説明用。

エラーがあるシナリオは実行されない。警告は実行に影響しないが、意図と違う動きになる可能性を示す。

## エラー

| コード | 内容 | 直し方 |
|---|---|---|
| E000 | YAML の構文エラー、読み込めない、最上位がマッピングでない | YAML の書式を直す |
| E001 | `name` がない | シナリオ名を書く |
| E002 | `app` がない | 対象のアプリ・URL を書く |
| E003 | `steps` がない | セクションを書く |
| E004 | `steps` が空 | セクションを書く |
| E005 | セクションがマッピングでない、`id` がない | `- id: "..."` の形にする |
| E006 | `actions` がない（`replay` もない）、リストでない | `actions:` のリストを書く |
| E010 | `app` の形式が不正（未知のプラットフォーム、空、パッケージ名・URL として不正） | 下の「app の形式」 |
| E011 | `id` が重複している | 別の名前にする |
| E012 | 1 つの行に `do` と `then` がある | 2 行に分ける |
| E013 | `wait` が数値でない | 秒数（数値）にする |
| E014 | `strict` や `config` の真偽値が true/false でない | `true` / `false` にする |
| E015 | `config` の値の型・範囲が不正（正の数でない、リストでないなど）。`config.type_delay`、`then` の `timeout`・`observe` が 0 以上の数でない | 正しい型・値にする |
| E016 | `config.on_failure`・`config.interrupts.mode` が決められた値でない | `on_failure`: stop_scenario / next_section / stop_all。`interrupts.mode`: allow / report / fail |
| E020 | `replay` がマッピングでない、`replay.from` のセクションがない | 存在する `id` を書く |
| E021 | `replay.to` のセクションがない | 存在する `id` を書く |
| E022 | `replay.from` が `to` より後のセクション | 順序を入れ替える |
| E023 | `replay` が循環している | 循環を断つ |
| E030 | 定義されていない変数 `(名前)` を使っている | `variables` に定義するか、文字どおりの括弧なら `\(` `\)` と書く |
| E031 | `variables` がマッピングでない、変数名が不正 | 変数名は英字か `_` で始まり、英数字と `_` だけ |
| E032 | 同じ変数名が 2 回定義されている | 1 つにする |
| E033 | 秘密の変数（`secret: true`）を `then` で使っている | AI に値を渡さないため照合できない。`then` から外す |
| E034 | アクションがマッピングでない、`do` も `then` もない、文が空 | `- do: "..."` / `- then: "..."` の形にする |

### app の形式

```yaml
app:
  android: "com.example.app"     # パッケージ名（英字で始まり、. で区切る）
  ios: "com.example.App"         # Bundle ID
  web: "https://example.com"     # http(s)・file の URL、またはシナリオからの相対パスの .html
```

文字列なら、URL・`.html` は Web、それ以外は Android と iOS で共通のパッケージ名・Bundle ID として検査する。

## 警告

| コード | 内容 | 意味 |
|---|---|---|
| W001 | `actions` が空 | 何もしないセクション |
| W002 | セクションに `then` がない | 確かめていないセクション。意図どおりなら問題ない |
| W003 | `then` が連続している | 問題ではない。1 つにまとめられることが多い |
| W004 | `config` に未知のキーがある | 綴りの誤りの可能性。無視される |
| W005 | 変数が使われていない | 消し忘れの可能性 |
| W006 | 変数に値がなく、実行時の入力が必要 | CI やバックグラウンド実行では、`--var` か `env:` がないと実行されない |
| W007 | `verify`・`config.verify` が書かれている | 廃止（判定は AI の画像判定に一本化）。無視される |
| W008 | `config.timeout` が「`do` の数 × 10 秒」より短い | AI 方式は 1 ステップ 3〜6 秒かかる。途中で打ち切られる可能性 |
| W009 | `do` に `timeout`・`observe` が書かれている | `then` にだけ有効。無視される |

## 例

```yaml
# E033: 秘密の変数を then で使っている
variables:
  password: {env: TEST_PASSWORD, secret: true}
steps:
  - id: "ログイン"
    actions:
      - do: "パスワード「(password)」でログインする"   # OK（do では使える）
      - then: "「(password)」が表示されていること"       # NG
```

```yaml
# E016 / E015
config:
  on_failure: skip          # NG: stop_scenario / next_section / stop_all
  interrupts:
    allow: "Cookie の同意"   # NG: リストにする → ["Cookie の同意"]
```

```yaml
# W009: timeout は then にだけ有効
- do: "保存する"
  timeout: 10               # 無視される
- then: "保存しました と表示されること"
  timeout: 10               # OK
```
