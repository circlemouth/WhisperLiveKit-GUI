# WhisperLiveKit Wrapper 仕様書（README-FOR-WRAPPER）

本リポジトリは upstream（`whisperlivekit`）を直接改変せず、GUI と API のラッパーとして統合・拡張します。upstream 連携ファイルは読み取り専用です。変更は `wrapper/` 配下とこの README、`WRAPPER-DEV-LOG.md` のみで行います。

## 目的 / 非目的
- 目的: 既存の `whisperlivekit.basic_server` を安全に起動・制御し、以下を提供する。
  - デスクトップ GUI（Tkinter）による起動・録音・可視化
  - OpenAI Whisper API 互換の REST エンドポイント（`/v1/audio/transcriptions`）
  - モデル管理（ダウンロード/削除/パス解決）と話者分離の前提設定
- 非目的:
  - Whisper 推論エンジンの再実装や精度改善
  - upstream コードの直接編集・分岐

## 要求 / 制約
- 必須: Python 3.11+、`ffmpeg`、ネットワークアクセス（モデル取得時）
- プラットフォーム: Windows/macOS/Linux
- セキュリティ: 既定は `127.0.0.1` バインド。外部公開はユーザー操作で有効化（`0.0.0.0`）
- 依存は環境別の `wrapper/requirements-nvidia.txt` または `wrapper/requirements-cpu-amd.txt` を参照。upstream は `pyproject.toml` に準拠
- GUI 表示言語: OS が日本語の場合は日本語、それ以外は英語

## ユースケース / ユーザーフロー
- ローカルでリアルタイム文字起こしを試す（GUI 起動 → Start API → 録音 → 結果表示/保存）
- 既存アプリから Whisper API 互換 REST を叩く（GUI/CLI で API 起動 → `POST /v1/audio/transcriptions`）
- モデルを事前に取得し、オフラインで利用（モデル管理 → Whisper/VAD/ダイアリゼーションモデル）
  - faster-whisper バックエンド選択時は、Whisper の重みは OpenAI 版ではなく CTranslate2 版
   （例: `Systran/faster-whisper-<size>`）を事前取得します。
- 話者分離を有効化（Hugging Face ログイン → モデル選択 → Start API）

## アーキテクチャ
- GUI 層（Python Tkinter）：`wrapper/cli/main.py` → `wrapper/app/gui.py`
  - WhisperLiveKit の Web UI（`http://<backend_host>:<backend_port>`）をブラウザで開く
  - Start/Stop で 2 プロセス起動/停止
    - Backend: `python -m whisperlivekit.basic_server`（`--model_cache_dir` にラッパー管理のHFキャッシュを付与）
    - API: `uvicorn wrapper.api.server:app`
  - 録音→WebSocket 送信、テキスト可視化、保存
 
- API 層（FastAPI）：`wrapper/api/server.py`
  - 受領音声を `ffmpeg` で 16kHz/mono PCM 化 → WebSocket で backend `/asr` へストリーミング → 連結テキスト返却
- モデル管理：`wrapper/app/model_manager.py` と CLI `wrapper/cli/model_manager_cli.py`
  - HF キャッシュと torch.hub キャッシュを wrapper 専用ディレクトリに分離

## I/O / 公開インターフェース
- CLI/GUI:
  - Tkinter GUI 起動: `python -m wrapper.cli.main`
- REST API:
  - エンドポイント: `POST http://<api_host>:<api_port>/v1/audio/transcriptions`
  - フォーム: `file=@audio.wav`、`model=whisper-1`
  - 例（APIキーなし）: `curl -X POST -F "file=@sample.wav" -F "model=whisper-1" http://127.0.0.1:8001/v1/audio/transcriptions`
  - APIキー（任意・GUIで有効化）:
    - ヘッダ `X-API-Key: <your_key>` または `Authorization: Bearer <your_key>` を付与
    - 例: `curl -H "X-API-Key: 1234" -F "file=@sample.wav" -F "model=whisper-1" http://127.0.0.1:8001/v1/audio/transcriptions`
  - レスポンス: `{ "text": "...", "model": "whisper-1" }`
