# WRAPPER-DEV-LOG

## 2025-11-02 (SimulStreaming WinError 206 継続調査)
- 背景／スコープ：simulstreaming backend をラッパー経由で起動すると、faster-whisper がモデルをダウンロードする段階で Windows Store 版 Python 固有の長い `LocalCache\Local\wrapper\WhisperLiveKit\Cache` パスを参照し続け、MAX_PATH 超過が原因で Hugging Face 側の保存処理が失敗している。
- 現状エラー：`FileNotFoundError: [WinError 206] ファイル名または拡張子が長すぎます`（`huggingface_hub.file_download` → `os.makedirs(pointer_path)`）。
- 試行した修正：
  - `wrapper/app/model_manager.py` でキャッシュ候補を検査し、長さが 120 文字を超える場合や `packages/pythonsoftwarefoundation.python.` を含む場合は `~/.cache/WhisperLiveKitWrapper` 配下へ強制フォールバック。
  - `WRAPPER_CACHE_DIR`, `HUGGINGFACE_HUB_CACHE`, `HF_HOME`, `TORCH_HOME` など関連環境変数を上書きし、設定後に stderr で現在値を出力するログを追加。
  - `huggingface_hub` の import を環境変数設定後に遅延させ、ライブラリ内部が旧パスをキャッシュしないよう調整。
  - パス判定時はバックスラッシュ／スラッシュを正規化し、Windows Store 版 Python の既定パスを確実に検出。
- なお改善せず：`python -m wrapper.cli.main` 実行時のログが依然として `LocalCache\Local\wrapper\WhisperLiveKit\Cache` を指しており、修正コードが読み込まれていないか、別モジュールによる再上書きが疑われる。
- 次アクション：実行時に `[wrapper.model_manager] cache root ->` が `~/.cache/WhisperLiveKitWrapper` へ切り替わるまで追跡し、必要なら旧キャッシュを手動で移行・削除する手順を README に追記する。
- リスク／課題：Windows Store 版 Python 環境でしか再現しないため、自動テストで網羅できず、モジュール import 順序や外部環境変数に強く依存する可能性が残る。

## 2025-11-03 (キャッシュルート強制移行実装)
- 決定事項：長大な Windows Store 版 Python のキャッシュパスが検出された場合は、`~/.cache/WhisperLiveKitWrapper` 以下へ必ずフォールバックし、旧ディレクトリ内の Hugging Face / Torch / Wrapper キャッシュを移行する。
- 根拠：`wrapper/app/model_manager.py` でフォールバック発生時に移行処理と `WRAPPER_CACHE_MIGRATED_FROM` 環境変数を設定するよう実装。これによりログで確実に新パスへ切り替わったか追跡できる。
- 未解決事項：移行後の旧ディレクトリ削除は手動。ACL や読み取り専用属性により移行できなかったファイルが残る可能性があり、stderr ログで警告するに留める。
- 次アクション：Windows Store 環境で GUI/CLI 起動ログが新ディレクトリを指すか再確認し、必要なら追加の移行ガイドを整備する。
