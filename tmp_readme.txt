# WhisperLiveKit Wrapper 仕様書�E�EEADME-FOR-WRAPPER�E�E

本リポジトリは upstream�E�Ewhisperlivekit`�E�を直接改変せず、GUI と API のラチE��ーとして統合�E拡張します。upstream 連携ファイルは読み取り専用です。変更は `wrapper/` 配下とこ�E README、`WRAPPER-DEV-LOG.md` のみで行います、E

## 目皁E/ 非目皁E
- 目皁E 既存�E `whisperlivekit.basic_server` を安�Eに起動�E制御し、以下を提供する、E
  - チE��クトッチEGUI�E�Ekinter�E�による起動�E録音・可視化
  - OpenAI Whisper API 互換の REST エンド�Eイント！E/v1/audio/transcriptions`�E�E
  - モチE��管琁E��ダウンローチE削除/パス解決�E�と話老E�E離の前提設宁E
- 非目皁E
  - Whisper 推論エンジンの再実裁E��精度改喁E
  - upstream コード�E直接編雁E�E刁E��E

## 要汁E/ 制紁E
- 忁E��E Python 3.11+、`ffmpeg`、ネチE��ワークアクセス�E�モチE��取得時�E�E
- プラチE��フォーム: Windows/macOS/Linux
- セキュリチE��: 既定�E `127.0.0.1` バインド。外部公開�Eユーザー操作で有効化！E0.0.0.0`�E�E
- 依存�E環墁E��の `wrapper/requirements-nvidia.txt` また�E `wrapper/requirements-cpu-amd.txt` を参照。upstream は `pyproject.toml` に準拠
- GUI 表示言誁E OS が日本語�E場合�E日本語、それ以外�E英誁E

## ユースケース / ユーザーフロー
- ローカルでリアルタイム斁E��起こしを試す！EUI 起勁EↁEStart API ↁE録音 ↁE結果表示/保存！E
- 既存アプリから Whisper API 互換 REST を叩く！EUI/CLI で API 起勁EↁE`POST /v1/audio/transcriptions`�E�E
- モチE��を事前に取得し、オフラインで利用�E�モチE��管琁EↁEWhisper/VAD/ダイアリゼーションモチE���E�E
  - faster-whisper バックエンド選択時は、Whisper の重みは OpenAI 版ではなぁECTranslate2 牁E
   �E�侁E `Systran/faster-whisper-<size>`�E�を事前取得します、E
- 話老E�E離を有効化！Eugging Face ログイン ↁEモチE��選抁EↁEStart API�E�E

## アーキチE��チャ
- GUI 層�E�Eython Tkinter�E�：`wrapper/cli/main.py` ↁE`wrapper/app/gui.py`
  - WhisperLiveKit の Web UI�E�Ehttp://<backend_host>:<backend_port>`�E�をブラウザで開く
  - Start/Stop で 2 プロセス起勁E停止
    - Backend: `python -m whisperlivekit.basic_server`�E�E--model_cache_dir` にラチE��ー管琁E�EHFキャチE��ュを付与！E
    - API: `uvicorn wrapper.api.server:app`
  - 録音→WebSocket 送信、テキスト可視化、保孁E
  - Advanced Settings は選択式UIを採用�E�誤入力防止�E�E
    - `Task`: `transcribe` / `translate`
    - `Backend`: `simulstreaming` / `faster-whisper`
    - `Log level`: `DEBUG` / `INFO` / `WARNING` / `ERROR` / `CRITICAL`
    - `Language`: 主要コード！Eauto`, `en`, `ja`, `zh`, `ko`, `fr`, `de`, `es`, `it`, `pt`, `ru`, `hi`, `th`, `vi`, `ar`, `id`, `nl`, `pl`, `tr`, `uk`�E�E `Other...`�E�任意�E力！E
    - `Buffer trimming`: `segment` / `sentence`�E�上流CLI仕様に合わせて選択式！E
 
- API 層�E�EastAPI�E�：`wrapper/api/server.py`
  - 受領音声めE`ffmpeg` で 16kHz/mono PCM 匁EↁEWebSocket で backend `/asr` へストリーミング ↁE連結テキスト返却
- モチE��管琁E��`wrapper/app/model_manager.py` と CLI `wrapper/cli/model_manager_cli.py`
  - HF キャチE��ュと torch.hub キャチE��ュめEwrapper 専用チE��レクトリに刁E��

## I/O / 公開インターフェース
- CLI/GUI:
  - Tkinter GUI 起勁E `python -m wrapper.cli.main`
