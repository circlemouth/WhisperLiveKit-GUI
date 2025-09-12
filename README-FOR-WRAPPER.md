# WhisperLiveKit Wrapper 仕様書 (README-FOR-WRAPPER)

> 付記（問題点サマリ）
> - 最近判明した接続/入出力の問題は `WRAPPER-DEV-LOG.md`（2025-09-02）に詳細を記録。
> - 要点:
>   - REST→Backend の WebSocket ハンドシェイク遅延/失敗は、接続先不一致や IPv6/IPv4 の食い違いが主因。`WRAPPER_BACKEND_*` を明示設定（特に `WRAPPER_BACKEND_CONNECT_HOST=127.0.0.1`）。
>   - FFmpeg 書き込み失敗は raw PCM を送っていたことが原因。修正済み（コンテナ付き送信、`.raw` は WAV 化）。
>   - OpenAI Whisper API 互換: `model` は必須だが無視。`response_format=json|text|srt|vtt|verbose_json` 対応、エラーは OpenAI 風 JSON。

本リポジトリは upstream（whisperlivekit）を直接改変せず、GUI と API のラッパーとして外側から統合・拡張します。変更は本書・開発ログ・`wrapper/` 配下に限定します。

## 目的 / 非目的
- 目的: 既存の `whisperlivekit.basic_server` をラッパー独自のランチャー経由で安全に起動・制御し、GUI（録音・可視化）と、Whisper API 互換 REST を提供する。
- 非目的: Whisper 推論アルゴリズムの改良・精度改善、upstream コードの直接編集。

## 要求 / 制約
- 必須: Python 3.11+, `ffmpeg`, ネットワークアクセス
- 対応OS: Windows / macOS / Linux
- セキュリティ: 既定は `127.0.0.1` バインド。外部公開はユーザー操作で明示的に有効化（`0.0.0.0`）。
- 改変方針: upstream は読み取り専用。呼び出しは import またはサブプロセス。

## ユースケース / フロー
- ローカルでリアルタイム音声→文字起こしを試す（GUI から Start/録音/表示/自動保存）。
  - 録音停止のたびにトランスクリプトをタイムスタンプ付きテキストファイルとして指定フォルダに自動保存。
- 既存アプリから OpenAI Whisper API 互換 REST を呼ぶ（`POST /v1/audio/transcriptions`）。
- モデル/VAD のダウンロード・管理（GUIの Model Manager）。
  - API 起動時、必要な Whisper/VAD/話者分離モデルがローカルに無ければ自動でダウンロードし、設定画面から確認・削除できる。
- Whisperモデルは SimulStreaming 用と Faster Whisper 用に区分して一覧表示し、モデル名からバックエンド名を省いた。既存のダウンロード済みモデルはそのまま利用できるが、他バックエンドを使う場合は各バックエンド用モデルを追加取得する。
- モデル選択欄の右側で使用するバックエンドを直接選択できるようになった。SimulStreaming を選択した場合は商用利用に別途許諾が必要である旨の注意書きを表示する。
- Faster Whisper バックエンドのモデル取得時は、ダウンロードしたスナップショットのパスを `latest` ファイルに記録し、起動時はこれを参照してモデルを特定する。`latest` や `snapshots` が見つからない場合は `.bin` ファイル探索にフォールバックし、手動配置モデルも読み込める。

- 未ダウンロードのモデルを指定した場合でも、キャッシュディレクトリが存在しないことによるエラーは発生せず、必要に応じて自動ダウンロード処理に委ねられる。特に Faster Whisper バックエンドでは、モデルが未取得の場合でもモデル名を `--model` として渡すことで `Invalid model size` エラーを避けてダウンロードにフォールバックする。

## アーキテクチャ
- GUI 層（Tkinter）: `wrapper/cli/main.py` → `wrapper/app/gui.py`
  - Start/Stop で 2 プロセス起動/停止
    - Backend: `python -m wrapper.app.backend_launcher`（内部で `whisperlivekit.basic_server` を起動）
      - 起動時に `torch.hub.load` をラップして `trust_repo=True` を既定化（Silero VAD 初回ダウンロードの互換性確保）
    - API: `uvicorn wrapper.api.server:app`
  - 録音パイプライン: 生PCM → FFmpeg で `audio/webm`(Opus) へ変換 → WebSocket `/asr` へストリーミング
  - Web UI（upstream）をブラウザで開く導線あり
  - ヘッダー右上に CUDA/FFmpeg の利用可否を表示し、最右にライセンスボタンを配置
 - Start/Stop API ボタンはヘッダー（タイトル右側）に配置。メインの2カラム設定画面はヘッダー左端の折りたたみボタンで表示/非表示を切替でき、状態は保存・復元される
   - 起動時のウィンドウサイズ: 高さは折りたたみ状態に応じて自動調整（未折りたたみ時は左カラムの自然高さに合わせた最大高、折りたたみ時はその状態の自然高）。横幅は初期算出幅の 1.2 倍で表示
