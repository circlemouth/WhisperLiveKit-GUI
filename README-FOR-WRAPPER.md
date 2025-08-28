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
    - `python -m wrapper.cli.main` で設定 GUI を起動。GUI は起動時に空きポートを自動選択して入力欄に表示し、必要に応じて編集できる。`Start API` でサービスを起動、`Stop API` で停止できる。`Auto-start API on launch` を有効にすると起動時に自動開始する。Whisper モデルは `Whisper model` のプルダウンから選択でき（`available_models.md` に掲載された公式モデル一覧）、`Enable diarization` をオンにすると話者分離が有効になる。`Segmentation model` と `Embedding model` は既定モデルをプルダウンから選ぶか、任意の Hugging Face モデル ID を手入力できる。モデル取得には `Hugging Face Login` ボタンからトークンを入力してログインする。
    - ネットワーク公開：`Allow external connections (0.0.0.0)` をオンにすると、バックエンドおよび API を `0.0.0.0` で待受（全インターフェース bind）する。Endpoints 欄には検出したLAN内の実IP（例：`192.168.x.x`）を用いたURLが直接表示され、外部端末からアクセスしやすい形式になる。LAN/WAN に公開されるため、ファイアウォール設定とポート開放の可否を必ず確認すること（セキュリティ上の推奨：必要時のみオン）。
    - 稼働中ロック：`Start API` でサーバー稼働中は、ホスト/ポート、モデル設定、話者分離設定、外部接続許可、Auto-start、HF ログインなど、サーバー挙動に影響する設定を自動でロック（無効化）する。`Stop API` で停止すると再び編集可能になる。
    - 起動後は Backend Web UI・WebSocket `/asr`・ファイル文字起こし API の各エンドポイントと用途が表示され、隣の `Copy` ボタンでクリップボードにコピーできる。レイアウトはサーバー設定・エンドポイント・録音・保存・トランスクリプトの各セクションに分かれており、ウィンドウのリサイズに応じて入力欄やテキスト領域が自動調整される。
    - 録音コントロール（Recorder）：`Start Recording` でマイク入力を `/asr` にストリーミングし、Transcript にリアルタイム表示。録音中は音量レベルと経過時間を表示し、`Stop Recording` で終了する。`Save transcript to file` をオンにすると保存先入力と `Browse` が有効になり、録音終了時に自動保存される。
    - 話者分離（Diarization）：Hugging Face ログインが成功している場合にのみ有効化できる。未ログイン時は有効化できず、関連モデル選択もロックされる。（環境変数 `HF_TOKEN` / `HUGGINGFACEHUB_API_TOKEN` / `HUGGING_FACE_HUB_TOKEN` または `huggingface_hub` に保存されたトークンが存在すれば、ログイン済みとして扱う）
    - `Open Web GUI` ボタンでブラウザから元の Web GUI を開ける。`License` ボタンで本リポジトリ同梱の `LICENSE` ファイルを新規ウィンドウに表示する。
      - `Open Web GUI` ボタンはバックエンドが起動中のみ有効化される。
      - `License` ウィンドウには upstream リポジトリ [QuentinFuxa/WhisperLiveKit](https://github.com/QuentinFuxa/WhisperLiveKit) へのリンクと「このアプリはこのレポジトリのラッパーです」の注記を表示する。
- API：
  - `POST /v1/audio/transcriptions`（multipart/form-data, field=`file`） → `{ "text": "..." }`
  - ffmpeg が見つからない場合 `500 ffmpeg_not_found` を返却。
- 設定：
    - 入力された設定は環境変数 `WRAPPER_BACKEND_HOST`/`WRAPPER_BACKEND_PORT` と `WRAPPER_API_HOST`/`WRAPPER_API_PORT` としてサブプロセスに渡される。GUI は既定でバックエンドと API を自動起動する（設定 `Auto-start API on launch` のデフォルトはオン）。環境変数 `WRAPPER_API_AUTOSTART=0` もしくはチェックボックスをオフにすると自動起動を無効化できる。ポート番号を指定しなかった場合は空きポートが自動的に割り当てられる。
    - `Allow external connections` をオンにするとホスト値は `0.0.0.0` に設定され、オフに戻した場合は直前のローカル用ホスト（例：`127.0.0.1`）を復元する。設定は `settings.json` に `allow_external` として永続化される。
    - Whisper 関連の設定は `model`、`diarization`、`segmentation_model`、`embedding_model` として保存され、未指定の場合は既定値が適用される。旧形式の設定ファイルは存在すれば自動読み込みされ、新項目はデフォルト値で補完される。
    - GUI 上で編集した設定は各 OS のユーザー設定ディレクトリ（例：`%LOCALAPPDATA%\\WhisperLiveKit\\wrapper\\settings.json`）に保存され、次回起動時に読み込まれる。保存に関わる設定（`save_enabled`、`save_path`）もここに保持される。初回起動時に旧 `~/.whisperlivekit-wrapper.json` が存在すれば自動的に移行される。フォーマット例は `wrapper/config/settings.example.json` を参照。

## 6. 実行・セットアップ手順
1. 必要要件：Python 3.11 以降、ffmpeg、インターネット接続。
2. セットアップ：`pip install -r requirements.txt` で `fastapi`, `uvicorn`, `websockets`, `sounddevice`, `platformdirs` などの依存ライブラリを導入。
3. 実行例：`python -m wrapper.cli.main` を実行すると設定 GUI が起動する。必要に応じてホストやポートを変更し、`Start API` で WhisperLiveKit とラッパー API を開始する。GUI は初期状態でバックエンドと API を自動開始する（環境変数 `WRAPPER_API_AUTOSTART=0` もしくは設定で無効化可能）。録音を行う場合は WebSocket URL を確認し、必要なら保存先ファイルを設定してから `Start Recording` ボタンでマイク入力を送信する。

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
  - 設定ファイルは `platformdirs` を通じて `AppData` 配下に保存され、旧ホームディレクトリの設定が存在すれば初回起動時に自動移行される。
- 既存ユーザーへの影響：移行処理が実装されており、以前の設定ファイルがあれば自動的に新ディレクトリへコピーされる。

## 13. MSIX オフライン対応（計画）
本節は、MSIX 配布を前提とした「完全オフライン運用」対応の実装計画です。現時点では計画のみで、実装は後続タスクで行います。

### 13.1 目標と範囲
- 目標：インターネット接続なしで GUI/API を起動・利用できること。
- 範囲：
  - 依存パッケージ（Python ランタイム＋site-packages）を同梱。
  - Whisper モデル・（任意）話者分離モデルをローカルに配置・管理。
  - Silero VAD と warmup 動作によりネットアクセスが発生しないよう制御。
  - GUI でモデルの有無・容量・削除などが確認・操作できる「モデル管理」機能を提供。

### 13.2 オフライン方針（要点）
- 既定で VAD/VAC を無効化し、PyTorch Hub 参照を回避（必要時のみ有効化）。
- warmup 音声を事前同梱し、起動前に一時ディレクトリへ配置（外部DLを回避）。
- Whisper/diarization モデルは MSIX に同梱または「事前フェッチ手順」でローカルキャッシュへ配置。
- 既定のキャッシュ/モデルディレクトリをユーザー領域（LocalCache）に固定し、GUI/CLI から参照・管理。

### 13.3 追加する GUI 機能（モデル管理・ダウンロード状況の可視化）
- モデル管理パネル（新規）
  - 一覧表示：モデル名、種類（Whisper/Segmentation/Embedding/VAD）、サイズ、配置場所、状態（利用可/欠損/未検証）
  - 操作：
    - ダウンロード/インポート（オンライン時 or 同梱アセットからのコピー）
    - 削除（安全な削除、使用中ロック時はガード）
    - 検証（ハッシュ照合による破損チェック）
    - フォルダを開く（エクスプローラで該当ディレクトリを開く）
  - 進捗表示：複数ジョブのキュー管理、個別/全体のプログレスバー、残り時間目安
  - ディスク使用量：モデルディレクトリの合計サイズ、上限アラート
- 設定連動：
  - Whisper モデル選択や話者分離 ON 時に、必要モデルが未配置ならインストールダイアログを提示
  - VAD（Silero）有効化時、PyTorch Hub キャッシュの有無をチェックして案内

### 13.4 配置ディレクトリとマニフェスト
- 既定パス（例）：`%LOCALAPPDATA%/Packages/<App>/LocalCache/WhisperLiveKit/models/`
  - `whisper/`（Whisper 本体モデル）
  - `diarization/segmentation/`
  - `diarization/embedding/`
  - `torch_hub/`（任意：Silero VAD 用の Hub キャッシュを同梱する場合）
- マニフェスト `models_manifest.json`（同梱）：
  - 各モデルの ID、期待ファイル一覧、サイズ、SHA256、表示名、依存関係
  - GUI/CLI はこのマニフェストを基に整合性チェックと UI 表示を行う

### 13.5 ランタイム制御と環境変数
- ラッパー起動時に下記を設定：
  - `TORCH_HOME`：`LocalCache/WhisperLiveKit/torch_hub`（同梱/事前配置がある場合）
  - `HF_HOME`：`LocalCache/WhisperLiveKit/hf`（話者分離モデルを使う場合のキャッシュ）
  - `WRAPPER_MODEL_DIR`：`LocalCache/WhisperLiveKit/models/whisper`
  - `WRAPPER_NO_VAC=1`（既定OFF化、GUIトグルで反転）
- warmup 回避策：
  - 事前同梱の `warmup.wav`（例：`wrapper/config/assets/warmup.wav`）を起動前に `%TEMP%/whisper_warmup_jfk.wav` へコピーし、upstream の外部DL分岐を踏ませない（上流改修なしで対応）。
  - 併せて upstream へ「引数で warmup スキップ or ローカル指定を正しく効かせる」パッチ提案をログ化。

### 13.6 追加 CLI（ビルド/運用補助、実装予定）
- `python -m wrapper.cli.prefetch`：
  - マニフェストに基づき Whisper/diarization/VAD（任意）を所定ディレクトリへ事前ダウンロード
  - 進捗表示、再開（resume）、ハッシュ検証、マニフェスト更新
- `python -m wrapper.cli.models`：
  - 一覧・検証・削除・インポート（zip 取り込み）等のモデル管理コマンド
- これら CLI は MSIX ビルド前ステップでも使用（オフライン化の前提作り）

### 13.7 MSIX ビルド計画（概要）
1) ビルド環境準備：Windows、署名証明書、`makeappx.exe`/`signtool.exe`
2) ランタイム同梱：Python 埋め込み or venv + `site-packages`、`sounddevice`（PortAudio DLL 同梱確認）
3) 依存導入：`pip install -r requirements.txt`（ビルド時）
4) モデル事前配置：`wrapper.cli.prefetch` で `LocalCache` 用の初期アセットを生成（インストール後、初回起動でコピー）
5) AppxManifest：
   - デバイス機能：マイクアクセス（`microphone`）
   - ネットワーク：`privateNetworkClientServer`（ローカルLAN用途）。オフライン運用時は `internetClient` なしでも可