- WebSocket（upstream 提供）:
  - `ws://<backend_host>:<backend_port>/asr`（GUI の Recorder もこれを利用）
- 設定ファイル（自動保存/読込）:
  - `~/.config/WhisperLiveKit/wrapper/settings.json`（OSにより適切な `platformdirs` パス）
- 主な環境変数（初期値や自動設定に利用）:
  - `WRAPPER_BACKEND_HOST` / `WRAPPER_BACKEND_PORT`
  - `WRAPPER_API_HOST` / `WRAPPER_API_PORT`
  - `WRAPPER_ALLOW_EXTERNAL=1`（`0.0.0.0` バインド）
  - `WRAPPER_MODEL`、`WRAPPER_USE_VAC=1`、`WRAPPER_DIARIZATION=1`
  - `WRAPPER_SEGMENTATION_MODEL`、`WRAPPER_EMBEDDING_MODEL`
  - `WRAPPER_CACHE_DIR`（モデル管理 CLI のキャッシュルート上書き）
  - `SSL_CERT_FILE`（VAD 用の証明書パスを明示）

## 実行・設定手順
1) 依存インストール
 - NVIDIA GPU 環境: `pip install -r wrapper/requirements-nvidia.txt`
 - CPU/AMD 環境: `pip install -r wrapper/requirements-cpu-amd.txt`
 - 互換性のため従来の `requirements.txt` も利用可能
 - `ffmpeg` をインストール（PATH で実行可能に）
 - 依存ライブラリを更新した場合は `python wrapper/scripts/generate_licenses.py` を実行し、`wrapper/licenses.json` を再生成

2) 追加依存（機能別）
- VAD（VAC）を有効化する場合:
  - `torchaudio` が必須です（`requirements-*.txt` に含まれますが、`torch` のバージョンと一致させてください）。
  - 例: `python -c "import torch; print(torch.__version__)"` で確認し、必要に応じて `pip install torchaudio==<上記のtorchバージョン>` を実行
  - macOS/Apple Silicon/py3.13 の一例: `pip install torchaudio==2.8.0`（Torch 2.8.0 の場合）
- 話者分離（Diarization）を有効化する場合:
  - Sortformer バックエンド: NVIDIA NeMo が必要です。
    - 例: `pip install "git+https://github.com/NVIDIA/NeMo.git@main#egg=nemo_toolkit[asr]"`
    - 注: macOS では環境構築が難しい場合があります。CPU での動作は時間がかかることがあります。
    - GUI は CUDA と NeMo を検出した場合のみ Sortformer を選択肢に表示します。未検出の場合は自動的に Diart に切り替わります。
  - Diart バックエンド: `diart` と関連依存が必要です。
    - 例: `pip install diart pyannote.audio rx`
  - Hugging Face ログインとモデル取得が前提となります（GUI の Login から設定）。
 

3) GUI 起動と基本操作（Tkinter）
- 起動: `python -m wrapper.cli.main`
- ヘッダーのライセンスボタン右に CUDA 検出状況アイコン（✅/❌）を表示
- 日本語環境ではラベルやメッセージが自動的に日本語表示になる
- Server Settings で host/port を確認（既定は空きポート自動割当）
- Backend 設定で SimulStreaming を選択して商用利用する場合は、SimulStreaming のライセンスを別途確認してください。
- Start API で backend と API を起動（Stop API で停止）。起動時にブラウザは自動起動しません。必要に応じて Endpoints 欄の「Open Web GUI」から開いてください。
- 稼働中（Start API 中）および録音中は、即時反映されない設定はロックされます。停止後に編集してください。
- Recorder で録音開始/停止、テキスト表示、保存先指定が可能
- Manage models で Whisper/VAD/関連モデルの取得・削除
- Hugging Face Login でトークン登録（話者分離の有効化に必須）

 