- REST API:
  - エンド�EインチE `POST http://<api_host>:<api_port>/v1/audio/transcriptions`
  - フォーム: `file=@audio.wav`、`model=whisper-1`
  - 例！EPIキーなし！E `curl -X POST -F "file=@sample.wav" -F "model=whisper-1" http://127.0.0.1:8001/v1/audio/transcriptions`
  - APIキー�E�任意�EGUIで有効化！E
    - ヘッダ `X-API-Key: <your_key>` また�E `Authorization: Bearer <your_key>` を付丁E
    - 侁E `curl -H "X-API-Key: 1234" -F "file=@sample.wav" -F "model=whisper-1" http://127.0.0.1:8001/v1/audio/transcriptions`
  - レスポンス: `{ "text": "...", "model": "whisper-1" }`
- WebSocket�E�Epstream 提供！E
  - `ws://<backend_host>:<backend_port>/asr`�E�EUI の Recorder もこれを利用�E�E
- 設定ファイル�E��E動保孁E読込�E�E
  - `~/.config/WhisperLiveKit/wrapper/settings.json`�E�ESにより適刁E�� `platformdirs` パス�E�E
- 主な環墁E��数�E��E期値めE�E動設定に利用�E�E
  - `WRAPPER_BACKEND_HOST` / `WRAPPER_BACKEND_PORT`
  - `WRAPPER_API_HOST` / `WRAPPER_API_PORT`
  - `WRAPPER_ALLOW_EXTERNAL=1`�E�E0.0.0.0` バインド！E
  - `WRAPPER_MODEL`、`WRAPPER_USE_VAC=1`、`WRAPPER_DIARIZATION=1`
  - `WRAPPER_SEGMENTATION_MODEL`、`WRAPPER_EMBEDDING_MODEL`
  - `WRAPPER_CACHE_DIR`�E�モチE��管琁ECLI のキャチE��ュルート上書き！E
  - `SSL_CERT_FILE`�E�EAD 用の証明書パスを�E示�E�E

## 実行�E設定手頁E
1) 依存インスト�Eル
 - NVIDIA GPU 環墁E `pip install -r wrapper/requirements-nvidia.txt`
 - CPU/AMD 環墁E `pip install -r wrapper/requirements-cpu-amd.txt`
 - 互換性のため従来の `requirements.txt` も利用可能
 - `ffmpeg` をインスト�Eル�E�EATH で実行可能に�E�E
 - 依存ライブラリを更新した場合�E `python wrapper/scripts/generate_licenses.py` を実行し、`wrapper/licenses.json` を�E生�E

2) 追加依存（機�E別�E�E
- VAD�E�EAC�E�を有効化する場吁E
  - `torchaudio` が忁E��です！Erequirements-*.txt` に含まれますが、`torch` のバ�Eジョンと一致させてください�E�、E
  - 侁E `python -c "import torch; print(torch.__version__)"` で確認し、忁E��に応じて `pip install torchaudio==<上記�Etorchバ�Eジョン>` を実衁E
  - macOS/Apple Silicon/py3.13 の一侁E `pip install torchaudio==2.8.0`�E�Eorch 2.8.0 の場合！E
- 話老E�E離�E�Eiarization�E�を有効化する場吁E
  - Sortformer バックエンチE NVIDIA NeMo が忁E��です、E
    - 侁E `pip install "git+https://github.com/NVIDIA/NeMo.git@main#egg=nemo_toolkit[asr]"`
    - 注: macOS では環墁E��築が難しい場合があります、EPU での動作�E時間がかかることがあります、E
    - GUI は CUDA と NeMo を検�Eした場合�Eみ Sortformer を選択肢に表示します。未検�Eの場合�E自動的に Diart に刁E��替わります、E
  - Diart バックエンチE `diart` と関連依存が忁E��です、E
    - 侁E `pip install diart pyannote.audio rx`
  - Hugging Face ログインとモチE��取得が前提となります！EUI の Login から設定）、E
 

3) GUI 起動と基本操作！Ekinter�E�E
- 起勁E `python -m wrapper.cli.main`
- ヘッダーのライセンスボタン右に CUDA 検�E状況アイコン�E�✅/❌）を表示
- 日本語環墁E��はラベルめE��チE��ージが�E動的に日本語表示になめE
- Server Settings で host/port を確認（既定�E空き�Eート�E動割当！E
- Backend 設定で SimulStreaming を選択して啁E��利用する場合�E、SimulStreaming のライセンスを別途確認してください、E
- Start API で backend と API を起動！Etop API で停止�E�。起動時にブラウザは自動起動しません。忁E��に応じて Endpoints 欁E�E「Open Web GUI」から開ぁE��ください、E
- 稼働中�E�Etart API 中�E�およ�E録音中は、即時反映されなぁE��定�EロチE��されます。停止後に編雁E��てください、E
- Recorder で録音開姁E停止、テキスト表示、保存�E持E��が可能
- Manage models で Whisper/VAD/関連モチE��の取得�E削除
- Hugging Face Login でト�Eクン登録�E�話老E�E離の有効化に忁E��！E

 

