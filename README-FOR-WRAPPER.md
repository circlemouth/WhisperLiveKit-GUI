# WhisperLiveKit Wrapper 仕様書 (README-FOR-WRAPPER)

本リポジトリは upstream（whisperlivekit）を直接改変せず、GUI と API のラッパーとして外側から統合・拡張します。変更は本書・開発ログ・`wrapper/` 配下に限定します。

## 目的 / 非目的
- 目的: 既存の `whisperlivekit.basic_server` を安全に起動・制御し、GUI（録音・可視化）と、Whisper API 互換 REST を提供する。
- 非目的: Whisper 推論アルゴリズムの改良・精度改善、upstream コードの直接編集。

## 要求 / 制約
- 必須: Python 3.11+, `ffmpeg`, ネットワークアクセス
- 対応OS: Windows / macOS / Linux
- セキュリティ: 既定は `127.0.0.1` バインド。外部公開はユーザー操作で明示的に有効化（`0.0.0.0`）。
- 改変方針: upstream は読み取り専用。呼び出しは import またはサブプロセス。

## ユースケース / フロー
- ローカルでリアルタイム音声→文字起こしを試す（GUI から Start/録音/表示/保存）。
- 既存アプリから OpenAI Whisper API 互換 REST を呼ぶ（`POST /v1/audio/transcriptions`）。
- モデル/VAD のダウンロード・管理（GUIの Model Manager）。

## アーキテクチャ
- GUI 層（Tkinter）: `wrapper/cli/main.py` → `wrapper/app/gui.py`
  - Start/Stop で 2 プロセス起動/停止
    - Backend: `python -m whisperlivekit.basic_server`
    - API: `uvicorn wrapper.api.server:app`
  - 録音パイプライン: 生PCM → FFmpeg で `audio/webm`(Opus) へ変換 → WebSocket `/asr` へストリーミング
  - Web UI（upstream）をブラウザで開く導線あり
  - ヘッダー右上に CUDA/FFmpeg の利用可否を表示し、最右にライセンスボタンを配置
- API 層（FastAPI）: `wrapper/api/server.py`
  - `POST /v1/audio/transcriptions`: 受領音声を FFmpeg で 16kHz/mono PCM 化 → backend `/asr` へWS中継 → テキスト連結返却
- 依存:
  - upstream パッケージ `whisperlivekit`（モデル推論・WSサーバ・Web UI 等）
  - `ffmpeg`（GUI録音のエンコード/REST入力のデコード）

## I/O / 公開インターフェース
- GUI: `python -m wrapper.cli.main`
- WebSocket（upstream 提供）: `ws://<backend_host>:<backend_port>/asr`
  - GUI の Recorder は `audio/webm`(Opus) を送信（raw PCM では送らない）。サーバ側で s16le/16kHz/mono に復号され処理される。
  - 録音停止時は「空バイト（b""）」を送信して EOF を明示。
- REST API（Wrapper）: `POST http://<api_host>:<api_port>/v1/audio/transcriptions`
  - multipart フォーム: `file=@sample.wav`, `model=whisper-1`
  - 入力音声は内部で 16kHz モノラル PCM に変換される（既に 16kHz/モノラル PCM の wav/raw であれば再変換を省略）
  - 推奨入力フォーマット: 16kHz モノラルの wav または raw（変換コストを避けるため）
  - APIキー（任意）: `X-API-Key: <key>` または `Authorization: Bearer <key>`
  - レスポンス例: `{ "text": "...", "model": "whisper-1" }`

## 実行・設定手順（概要）
1) Backend 起動: `python -m whisperlivekit.basic_server --host 127.0.0.1 --port 8000 [...options]`
2) Wrapper API 起動: `WRAPPER_BACKEND_HOST=127.0.0.1 WRAPPER_BACKEND_PORT=8000 uvicorn wrapper.api.server:app --host 127.0.0.1 --port 8001`
3) GUI から Start / 録音 / 可視化 / 保存