6) 初回起動フロー：
   - バンドル内の初期アセットを `LocalCache` に展開
   - warmup.wav を `%TEMP%` に生成（存在チェック）
   - 設定/モデルの存在検証 → GUI へ反映

### 13.8 エラーハンドリング・UX（実装方針）
- モデル欠損時：起動時に警告ダイアログとモデル管理パネルへの導線
- 認可/権限：マイク権限が無い場合のガイダンス
- 破損検知：SHA256 不一致時に再インポート/削除を案内
- VAD 有効化時：PyTorch 未同梱/Hub 未配置なら明示警告（機能限定で継続）

### 13.9 セキュリティ/ライセンス
- HF トークンは GUI から任意入力（保存オプションはデフォルト OFF、保存時は OS 既定のユーザー領域に暗号化保管を検討）
- モデル配布ライセンス確認（Whisper、pyannote、Silero、PortAudio など）
- ffmpeg の同梱はライセンス要件を確認し、既定は同梱せずユーザー導入ガイドを提示（将来オプション同梱も検討）

### 13.10 リスクと回避策（未解決含む）
- 上流 warmup 実装が引数を無視し外部DLに流れる問題：同梱ファイルを `%TEMP%` へ配置して回避。上流へパッチ提案（本リポでは適用しない）。
- `sounddevice` の PortAudio DLL：MSIX での同梱・読込パス検証が必要。
- Silero VAD（torch.hub）キャッシュ：既定は無効化。将来必要なら `TORCH_HOME` へ事前配置または起動時コピー対応。
- ディスク容量：大規模モデル同梱時のパッケージサイズ肥大。モデルは選択同梱＋後からインポート方式を基本とする。

