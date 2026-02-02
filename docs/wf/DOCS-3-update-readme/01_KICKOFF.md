# キックオフ: DOCS-3-update-readme

> Issue: #3
> 作成日: 2026-02-02
> リビジョン: 1

## 目標

README.md を現状の実装とスキル構成に合わせて更新し、ユーザーが正確な情報を得られるようにする。

## 完了条件

- [ ] README.md が現在のスキル構成を正確に反映していること
- [ ] シナリオ例が最新のYAMLスキーマ（variables、対話式入力等）を含むこと
- [ ] ディレクトリ構造が実際のファイル配置と一致していること

## 制約

- 既存の README.md の構造とスタイルを維持する
- 日本語での記述を継続する

## 対象外

- 新機能の追加（ドキュメント更新のみ）
- 英語版ドキュメントの作成

## 依存関係

### 前提条件

- なし（ドキュメント更新のみ）

### 影響範囲

- README.md（ユーザー向けドキュメント）

### 競合の可能性

- なし

## 未決定事項

- [ ] 特になし

## 備考

### 現状確認結果

**スキル構成（6スキル）:**
- uiai-android-test: Android UIテスト
- uiai-ios-test: iOS UIテスト
- uiai-web-test: Web UIテスト
- uiai-scenario-check: シナリオ検証
- uiai-video-to-scenario: 動画からシナリオ生成
- uiai-create: スキル作成ウィザード

**エージェント構成（9エージェント）:**
- adb-test-runner.md / adb-test-evaluator.md
- ios-test-runner.md / ios-test-evaluator.md
- web-test-runner.md / web-test-evaluator.md
- video-frame-extractor.md / video-frame-analyzer.md / video-scenario-generator.md

**シナリオスキーマの新機能:**
- variables セクション（変数定義）
- 対話式変数入力（プレースホルダー変数）
- replay 機能
- strict モード

README.md のシナリオ例は基本的な構文のみで、これらの新機能が反映されていない。
