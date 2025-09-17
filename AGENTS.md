# ラッパー開発方針と運用指示（Wrapper Build Guidelines）

本リポジトリは、大半のファイルが別リポジトリ（upstream）に依存・連携しています。既存コードへの変更を極力避け、ラッパー（wrapper）アプリケーションとして外側から拡張・統合します。本書はそのための方針・運用指示をまとめたものです。

## 基本方針
- 既存の upstream 連携ファイルは「読み取り専用」とみなす。
- 修正は原則、次の範囲に限定する：
  - `AGENTS.md`（本ファイル）
  - `README-FOR-WRAPPER.md`（ラッパーの仕様書）
  - `WRAPPER-DEV-LOG.md`（開発ログ）
  - `wrapper/` 配下（新規に作成するラッパー実装一式）
- 既存パッケージやスクリプトは import またはサブプロセス実行で利用し、直接改変しない。
- upstream に提案が必要な変更は、本リポでは適用せずパッチ案・検討事項として `WRAPPER-DEV-LOG.md` に記録する。

## ディレクトリと命名
- 仕様書（正）：`README-FOR-WRAPPER.md`
- 開発ログ：`WRAPPER-DEV-LOG.md`
- 実装ルート：`wrapper/`
  - 例）`wrapper/cli/`（CLI エントリ）、`wrapper/app/`（UI/サービス層）、`wrapper/config/`（設定・テンプレート）

## ドキュメント運用
- 仕様書（README-FOR-WRAPPER.md）に必ず含める事項：
  - 目的・非目的、要求・制約
  - ユーザーフロー／ユースケース
  - アーキテクチャ（構成、責務、依存関係）
  - I/O／公開インターフェース（CLI, API, 設定）
  - 実行・設定手順、エラーハンドリング、ログ・テレメトリ
  - セキュリティ・プライバシー、パフォーマンス目標、リリース計画
- 開発ログ（WRAPPER-DEV-LOG.md）：
  - 日付ごとに「決定事項」「根拠」「未解決事項」「次アクション」「リスク」を短く記録。
  - upstream 提案が必要な差分や課題もここに集約。

## 実装の原則
- 既存機能の呼び出しは「合成（composition）」を基本とし、ラッパー側で入出力・設定・可視化を提供する。
- 既存コードに手を入れずに行える方策を優先：
  - 例：`python -m whisperlivekit.basic_server ...` のサブプロセス起動、または `whisperlivekit` の公開 API import。
- 設定は `wrapper/config/` にテンプレートを置き、環境変数や CLI 引数で上書き可能とする。

## 作業フロー（推奨）
1. `README-FOR-WRAPPER.md` を初期化し、目的・要求・I/F を確定。
2. `wrapper/` に最小エントリ（例：`wrapper/cli/main.py`）を追加。
3. 以後の変更は `wrapper/` と 3 ドキュメント（本書・仕様書・開発ログ）のみに限定。
4. 意思決定・仕様変更は都度 `WRAPPER-DEV-LOG.md` に追記。
5. upstream に変更が必要と判明した場合は、本リポでは触らず、パッチ案をログ化。

## テスト運用
- GUI からの API 起動とモデル管理を通しで検証する統合テストスクリプトを `wrapper/scripts/full_stack_integration_test.py` に用意した。
- `wrapper/app`・`wrapper/api`・モデル管理・GUI 起動フロー・ダウンロード処理・音声入出力に影響する変更を加えた場合は、**必ず** `python wrapper/scripts/full_stack_integration_test.py` を実行し、成功することを確認する。
- テストスクリプトはスタブ化したバックエンドとダミーモデルを用いて GUI 実際の挙動を模擬する。必要に応じてスクリプトの維持・更新も合わせて行うこと。

## 完了定義（Definition of Done）
- CLI/GUI エントリから既存機能を起動・制御できること。
- 設定テンプレートと実行手順がドキュメント化されていること。
- 主要シナリオの動作確認手順が `README-FOR-WRAPPER.md` に記載されていること。
- すべての決定と未解決事項が `WRAPPER-DEV-LOG.md` に追跡できること。

## 初期チェックリスト
- [ ] `README-FOR-WRAPPER.md` を作成し雛形を埋める
- [ ] `WRAPPER-DEV-LOG.md` を作成し運用開始
- [ ] `wrapper/cli/main` の最小起動を用意
- [ ] 既存コードへの直接変更ゼロを維持
- [ ] 主要ユースケースの通し動作を確認

（注）上記以外のファイル変更は、明示の合意がある場合のみ行うこと。
最終的な作業や編集内容の返答は日本語で行うこと。