### 13.11 マイルストーン（実装順）
1) 設計確定・マニフェスト定義（本節）
2) CLI `prefetch/models` 雛形とマニフェスト生成/検証ロジック
3) GUI：モデル管理パネル・進捗表示・削除/検証
4) ランタイム：環境変数設定、初回起動のアセット展開と warmup 回避
5) MSIX ビルドスクリプトと AppxManifest（権限/能力）
6) QA：完全オフラインでの動作検証（録音→WS→API、一通り）

### 13.12 実装対象（ラッパー側のみ）
- `wrapper/cli/prefetch.py`（新規）：事前ダウンロード/検証/マニフェスト生成
- `wrapper/cli/models.py`（新規）：モデル一覧/削除/検証/インポート
- `wrapper/app/gui.py`：モデル管理 UI、VAD/VAC トグル、進捗ダイアログ
- `wrapper/config/models_manifest.example.json`（新規）：マニフェスト雛形
- `wrapper/config/assets/warmup.wav`（新規）：同梱 warmup 用音声
- `README-FOR-WRAPPER.md`：運用手順とトラブルシュート追記（本節）
- `WRAPPER-DEV-LOG.md`：上流提案（warmup スキップ/引数尊重）と進捗の記録

### 13.13 完了定義（オフライン観点の追加）
- ネット接続なしで GUI/API/録音ストリーミングが起動・動作する
- モデル管理パネルでローカルモデルの有無・検証・削除が可能
- 初回起動で warmup 外部DLが発生しない（同梱で回避）
- MSIX パッケージに必要権限が宣言され、初回展開と設定永続化が機能