4) API だけを起動したい場合（手動）
- Backend: `python -m whisperlivekit.basic_server --host 127.0.0.1 --port 8000 [--model_dir <PATH>] [...options]`
- API: `WRAPPER_BACKEND_HOST=127.0.0.1 WRAPPER_BACKEND_PORT=8000 uvicorn wrapper.api.server:app --host 127.0.0.1 --port 8001`

## エラーハンドリング / ログ・テレメトリ
- `ffmpeg` が無い場合: API は `500 (ffmpeg_not_found)` を返す
- 音声変換失敗: `400 (ffmpeg_failed)` を返す
- backend 未起動/接続失敗: WebSocket 例外 → API は 5xx 応答の可能性
- ログ: backend と API は標準出力へログ出力（GUI から起動時も同様）
- テレメトリ: 送信なし。モデル取得時に Hugging Face へのアクセスが発生

## トラブルシューティング
- `ModuleNotFoundError: No module named 'torchaudio'`
  - VAD（VAC）機能が有効なときに発生します。`pip install torchaudio==<torchのバージョン>` を実施してください。
- Sortformer が選択肢に表示されない、または選択後に起動直後に停止する
  - CUDA または NeMo が検出されていない可能性があります。`pip install "git+https://github.com/NVIDIA/NeMo.git@main#egg=nemo_toolkit[asr]"`
  - macOS では依存解決に時間/調整が必要な場合があります。Diart バックエンドへ切替も検討してください。
- Diart で依存エラー
  - `pip install diart pyannote.audio rx` を実施。Hugging Face モデルの初回ダウンロードにはネットワークが必要です。

## セキュリティ / プライバシー
- 既定は `127.0.0.1` バインド。`Allow external connections` を有効にすると `0.0.0.0` で待受
- 公開時はファイアウォール/ポート開放/反向プロキシ（TLS/認証）の考慮が必須
- APIキー（オプション）: GUI の「Security > Require API key for Wrapper API」を有効にし、キーを設定
  - 保存先: `~/.config/WhisperLiveKit/wrapper/settings.json`（平文保存）
  - リクエスト時は `X-API-Key` ヘッダ、または `Authorization: Bearer <key>` を使用
  - 認証失敗: `401 unauthorized`、キー未設定で要件ON: `500 api_key_not_configured`
- 上流の Backend（Web UI と WebSocket `/asr`）にはラッパー側で認証を付与していません（上流コード非改変方針のため）。
  - `--ssl-certfile`/`--ssl-keyfile`（backend 引数）で TLS 終端に対応可能

## パフォーマンス目標（参考）
- 低遅延（< 数百 ms レベルのバッファリング）での逐次文字起こし
- モデルとハードウェアに依存。`large-v3` 以上は高負荷のため、必要に応じて `tiny/base/small` を推奨
- VAD 有効時は torch.hub の初回取得が発生。証明書問題回避のため既定では無効（GUI から有効化）

## リリース計画/今後のタスク
- 配布パッケージング（PyInstaller など）の検討
- API 認証/簡易ダッシュボードの追加検討
- upstream への改善提案は `WRAPPER-DEV-LOG.md` に記録

## 主要ファイル
- GUI（Tkinter）: `wrapper/app/gui.py`（エントリ: `python -m wrapper.cli.main`）
- API: `wrapper/api/server.py`（FFmpeg 変換 → WS `/asr`）
- モデル管理: `wrapper/app/model_manager.py`、`wrapper/cli/model_manager_cli.py`
- 設定テンプレート: `wrapper/config/settings.example.json`
- ライセンス一覧: `wrapper/licenses.json`（GUI の Licenses ボタンから参照、`python wrapper/scripts/generate_licenses.py` で再生成）

## 動作確認チェック
- `python -m wrapper.cli.main` で GUI が起動し、Start/Stop が機能する
- Web UI が `http://<backend_host>:<backend_port>` で開ける
- `curl` で `/v1/audio/transcriptions` に音声を投げてテキストが返る
- モデル管理で Whisper/VAD が取得/削除できる
- 設定が `settings.json` に保存/復元される

この README と `WRAPPER-DEV-LOG.md` は、仕様変更や意思決定に合わせて随時更新します。