- 主要環境変数（GUI→APIへ引継ぎ）
  - `WRAPPER_BACKEND_HOST` / `WRAPPER_BACKEND_PORT`
  - `WRAPPER_BACKEND_SSL=1`（wss 接続を指定）
  - `WRAPPER_REQUIRE_API_KEY=1`, `WRAPPER_API_KEY=<key>`

## エラーハンドリング / ログ
- FFmpeg が無い: `500 ffmpeg_not_found`（API）、GUI ステータスに表示
- 音声変換失敗: `400 ffmpeg_failed`（API）
- WS 側の終了: サーバは結果送信後に `{ "type": "ready_to_stop" }` を返す。GUI は受信スレッドで反映。

## セキュリティ / プライバシー
- デフォルトはローカルバインド。外部公開する場合は TLS/認証/ファイアウォール等を考慮。
- Wrapper API は任意で API キーを要求可能（GUI で設定）。

## パフォーマンス目標
- 低遅延の逐次文字起こし（数百ms〜程度のバッファリング）
- モデル・HW に依存。高負荷の場合は `tiny/base/small` を推奨。

## リリース計画（抜粋）
- バイナリ配布（PyInstaller等）検討
- API 認証/ダッシュボードの拡充
- upstream 提案は `WRAPPER-DEV-LOG.md` にパッチ案として記録

## トラブルシューティング: FFmpeg 入力形式の不一致（解消済）
- 症状: 「Error writing to FFmpeg: Connection lost」等。
- 原因: サーバ側 FFmpeg は `-i pipe:0` でヘッダから入力形式を自動判定。raw PCM を送ると判別不可で失敗。
- 対応: GUI は FFmpeg で `audio/webm`(Opus) にエンコードして送信（本リポで実装済）。録音停止時は空バイトで EOF を明示。
  - 参照: `wrapper/app/gui.py:_recording_worker`

## トラブルシューティング: 「Diart backend requires diart」
- 症状: GUI 起動時（Start API）に「Cannot start due to missing dependencies: Diart backend requires diart.」が表示される。
- 前提: 話者分離（Diarization）を有効化し、バックエンドに `diart` を選択している場合にチェックが走る。
- 原因: 実行中の Python 環境に `diart`（および関連依存 `pyannote.audio`, `rx`）がインストールされていない、または別環境に入っている。
- 解決手順:
  - 1) 現在GUIを起動している Python を特定する。
    - 例: `which python`（Windowsは `where python`）、`python -V`
  - 2) 同じ Python でモジュールを確認する。
    - 例: `python -c "import diart, pkgutil; print('diart OK')"`
  - 3) 未導入ならインストール（CPU/AMD環境の例）:
    - `pip install -r wrapper/requirements-cpu-amd.txt`
    - または最小構成: `pip install diart pyannote.audio rx`
  - 4) それでも失敗する場合は、仮想環境の混在を疑い、GUI と同じ環境で再度インストールする（`python -m pip install ...` 形式を推奨）。
- 備考:
  - `wrapper/requirements-cpu-amd.txt` には `diart`, `pyannote.audio`, `rx` を含めています。NVIDIA 環境では `wrapper/requirements-nvidia.txt` を使用してください。
  - `diart` のモデル取得には Hugging Face のネットワークアクセスが必要です（初回のみ）。

## 依存関係のインストール（例）
- CPU/AMD 環境: `pip install -r wrapper/requirements-cpu-amd.txt`
- NVIDIA 環境: `pip install -r wrapper/requirements-nvidia.txt`
- 追加オプション（任意）:
  - VAD 有効時の `torchaudio` は Torch のバージョンに揃えてください（GUIが不足時に案内を表示）。
  - Sortformer バックエンドを使う場合は CUDA + NVIDIA NeMo が必要です。

## 主要ファイル
- GUI: `wrapper/app/gui.py`（エントリ: `python -m wrapper.cli.main`）
- API: `wrapper/api/server.py`
- 設定テンプレート: `wrapper/config/`
- ライセンス一覧: `wrapper/licenses.json`

本仕様書と `WRAPPER-DEV-LOG.md` は、仕様変更・意思決定に合わせて更新します。
