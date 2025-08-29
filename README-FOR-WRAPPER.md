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
    - `python -m wrapper.cli.main` で設定 GUI を起動。GUI は起動時に空きポートを自動選択して入力欄に表示し、必要に応じて編集できる。`Start API` でサービスを起動、`Stop API` で停止できる。`Auto-start API on launch` を有効にすると起動時に自動開始する。Whisper モデルは `Whisper model` のプルダウンから選択でき（`available_models.md` に掲載された公式モデル一覧）、`Enable diarization` をオンにすると話者分離が有効になる。`Segmentation model` と `Embedding model` は既定モデルをプルダウンから選ぶか、任意の Hugging Face モデル ID を手入力できる。モデル取得・管理系は Start/Stop の行の左端に集約され、`Manage models`（ダウンロード/削除/用途表示）と `Hugging Face Login`（トークン入力・検証）が配置される。選択した Whisper モデルや話者分離モデルがローカルに存在しない場合は `Start API` を押すと自動ダウンロードが始まり、完了後にサーバーが起動する。
    - `Use voice activity controller (VAD)` チェックボックスで Silero VAD を利用できる。VAD 用証明書ファイルを `VAD certificate` で既存のファイルとして指定するまで有効化できない。無効なパスや未指定の場合は自動的にロックされる。
    - `Advanced settings` ボタンからウォームアップ音声、言語・タスク、バックエンド種別、ログレベル、SSL 証明書/鍵、バッファトリミングなど詳細なサーバー設定を行える。`VAD Settings` では VAC チャンクサイズを、`Diarization Settings` では話者分離バックエンドを選択できる。
    - ネットワーク公開：`Allow external connections (0.0.0.0)` をオンにすると、バックエンドおよび API を `0.0.0.0` で待受（全インターフェース bind）する。Endpoints 欄には検出したLAN内の実IP（例：`192.168.x.x`）を用いたURLが直接表示され、外部端末からアクセスしやすい形式になる。LAN/WAN に公開されるため、ファイアウォール設定とポート開放の可否を必ず確認すること（セキュリティ上の推奨：必要時のみオン）。
    - 稼働中ロック：`Start API` でサーバー稼働中は、ホスト/ポート、モデル設定、話者分離設定、外部接続許可、Auto-start、HF ログインなど、サーバー挙動に影響する設定を自動でロック（無効化）する。`Stop API` で停止すると再び編集可能になる。
    - 起動後は Backend Web UI・WebSocket `/asr`・ファイル文字起こし API の各エンドポイントと用途が表示され、隣の `Copy` ボタンでクリップボードにコピーできる。レイアウトは `PanedWindow` による2カラム構成（左：Server Settings＋Endpoints、右：Recorder）で、最小幅は動的に追従する。
      - 左（Server/Endpoints）の横幅は全体の約 2/3 に固定（スプリッタ操作でも比率を維持）。
      - 横幅の最小値制約は設けない（比率固定のみ）。
      - 両ペインのウェイトは等しく、比率固定に合わせて自動再配置される。
      - Recorder の縦方向は左カラム（Server Settings＋Endpoints）の合計高さを上限にキャップされ、左を超えて伸びない。ウィンドウの高さは初期の最小高さに固定され、縦方向のリサイズは不可（横方向は可）。
    - GUI テーマは `litera` に固定（切替機能は提供しない）。
    - デザイン刷新（litera前提）：
      - 基本フォントサイズを拡大（可読性向上）。
      - セクション見出しを大きく太字＋プライマリ色で強調、直下にセパレータを追加。
      - 主要操作（Start/Stop）ボタンを右寄せ、`Start` はプライマリ、`Stop` はデンジャー色で明確化。
      - 入力欄・ボタンの余白を増やし、情報密度を調整。
      - 折りたたみUIは廃止し、常時展開表示に統一（見通しと操作性を優先）。
    - ヘッダ直下にアイコン付きツールバーを設け、録音開始／停止やモデル管理をワンクリックで実行できる。
    - サーバー設定・録音・エンドポイント各パネルは折りたたみ可能なセクションとして実装し、リサイズ時にもレイアウトが崩れにくいレスポンシブ構成になっている。
    - モデルダウンロードや録音状態は常設のステータスバーとプログレスバーに表示され、モーダルダイアログを使わずに進捗を確認できる。
    - Hugging Face トークン検証：`Hugging Face Login` から入力されたアクセストークンは即時に検証され、whoami 成功時のみ「Enable diarization」が有効化される。トークンが未入力または無効な場合はチェックボックスがロックされる。
    - 録音コントロール（Recorder）：`Start Recording` でマイク入力を `/asr` にストリーミングし、Transcript にリアルタイム表示。録音中は音量レベルと経過時間を表示し、`Stop Recording` で終了する。`Save transcript to file` をオンにすると保存先入力と `Browse` が有効になり、録音終了時に自動保存される。
    - 話者分離（Diarization）：Hugging Face ログインが成功している場合にのみ有効化できる。未ログイン時は有効化できず、関連モデル選択もロックされる。（環境変数 `HF_TOKEN` / `HUGGINGFACEHUB_API_TOKEN` / `HUGGING_FACE_HUB_TOKEN` または `huggingface_hub` に保存されたトークンが存在すれば、ログイン済みとして扱う）
      - `Open Web GUI` ボタンでブラウザから元の Web GUI を開ける。`License` ボタンはメインウィンドウ右上にあり、本リポジトリ同梱の `LICENSE` ファイルと依存ライブラリのライセンス一覧およびライセンス本文を新規ウィンドウに表示する（`wrapper/licenses.json` を読み込む）。
        - 依存ライブラリのライセンス情報は `python wrapper/scripts/generate_licenses.py` を実行することで更新される。ライセンス情報やライセンス本文が取得できなかったライブラリは表示されない。
      - `Open Web GUI` ボタンはバックエンドが起動中のみ有効化される。
      - `License` ウィンドウには upstream リポジトリ [QuentinFuxa/WhisperLiveKit](https://github.com/QuentinFuxa/WhisperLiveKit) へのリンクと「このアプリはこのレポジトリのラッパーです」の注記を表示する。
- API：
  - `POST /v1/audio/transcriptions`（multipart/form-data, field=`file`） → `{ "text": "..." }`
  - ffmpeg が見つからない場合 `500 ffmpeg_not_found` を返却。
- 設定：
    - 入力された設定は環境変数 `WRAPPER_BACKEND_HOST`/`WRAPPER_BACKEND_PORT` と `WRAPPER_API_HOST`/`WRAPPER_API_PORT` としてサブプロセスに渡される。GUI は既定でバックエンドと API を自動起動する（設定 `Auto-start API on launch` のデフォルトはオン）。環境変数 `WRAPPER_API_AUTOSTART=0` もしくはチェックボックスをオフにすると自動起動を無効化できる。ポート番号を指定しなかった場合は空きポートが自動的に割り当てられる。
    - `Allow external connections` をオンにするとホスト値は `0.0.0.0` に設定され、オフに戻した場合は直前のローカル用ホスト（例：`127.0.0.1`）を復元する。設定は `settings.json` に `allow_external` として永続化される。
     - Whisper 関連の設定は `model`、`use_vac`、`vad_certfile`、`diarization`、`segmentation_model`、`embedding_model` に加え、`warmup_file`、`confidence_validation`、`punctuation_split`、`diarization_backend`、`min_chunk_size`、`language`、`task`、`backend`、`vac_chunk_size`、`buffer_trimming`、`buffer_trimming_sec`、`log_level`、`ssl_certfile`、`ssl_keyfile`、`frame_threshold` を保存する。旧形式の設定ファイルは存在すれば自動読み込みされ、新項目はデフォルト値で補完される。
    - GUI 上で編集した設定は各 OS のユーザー設定ディレクトリ（例：`%LOCALAPPDATA%\\WhisperLiveKit\\wrapper\\settings.json`）に保存され、次回起動時に読み込まれる。保存に関わる設定（`save_enabled`、`save_path`）もここに保持される。初回起動時に旧 `~/.whisperlivekit-wrapper.json` が存在すれば自動的に移行される。フォーマット例は `wrapper/config/settings.example.json` を参照。

## 6. 実行・セットアップ手順
1. 必要要件：Python 3.11 以降、ffmpeg、インターネット接続。
2. セットアップ：`pip install -r requirements.txt` で `fastapi`, `uvicorn`, `websockets`, `sounddevice`, `platformdirs` などの依存ライブラリを導入。GUI のテーマ切替には別途 `ttkbootstrap` が必要なため、未インストールの場合は `pip install ttkbootstrap` を実行する。
3. 実行例：`python -m wrapper.cli.main` を実行すると設定 GUI が起動する。必要に応じてホストやポートを変更し、`Start API` で WhisperLiveKit とラッパー API を開始する。GUI は初期状態でバックエンドと API を自動開始する（環境変数 `WRAPPER_API_AUTOSTART=0` もしくは設定で無効化可能）。録音を行う場合は WebSocket URL を確認し、必要なら保存先ファイルを設定してから `Start Recording` ボタンでマイク入力を送信する。
4. 依存ライブラリを更新した場合は `python wrapper/scripts/generate_licenses.py` を実行してライセンス情報ファイル `wrapper/licenses.json` を再生成し、ライセンス本文を含めてリポジトリにコミットする。

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

## 13. MSIX 配布（モデル非同梱・Hugging Face ダウンロード計画）
本節は、MSIX パッケージにモデルを含めず、必要に応じて Hugging Face からダウンロードする運用の計画である。実装の進行に合わせて本計画を更新する。

### 13.1 目標と範囲
- 目標：MSIX インストーラにはモデルを同梱せず、初回起動またはユーザー操作でモデルを取得できること。
- 範囲：
  - Whisper モデルおよび話者分離モデルを Hugging Face からダウンロードして利用。
  - GUI でモデルのダウンロード状況を可視化し、削除などの管理が可能。
  - ダウンロード済みモデルはユーザー領域に保存し、再利用できるようにする。

### 13.2 モデルダウンロードと管理
- ラッパーは `huggingface_hub` を利用してモデルを取得。
- GUI に「モデル管理」パネルを実装し、以下を提供：
  - モデル一覧とローカル保存状況の表示。
  - ダウンロード進捗（プログレスバー）表示。
  - 削除ボタンによるローカルモデルの削除。
  - Whisper モデルに加え、話者分離（Segmentation/Embedding）モデルも同パネルで管理可能。

### 13.3 配置ディレクトリと環境変数
- 既定のモデル保存先：`%LOCALAPPDATA%/Packages/<App>/LocalCache/WhisperLiveKit/hf-cache/`。
- Whisper モデルはダウンロード後にパスを解決し、`--model_dir` 引数で `whisperlivekit.basic_server` に渡す。
- `HUGGINGFACE_HUB_CACHE` および `HF_HOME` をこのディレクトリに設定し、話者分離モデルも同キャッシュを利用する。

### 13.4 CLI/自動化
- `wrapper.cli.prefetch`（計画中）：GUI 以外でも事前ダウンロードできる CLI を提供。
- `wrapper.cli.models`（計画中）：モデルの一覧・削除・検証を CLI から実行可能にする。

### 13.5 MSIX ビルド時の考慮
- インストーラには Python ランタイムと依存パッケージのみを含め、モデルは含めない。
- 初回起動時にユーザーがモデルを選択しダウンロードするフローを案内する。
- AppxManifest ではマイクアクセス (`microphone`) とローカルネットワーク (`privateNetworkClientServer`) を宣言。

### 13.6 UX・エラーハンドリング
 - モデル未ダウンロードの状態でサーバーを起動すると、自動的にダウンロードが開始され、完了後に起動する。
- ダウンロード失敗時はエラーメッセージを表示し、再試行ボタンを提供（今後実装）。
- ダウンロード済みモデルの破損チェックやハッシュ検証は後続タスク。

### 13.7 実装対象（ラッパー側）
- `wrapper/app/model_manager.py`：Hugging Face からのモデル取得・削除・状態確認。
- `wrapper/app/gui.py`：モデル管理 UI、`--model_dir` 連携。
- `README-FOR-WRAPPER.md`：本計画と利用手順の記載（本節）。
- `WRAPPER-DEV-LOG.md`：進捗と決定事項の記録。

### 13.8 完了定義
- モデル非同梱の MSIX を配布し、GUI から Whisper モデルをダウンロード・削除できる。
- ダウンロード済みモデルを使用してバックエンド/API を起動できる。
 - 話者分離モデルおよび VAD モデルのダウンロード・削除に対応し、モデル一覧には各モデルの用途が表示される。
