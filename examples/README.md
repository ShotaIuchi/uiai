# examples

実際に走らせられるシナリオ。`sample/` は書式の例（実在しない `com.example.app` 向け）で、実行はしない。

| シナリオ | 対象 | 必要なもの |
|---|---|---|
| `web-demo.yaml` | 同梱の Web 試験アプリ（`web-demo/index.html`） | Chromium（`uiai setup`） |
| `web-wikipedia.yaml` | ja.wikipedia.org | Chromium、ネットワーク |
| `android-settings.yaml` | Android の設定アプリ | adb で接続した端末かエミュレータ |

```sh
uv run --script engine/main.py run examples/web-demo.yaml
```

## acceptance/（わざと壊したシナリオ）

失敗・未実行・警告・伏せ字が、期待どおりに出るかを確かめる。

| シナリオ | 期待する結果 |
|---|---|
| `missing-button.yaml` | 不合格。「パスワードを忘れた方」の `do` が失敗し、残り 3 ステップは未実行 |
| `delayed-error.yaml` | 不合格。「エラーが表示されていないこと」が、観察中に出たエラーの帯で不合格。ほかは合格 |
| `error-dialog.yaml` | 不合格。「タスク画面を開く」の `do` が「エラー表示」で失敗（ダイアログは閉じない） |
| `secret.yaml` | 合格。`UIAI_DEMO_PASSWORD=password123` を渡して実行し、結果フォルダに `password123` が出ない |
| `interrupt-warning.yaml` | 警告付き合格。Cookie 同意ダイアログを閉じたことが警告になる |

```sh
UIAI_DEMO_PASSWORD=password123 uv run --script engine/main.py run examples/acceptance/
```

秘密の値は単独で走らせて確かめる（ほかの受け入れシナリオは `password123` を平文で書いているため、まとめて走らせると検索に引っかかる）。

```sh
UIAI_DEMO_PASSWORD=password123 uv run --script engine/main.py run examples/acceptance/secret.yaml --run-id secret-check
grep -r password123 .uiai/results/secret-check/ || echo "出ていない"
```