- 右カラムを Endpoints / Recorder / Logs の三段構成とし、ログ欄は Recorder の下部に配置。ステータス表示と進捗バーを廃止し、ログ欄は最低4行を維持しつつトランスクリプト欄と柔軟に高さを分配。トランスクリプト表示欄の縦幅は従来比でおよそ 2/3 に調整
  - ウィンドウ拡大後に左右カラムが伸びても、縮小時に高さがウィンドウに追随して UI 全体が常に表示されるよう ScrollableFrame を改修。ウィンドウ最大高さは左カラムの自然高さに合わせて制限
  - 以前の「ウィンドウ／ペインの最小サイズ固定」は撤廃し、自由なリサイズとスクロールで運用（小画面でのはみ出しを解消）
  - 旧レイアウト（下部パネルにログを表示）は廃止し、環境変数での切替は不可
  - GUIセクション（スクロール領域）はウィンドウ高さに追従し、はみ出す分はスクロールで閲覧可能（固定的な最小高さの強制は行わない）

- API 層（FastAPI）: `wrapper/api/server.py`
  - `POST /v1/audio/transcriptions`: 入力形式を判定し、16kHz/mono の wav/raw はそのまま、その他は FFmpeg で 16kHz/mono PCM 化 → backend `/asr` へWS中継 → テキスト連結返却
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
  - 音声形式: 16kHz モノラル (wav/raw) を推奨。これらは再変換せずに処理され、その他の形式は ffmpeg により変換される。
  - APIキー（任意）: `X-API-Key: <key>` または `Authorization: Bearer <key>`
  - レスポンス例: `{ "text": "...", "model": "whisper-1" }`

## 実行・設定手順（概要）
1) Backend 起動: `python -m wrapper.app.backend_launcher --host 127.0.0.1 --port 8000 [...options]`
2) Wrapper API 起動: `WRAPPER_BACKEND_HOST=127.0.0.1 WRAPPER_BACKEND_PORT=8000 uvicorn wrapper.api.server:app --host 127.0.0.1 --port 8001`
3) GUI から Start / 録音 / 可視化 / 保存

- 主要環境変数（GUI→APIへ引継ぎ）
  - `WRAPPER_BACKEND_HOST` / `WRAPPER_BACKEND_PORT`
  - `WRAPPER_BACKEND_SSL=1`（wss 接続を指定）
  - `WRAPPER_REQUIRE_API_KEY=1`, `WRAPPER_API_KEY=<key>`

## エラーハンドリング / ログ
- バックエンド/API の標準出力と標準エラーはGUIのログ欄と同時にターミナルにも表示される。`PYTHONUNBUFFERED=1` と `-u` オプションによりバッファリングを無効化し、macOSでログが出力されない問題を解消。
- FFmpeg が無い: `500 ffmpeg_not_found`（API）、GUIログに表示
- GUI から Start API を実行した際に FFmpeg が見つからない場合、警告ダイアログを表示して起動を中止する
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

## トラブルシューティング: Windowsで "speechbrain hyperparams.yaml" が見つからない
- 症状: バックエンド起動時に `FileNotFoundError: ... speechbrain\hyperparams.yaml` が表示される。
- 原因: Windows 環境では `pyannote.audio` が必要とする `hyperparams.yaml` や `custom.py` へのシンボリックリンク作成に失敗する場合がある。
- 対応: 起動時にこれらファイルの存在を確認し、ラッパーの Model Manager で `speechbrain/spkrec-ecapa-voxceleb` を取得して必要ファイルをコピーするよう修正済み（不足分は Hub から直接取得）。シンボリックリンクは使用しない。

## 依存関係のインストール（例）
- CPU/AMD 環境: `pip install -r wrapper/requirements-cpu-amd.txt`
- NVIDIA 環境: `pip install -r wrapper/requirements-nvidia.txt`
- 追加オプション（任意）:
  - VAD 有効時の `torchaudio` は Torch のバージョンに揃えてください（GUIが不足時に案内を表示）。
  - Sortformer バックエンドを使う場合は CUDA + NVIDIA NeMo が必要です。

## Submodule 管理（upstream の取り込み方）
- 本リポは upstream をサブモジュールとして参照します（ローカル改変なし）。
- 初回/取得後は以下を実行:
  - `git submodule update --init --recursive`
- 配置パス: `submodules/WhisperLiveKit`
  - ランチャー `wrapper/app/backend_launcher.py` が `sys.path` に上記パスを自動追加します。
  - そのため `pip install whisperlivekit` は不要です（requirements からも除外済み）。
  - サブモジュールを更新する場合: `git -C submodules/WhisperLiveKit pull` または `git submodule update --remote --merge`

## 主要ファイル
- GUI: `wrapper/app/gui.py`（エントリ: `python -m wrapper.cli.main`）
- API: `wrapper/api/server.py`
- 設定テンプレート: `wrapper/config/`
- ライセンス一覧: `wrapper/licenses.json`

本仕様書と `WRAPPER-DEV-LOG.md` は、仕様変更・意思決定に合わせて更新します。
## GUI の振る舞い（録音・文字起こし）
- 処理中インジケータ: 録音開始後からバックエンド側での最終処理が完了するまで、録音開始ボタンの右側にスピナーを表示します。
- 再開時の確認: 処理が継続中（停止後の後処理を含む）に「Start Recording」を押すと確認ダイアログを表示し、同意した場合は現在の処理を中止して新しいセッションをクリーンに開始します。