4) API だけを起動したい場合（手動！E
- Backend: `python -m whisperlivekit.basic_server --host 127.0.0.1 --port 8000 [--model_dir <PATH>] [...options]`
- API: `WRAPPER_BACKEND_HOST=127.0.0.1 WRAPPER_BACKEND_PORT=8000 uvicorn wrapper.api.server:app --host 127.0.0.1 --port 8001`

## エラーハンドリング / ログ・チE��メトリ
- `ffmpeg` が無ぁE��吁E API は `500 (ffmpeg_not_found)` を返す
- 音声変換失敁E `400 (ffmpeg_failed)` を返す
- backend 未起勁E接続失敁E WebSocket 例夁EↁEAPI は 5xx 応答�E可能性
- ログ: backend と API は標準�E力へログ出力！EUI から起動時も同様！E
- チE��メトリ: 送信なし。モチE��取得時に Hugging Face へのアクセスが発甁E

## トラブルシューチE��ング
- `ModuleNotFoundError: No module named 'torchaudio'`
  - VAD�E�EAC�E�機�Eが有効なときに発生します。`pip install torchaudio==<torchのバ�Eジョン>` を実施してください、E
- Sortformer が選択肢に表示されなぁE��また�E選択後に起動直後に停止する
  - CUDA また�E NeMo が検�EされてぁE��ぁE��能性があります。`pip install "git+https://github.com/NVIDIA/NeMo.git@main#egg=nemo_toolkit[asr]"`
  - macOS では依存解決に時間/調整が忁E��な場合があります、Eiart バックエンドへ刁E��も検討してください、E
- Diart で依存エラー
  - `pip install diart pyannote.audio rx` を実施、Eugging Face モチE��の初回ダウンロードにはネットワークが忁E��です、E

## セキュリチE�� / プライバシー
- 既定�E `127.0.0.1` バインド。`Allow external connections` を有効にすると `0.0.0.0` で征E��
- 公開時はファイアウォール/ポ�Eト開放/反向プロキシ�E�ELS/認証�E��E老E�Eが忁E��E
- APIキー�E�オプション�E�E GUI の「Security > Require API key for Wrapper API」を有効にし、キーを設宁E
  - 保存�E: `~/.config/WhisperLiveKit/wrapper/settings.json`�E�平斁E��存！E
  - リクエスト時は `X-API-Key` ヘッダ、また�E `Authorization: Bearer <key>` を使用
  - 認証失敁E `401 unauthorized`、キー未設定で要件ON: `500 api_key_not_configured`
- 上流�E Backend�E�Eeb UI と WebSocket `/asr`�E�にはラチE��ー側で認証を付与してぁE��せん�E�上流コード非改変方針�Eため�E�、E
  - `--ssl-certfile`/`--ssl-keyfile`�E�Eackend 引数�E�で TLS 終端に対応可能

## パフォーマンス目標（参老E��E
- 低遅延�E�E 数百 ms レベルのバッファリング�E�での逐次斁E��起こし
- モチE��とハ�Eドウェアに依存。`large-v3` 以上�E高負荷のため、忁E��に応じて `tiny/base/small` を推奨
- VAD 有効時�E torch.hub の初回取得が発生。証明書問題回避のため既定では無効�E�EUI から有効化！E

## リリース計画/今後�Eタスク
- 配币E��チE��ージング�E�EyInstaller など�E��E検訁E
- API 認証/簡易ダチE��ュボ�Eド�E追加検訁E
- upstream への改喁E��案�E `WRAPPER-DEV-LOG.md` に記録

## 主要ファイル
- GUI�E�Ekinter�E�E `wrapper/app/gui.py`�E�エントリ: `python -m wrapper.cli.main`�E�E
- API: `wrapper/api/server.py`�E�EFmpeg 変換 ↁEWS `/asr`�E�E
- モチE��管琁E `wrapper/app/model_manager.py`、`wrapper/cli/model_manager_cli.py`
- 設定テンプレーチE `wrapper/config/settings.example.json`
- ライセンス一覧: `wrapper/licenses.json`
  - GUI の Licenses ボタンから「各ライブラリごとにライセンス本斁E��を選択表示
  - 依存更新時�E `python wrapper/scripts/generate_licenses.py` を実行し再生戁E

## 動作確認チェチE��
- `python -m wrapper.cli.main` で GUI が起動し、Start/Stop が機�Eする
- Web UI ぁE`http://<backend_host>:<backend_port>` で開けめE
- `curl` で `/v1/audio/transcriptions` に音声を投げてチE��ストが返る
- モチE��管琁E�� Whisper/VAD が取征E削除できる
- 設定が `settings.json` に保孁E復允E��れる

こ�E README と `WRAPPER-DEV-LOG.md` は、仕様変更めE��思決定に合わせて随時更新します、E
