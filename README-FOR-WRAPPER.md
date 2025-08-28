# README for Wrapper Application

本書は、既存の WhisperLiveKit を改変せずに外側から統合・制御する「ラッパー（wrapper）」アプリケーションの仕様書です。下記の各項目を埋めながら開発を進めてください。

## 1. 概要（目的・非目的）
- 目的：既存の WhisperLiveKit を改変せず、Windows で起動しやすい GUI と Whisper API 互換の音声ファイル文字起こし API を提供する。
- 非目的：WebSocket ストリーム処理ロジックやモデル実装自体の改変。

## 2. 想定ユーザーとユースケース
- 代表的ユースケース：
  - ダブルクリックで GUI を起動し、ブラウザ上でリアルタイム文字起こしを利用。
  - REST API `/v1/audio/transcriptions` に音声ファイルを送信し、一括で文字起こし結果を取得。

## 3. 要求・制約
- 機能要求：GUI からポート番号などの環境依存値を指定し、既存 WebSocket サーバーとラッパー API を起動・停止できること。
- 品質要求（性能・可用性・運用性 など）：ffmpeg が存在しない場合はエラーメッセージを返す。
- 制約（既存リポ変更不可、依存関係、実行環境 など）：`whisperlivekit` をサブプロセスで起動。`ffmpeg` と Python 3.11+ が必要。

## 4. アーキテクチャ
- 構成：`wrapper/` 配下に CLI/UI/設定を配置（例：`wrapper/cli/`, `wrapper/app/`, `wrapper/config/`）
- 依存：既存の `whisperlivekit`（import またはサブプロセス起動）
- 責務分担：ラッパーは入出力・オーケストレーション・設定・UI を担当

## 5. インターフェース
- CLI/GUI：
    - `python -m wrapper.cli.main` で設定 GUI を起動。GUI は起動時に空きポートを自動選択して入力欄に表示し、必要に応じて編集できる。`Start API` でサービスを起動、`Stop API` で停止できる。`Auto-start API on launch` を有効にすると起動時に自動開始する。起動後は Backend Web UI・WebSocket `/asr`・ファイル文字起こし API の各エンドポイントと用途が表示され、隣の `Copy` ボタンでクリップボードにコピーできる。
- API：
  - `POST /v1/audio/transcriptions`（multipart/form-data, field=`file`） → `{ "text": "..." }`
  - ffmpeg が見つからない場合 `500 ffmpeg_not_found` を返却。
- 設定：
    - 入力された設定は環境変数 `WRAPPER_BACKEND_HOST`/`WRAPPER_BACKEND_PORT` と `WRAPPER_API_HOST`/`WRAPPER_API_PORT` としてサブプロセスに渡される。`WRAPPER_API_AUTOSTART=1` を指定すると GUI 起動時に自動で API を開始する。ポート番号を指定しなかった場合は空きポートが自動的に割り当てられる。

## 6. 実行・セットアップ手順
1. 必要要件：Python 3.11 以降、ffmpeg、インターネット接続。
2. セットアップ：依存ライブラリ `fastapi`, `uvicorn`, `websockets` をインストール。
3. 実行例：`python -m wrapper.cli.main` を実行すると設定 GUI が起動する。必要に応じてホストやポートを変更し、`Start API` で WhisperLiveKit とラッパー API を開始する。`Auto-start API on launch` を有効にするか、環境変数 `WRAPPER_API_AUTOSTART=1` を指定すると GUI 起動と同時に自動で API が開始される。

## 7. エラーハンドリングとログ／テレメトリ
- 例外分類・リトライ方針、ユーザー通知方法
- ログの出力先・粒度・フォーマット
- 収集指標（必要なら）とオプトアウト方法

## 8. セキュリティ／プライバシー
- 入力データの扱い、保存可否、マスキング方針
- 権限・認可（必要なら）

## 9. パフォーマンス目標
- レイテンシ、スループット、リソース使用の目安
- ベンチ観点（テストデータ、条件）

## 10. リリース計画
- マイルストーン（MVP → Beta → GA）
- 互換ポリシー（CLI 引数や設定の安定性）

## 11. 付録（TODO / 未解決事項）
- TODO：
- 未解決事項：

## 12. Windows 向け MSIX パッケージング
- 目的：Windows ネイティブな配布形態を提供するため、MSIX 形式でのパッケージ化を想定する。
- 追加実装の候補：
  - PyInstaller で `wrapper/cli/main.py` を単一 exe 化するビルドスクリプト（例：`wrapper/scripts/build_msix.ps1`）。
  - `AppxManifest.xml` を用意し、`whisperlivekit/web` など必要な静的ファイルを同梱する設定。
  - `makeappx.exe` によるパッケージ生成と `signtool.exe` による署名フロー。
  - 設定ファイルやモデルデータを `AppData` 配下へ移行する初回起動時のロジック。
- 既存ユーザーへの影響：MSIX 版では設定ディレクトリが変更されるため、従来の設定を自動コピーする移行処理が必要。

