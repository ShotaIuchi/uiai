---
name: scenario-check
description: シナリオ YAML の形式を検査し、問題の説明・修正案の提示・自動修正を行う。検査そのものはエンジンの `uiai check` で行う。「シナリオをチェックして」「YAML を検証して」などで使う。
argument-hint: "<シナリオかフォルダ>... [fix=true] [dry-run=true] [strict=true]"
allowed-tools: Bash(uiai *)
---

# /uiai:scenario-check

シナリオ YAML を検査し、エラーと警告を説明する。`fix=true` なら、自動で直せるものを直す。
検査の判定は `uiai check`（このプラグインの `bin/uiai`）に任せる。AI が独自に判定ルールを足したり、省いたりしない。

## 引数

| 引数 | 既定 | 説明 |
|---|---|---|
| シナリオ | （必須） | ファイルかフォルダ（フォルダは配下の `*.yaml`・`*.yml`）。glob も可 |
| `fix` | `false` | 自動修正する |
| `dry-run` | `false` | 修正内容を見せるだけで、ファイルは変えない（`fix=true` のとき） |
| `strict` | `false` | 警告も失敗として扱う |

## 手順

1. 検査する。

   ```sh
   uiai check <シナリオ>... --json [--strict]
   ```

   結果はファイルごとの問題のリスト（`code`・`level`・`message`・`where`）。終了コードは、問題なしなら 0、エラーがある（`--strict` なら警告も）と 1、シナリオがなければ 2。

2. [output-format.md](references/output-format.md) の形で報告する。各問題の意味と直し方は [validation-rules.md](references/validation-rules.md) を見て、必要なら短く添える。

3. `fix=true` のとき:
   - [auto-fix-rules.md](references/auto-fix-rules.md) で「自動修正できる」としたものだけを直す。それ以外は修正案を示すだけにする。
   - `dry-run=true` なら、変更前後を見せるだけでファイルは変えない。
   - 直したら、もう一度 `uiai check` を実行し、問題が消えたこと・新しい問題が出ていないことを確かめてから報告する。

`fix` の指定がなければ、ファイルは変えない。直すべき問題があれば、報告のあとに「修正しますか？」と確認する。

## 関連

- `/uiai:test` — 検査済みのシナリオを実行する
- [シナリオ仕様](../test/references/scenario-schema.md)
