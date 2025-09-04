import os
import socket
import subprocess
import sys
import time
import webbrowser
import tkinter as tk
from tkinter import filedialog, simpledialog, font, messagebox
import ttkbootstrap as ttkb
from ttkbootstrap import ttk
from ttkbootstrap.icons import Emoji
import audioop
import json
import queue
import threading
from pathlib import Path
import shutil
from platformdirs import user_config_path
import locale
try:
    import keyring  # type: ignore
except Exception:
    keyring = None

from . import model_manager


def _load_whisper_models() -> list[str]:
    models_file = Path(__file__).resolve().parents[2] / "available_models.md"
    models: list[str] = []
    try:
        with open(models_file, "r", encoding="utf-8") as f:
            collecting = False
            for line in f:
                line = line.strip()
                if line.startswith("- "):
                    models.append(line[2:].split()[0])
                    collecting = True
                elif collecting and not line:
                    break
    except Exception:
        models = [
            "tiny.en",
            "tiny",
            "base.en",
            "base",
            "small.en",
            "small",
            "medium.en",
            "medium",
            "large-v1",
            "large-v2",
            "large-v3",
            "large-v3-turbo",
        ]
    return models


WHISPER_MODELS = _load_whisper_models()
SEGMENTATION_MODELS = ["pyannote/segmentation-3.0", "pyannote/segmentation"]
EMBEDDING_MODELS = ["pyannote/embedding", "speechbrain/spkrec-ecapa-voxceleb"]
VAD_MODELS = [model_manager.VAD_REPO]
ALL_MODELS = WHISPER_MODELS + SEGMENTATION_MODELS + EMBEDDING_MODELS + VAD_MODELS
MODEL_USAGE = {m: "Whisper" for m in WHISPER_MODELS}
MODEL_USAGE.update({m: "Segmentation" for m in SEGMENTATION_MODELS})
MODEL_USAGE.update({m: "Embedding" for m in EMBEDDING_MODELS})
MODEL_USAGE.update({model_manager.VAD_REPO: "VAD"})


CONFIG_DIR = user_config_path("WhisperLiveKit", "wrapper")
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_FILE = CONFIG_DIR / "settings.json"
OLD_CONFIG_FILE = Path.home() / ".whisperlivekit-wrapper.json"
LICENSE_FILE = Path(__file__).resolve().parents[2] / "LICENSE"
THIRD_PARTY_LICENSES_FILE = Path(__file__).resolve().parents[1] / "licenses.json"
HF_KEYRING_SERVICE = "WhisperLiveKit-Wrapper"


def _is_cuda_available() -> bool:
    try:
        import torch  # type: ignore
        return torch.cuda.is_available()
    except Exception:
        return False


CUDA_AVAILABLE = _is_cuda_available()


def _is_ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


FFMPEG_AVAILABLE = _is_ffmpeg_available()


def _is_sortformer_supported() -> bool:
    """Return True if CUDA and NeMo are available."""
    try:
        import torch  # type: ignore
        if not torch.cuda.is_available():
            return False
        import nemo.collections.asr  # type: ignore  # noqa: F401
    except Exception:
        return False
    return True


SORTFORMER_AVAILABLE = _is_sortformer_supported()


TRANSLATIONS_JA = {
    "API": "API",
    "API key": "APIキー",
    "Advanced Settings": "詳細設定",
    "Allow external connections (0.0.0.0)": "外部接続を許可 (0.0.0.0)",
    "Auto-start API on launch": "起動時にAPIを自動開始",
    "Backend": "バックエンド",
    "Backend Web UI": "バックエンドWeb UI",
    "Browse": "参照",
    "Browse...": "参照...",
    "Buffer trimming": "バッファ削除",
    "Buffer trimming sec": "バッファ削除秒",
    "Close": "閉じる",
    "Copied!": "コピーしました!",
    "Copy": "コピー",
    "Custom CA certificate": "独自CA証明書",
    "Delete": "削除",
    "Diarization": "話者分離",
    "Diarization Settings": "話者分離設定",
    "Diarization backend": "話者分離バックエンド",
    "Download": "ダウンロード",
    "Embedding model": "埋め込みモデル",
    "Enable diarization": "話者分離を有効化",
    "Endpoints": "エンドポイント",
    "File transcription API": "ファイル文字起こしAPI",
    "Frame threshold": "フレーム閾値",
    "Get HF token": "HFトークン取得",
    "Host": "ホスト",
    "Hugging Face access token": "Hugging Faceアクセストークン",
    "Hugging Face login is required to enable diarization.": "話者分離を有効にするにはHugging Faceログインが必要です。",
    "Language": "言語",
    "License": "ライセンス",
    "CUDA: Available": "CUDA: 利用可",
    "CUDA: Not available": "CUDA: 利用不可",
    "FFmpeg: Available": "FFmpeg: 利用可",
    "FFmpeg: Not available": "FFmpeg: 利用不可",
    "Log level": "ログレベル",
    "Manage models": "モデル管理",
    "Min chunk size": "最小チャンクサイズ",
    "Model": "モデル",
    "Open Web GUI": "Web GUIを開く",
    "Port": "ポート",
    "Recorder": "レコーダー",
    "Require API key for Wrapper API": "Wrapper APIにAPIキーを要求",
    "SSL certfile": "SSL証明書",
    "SSL keyfile": "SSL鍵ファイル",
    "Save path": "保存パス",
    "Save transcript to file": "ファイルに保存",
    "Security": "セキュリティ",
    "Segmentation model": "セグメンテーションモデル",
    "Server Settings": "サーバー設定",
    "Show": "表示",
    "Start API": "API開始",
    "Start Recording": "録音開始",
    "Stop API": "API停止",
    "Stop Recording": "録音停止",
    "Streaming WebSocket /asr": "ストリーミングWebSocket /asr",
    "Task": "タスク",
    "This app is a wrapper for the above repository.": "本アプリは上記リポジトリのラッパーです。",
    "Transcript": "トランスクリプト",
    "Use confidence validation": "信頼度検証を使用",
    "Use punctuation split": "句読点分割を使用",
    "Use voice activity controller (VAD)": "音声活動検出(VAD)を使用",
    "VAC chunk size": "VACチャンクサイズ",
    "VAD": "VAD",
    "VAD Settings": "VAD設定",
    "Validate": "検証",
    "Validated": "検証済",
    "Warmup file": "ウォームアップファイル",
    "Whisper model": "Whisperモデル",
    "WhisperLiveKit Wrapper": "WhisperLiveKit Wrapper",
    "Settings locked": "設定はロックされています",
    "Stop API before changing settings.": "設定を変更する前にAPIを停止してください。",
    "Stop API before changing VAD settings.": "VAD設定を変更する前にAPIを停止してください。",
    "Stop API before changing diarization settings.": "話者分離設定を変更する前にAPIを停止してください。",
    "Models locked": "モデルはロックされています",
    "Stop API before managing models.": "モデル管理の前にAPIを停止してください。",
    "Enable token editing? You can re-validate a new token.": "トークン編集を有効にしますか? 新しいトークンを再検証できます。",
    "Please enter an access token.": "アクセス トークンを入力してください。",
    "Invalid token:": "トークンが無効です:",
    "Token check failed:": "トークンチェックに失敗しました:",
    "Token is valid. You can enable Diarization now.": "トークンは有効です。話者分離を有効にできます。",
    "Note: Token was not saved in keyring; it won't persist across restarts.": "注意: トークンはキーチェーンに保存されなかったため、再起動後は保持されません。",
    "Token is valid, but saving credentials failed. You may need to login via CLI.": "トークンは有効ですが、資格情報の保存に失敗しました。CLIでログインする必要があるかもしれません。",
    "Diarization requires Hugging Face login": "話者分離にはHugging Faceログインが必要です",
    "Download failed:": "ダウンロード失敗:",
    "Download complete": "ダウンロード完了",
    "stopped": "停止",
    "stopping": "停止中",
    "connecting": "接続中",
    "recording": "録音中",
    "error:": "エラー:",
    "saved:": "保存済:",
    "save failed:": "保存失敗:",
    "missing dependency:": "依存関係がありません:",
    "Hugging Face login succeeded": "Hugging Faceログイン成功",
    "Token is valid": "トークンは有効です",
    "but storing credentials failed:": "しかし資格情報の保存に失敗しました:",
    "Invalid Hugging Face token:": "Hugging Faceトークンが無効:",
    "Hugging Face token check failed:": "Hugging Faceトークン確認失敗:",
    "Hugging Face token valid": "Hugging Faceトークン有効",
    "Downloading": "ダウンロード中",
    "downloaded": "ダウンロード済",
    "This console is for log output only and cannot be used as a CLI.": "このコンソール欄はログ出力専用であり、CLIとしては使用できません。",
    "For commercial use of the SimulStreaming backend, please check the SimulStreaming license.": "SimulStreaming をバックエンドとして商用利用する場合、SimulStreaming のライセンスを確認してください。",
    "missing": "未取得",
    "Server is not running. Please press Start API before recording.": "サーバー未起動です。録音するには先に『Start API』を押してください。",
}


class CollapsibleSection(ttk.Frame):
    def __init__(self, master: tk.Widget, title: str):
        super().__init__(master)
        self._open = tk.BooleanVar(value=True)
        header = ttk.Frame(self)
        header.pack(fill="x", pady=(2, 2))
        self._toggle_btn = ttk.Button(header, width=2, text="▾", command=self.toggle)
        self._toggle_btn.pack(side="left")
        ttk.Label(header, text=title, style="SectionHeader.TLabel").pack(side="left", padx=(4, 0))
        # セクション見出し直下にセパレータで区切る
        ttk.Separator(self, orient="horizontal").pack(fill="x", pady=(4, 8))
        self.container = ttk.Frame(self)
        self.container.pack(fill="both", expand=True)

    def _resize_to_content(self) -> None:
        # スクロール対応：自動リサイズを無効化（ユーザーによる手動リサイズを尊重）
        pass

    def toggle(self) -> None:
        if self._open.get():
            self.container.forget()
            self._toggle_btn.config(text="▸")
            self._open.set(False)
        else:
            self.container.pack(fill="both", expand=True)
            self._toggle_btn.config(text="▾")
            self._open.set(True)
        # 開閉に応じてウィンドウサイズを自動調整
        self._resize_to_content()


class ScrollableFrame(ttk.Frame):
    def __init__(self, master: tk.Misc):
        super().__init__(master)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self._canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0)
        self._vsb = ttk.Scrollbar(self, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=self._vsb.set)
        # ダークテーマ時にキャンバス背景が浮かないよう配色
        try:
            _style = ttkb.Style()
            _bg = getattr(_style.colors, "bg", "#222222")
            self._canvas.configure(background=_bg)
        except Exception:
            pass
        self._canvas.grid(row=0, column=0, sticky="nsew")
        self._vsb.grid(row=0, column=1, sticky="ns")
        # 内部フレーム
        self.inner = ttk.Frame(self._canvas)
        self._window = self._canvas.create_window((0, 0), window=self.inner, anchor="nw")

        def _on_configure_inner(_e=None):
            self._canvas.configure(scrollregion=self._canvas.bbox("all"))
            # 横幅をキャンバス幅に合わせる
            try:
                self._canvas.itemconfigure(self._window, width=self._canvas.winfo_width())
            except Exception:
                pass
            # 高さをキャンバスに追従させ、余白がある場合は拡張
            try:
                # 子ウィジェットの実高さからコンテンツの自然な高さを取得
                self.inner.update_idletasks()
                content_h = 0
                for child in self.inner.winfo_children():
                    bottom = child.winfo_y() + child.winfo_height()
                    if bottom > content_h:
                        content_h = bottom
                canvas_h = self._canvas.winfo_height()
                target_h = canvas_h if content_h <= canvas_h else content_h
                self._canvas.itemconfigure(self._window, height=target_h)
                self._canvas.configure(scrollregion=self._canvas.bbox("all"))
                if content_h <= canvas_h + 1:
                    self._vsb.grid_remove()
                else:
                    self._vsb.grid(row=0, column=1, sticky="ns")
            except Exception:
                pass

        def _on_configure_canvas(_e=None):
            try:
                self._canvas.itemconfigure(self._window, width=self._canvas.winfo_width())
            except Exception:
                pass
            # スクロール必要性を再評価し、余白があれば高さを拡張
            try:
                self.inner.update_idletasks()
                content_h = 0
                for child in self.inner.winfo_children():
                    bottom = child.winfo_y() + child.winfo_height()
                    if bottom > content_h:
                        content_h = bottom
                canvas_h = self._canvas.winfo_height()
                target_h = canvas_h if content_h <= canvas_h else content_h
                self._canvas.itemconfigure(self._window, height=target_h)
                self._canvas.configure(scrollregion=self._canvas.bbox("all"))
                if content_h <= canvas_h + 1:
                    self._vsb.grid_remove()
                else:
                    self._vsb.grid(row=0, column=1, sticky="ns")
            except Exception:
                pass

        self.inner.bind("<Configure>", _on_configure_inner)
        self._canvas.bind("<Configure>", _on_configure_canvas)
        # スクロールホイール
        self._canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _on_mousewheel(self, event):  # pragma: no cover - UI event
        try:
            delta = int(-1 * (event.delta / 120))
            self._canvas.yview_scroll(delta, "units")
        except Exception:
            pass


class WrapperGUI:
    def __init__(self, master: tk.Tk):
        self.master = master
        lang = locale.getdefaultlocale()
        lang_code = lang[0] if lang and lang[0] else ""
        self._translations = TRANSLATIONS_JA if lang_code.startswith("ja") else {}
        master.title(self._t("WhisperLiveKit Wrapper"))

        # Variables
        # 固定テーマ: ダーク系（ttkbootstrap: darkly）
        self.theme = tk.StringVar(value="darkly")
        self.backend_host = tk.StringVar(value=os.getenv("WRAPPER_BACKEND_HOST", "127.0.0.1"))
        b_port_env = os.getenv("WRAPPER_BACKEND_PORT")
        if b_port_env:
            b_port = b_port_env
        else:
            b_port = str(self._find_free_port())
        self.backend_port = tk.StringVar(value=b_port)

        self.api_host = tk.StringVar(value=os.getenv("WRAPPER_API_HOST", "127.0.0.1"))
        a_port_env = os.getenv("WRAPPER_API_PORT")
        if a_port_env:
            a_port = a_port_env
        else:
            a_port = str(self._find_free_port(exclude={int(b_port)}))
        self.api_port = tk.StringVar(value=a_port)
        # Default OFF: do not auto-start API unless explicitly enabled
        self.auto_start = tk.BooleanVar(value=os.getenv("WRAPPER_API_AUTOSTART", "0") == "1")
        # Allow external connections (bind 0.0.0.0)
        self.allow_external = tk.BooleanVar(value=os.getenv("WRAPPER_ALLOW_EXTERNAL") == "1")
        # Keep last local-only hosts to restore when toggled off
        self._last_local_backend_host = "127.0.0.1"
        self._last_local_api_host = "127.0.0.1"

        # Wrapper API key settings
        self.use_api_key = tk.BooleanVar(value=False)
        self.api_key = tk.StringVar(value="")
        self.api_key_show = tk.BooleanVar(value=False)

        self.model = tk.StringVar(value=os.getenv("WRAPPER_MODEL", "large-v3"))
        # Use voice activity controller (Silero via torch.hub). Default off to avoid GitHub SSL/network issues.
        self.use_vac = tk.BooleanVar(value=os.getenv("WRAPPER_USE_VAC", "0") == "1")
        self.vad_certfile = tk.StringVar(value=os.getenv("SSL_CERT_FILE", ""))
        self.diarization = tk.BooleanVar(value=os.getenv("WRAPPER_DIARIZATION") == "1")
        self.segmentation_model = tk.StringVar(
            value=os.getenv("WRAPPER_SEGMENTATION_MODEL", "pyannote/segmentation-3.0")
        )
        self.embedding_model = tk.StringVar(
            value=os.getenv("WRAPPER_EMBEDDING_MODEL", "pyannote/embedding")
        )

        # Advanced backend options
        self.warmup_file = tk.StringVar(value="")
        self.confidence_validation = tk.BooleanVar(value=False)
        self.punctuation_split = tk.BooleanVar(value=False)
        default_backend = "sortformer" if SORTFORMER_AVAILABLE else "diart"
        self.diarization_backend = tk.StringVar(value=default_backend)
        self.min_chunk_size = tk.DoubleVar(value=0.5)
        self.language = tk.StringVar(value="auto")
        self.task = tk.StringVar(value="transcribe")
        self.backend = tk.StringVar(value="simulstreaming")
        self.vac_chunk_size = tk.DoubleVar(value=0.04)
        self.buffer_trimming = tk.StringVar(value="segment")
        self.buffer_trimming_sec = tk.DoubleVar(value=15.0)
        self.log_level = tk.StringVar(value="DEBUG")
        self.ssl_certfile = tk.StringVar(value="")
        self.ssl_keyfile = tk.StringVar(value="")
        self.frame_threshold = tk.IntVar(value=25)

        self.web_endpoint = tk.StringVar()
        self.ws_endpoint = tk.StringVar()
        self.api_endpoint = tk.StringVar()
        # HF login state (for diarization gating)
        self.hf_logged_in: bool = False
        self._hf_username: str | None = None
        self.hf_token = tk.StringVar(value=os.getenv("HF_TOKEN", ""))
        # HF token edit mode (when true, allow re-input even if logged in)
        self._hf_edit_mode: bool = False

        # Recording-related variables
        self.ws_url = tk.StringVar()
        self.is_recording = False
        self.status_var = tk.StringVar(value="stopped")
        self.timer_var = tk.StringVar(value="00:00")
        self.level_var = tk.DoubleVar(value=0.0)
        self.save_path = tk.StringVar()
        self.save_enabled = tk.BooleanVar(value=False)

        # Layout: 右カラムにログ・ステータス・進捗を配置

        self._load_settings()
        # テーマは設定を尊重（既定は darkly）。
        if not self.theme.get():
            self.theme.set("darkly")

        # 設定のオートセーブ: 主要な設定変数に対して変更検知で保存
        self._setup_autosave()

        self.style = ttkb.Style(theme=self.theme.get())
        # ダークテーマでクラシックTk要素にも配色を適用
        self._fg = getattr(self.style.colors, "fg", "#EAEAEA")
        self._bg = getattr(self.style.colors, "bg", "#222222")
        # 基本フォントと余白を拡大
        try:
            master.option_add("*Font", ("Segoe UI", 12))
        except Exception:
            pass
        self.style.configure("TLabel", padding=6)
        self.style.configure("TButton", padding=6)
        # API Start/Stopボタン用の目立つスタイル
        try:
            # より大きくて目立つAPIコントロールボタン
            self.style.configure("ApiStart.TButton", 
                               font=("Segoe UI", 12, "bold"),
                               padding=(12, 8))
            self.style.configure("ApiStop.TButton", 
                               font=("Segoe UI", 12, "bold"),
                               padding=(12, 8))
            # 通常ボタンのスタイル
            self.style.configure("primary.TButton", padding=6)
            self.style.configure("danger.TButton", padding=6)
        except Exception:
            pass
        self.style.configure("TLabelframe", padding=12)
        # 見出しの視認性を向上（サイズ増、プライマリ色）
        primary_fg = None
        try:
            primary_fg = self.style.colors.primary
        except Exception:
            primary_fg = None
        self.style.configure("Header.TLabel", font=("Segoe UI", 24, "bold"))
        self.style.configure(
            "SectionHeader.TLabel",
            font=("Segoe UI", 14, "bold"),
            foreground=primary_fg if primary_fg else None,
        )
        # 録音時間表示用の大きめフォント
        self.style.configure("Timer.TLabel", font=("Segoe UI", 20, "bold"))

        master.columnconfigure(0, weight=1)

        row = 0
        # App header（テーマセレクタは撤去し、ライセンスのみ配置）
        header = ttk.Frame(master)
        header.grid(row=row, column=0, sticky="ew", padx=10, pady=(8, 0))
        header.columnconfigure(1, weight=1)
        ttk.Label(header, text="WhisperLiveKit Wrapper", style="Header.TLabel").grid(row=0, column=0, sticky="w")
        # Be tolerant: Emoji.get may return None on some platforms/themes
        try:
            ok_emoji = Emoji.get("check mark button")
            ng_emoji = Emoji.get("cross mark")
            ok_char = ok_emoji.char if ok_emoji is not None else "✓"
            ng_char = ng_emoji.char if ng_emoji is not None else "✗"
        except Exception:
            ok_char, ng_char = "✓", "✗"
        cuda_char = ok_char if CUDA_AVAILABLE else ng_char
        cuda_text = self._t("CUDA: Available") if CUDA_AVAILABLE else self._t("CUDA: Not available")
        ffmpeg_char = ok_char if FFMPEG_AVAILABLE else ng_char
        ffmpeg_text = self._t("FFmpeg: Available") if FFMPEG_AVAILABLE else self._t("FFmpeg: Not available")
        ttk.Label(header, text=f"{cuda_char} {cuda_text}").grid(row=0, column=2, sticky="e", padx=(5, 0))
        ttk.Label(header, text=f"{ffmpeg_char} {ffmpeg_text}").grid(row=0, column=3, sticky="e", padx=(5, 0))
        ttk.Button(header, text="Licenses", command=self.show_license).grid(row=0, column=4, sticky="e")
        # 高さ計算用に参照保持
        self.header = header
        row += 1

        # Toolbar（再生/設定アイコン）は機能重複のため削除

        # スクロール可能な2カラムメインコンテンツ領域
        scroll_container = ScrollableFrame(master)
        scroll_container.grid(row=row, column=0, sticky="nsew", padx=10, pady=5)
        master.rowconfigure(row, weight=1)
        scroll_container.inner.columnconfigure(0, weight=1)
        scroll_container.inner.rowconfigure(0, weight=1)
        # メイン領域の参照を保持
        self.scroll_container = scroll_container

        # PanedWindowをスクロール可能フレーム内に配置
        content = ttk.Panedwindow(scroll_container.inner, orient=tk.HORIZONTAL)
        content.grid(row=0, column=0, sticky="ew")
        self.content = content

        # 左カラム: Server Settings のみ（右カラムの高さに合わせて拡張）
        left_col = ttk.Frame(content)
        left_col.columnconfigure(0, weight=1)
        left_col.rowconfigure(0, weight=1)  # Server Settingsセクションが拡張可能
        server_frame = ttk.Labelframe(left_col, text="Server Settings")
        server_frame.grid(row=0, column=0, sticky="nsew")  # 縦方向にも拡張
        server_frame.columnconfigure(1, weight=1)
        config_frame = server_frame
        self.left_col = left_col
        self.server_frame = server_frame
        r = 0
        # Auto-start on top of Server Settings
        self.auto_start_chk = ttk.Checkbutton(config_frame, text="Auto-start API on launch", variable=self.auto_start)
        self.auto_start_chk.grid(row=r, column=0, columnspan=2, sticky=tk.W)
        r += 1
        # 1) 接続ポリシー（外部公開）
        self.allow_external_chk = ttk.Checkbutton(
            config_frame,
            text="Allow external connections (0.0.0.0)",
            variable=self.allow_external,
            command=self._toggle_allow_external,
        )
        self.allow_external_chk.grid(row=r, column=0, columnspan=2, sticky=tk.W)
        r += 1
        # 2) バックエンド接続先（ホスト/ポート）を横並びに配置
        ttk.Label(config_frame, text="Backend").grid(row=r, column=0, sticky=tk.W)
        be_row = ttk.Frame(config_frame)
        be_row.grid(row=r, column=1, sticky="ew")
        be_row.columnconfigure(1, weight=1, minsize=120)  # Backend Host入力欄の最低幅を120pxに設定
        # 参照保持（レスポンシブ再配置用）
        self.be_row = be_row
        self.be_host_label = ttk.Label(be_row, text="Host")
        self.be_host_label.grid(row=0, column=0, padx=(0, 4))
        self.backend_host_entry = ttk.Entry(be_row, textvariable=self.backend_host, width=18)
        self.backend_host_entry.grid(row=0, column=1, sticky="ew")
        self.be_port_label = ttk.Label(be_row, text="Port")
        self.be_port_label.grid(row=0, column=2, padx=(8, 4))
        self.backend_port_entry = ttk.Entry(be_row, textvariable=self.backend_port, width=8)
        self.backend_port_entry.grid(row=0, column=3, sticky=tk.W)
        r += 1
        # 3) API 接続先（ホスト/ポート）を横並びに配置
        ttk.Label(config_frame, text="API").grid(row=r, column=0, sticky=tk.W)
        api_row = ttk.Frame(config_frame)
        api_row.grid(row=r, column=1, sticky="ew")
        api_row.columnconfigure(1, weight=1, minsize=120)  # API Host入力欄の最低幅を120pxに設定
        # 参照保持（レスポンシブ再配置用）
        self.api_row = api_row
        self.api_host_label = ttk.Label(api_row, text="Host")
        self.api_host_label.grid(row=0, column=0, padx=(0, 4))
        self.api_host_entry = ttk.Entry(api_row, textvariable=self.api_host, width=18)
        self.api_host_entry.grid(row=0, column=1, sticky="ew")
        self.api_port_label = ttk.Label(api_row, text="Port")
        self.api_port_label.grid(row=0, column=2, padx=(8, 4))
        self.api_port_entry = ttk.Entry(api_row, textvariable=self.api_port, width=8)
        self.api_port_entry.grid(row=0, column=3, sticky=tk.W)
        r += 1
        # 4) 起動ポリシー（moved to top）
        # Security (API key)
        ttk.Separator(config_frame, orient="horizontal").grid(row=r, column=0, columnspan=2, sticky="ew", pady=(6, 6))
        r += 1
        ttk.Label(config_frame, text="Security", style="SectionHeader.TLabel").grid(row=r, column=0, columnspan=2, sticky=tk.W)
        r += 1
        self.api_key_chk = ttk.Checkbutton(
            config_frame,
            text="Require API key for Wrapper API",
            variable=self.use_api_key,
            command=self._update_api_key_widgets,
        )
        self.api_key_chk.grid(row=r, column=0, columnspan=2, sticky=tk.W)
        r += 1
        ttk.Label(config_frame, text="API key").grid(row=r, column=0, sticky=tk.W)
        api_row = ttk.Frame(config_frame)
        api_row.grid(row=r, column=1, sticky="ew")
        api_row.columnconfigure(0, weight=1)
        self.api_key_entry = ttk.Entry(api_row, textvariable=self.api_key, show="*")
        self.api_key_entry.grid(row=0, column=0, sticky="ew")
        self.api_key_show_chk = ttk.Checkbutton(api_row, text="Show", variable=self.api_key_show, command=self._update_api_key_widgets)
        self.api_key_show_chk.grid(row=0, column=1, padx=(6, 0))
        r += 1
        # 5) Model section header + selection
        ttk.Separator(config_frame, orient="horizontal").grid(row=r, column=0, columnspan=2, sticky="ew", pady=(6, 6))
        r += 1
        ttk.Label(config_frame, text="Model", style="SectionHeader.TLabel").grid(row=r, column=0, columnspan=2, sticky=tk.W)
        r += 1
        ttk.Label(config_frame, text="Whisper model").grid(row=r, column=0, sticky=tk.W)
        self.model_combo = ttk.Combobox(
            config_frame,
            textvariable=self.model,
            values=WHISPER_MODELS,
            state="readonly",
            width=20,
        )
        self.model_combo.grid(row=r, column=1, sticky="ew")
        r += 1
        # (Advanced Settings button was moved next to Hugging Face Login in Start/Stop row)
        r += 1
        # 6) VAD section
        ttk.Separator(config_frame, orient="horizontal").grid(row=r, column=0, columnspan=2, sticky="ew", pady=(6, 6))
        r += 1
        ttk.Label(config_frame, text="VAD", style="SectionHeader.TLabel").grid(row=r, column=0, columnspan=2, sticky=tk.W)
        r += 1
        self.vac_chk = ttk.Checkbutton(
            config_frame,
            text="Use voice activity controller (VAD)",
            variable=self.use_vac,
        )
        self.vac_chk.grid(row=r, column=0, columnspan=2, sticky=tk.W)
        r += 1
        # (VAD certificate moved into Advanced Settings dialog)
        r += 1
        # VAD Settings aligned to the right (enabled only if VAD is on)
        vad_row = ttk.Frame(config_frame)
        vad_row.grid(row=r, column=0, columnspan=2, sticky="ew")
        vad_row.columnconfigure(0, weight=1)
        self.vad_settings_btn = ttk.Button(vad_row, text="VAD Settings", command=self._open_vad_settings, bootstyle="info")
        self.vad_settings_btn.grid(row=0, column=1, sticky="e")
        r += 1
        # 7) Diarization section
        ttk.Separator(config_frame, orient="horizontal").grid(row=r, column=0, columnspan=2, sticky="ew", pady=(6, 6))
        r += 1
        ttk.Label(config_frame, text="Diarization", style="SectionHeader.TLabel").grid(row=r, column=0, columnspan=2, sticky=tk.W)
        r += 1
        # Hugging Face access token (top of section)
        ttk.Label(config_frame, text="Hugging Face access token").grid(row=r, column=0, sticky=tk.W)
        token_row = ttk.Frame(config_frame)
        token_row.grid(row=r, column=1, sticky="ew")
        token_row.columnconfigure(0, weight=1)
        self.hf_token_entry = ttk.Entry(token_row, textvariable=self.hf_token, show="*")
        self.hf_token_entry.grid(row=0, column=0, sticky="ew")
        self.hf_token_btn = ttk.Button(token_row, text="Validate", command=self._validate_hf_token, bootstyle="info")
        self.hf_token_btn.grid(row=0, column=1, padx=(4,0))
        r += 1
        self.diarization_chk = ttk.Checkbutton(
            config_frame,
            text="Enable diarization",
            variable=self.diarization,
            command=self._on_diarization_toggle,
            bootstyle="info",
        )
        self.diarization_chk.grid(row=r, column=0, columnspan=2, sticky=tk.W)
        # トークン未検証の間は無効化
        self.diarization_chk.config(state=tk.DISABLED)
        r += 1
        ttk.Label(config_frame, text="Segmentation model").grid(row=r, column=0, sticky=tk.W)
        self.seg_model_combo = ttk.Combobox(
            config_frame,
            textvariable=self.segmentation_model,
            values=SEGMENTATION_MODELS,
            width=20,
        )
        self.seg_model_combo.grid(row=r, column=1, sticky="ew")
        r += 1
        ttk.Label(config_frame, text="Embedding model").grid(row=r, column=0, sticky=tk.W)
        self.emb_model_combo = ttk.Combobox(
            config_frame,
            textvariable=self.embedding_model,
            values=EMBEDDING_MODELS,
            width=20,
        )
        self.emb_model_combo.grid(row=r, column=1, sticky="ew")
        r += 1
        # Diarization hint (English)
        self.hf_hint = ttk.Label(
            config_frame,
            text="Hugging Face login is required to enable diarization.",
            wraplength=460,
            justify="left",
        )
        self.hf_hint.grid(row=r, column=0, columnspan=2, sticky=tk.W)
        r += 1
        # Helpful links (token and model license pages)
        hf_links = ttk.Frame(config_frame)
        hf_links.grid(row=r, column=0, columnspan=2, sticky="ew")
        hf_links.columnconfigure(0, weight=1)
        # 左列の最低幅を十分に確保（潰れ防止）
        config_frame.columnconfigure(1, minsize=450)
        ttk.Button(
            hf_links,
            text="Get HF token",
            command=lambda: webbrowser.open("https://huggingface.co/settings/tokens"),
        ).pack(side="left", padx=(0, 6))
        ttk.Button(
            hf_links,
            text="pyannote/segmentation-3.0",
            command=lambda: webbrowser.open("https://huggingface.co/pyannote/segmentation-3.0"),
        ).pack(side="left", padx=(0, 6))
        ttk.Button(
            hf_links,
            text="pyannote/embedding",
            command=lambda: webbrowser.open("https://huggingface.co/pyannote/embedding"),
        ).pack(side="left")
        r += 1
        # Diarization Settings button を独立した行に配置（潰れ防止、右寄せ）
        diar_settings_frame = ttk.Frame(config_frame)
        diar_settings_frame.grid(row=r, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        diar_settings_frame.columnconfigure(0, weight=1)
        self.diar_settings_btn = ttk.Button(diar_settings_frame, text="Diarization Settings", command=self._open_diarization_settings, bootstyle="info")
        self.diar_settings_btn.grid(row=0, column=0, sticky="e")
        r += 1
        # 8) 起動/停止操作
        ttk.Separator(config_frame, orient="horizontal").grid(row=r, column=0, columnspan=2, sticky="ew", pady=(6, 6))
        r += 1
        # 左側ボタン群を独立した行に配置（重なり防止）
        left_actions_row = ttk.Frame(config_frame)
        left_actions_row.grid(row=r, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        self.manage_models_btn = ttk.Button(left_actions_row, text="Manage models", command=self._open_model_manager)
        self.manage_models_btn.pack(side="left", padx=(0, 6))
        # Advanced Settings button
        self.adv_btn = ttk.Button(left_actions_row, text="Advanced Settings", command=self._open_backend_settings)
        self.adv_btn.pack(side="left")
        r += 1

        # 可変スペース（ウィンドウ高さに応じて拡張）
        config_frame.rowconfigure(r, weight=1)
        r += 1

        # API Start/Stopボタン（サーバー設定の最下部、中央揃え・横並び・等分）
        api_control_row = ttk.Frame(config_frame)
        api_control_row.grid(row=r, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        api_control_row.columnconfigure(0, weight=1, uniform="api")
        api_control_row.columnconfigure(1, weight=1, uniform="api")

        self.start_btn = ttk.Button(
            api_control_row,
            text="🚀 Start API",
            command=self.start_api,
            bootstyle="success",
            style="ApiStart.TButton",
        )
        self.start_btn.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        self.stop_btn = ttk.Button(
            api_control_row,
            text="🛑 Stop API",
            command=self.stop_api,
            bootstyle="danger",
            style="ApiStop.TButton",
        )
        self.stop_btn.grid(row=0, column=1, sticky="ew", padx=(6, 0))

        # 右カラム: Endpoints + Recorder + Logs（PanedWindow右ペイン）
        right_panel = ttk.Frame(content)
        right_panel.columnconfigure(0, weight=1)
        right_panel.rowconfigure(1, weight=2)  # Recorderセクションが拡張可能
        right_panel.rowconfigure(2, weight=1)  # Logsセクション（Recorderの約半分）
        self.right_panel = right_panel

        # Endpointsを右カラムの上部に移動（1行固定・サブフレームでエントリとボタンを並べる）
        endpoints_frame = ttk.Labelframe(right_panel, text="Endpoints")
        endpoints_frame.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        endpoints_frame.columnconfigure(1, weight=1)  # 右列（サブフレーム）を伸縮
        self.endpoints_frame = endpoints_frame
        er = 0
        # Backend Web UI
        ttk.Label(endpoints_frame, text="Backend Web UI").grid(row=er, column=0, sticky=tk.W)
        web_row = ttk.Frame(endpoints_frame)
        web_row.grid(row=er, column=1, sticky="ew")
        web_row.columnconfigure(0, weight=1)
        # 右カラムの最小幅を抑えるため、Entryはやや短めに
        self.web_endpoint_entry = ttk.Entry(web_row, textvariable=self.web_endpoint, width=30, state="readonly")
        self.web_endpoint_entry.grid(row=0, column=0, sticky="ew")
        self.open_web_btn = ttk.Button(web_row, text="Open Web GUI", command=self.open_web_gui, state=tk.DISABLED)
        self.open_web_btn.grid(row=0, column=1, padx=(6,0), sticky="e")
        er += 1
        # Streaming WebSocket
        ttk.Label(endpoints_frame, text="Streaming WebSocket /asr").grid(row=er, column=0, sticky=tk.W)
        ws_row = ttk.Frame(endpoints_frame)
        ws_row.grid(row=er, column=1, sticky="ew")
        ws_row.columnconfigure(0, weight=1)
        self.ws_endpoint_entry = ttk.Entry(ws_row, textvariable=self.ws_endpoint, width=30, state="readonly")
        self.ws_endpoint_entry.grid(row=0, column=0, sticky="ew")
        self.copy_ws_btn = ttk.Button(ws_row, text="Copy", command=lambda: self._copy_with_feedback(self.copy_ws_btn, self.ws_endpoint.get()))
        self.copy_ws_btn.grid(row=0, column=1, padx=(6,0), sticky="e")
        er += 1
        # File transcription API
        ttk.Label(endpoints_frame, text="File transcription API").grid(row=er, column=0, sticky=tk.W)
        api_row = ttk.Frame(endpoints_frame)
        api_row.grid(row=er, column=1, sticky="ew")
        api_row.columnconfigure(0, weight=1)
        self.api_endpoint_entry = ttk.Entry(api_row, textvariable=self.api_endpoint, width=30, state="readonly")
        self.api_endpoint_entry.grid(row=0, column=0, sticky="ew")
        self.copy_api_btn = ttk.Button(api_row, text="Copy", command=lambda: self._copy_with_feedback(self.copy_api_btn, self.api_endpoint.get()))
        self.copy_api_btn.grid(row=0, column=1, padx=(6,0), sticky="e")
        er += 1
        note_font = font.Font(size=8)
        self.endpoints_note_label = ttk.Label(
            endpoints_frame,
            text="※16kHz モノラル (wav, raw) 形式での入力を推奨",
            font=note_font,
        )
        self.endpoints_note_label.grid(row=er, column=0, columnspan=2, sticky=tk.W)
        
        record_frame = ttk.Labelframe(right_panel, text="Recorder")
        # Endpointsの下に配置、縦に拡張
        record_frame.grid(row=1, column=0, sticky="nsew")
        record_frame.columnconfigure(1, weight=1)
        self.record_frame = record_frame
        # Recording controls
        r = 0
        self.record_btn = ttk.Button(record_frame, text="Start Recording", command=self.toggle_recording)
        self.record_btn.grid(row=r, column=0, sticky=tk.W)
        # 録音時間はボタンの右隣に大きく表示
        self.timer_label = ttk.Label(record_frame, textvariable=self.timer_var, style="Timer.TLabel")
        self.timer_label.grid(row=r, column=1, sticky=tk.W, padx=(8, 0))
        r += 1
        # サーバー未起動時のガイダンス（録音ボタン直下）
        self.record_hint_label = ttk.Label(
            record_frame,
            text=self._t("Server is not running. Please press Start API before recording."),
            justify="left",
        )
        self.record_hint_label.grid(row=r, column=0, columnspan=3, sticky="ew", pady=(0, 2))
        
        # 動的な折り返し調整のため、wraplengthを親フレーム幅に合わせて更新
        def _update_wraplength():
            try:
                width = record_frame.winfo_width()
                if width > 1:  # ウィンドウが実際にレンダリングされている場合のみ
                    self.record_hint_label.configure(wraplength=max(width - 40, 200))
            except:
                pass
        
        # 初期設定と定期更新
        record_frame.after(100, _update_wraplength)
        record_frame.bind('<Configure>', lambda e: _update_wraplength())
        r += 1
        ttk.Progressbar(record_frame, variable=self.level_var, maximum=1.0).grid(row=r, column=0, columnspan=3, sticky="ew")
        r += 1
        # Transcript area inside Recorder (moved above Save options)
        trans_frame = ttk.Labelframe(record_frame, text="Transcript")
        trans_frame.grid(row=r, column=0, columnspan=3, sticky="nsew", pady=(5,0))
        trans_frame.columnconfigure(0, weight=1)
        trans_frame.rowconfigure(0, weight=1)
        record_frame.rowconfigure(r, weight=1)
        self.transcript_box = tk.Text(trans_frame, state="disabled")
        try:
            self.transcript_box.configure(font=("Segoe UI", 12))
        except Exception:
            pass
        # ダークテーマに合わせて Text の配色を調整
        try:
            self.transcript_box.configure(bg=self._bg, fg=self._fg, insertbackground=self._fg)
        except Exception:
            pass
        self.transcript_box.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(trans_frame, orient="vertical", command=self.transcript_box.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.transcript_box.configure(yscrollcommand=scroll.set)
        r += 1
        # Save options within Recorder
        self.save_enabled_chk = ttk.Checkbutton(record_frame, text="Save transcript to file", variable=self.save_enabled, command=self._update_save_widgets)
        self.save_enabled_chk.grid(row=r, column=0, columnspan=2, sticky=tk.W)
        r += 1
        ttk.Label(record_frame, text="Save path").grid(row=r, column=0, sticky=tk.W)
        self.save_entry = ttk.Entry(record_frame, textvariable=self.save_path)
        self.save_entry.grid(row=r, column=1, sticky="ew")
        self.save_browse_btn = ttk.Button(record_frame, text="Browse", command=self.choose_save_path)
        self.save_browse_btn.grid(row=r, column=2, padx=5)
        r += 1

        # --- Logs panel (右カラムの最下段) ---
        log_panel = ttk.Frame(right_panel)
        log_panel.columnconfigure(0, weight=1)
        log_panel.rowconfigure(0, weight=1)
        log_panel.grid(row=2, column=0, sticky="nsew", pady=(5,0))
        log_frame = ttk.Labelframe(log_panel, text="Logs")
        log_frame.grid(row=0, column=0, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        # ログ欄は最低4行を維持しつつ、ウィンドウ高さに応じて拡縮
        self.log_text = tk.Text(log_frame, state="disabled", wrap="none", height=6)
        try:
            self.log_text.configure(bg=self._bg, fg=self._fg, insertbackground=self._fg)
        except Exception:
            pass
        self.log_text.grid(row=0, column=0, sticky="nsew")
        log_scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        log_scroll.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=log_scroll.set)
        log_note_font = font.nametofont("TkDefaultFont").copy()
        try:
            log_note_font.configure(size=8)
        except Exception:
            pass
        # 備考ラベルは参照を保持（高さ計算用）
        self.log_note_label = ttk.Label(
            log_frame,
            text=self._t(
                "This console is for log output only and cannot be used as a CLI.",
            ),
            font=log_note_font,
        )
        self.log_note_label.grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 0))
        try:
            self.log_text.tag_configure("backend", foreground="#8ec07c")
            self.log_text.tag_configure("api", foreground="#83a598")
            self.log_text.tag_configure("stderr", foreground="#fb4934")
        except Exception:
            pass

        # ログ欄の最小高さを設定（4行分）
        try:
            line_h = font.Font(font=self.log_text.cget("font")).metrics("linespace")
            min_log_h = line_h * 4 + 10
            log_panel.rowconfigure(0, weight=1, minsize=min_log_h)
            right_panel.rowconfigure(2, weight=1, minsize=min_log_h)
        except Exception:
            pass

        self.backend_proc: subprocess.Popen | None = None
        self.api_proc: subprocess.Popen | None = None
        self._log_threads: list[threading.Thread] = []

        self._update_diarization_fields()
        self._update_hf_token_widgets()
        self._update_api_key_widgets()

        for var in [self.backend_host, self.backend_port, self.api_host, self.api_port]:
            var.trace_add("write", self.update_endpoints)
        # Update endpoints also when external toggle changes
        self.allow_external.trace_add("write", self.update_endpoints)
        # Save enable toggle should update widgets
        self.save_enabled.trace_add("write", lambda *_: self._update_save_widgets())
        self.vad_certfile.trace_add("write", lambda *_: self._update_vad_state())
        self.use_vac.trace_add("write", lambda *_: self._update_vad_state())
        self.update_endpoints()
        # Apply initial save widgets state
        self._update_save_widgets()
        self._update_vad_state()
        self.api_key_show.trace_add("write", lambda *_: self._update_api_key_widgets())
        # reflect token widgets state on startup
        self._update_hf_token_widgets()
        self.use_api_key.trace_add("write", lambda *_: self._update_api_key_widgets())
        # Normalize saved string choices to avoid invalid values in readonly combos
        try:
            self._normalize_saved_choices()
        except Exception:
            pass

        master.protocol("WM_DELETE_WINDOW", self.on_close)
        # Initialize external toggle effect
        self._apply_allow_external_initial()
        # Ensure initial lock state reflects not running
        self._set_running_state(False)
        # Async check of HF login state
        threading.Thread(target=self._init_check_hf_login, daemon=True).start()
        # 固定2カラムレイアウトを適用し、最小サイズを設定
        self.master.after(0, self._apply_fixed_layout)
        self.master.after(50, self._lock_minsize_by_content)
        # PanedWindow に左右ペインを追加（左:固定、右:拡張）
        try:
            # 左を広めに確保（縮小/拡張の配分で左優先）
            self.content.add(self.left_col, weight=2)
            self.content.add(self.right_panel, weight=1)
        except Exception:
            pass
        # 左右の比率固定は廃止（ユーザーのリサイズに任せる）
        self._localize_widgets()
        # 左右ペインの最小幅を固定（動的変更は行わず潰れを防止）
        try:
            self.content.paneconfigure(self.left_col, minsize=800)
            # 右ペインの最小幅を少し狭める
            self.content.paneconfigure(self.right_panel, minsize=360)
        except Exception:
            pass

    def _t(self, text: str) -> str:
        return self._translations.get(text, text)

    def _localize_widgets(self) -> None:
        if not self._translations:
            return

        def apply(widget: tk.Widget) -> None:
            try:
                txt = widget.cget("text")
                if txt in self._translations:
                    widget.config(text=self._translations[txt])
            except Exception:
                pass
            for child in widget.winfo_children():
                apply(child)

        apply(self.master)

    def _apply_fixed_layout(self) -> None:
        # PanedWindow を用いた固定2カラム（左右同高さ）配置
        try:
            self.master.update_idletasks()
        except Exception:
            pass
        self._lock_minsize_by_content()
        # 初期サッシュ位置を左寄りに（右をやや狭める）
        try:
            w = self.content.winfo_width()
            if w <= 1:
                # レイアウトが確定していない場合は再試行し、左ペインが消えるのを防ぐ
                self.master.after(50, self._apply_fixed_layout)
                return
            # 左約62%, 右約38%
            self.content.sashpos(0, int(w * 0.62))
        except Exception:
            pass

    # 左右ペイン比率の固定ロジックは撤廃

    def _lock_minsize_by_content(self) -> None:
        # スクロール対応：最小サイズのみ設定し、縦方向リサイズを許可
        root = self.master
        try:
            root.update_idletasks()
            # 横幅の最小幅を設定（左右ペインの最小幅を合算し、少し余白）
            # 左800 + 右360 ≒ 1160 → 1200を下限に設定
            min_w = 1200
            min_h = 800  # 縦方向の最小高さを設定（スクロール可能）
            # 最小サイズのみ設定（固定サイズは設定しない）
            root.minsize(min_w, min_h)
            try:
                # 最大サイズ制限を削除（縦方向も自由にリサイズ可能）
                root.maxsize(100000, 100000)
            except Exception:
                pass
            try:
                root.resizable(True, True)
            except Exception:
                pass
        except Exception:
            pass

    # （横幅制約の実装は撤廃）

    # 高さキャップは撤廃（Recorder は右ペインの全高を使用）

    # --- ログ表示ユーティリティ ---
    def _append_log(self, source: str, text: str, is_stderr: bool = False) -> None:
        try:
            tag = None
            if is_stderr:
                tag = "stderr"
            else:
                if source == "backend":
                    tag = "backend"
                elif source == "api":
                    tag = "api"
            self.log_text.configure(state="normal")
            if tag:
                self.log_text.insert("end", text, tag)
            else:
                self.log_text.insert("end", text)
            # 軽いトリミング（過剰肥大の防止）
            try:
                if int(self.log_text.index('end-1c').split('.')[0]) > 2000:
                    self.log_text.delete('1.0', '200.0')
            except Exception:
                pass
            self.log_text.see("end")
            self.log_text.configure(state="disabled")
        except Exception:
            pass

    def _start_log_reader(self, proc: subprocess.Popen, source: str) -> None:
        if proc.stdout is None or proc.stderr is None:
            return
        def _read_stream(stream, is_stderr: bool = False):
            try:
                for line in iter(stream.readline, ''):
                    if not line:
                        break
                    print(
                        line,
                        end="",
                        file=sys.stderr if is_stderr else sys.stdout,
                        flush=True,
                    )
                    self.master.after(0, self._append_log, source, line, is_stderr)
            except Exception:
                pass
        t_out = threading.Thread(target=_read_stream, args=(proc.stdout, False), daemon=True)
        t_err = threading.Thread(target=_read_stream, args=(proc.stderr, True), daemon=True)
        t_out.start(); t_err.start()
        self._log_threads.extend([t_out, t_err])

    # 左カラムの二段化ロジックは廃止（最小幅で保護）

    # 右側エンドポイントは1行固定（サブフレーム内でボタン/エントリを横並び）

    def start_api(self):
        if self.api_proc or self.backend_proc:
            return
        # 起動前の依存関係チェック（VAD/話者分離など可否を事前確認）
        if not self._check_runtime_dependencies():
            return
        missing: list[str] = []
        model = self.model.get().strip()
        # For SimulStreaming, backend downloads weights itself; skip HF snapshot prefetch
        backend_choice = self.backend.get().strip()
        if model and backend_choice != "simulstreaming":
            # For faster-whisper backend, ensure CT2 weights are cached
            if backend_choice == "faster-whisper":
                if not model_manager.is_model_downloaded(model, backend="faster-whisper"):
                    missing.append(model)
            else:
                if not model_manager.is_model_downloaded(model):
                    missing.append(model)
        if self.diarization.get() and self.hf_logged_in:
            seg = self.segmentation_model.get().strip()
            if seg and not model_manager.is_model_downloaded(seg):
                missing.append(seg)
            emb = self.embedding_model.get().strip()
            if emb and not model_manager.is_model_downloaded(emb):
                missing.append(emb)
        if self.use_vac.get() and not model_manager.is_model_downloaded(model_manager.VAD_REPO):
            missing.append(model_manager.VAD_REPO)
        if missing:
            self.start_btn.config(state=tk.DISABLED)
            self._download_and_start(missing)
            return
        self._launch_server()

    def _download_and_start(self, models: list[str]) -> None:
        def worker() -> None:
            try:
                backend_choice = self.backend.get().strip()
                for m in models:
                    label = f"{self._t('Downloading')} {m}"
                    self.master.after(0, lambda l=label: self.status_var.set(l))
                    # If current backend is faster-whisper and target is a Whisper size name,
                    # download the CTranslate2 weights instead of openai/whisper.
                    if backend_choice == "faster-whisper" and m in WHISPER_MODELS:
                        model_manager.download_model(m, backend="faster-whisper")
                    else:
                        model_manager.download_model(m)
                self.master.after(0, self._on_download_success)
            except Exception as e:  # pragma: no cover - GUI display
                self.master.after(0, lambda err=e: self.status_var.set(f"{self._t('Download failed:')} {err}"))
                self.master.after(0, lambda: self.start_btn.config(state=tk.NORMAL))

        threading.Thread(target=worker, daemon=True).start()

    def _on_download_success(self) -> None:
        self.status_var.set(self._t("Download complete"))
        self._launch_server()

    def _launch_server(self) -> None:
        b_host = self.backend_host.get()
        b_port = self.backend_port.get()
        a_host = self.api_host.get()
        a_port = self.api_port.get()

        env = os.environ.copy()
        env["WRAPPER_BACKEND_HOST"] = b_host
        env["WRAPPER_BACKEND_PORT"] = b_port
        env["WRAPPER_API_HOST"] = a_host
        env["WRAPPER_API_PORT"] = a_port
        env["HUGGINGFACE_HUB_CACHE"] = str(model_manager.HF_CACHE_DIR)
        env["TORCH_HOME"] = str(model_manager.TORCH_CACHE_DIR)
        # Ensure child Python processes flush output immediately so logs appear in real time
        env["PYTHONUNBUFFERED"] = "1"
        # Propagate Hugging Face token to backend process if available
        try:
            token: str | None = None
            # Prefer token from system keyring when available
            if self._keyring_available():
                token = self._keyring_get_token()
            # Fallback to GUI entry (avoid masked placeholder)
            if not token:
                t = (self.hf_token.get() or "").strip()
                if t and t != "********":
                    token = t
            # Fallback to huggingface_hub stored token
            if not token:
                try:
                    from huggingface_hub import HfFolder  # type: ignore
                    token = HfFolder.get_token()
                except Exception:
                    token = None
            # Fallback to pre-set environment
            if not token:
                for k in ("HUGGING_FACE_HUB_TOKEN", "HUGGINGFACEHUB_API_TOKEN", "HF_TOKEN"):
                    if os.getenv(k):
                        token = os.getenv(k)
                        break
            if token:
                # Set common aliases used by huggingface_hub/pyannote
                env["HUGGING_FACE_HUB_TOKEN"] = token
                env["HUGGINGFACEHUB_API_TOKEN"] = token
                env["HF_TOKEN"] = token
                # Also persist token to huggingface_hub store if not already present,
                # because some libs pass use_auth_token=True which reads from HfFolder.
                try:
                    from huggingface_hub import HfFolder, login as hf_login  # type: ignore
                    if not HfFolder.get_token():
                        hf_login(token=token, add_to_git_credential=False)
                except Exception:
                    pass
        except Exception:
            pass
        cert = self.vad_certfile.get().strip()
        if cert and Path(cert).is_file():
            env["SSL_CERT_FILE"] = cert
        # Fallback: if no SSL_CERT_FILE is provided, try to use certifi CA bundle
        if "SSL_CERT_FILE" not in env:
            try:
                import certifi  # type: ignore
                env["SSL_CERT_FILE"] = certifi.where()
            except Exception:
                pass

        backend_cmd = [
            sys.executable,
            "-u",
            "-m",
            "whisperlivekit.basic_server",
            "--host",
            b_host,
            "--port",
            b_port,
        ]
        # Share wrapper-managed cache directory with backend for consistency
        backend_cmd += ["--model_cache_dir", str(model_manager.HF_CACHE_DIR)]
        model = self.model.get().strip()
        if model:
            # SimulStreaming expects a model name (e.g. 'large-v3') or a --model-path
            # pointing to '<dir>/<name>.pt' so that load_model(name=<name>, download_root=<dir>) works.
            if self.backend.get().strip() == "simulstreaming":
                cache_dir = str(model_manager.HF_CACHE_DIR)
                backend_cmd += ["--model", model]
                backend_cmd += ["--model-path", str(Path(cache_dir) / f"{model}.pt")]
            else:
                # Other backends can consume a local snapshot directory
                if self.backend.get().strip() == "faster-whisper":
                    backend_cmd += ["--model_dir", str(model_manager.get_model_path(model, backend="faster-whisper"))]
                else:
                    backend_cmd += ["--model_dir", str(model_manager.get_model_path(model))]
        if self.diarization.get() and self.hf_logged_in:
            backend_cmd.append("--diarization")
            seg = self.segmentation_model.get().strip()
            if seg:
                backend_cmd += ["--segmentation-model", seg]
            emb = self.embedding_model.get().strip()
            if emb:
                backend_cmd += ["--embedding-model", emb]
            db = self.diarization_backend.get().strip()
            if db:
                backend_cmd += ["--diarization-backend", db]

        warm = self.warmup_file.get().strip()
        if warm:
            backend_cmd += ["--warmup-file", warm]
        if self.confidence_validation.get():
            backend_cmd.append("--confidence-validation")
        if self.punctuation_split.get():
            backend_cmd.append("--punctuation-split")
        backend_cmd += ["--min-chunk-size", str(self.min_chunk_size.get())]
        backend_cmd += ["--language", self.language.get()]
        backend_cmd += ["--task", self.task.get()]
        backend_cmd += ["--backend", self.backend.get()]

        # Disable VAC by default unless explicitly enabled to prevent torch.hub GitHub SSL failures
        if self.use_vac.get():
            backend_cmd += ["--vac-chunk-size", str(self.vac_chunk_size.get())]
        else:
            backend_cmd.append("--no-vac")

        backend_cmd += ["--buffer_trimming", self.buffer_trimming.get()]
        backend_cmd += ["--buffer_trimming_sec", str(self.buffer_trimming_sec.get())]
        backend_cmd += ["--log-level", self.log_level.get()]
        certfile = self.ssl_certfile.get().strip()
        if certfile:
            backend_cmd += ["--ssl-certfile", certfile]
        keyfile = self.ssl_keyfile.get().strip()
        if keyfile:
            backend_cmd += ["--ssl-keyfile", keyfile]
        backend_cmd += ["--frame-threshold", str(self.frame_threshold.get())]

        # Launch backend with propagated environment (includes HF token/cache paths)
        self.backend_proc = subprocess.Popen(
            backend_cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        try:
            self._start_log_reader(self.backend_proc, "backend")
        except Exception:
            pass
        # 自動でブラウザは開かない（必要なら Endpoints の "Open Web GUI" ボタンから開く）
        time.sleep(2)

        # API key settings for wrapper API
        use_key = bool(self.use_api_key.get()) and bool(self.api_key.get().strip())
        env["WRAPPER_REQUIRE_API_KEY"] = "1" if use_key else "0"
        if use_key:
            env["WRAPPER_API_KEY"] = self.api_key.get().strip()

        # Inform API server whether backend uses SSL (for ws/wss selection)
        env["WRAPPER_BACKEND_SSL"] = (
            "1" if (bool(self.ssl_certfile.get().strip()) and bool(self.ssl_keyfile.get().strip())) else "0"
        )

        self.api_proc = subprocess.Popen(
            [
                sys.executable,
                "-u",
                "-m",
                "uvicorn",
                "wrapper.api.server:app",
                "--host",
                a_host,
                "--port",
                a_port,
            ],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        try:
            self._start_log_reader(self.api_proc, "api")
        except Exception:
            pass
        self._set_running_state(True)

    def stop_api(self):
        try:
            self._append_log("gui", "Stopping processes...\n")
        except Exception:
            pass
        for proc in [self.api_proc, self.backend_proc]:
            if proc and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
        self.api_proc = None
        self.backend_proc = None
        self._set_running_state(False)

    def on_close(self):
        self.stop_api()
        self._save_settings()
        self.master.destroy()

    def _check_runtime_dependencies(self) -> bool:
        """Perform a simple check that required dependencies for enabled features are present.
        If any are missing, show a message and cancel startup.
        """
        problems: list[str] = []
        suggestions: list[str] = []

        # ffmpeg is used by the API for audio conversion.
        try:
            import shutil as _shutil  # noqa: F401
            if shutil.which("ffmpeg") is None:
                problems.append("ffmpeg not found (not on PATH).")
                suggestions.append("macOS: brew install ffmpeg / Windows: choco install ffmpeg, etc")
        except Exception:
            pass

        # torchaudio is required when VAD (VAC) is enabled
        if self.use_vac.get():
            try:
                import torchaudio  # type: ignore  # noqa: F401
            except Exception:
                try:
                    import torch  # type: ignore
                    torch_ver = getattr(torch, "__version__", "<torch_version>")
                except Exception:
                    torch_ver = "<torch_version>"
                problems.append("torchaudio is required to enable VAD.")
                suggestions.append(f"pip install torchaudio=={torch_ver}")

        # Dependencies for diarization
        if self.diarization.get():
            backend = self.diarization_backend.get().strip()
            if backend == "sortformer":
                if not SORTFORMER_AVAILABLE:
                    problems.append("Sortformer backend requires CUDA and NVIDIA NeMo.")
                    suggestions.append('pip install "git+https://github.com/NVIDIA/NeMo.git@main#egg=nemo_toolkit[asr]"')
            elif backend == "diart":
                try:
                    import diart  # type: ignore  # noqa: F401
                except Exception:
                    problems.append("Diart backend requires diart.")
                    suggestions.append("pip install diart pyannote.audio rx")

        if problems:
            try:
                from tkinter import messagebox as _mb
                msg = "\n".join(["\u26a0\ufe0f Cannot start due to missing dependencies:"] + problems)
                if suggestions:
                    msg += "\n\nInstallation examples:\n- " + "\n- ".join(suggestions)
                _mb.showerror("Missing dependencies", msg)
            except Exception:
                pass
            # ステータス表示も更新
            self.status_var.set(self._t("stopped"))
            return False
        return True

    def _setup_autosave(self) -> None:
        """Attach traces to main Tk variables for automatic saving."""
        vars_to_watch: list[tk.Variable] = [
            self.backend_host,
            self.backend_port,
            self.api_host,
            self.api_port,
            self.auto_start,
            self.allow_external,
            self.model,
            self.use_api_key,
            self.api_key,
            self.use_vac,
            self.vad_certfile,
            self.diarization,
            self.segmentation_model,
            self.embedding_model,
            self.warmup_file,
            self.confidence_validation,
            self.punctuation_split,
            self.diarization_backend,
            self.min_chunk_size,
            self.language,
            self.task,
            self.backend,
            self.vac_chunk_size,
            self.buffer_trimming,
            self.buffer_trimming_sec,
            self.log_level,
            self.ssl_certfile,
            self.ssl_keyfile,
            self.frame_threshold,
            self.save_path,
            self.save_enabled,
            self.theme,
        ]

        def _autosave(*_args):  # pragma: no cover - UI event
            try:
                self._save_settings()
            except Exception:
                pass

        for v in vars_to_watch:
            try:
                v.trace_add("write", _autosave)
            except Exception:
                pass

    def available_diarization_backends(self) -> list[str]:
        backs = ["diart"]
        if SORTFORMER_AVAILABLE:
            backs.insert(0, "sortformer")
        return backs

    def available_backends(self) -> list[str]:
        """Selectable ASR backend implementations for the upstream server."""
        # 現状の想定バックエンド（実装分岐あり）
        return [
            "simulstreaming",
            "faster-whisper",
        ]

    def available_tasks(self) -> list[str]:
        return ["transcribe", "translate"]

    def available_log_levels(self) -> list[str]:
        return ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

    def available_languages(self) -> list[str]:
        """Common language codes plus 'auto'."""
        return [
            "auto",
            "en",  # English
            "ja",  # Japanese
            "zh",  # Chinese (generic)
            "ko",  # Korean
            "fr",  # French
            "de",  # German
            "es",  # Spanish
            "it",  # Italian
            "pt",  # Portuguese
            "ru",  # Russian
            "hi",  # Hindi
            "th",  # Thai
            "vi",  # Vietnamese
            "ar",  # Arabic
            "id",  # Indonesian
            "nl",  # Dutch
            "pl",  # Polish
            "tr",  # Turkish
            "uk",  # Ukrainian
        ]

    def _normalize_saved_choices(self) -> None:
        """Normalize saved string choices to known sets with safe fallbacks."""
        try:
            lv = (self.log_level.get() or "").strip().upper()
            if lv not in self.available_log_levels():
                lv = "DEBUG"
            self.log_level.set(lv)
        except Exception:
            pass
        try:
            be = (self.backend.get() or "").strip()
            if be not in self.available_backends():
                be = "simulstreaming"
            self.backend.set(be)
        except Exception:
            pass
        try:
            task = (self.task.get() or "").strip()
            if task not in self.available_tasks():
                task = "transcribe"
            self.task.set(task)
        except Exception:
            pass
        try:
            buf = (self.buffer_trimming.get() or "").strip()
            if buf not in ("segment", "sentence"):
                buf = "segment"
            self.buffer_trimming.set(buf)
        except Exception:
            pass

    def _update_api_key_widgets(self) -> None:
        # Lock API key controls while running or recording; enable only when Use API key is ON
        running = self.api_proc is not None or self.backend_proc is not None
        locked = running or bool(self.is_recording)
        try:
            self.api_key_chk.config(state=(tk.DISABLED if locked else tk.NORMAL))
        except Exception:
            pass
        state = tk.NORMAL if (self.use_api_key.get() and not locked) else tk.DISABLED
        try:
            self.api_key_entry.config(state=state)
        except Exception:
            pass
        # show/hide checkbox mirrors the entry state
        try:
            self.api_key_show_chk.config(state=state)
        except Exception:
            pass
        # Apply masking based on checkbox
        try:
            self.api_key_entry.config(show=("" if self.api_key_show.get() else "*"))
        except Exception:
            pass

    def copy_to_clipboard(self, text: str) -> None:
        self.master.clipboard_clear()
        self.master.clipboard_append(text)

    def _copy_with_feedback(self, btn: ttk.Button, text: str) -> None:
        """After copying, temporarily change the button to provide feedback."""
        try:
            self.copy_to_clipboard(text)
        except Exception:
            return
        # 現在の表示を保持
        prev_text = btn.cget("text")
        prev_state = btn.cget("state")
        prev_style = None
        try:
            prev_style = btn.cget("bootstyle")
        except Exception:
            prev_style = None
        # フィードバック表示
        try:
            btn.config(text=self._t("Copied!"), state=tk.DISABLED)
            try:
                btn.config(bootstyle="success")
            except Exception:
                pass
        except Exception:
            pass
        # 一定時間後に元に戻す
        def _restore():
            try:
                btn.config(text=prev_text, state=prev_state)
                if prev_style is not None:
                    btn.config(bootstyle=prev_style)
            except Exception:
                pass
        self.master.after(1200, _restore)

    def choose_save_path(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if path:
            self.save_path.set(path)

    def _open_backend_settings(self) -> None:
        # 稼働中/録音中は設定変更不可（ダイアログを開かない）
        if (self.api_proc is not None or self.backend_proc is not None) or self.is_recording:
            try:
                messagebox.showinfo(self._t("Settings locked"), self._t("Stop API before changing settings."))
            except Exception:
                pass
            return
        BackendSettingsDialog(self.master, self)

    def _open_vad_settings(self) -> None:
        if (self.api_proc is not None or self.backend_proc is not None) or self.is_recording:
            try:
                messagebox.showinfo(self._t("Settings locked"), self._t("Stop API before changing VAD settings."))
            except Exception:
                pass
            return
        VADSettingsDialog(self.master, self)

    def _open_diarization_settings(self) -> None:
        if (self.api_proc is not None or self.backend_proc is not None) or self.is_recording:
            try:
                messagebox.showinfo(self._t("Settings locked"), self._t("Stop API before changing diarization settings."))
            except Exception:
                pass
            return
        DiarizationSettingsDialog(self.master, self)

    def choose_vad_certfile(self) -> None:
        path = filedialog.askopenfilename(
            filetypes=[
                ("Certificate files", "*.pem *.crt *.cer"),
                ("All files", "*.*"),
            ]
        )
        if path:
            self.vad_certfile.set(path)

    def update_endpoints(self, *_: object) -> None:
        b_host = self.backend_host.get()
        b_port = self.backend_port.get()
        a_host = self.api_host.get()
        a_port = self.api_port.get()
        # In external mode, show LAN IP for convenience
        display_b_host = b_host
        display_a_host = a_host
        if self.allow_external.get():
            ips = self._get_local_ips()
            if ips:
                display_b_host = ips[0]
                display_a_host = ips[0]
        # HTTPS/WSS if SSL cert+key specified for backend
        use_ssl = bool(self.ssl_certfile.get().strip()) and bool(self.ssl_keyfile.get().strip())
        http_scheme = "https" if use_ssl else "http"
        ws_scheme = "wss" if use_ssl else "ws"
        self.web_endpoint.set(f"{http_scheme}://{display_b_host}:{b_port}/")
        ws = f"{ws_scheme}://{display_b_host}:{b_port}/asr"
        self.ws_endpoint.set(ws)
        # Recorder follows the backend WebSocket endpoint
        self.ws_url.set(ws)
        # Wrapper API (this process) runs without SSL; keep http
        self.api_endpoint.set(f"http://{display_a_host}:{a_port}/v1/audio/transcriptions")
        # Note: in external mode, endpoints already display LAN IPs directly

    def open_web_gui(self) -> None:
        url = self.web_endpoint.get()
        try:
            webbrowser.open(url)
        except Exception:
            pass

    def show_license(self) -> None:
        """Display project and third-party licenses per library with full text.

        左にライブラリ一覧、右に選択項目のライセンス本文を表示する。
        """
        top = tk.Toplevel(self.master)
        top.title("Licenses")
        top.geometry("960x600")

        # ルート横分割
        paned = ttk.Panedwindow(top, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        # 左: ライブラリ一覧
        left = ttk.Frame(paned)
        left.columnconfigure(0, weight=1)
        left.rowconfigure(1, weight=1)
        ttk.Label(left, text=self._t("License"), style="SectionHeader.TLabel").grid(row=0, column=0, sticky="w", padx=6, pady=(6, 2))
        listbox = tk.Listbox(left, activestyle="dotbox")
        listbox.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 6))
        lb_scroll = ttk.Scrollbar(left, orient="vertical", command=listbox.yview)
        lb_scroll.grid(row=1, column=1, sticky="ns", pady=(0, 6))
        listbox.configure(yscrollcommand=lb_scroll.set)

        # 右: ライセンス本文
        right = ttk.Frame(paned)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)
        text = tk.Text(right, wrap="word", state="disabled")
        text.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(right, orient="vertical", command=text.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        text.configure(yscrollcommand=scroll.set)
        # テーマカラーに合わせて配色
        try:
            text.configure(bg=self._bg, fg=self._fg, insertbackground=self._fg)
        except Exception:
            pass

        # 下: リンク/操作
        bottom = ttk.Frame(top)
        bottom.pack(fill=tk.X, padx=6, pady=6)
        ttk.Button(
            bottom,
            text="QuentinFuxa/WhisperLiveKit",
            command=lambda: webbrowser.open("https://github.com/QuentinFuxa/WhisperLiveKit"),
        ).pack(side=tk.LEFT)
        try:
            small_font = font.nametofont("TkDefaultFont").copy()
            size = int(small_font.cget("size"))
        except Exception:
            small_font = None
            size = 10
        if small_font is not None:
            small_font.configure(size=max(size - 2, 8))
        ttk.Label(
            bottom,
            text=self._t("This app is a wrapper for the above repository."),
            font=small_font if small_font is not None else None,
        ).pack(side=tk.LEFT, padx=8)
        copy_btn = ttk.Button(bottom, text=self._t("Copy"))
        copy_btn.pack(side=tk.RIGHT)

        # ペインに追加
        paned.add(left, weight=1)
        paned.add(right, weight=3)

        # データソース: 先頭に本体 LICENSE、その後にサードパーティ
        entries: list[dict[str, str]] = []
        # 本体
        try:
            proj_text = LICENSE_FILE.read_text(encoding="utf-8")
        except Exception as e:
            proj_text = f"Failed to load license: {e}"
        entries.append({
            "display": "Project: WhisperLiveKit Wrapper",
            "license": "Project License",
            "license_text": proj_text,
        })
        # 3rd party
        try:
            third_party = json.loads(THIRD_PARTY_LICENSES_FILE.read_text(encoding="utf-8"))
        except Exception:
            third_party = []
        # 表示用に整形・ソート
        for item in third_party:
            name = item.get("name", "")
            version = item.get("version", "")
            lic = item.get("license", "")
            entries.append({
                "display": f"{name} {version} — {lic}",
                "license": lic or "",
                "license_text": item.get("license_text", ""),
                "name": name,
                "version": version,
            })
        entries = [entries[0]] + sorted(entries[1:], key=lambda x: x.get("display", "").lower())

        for e in entries:
            listbox.insert(tk.END, e.get("display", ""))

        def show_entry(index: int) -> None:
            if index < 0 or index >= len(entries):
                return
            e = entries[index]
            body = e.get("license_text") or ""
            header_lines: list[str] = []
            if "name" in e:
                header_lines.append(e.get("display", ""))
            else:
                header_lines.append("WhisperLiveKit Wrapper")
            lic_name = e.get("license", "")
            if lic_name:
                header_lines.append(lic_name)
            header = "\n".join(header_lines)
            content = header + ("\n\n" if header else "")
            if body.strip():
                content += body.strip()
            else:
                content += "(No license text bundled. See package metadata.)"
            text.config(state="normal")
            text.delete("1.0", tk.END)
            text.insert("1.0", content)
            text.config(state="disabled")

        def on_select(_evt=None):  # pragma: no cover - UI event
            try:
                sel = listbox.curselection()
                if sel:
                    show_entry(int(sel[0]))
            except Exception:
                pass

        listbox.bind("<<ListboxSelect>>", on_select)

        def copy_current():  # pragma: no cover - UI event
            try:
                data = text.get("1.0", tk.END)
                self.copy_to_clipboard(data)
                self._copy_with_feedback(copy_btn, self._t("Copied!"))
            except Exception:
                pass

        copy_btn.config(command=copy_current)

        # 初期選択（先頭=本体）
        try:
            listbox.selection_set(0)
            show_entry(0)
        except Exception:
            pass

    def login_hf(self) -> None:
        token = simpledialog.askstring("Hugging Face Login", "Enter token", show="*")
        if token:
            threading.Thread(target=self._run_hf_login, args=(token,), daemon=True).start()

    def _run_hf_login(self, token: str) -> None:
        # 1) トークンの有効性を whoami で検証
        valid = False
        username: str | None = None
        whoami_err: Exception | None = None
        try:
            try:
                from huggingface_hub import HfApi  # type: ignore
                api = HfApi()
                info = api.whoami(token=token)
                username = info.get("name") if isinstance(info, dict) else None
                valid = True
            except Exception as e:
                valid = False
                whoami_err = e
            # 2) 有効なら資格情報を CLI 側に保存（任意だが利便性のため）
            if valid:
                cli_ok = True
                cli_err: Exception | None = None
                try:
                    res = subprocess.run(
                        ["huggingface-cli", "login", "--token", token],
                        check=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )
                    cli_ok = (res.returncode == 0)
                except Exception as e:
                    cli_ok = False
                    cli_err = e

                def _ok():
                    self.hf_logged_in = True
                    self._hf_username = username
                    if cli_ok:
                        self.status_var.set(
                            f"{self._t('Hugging Face login succeeded')}{f' as {username}' if username else ''}"
                        )
                        try:
                            messagebox.showinfo(
                                "Hugging Face",
                                f"Login successful{f' as {username}' if username else ''}. Diarization can be enabled.",
                            )
                        except Exception:
                            pass
                    else:
                        self.status_var.set(
                            f"{self._t('Token is valid')}{f' for {username}' if username else ''}, {self._t('but storing credentials failed:')} {cli_err}"
                        )
                        try:
                            messagebox.showwarning(
                                "Hugging Face",
                                self._t("Token is valid, but saving credentials failed. You may need to login via CLI."),
                            )
                        except Exception:
                            pass
                    self._apply_hf_login_state()
                self.master.after(0, _ok)
            else:
                def _ng():
                    self.status_var.set(f"{self._t('Invalid Hugging Face token:')} {whoami_err}")
                    self.hf_logged_in = False
                    self._hf_username = None
                    self._apply_hf_login_state()
                    try:
                        messagebox.showerror("Hugging Face", f"{self._t('Invalid token:')} {whoami_err}")
                    except Exception:
                        pass
                self.master.after(0, _ng)
        except Exception as e:  # pragma: no cover - safety net
            def _ng2(err=e):
                self.status_var.set(f"{self._t('Hugging Face token check failed:')} {err}")
                self.hf_logged_in = False
                self._hf_username = None
                self._apply_hf_login_state()
                try:
                    messagebox.showerror("Hugging Face", f"{self._t('Token check failed:')} {err}")
                except Exception:
                    pass
            self.master.after(0, _ng2)

    def _update_diarization_fields(self, *_: object) -> None:
        # Only active when diarization is toggled AND HF is logged in
        state = tk.NORMAL if (self.diarization.get() and self.hf_logged_in) else tk.DISABLED
        self.seg_model_combo.config(state=state)
        self.emb_model_combo.config(state=state)
        try:
            self.diar_settings_btn.config(state=state)
        except Exception:
            pass

    def _on_diarization_toggle(self) -> None:
        if self.diarization.get() and not self.hf_logged_in:
            # Revert and notify
            self.diarization.set(False)
            self.status_var.set(self._t("Diarization requires Hugging Face login"))
        self._update_diarization_fields()

    def _open_model_manager(self) -> None:
        if (self.api_proc is not None or self.backend_proc is not None) or self.is_recording:
            try:
                messagebox.showinfo(self._t("Models locked"), self._t("Stop API before managing models."))
            except Exception:
                pass
            return
        ModelManagerDialog(self.master, self)

    def _toggle_allow_external(self) -> None:
        # Save current local hosts when enabling
        if self.allow_external.get():
            self._last_local_backend_host = self.backend_host.get()
            self._last_local_api_host = self.api_host.get()
            self.backend_host.set("0.0.0.0")
            self.api_host.set("0.0.0.0")
        else:
            # Restore previous local-only hosts
            self.backend_host.set(self._last_local_backend_host or "127.0.0.1")
            self.api_host.set(self._last_local_api_host or "127.0.0.1")

    def _on_theme_change(self) -> None:
        self.style.theme_use(self.theme.get())
        self._save_settings()

    def _load_settings(self) -> None:
        config_present = CONFIG_FILE.exists()
        if not config_present and OLD_CONFIG_FILE.exists():
            try:
                shutil.move(str(OLD_CONFIG_FILE), CONFIG_FILE)
                config_present = True
            except Exception:
                pass
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}
        self.backend_host.set(data.get("backend_host", self.backend_host.get()))
        self.backend_port.set(data.get("backend_port", self.backend_port.get()))
        self.api_host.set(data.get("api_host", self.api_host.get()))
        self.api_port.set(data.get("api_port", self.api_port.get()))
        if "auto_start" in data:
            self.auto_start.set(data["auto_start"])
        elif config_present:
            self.auto_start.set(False)
        self.model.set(data.get("model", self.model.get()))
        self.use_api_key.set(data.get("use_api_key", self.use_api_key.get()))
        self.api_key.set(data.get("api_key", self.api_key.get()))
        self.use_vac.set(data.get("use_vac", self.use_vac.get()))
        self.vad_certfile.set(data.get("vad_certfile", self.vad_certfile.get()))
        self.diarization.set(data.get("diarization", self.diarization.get()))
        self.segmentation_model.set(data.get("segmentation_model", self.segmentation_model.get()))
        self.embedding_model.set(data.get("embedding_model", self.embedding_model.get()))
        self.ws_url.set(data.get("ws_url", self.ws_url.get()))
        self.save_path.set(data.get("save_path", self.save_path.get()))
        self.save_enabled.set(data.get("save_enabled", False))
        self.allow_external.set(data.get("allow_external", self.allow_external.get()))
        self.theme.set(data.get("theme", self.theme.get()))
        self.warmup_file.set(data.get("warmup_file", self.warmup_file.get()))
        self.confidence_validation.set(data.get("confidence_validation", self.confidence_validation.get()))
        self.punctuation_split.set(data.get("punctuation_split", self.punctuation_split.get()))
        backend_cfg = data.get("diarization_backend", self.diarization_backend.get())
        if not SORTFORMER_AVAILABLE and backend_cfg == "sortformer":
            self.diarization_backend.set("diart")
            try:
                from tkinter import messagebox as _mb
                _mb.showwarning(
                    "Sortformer unavailable",
                    "CUDA and NeMo not found; switched diarization backend to 'diart'.",
                )
            except Exception:
                pass
        else:
            self.diarization_backend.set(backend_cfg)
        self.min_chunk_size.set(data.get("min_chunk_size", self.min_chunk_size.get()))
        self.language.set(data.get("language", self.language.get()))
        self.task.set(data.get("task", self.task.get()))
        self.backend.set(data.get("backend", self.backend.get()))
        self.vac_chunk_size.set(data.get("vac_chunk_size", self.vac_chunk_size.get()))
        self.buffer_trimming.set(data.get("buffer_trimming", self.buffer_trimming.get()))
        self.buffer_trimming_sec.set(data.get("buffer_trimming_sec", self.buffer_trimming_sec.get()))
        self.log_level.set(data.get("log_level", self.log_level.get()))
        self.ssl_certfile.set(data.get("ssl_certfile", self.ssl_certfile.get()))
        self.ssl_keyfile.set(data.get("ssl_keyfile", self.ssl_keyfile.get()))
        self.frame_threshold.set(data.get("frame_threshold", self.frame_threshold.get()))

    def _save_settings(self) -> None:
        data = {
            "backend_host": self.backend_host.get(),
            "backend_port": self.backend_port.get(),
            "api_host": self.api_host.get(),
            "api_port": self.api_port.get(),
            "auto_start": self.auto_start.get(),
            "model": self.model.get(),
            "use_api_key": self.use_api_key.get(),
            "api_key": self.api_key.get(),
            "use_vac": self.use_vac.get(),
            "vad_certfile": self.vad_certfile.get(),
            "diarization": self.diarization.get(),
            "segmentation_model": self.segmentation_model.get(),
            "embedding_model": self.embedding_model.get(),
            "ws_url": self.ws_url.get(),
            "save_path": self.save_path.get(),
            "save_enabled": self.save_enabled.get(),
            "allow_external": self.allow_external.get(),
            "theme": self.theme.get(),
            "warmup_file": self.warmup_file.get(),
            "confidence_validation": self.confidence_validation.get(),
            "punctuation_split": self.punctuation_split.get(),
            "diarization_backend": self.diarization_backend.get(),
            "min_chunk_size": self.min_chunk_size.get(),
            "language": self.language.get(),
            "task": self.task.get(),
            "backend": self.backend.get(),
            "vac_chunk_size": self.vac_chunk_size.get(),
            "buffer_trimming": self.buffer_trimming.get(),
            "buffer_trimming_sec": self.buffer_trimming_sec.get(),
            "log_level": self.log_level.get(),
            "ssl_certfile": self.ssl_certfile.get(),
            "ssl_keyfile": self.ssl_keyfile.get(),
            "frame_threshold": self.frame_threshold.get(),
        }
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def toggle_recording(self) -> None:
        if self.is_recording:
            self.is_recording = False
            self.record_btn.config(text=self._t("Start Recording"))
            try:
                if hasattr(self, "toolbar_record_btn"):
                    # ツールバーが存在する場合のみ反映
                    icon_play = Emoji.get('black right-pointing triangle').char
                    self.toolbar_record_btn.config(text=icon_play, bootstyle="success")
            except Exception:
                pass
            self.status_var.set(self._t("stopping"))
        else:
            self.is_recording = True
            self.record_btn.config(text=self._t("Stop Recording"))
            try:
                if hasattr(self, "toolbar_record_btn"):
                    icon_stop = Emoji.get('black square button').char
                    self.toolbar_record_btn.config(text=icon_stop, bootstyle="danger")
            except Exception:
                pass
            self.status_var.set(self._t("connecting"))
            self.timer_var.set("00:00")
            self.transcript_box.configure(state="normal")
            self.transcript_box.delete("1.0", tk.END)
            self.transcript_box.configure(state="disabled")
            threading.Thread(target=self._recording_worker, daemon=True).start()
            self.start_time = time.time()
            self._update_timer()
            # 設定をロック（サーバー稼働中と同様に）
            try:
                self._set_running_state(self.api_proc is not None or self.backend_proc is not None)
            except Exception:
                pass
    def _recording_worker(self) -> None:
        """Record PCM, encode to audio/webm(opus) via FFmpeg, stream over WS."""
        try:
            import sounddevice as sd
            from websockets.sync.client import connect
        except Exception as e:  # pragma: no cover - dependency missing
            self.master.after(0, lambda err=e: self.status_var.set(f"{self._t('missing dependency:')} {err}"))
            self.is_recording = False
            return

        ws_url = self.ws_url.get()
        q: queue.Queue[bytes] = queue.Queue()

        def audio_callback(indata, frames, time_info, status):  # pragma: no cover - realtime
            q.put(bytes(indata))
            rms = audioop.rms(indata, 2) / 32768
            self.master.after(0, lambda v=rms: self.level_var.set(v))

        # Prepare FFmpeg command to take raw PCM and produce audio/webm (opus)
        ffmpeg_cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "error",
            "-f", "s16le",
            "-ac", "1",
            "-ar", "16000",
            "-i", "pipe:0",
            "-c:a", "libopus",
            "-b:a", "48k",
            "-f", "webm",
            "pipe:1",
        ]

        ffmpeg_proc: subprocess.Popen | None = None
        feeder_thread: threading.Thread | None = None
        sender_thread: threading.Thread | None = None

        try:
            with connect(ws_url) as websocket:
                self.master.after(0, lambda: self.status_var.set(self._t("recording")))

                # WebSocket receiver (backend -> GUI)
                def receiver():
                    while True:
                        try:
                            msg = websocket.recv()
                        except Exception:
                            break
                        try:
                            data = json.loads(msg)
                            text = data.get("buffer_transcription") or data.get("text") or ""
                            if text:
                                self.master.after(0, lambda t=text: self._append_transcript(t))
                        except Exception:
                            continue

                recv_thread = threading.Thread(target=receiver, daemon=True)
                recv_thread.start()

                # Start FFmpeg encoder process
                try:
                    ffmpeg_proc = subprocess.Popen(
                        ffmpeg_cmd,
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        bufsize=0,
                    )
                except FileNotFoundError as e:
                    self.master.after(0, lambda err=e: self.status_var.set(f"{self._t('error:')} ffmpeg not found"))
                    return

                # Feed PCM to FFmpeg.stdin
                def feed_ffmpeg():  # pragma: no cover - realtime
                    assert ffmpeg_proc is not None and ffmpeg_proc.stdin is not None
                    while self.is_recording or not q.empty():
                        try:
                            data = q.get(timeout=0.1)
                        except Exception:
                            data = None
                        if not data:
                            continue
                        try:
                            ffmpeg_proc.stdin.write(data)
                            ffmpeg_proc.stdin.flush()
                        except Exception:
                            break
                    # Close stdin to flush/finish encoder
                    try:
                        ffmpeg_proc.stdin.close()
                    except Exception:
                        pass

                # Read encoded webm bytes from FFmpeg.stdout and send to WS
                def send_webm():  # pragma: no cover - realtime
                    assert ffmpeg_proc is not None and ffmpeg_proc.stdout is not None
                    try:
                        while True:
                            chunk = ffmpeg_proc.stdout.read(4096)
                            if not chunk:
                                break
                            try:
                                websocket.send(chunk)
                            except Exception:
                                break
                    except Exception:
                        pass

                feeder_thread = threading.Thread(target=feed_ffmpeg, daemon=True)
                sender_thread = threading.Thread(target=send_webm, daemon=True)

                # Start audio capture
                with sd.RawInputStream(
                    samplerate=16000,
                    channels=1,
                    dtype="int16",
                    blocksize=1600,
                    callback=audio_callback,
                ):
                    feeder_thread.start()
                    sender_thread.start()
                    # Wait until user stops recording
                    while self.is_recording:
                        time.sleep(0.05)

                # After stopping: ensure FFmpeg finishes, then signal EOF to backend
                if feeder_thread:
                    feeder_thread.join(timeout=5)
                if ffmpeg_proc:
                    try:
                        ffmpeg_proc.wait(timeout=5)
                    except Exception:
                        try:
                            ffmpeg_proc.kill()
                        except Exception:
                            pass
                if sender_thread:
                    sender_thread.join(timeout=5)

                # Explicit EOF for backend (empty binary frame)
                try:
                    websocket.send(b"")
                except Exception:
                    pass

                recv_thread.join(timeout=5)
        except Exception as e:
            self.master.after(0, lambda err=e: self.status_var.set(f"{self._t('error:')} {err}"))
        finally:
            self.is_recording = False
            # 設定ロック解除を反映
            try:
                self.master.after(0, lambda: self._set_running_state(self.api_proc is not None or self.backend_proc is not None))
            except Exception:
                pass
            self.master.after(0, self._finalize_recording)

    def _append_transcript(self, text: str) -> None:
        self.transcript_box.configure(state="normal")
        self.transcript_box.insert(tk.END, text + "\n")
        self.transcript_box.see(tk.END)
        self.transcript_box.configure(state="disabled")

    def _update_timer(self) -> None:
        if not self.is_recording:
            return
        elapsed = int(time.time() - getattr(self, "start_time", time.time()))
        self.timer_var.set(f"{elapsed // 60:02d}:{elapsed % 60:02d}")
        self.master.after(1000, self._update_timer)

    def _finalize_recording(self) -> None:
        self.record_btn.config(text=self._t("Start Recording"))
        self.status_var.set(self._t("stopped"))
        path = self.save_path.get().strip()
        if self.save_enabled.get() and path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(self.transcript_box.get("1.0", tk.END))
                self.status_var.set(f"{self._t('saved:')} {path}")
            except Exception as e:  # pragma: no cover - filesystem errors
                self.status_var.set(f"{self._t('save failed:')} {e}")

    @staticmethod
    def _find_free_port(exclude: set[int] | None = None) -> int:
        while True:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('', 0))
                port = s.getsockname()[1]
            if exclude and port in exclude:
                continue
            return port

    @staticmethod
    def _get_local_ips() -> list[str]:
        ips: set[str] = set()
        # Method 1: primary outbound interface (UDP no-send)
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                ip = s.getsockname()[0]
                if ip and not ip.startswith("127."):
                    ips.add(ip)
        except Exception:
            pass
        # Method 2: hostname resolution
        try:
            hostname = socket.gethostname()
            for res in socket.getaddrinfo(hostname, None, socket.AF_INET, socket.SOCK_STREAM):
                ip = res[4][0]
                if ip and not ip.startswith("127."):
                    ips.add(ip)
        except Exception:
            pass
        # Prefer sorted stability
        return sorted(ips)

    def _set_running_state(self, running: bool) -> None:
        # Lock settings that affect server process while running OR recording
        locked = running or bool(self.is_recording)
        state_entry = tk.DISABLED if locked else tk.NORMAL
        # Entries（host/port）
        self.backend_host_entry.config(state=state_entry)
        self.backend_port_entry.config(state=state_entry)
        self.api_host_entry.config(state=state_entry)
        self.api_port_entry.config(state=state_entry)
        # Checkbuttons
        self.auto_start_chk.config(state=state_entry)
        # Diarization also gated by HF login
        self.diarization_chk.config(state=(tk.DISABLED if locked or not self.hf_logged_in else tk.NORMAL))
        self.allow_external_chk.config(state=state_entry)
        # HF token controls
        try:
            self.hf_token_entry.config(state=state_entry)
            self.hf_token_btn.config(state=state_entry)
        except Exception:
            pass
        # Comboboxes
        self.model_combo.config(state="disabled" if locked else "readonly")
        # Respect diarization toggle for related combos
        if locked:
            self.seg_model_combo.config(state="disabled")
            self.emb_model_combo.config(state="disabled")
        else:
            self._update_diarization_fields()
        # Buttons
        try:
            self.manage_models_btn.config(state=state_entry)
        except Exception:
            pass
        try:
            self.adv_btn.config(state=state_entry)
        except Exception:
            pass
        try:
            # Diarization Settings button should also be locked while running/recording
            if locked:
                self.diar_settings_btn.config(state=tk.DISABLED)
            else:
                self._update_diarization_fields()
        except Exception:
            pass
        # Start/Stop/Open Web are tied to running state (not recording)
        self.start_btn.config(state=tk.DISABLED if running else tk.NORMAL)
        self.stop_btn.config(state=tk.NORMAL if running else tk.DISABLED)
        self.open_web_btn.config(state=tk.NORMAL if running else tk.DISABLED)
        self._update_vad_state()
        self._update_hf_token_widgets()
        self._update_api_key_widgets()
        # 録音ボタンとヒント表示の制御（サーバー未起動時は録音不可）
        try:
            if running or self.is_recording:
                # サーバー起動中（または録音中）はボタン有効・ヒント非表示
                self.record_btn.config(state=tk.NORMAL)
                if hasattr(self, "record_hint_label"):
                    self.record_hint_label.grid_remove()
            else:
                # 未起動時はボタン無効・ヒント表示
                self.record_btn.config(state=tk.DISABLED)
                if hasattr(self, "record_hint_label"):
                    self.record_hint_label.grid()
        except Exception:
            pass

    def _update_save_widgets(self) -> None:
        state = tk.NORMAL if self.save_enabled.get() else tk.DISABLED
        self.save_entry.config(state=state)
        self.save_browse_btn.config(state=state)

    def _update_vad_state(self) -> None:
        running = self.api_proc is not None or self.backend_proc is not None
        locked = running or bool(self.is_recording)
        # VAD toggle is available when not running/recording
        if locked:
            self.vac_chk.config(state=tk.DISABLED)
        else:
            self.vac_chk.config(state=tk.NORMAL)
        # Certificate selection is only available when VAD is enabled and not locked
        cert_controls_state = tk.NORMAL if (self.use_vac.get() and not locked) else tk.DISABLED
        try:
            self.vad_cert_entry.config(state=cert_controls_state)
            self.vad_cert_browse.config(state=cert_controls_state)
        except Exception:
            pass
        # VAD Settings button is enabled only when VAD is ON and not locked
        try:
            self.vad_settings_btn.config(state=(tk.NORMAL if (self.use_vac.get() and not locked) else tk.DISABLED))
        except Exception:
            pass

    def _update_hf_token_widgets(self) -> None:
        """Present HF token controls based on login and edit mode.
        - When logged in and not in edit mode: disable entry, show button as "Validated"; clicking asks to enable editing.
        - When not logged in or in edit mode: enable entry (unless locked), show button as "Validate".
        """
        # If widgets not yet created, return
        if not hasattr(self, 'hf_token_entry') or not hasattr(self, 'hf_token_btn'):
            return
        running = self.api_proc is not None or self.backend_proc is not None
        locked = running or bool(self.is_recording)
        # If locked, both disabled regardless of state
        if locked:
            try:
                self.hf_token_entry.config(state=tk.DISABLED)
                self.hf_token_btn.config(state=tk.DISABLED)
            except Exception:
                pass
            return
        # Not locked:
        if self.hf_logged_in and not self._hf_edit_mode:
            try:
                # Mask with dummy placeholder and disable editing
                try:
                    self.hf_token_entry.config(show="")
                except Exception:
                    pass
                self.hf_token.set("********")
                self.hf_token_entry.config(state=tk.DISABLED)
                self.hf_token_btn.config(text=self._t("Validated"), command=self._confirm_enable_hf_edit, bootstyle="success")
                self.hf_token_btn.config(state=tk.NORMAL)
            except Exception:
                pass
        else:
            try:
                # Enable editing with hidden characters
                try:
                    self.hf_token_entry.config(show="*")
                except Exception:
                    pass
                if self.hf_token.get() == "********":
                    self.hf_token.set("")
                self.hf_token_entry.config(state=tk.NORMAL)
                self.hf_token_btn.config(text=self._t("Validate"), command=self._validate_hf_token, bootstyle="info")
                self.hf_token_btn.config(state=tk.NORMAL)
            except Exception:
                pass

    def _confirm_enable_hf_edit(self) -> None:
        """Ask user to enable token editing when already validated."""
        try:
            if messagebox.askyesno("Hugging Face", self._t("Enable token editing? You can re-validate a new token.")):
                self._hf_edit_mode = True
                self._update_hf_token_widgets()
        except Exception:
            # Fallback without prompt
            self._hf_edit_mode = True
            self._update_hf_token_widgets()

    def _apply_allow_external_initial(self) -> None:
        # Apply initial allow_external state to hosts without losing user's explicit values
        if self.allow_external.get():
            # Only override when current hosts look like localhost
            if self.backend_host.get() in {"127.0.0.1", "localhost"}:
                self.backend_host.set("0.0.0.0")
            if self.api_host.get() in {"127.0.0.1", "localhost"}:
                self.api_host.set("0.0.0.0")

    def _init_check_hf_login(self) -> None:
        # Validate that a usable, valid HF token exists (not just presence).
        logged = False
        username: str | None = None
        try:
            token: str | None = None
            try:
                # Prefer token from system keyring (if available)
                token = self._keyring_get_token() if self._keyring_available() else None
                # Then explicit GUI token (not persisted)
                if not token and self.hf_token.get().strip():
                    token = self.hf_token.get().strip()
                # Then env vars
                if not token:
                    for k in ("HF_TOKEN", "HUGGINGFACEHUB_API_TOKEN", "HUGGING_FACE_HUB_TOKEN"):
                        if os.getenv(k):
                            token = os.getenv(k)
                            break
                # Then huggingface_hub stored token
                if token is None:
                    from huggingface_hub import HfFolder  # type: ignore
                    token = HfFolder.get_token()
            except Exception:
                token = None

            # If we have a token candidate, verify it via whoami
            if token:
                try:
                    from huggingface_hub import HfApi  # type: ignore
                    api = HfApi()
                    info = api.whoami(token=token)
                    username = info.get("name") if isinstance(info, dict) else None
                    logged = True
                except Exception:
                    logged = False
            # Otherwise or if above failed, fallback to CLI whoami using stored creds
            if not logged:
                try:
                    res = subprocess.run(
                        ["huggingface-cli", "whoami"],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )
                    logged = res.returncode == 0
                except Exception:
                    pass
        finally:
            self.hf_logged_in = logged
            self._hf_username = username if logged else None
            self.master.after(0, self._apply_hf_login_state)

    def _keyring_available(self) -> bool:
        return keyring is not None

    def _keyring_get_token(self) -> str | None:
        if not self._keyring_available():
            return None
        try:
            return keyring.get_password(HF_KEYRING_SERVICE, "huggingface")  # type: ignore
        except Exception:
            return None

    def _keyring_set_token(self, token: str) -> bool:
        if not self._keyring_available():
            return False
        try:
            keyring.set_password(HF_KEYRING_SERVICE, "huggingface", token)  # type: ignore
            return True
        except Exception:
            return False

    def _keyring_delete_token(self) -> None:
        if not self._keyring_available():
            return
        try:
            keyring.delete_password(HF_KEYRING_SERVICE, "huggingface")  # type: ignore
        except Exception:
            pass

    def _validate_hf_token(self) -> None:
        tok = self.hf_token.get().strip()
        if not tok:
            try:
                messagebox.showwarning("Hugging Face", self._t("Please enter an access token."))
            except Exception:
                pass
            return

        def worker(token: str) -> None:
            valid = False
            username: str | None = None
            err: Exception | None = None
            try:
                from huggingface_hub import HfApi  # type: ignore
                api = HfApi()
                info = api.whoami(token=token)
                username = info.get("name") if isinstance(info, dict) else None
                valid = True
            except Exception as e:
                err = e
                valid = False
            finally:
                def _apply():
                    if valid:
                        self.hf_logged_in = True
                        self._hf_username = username
                        # Exit edit mode after successful validation
                        self._hf_edit_mode = False
                        # Store securely in system keyring if possible (no plaintext config)
                        saved = self._keyring_set_token(token)
                        self.status_var.set(f"{self._t('Hugging Face token valid')}{f' for {username}' if username else ''}.")
                        try:
                            info_msg = self._t("Token is valid. You can enable Diarization now.")
                            if not saved:
                                info_msg += "\n" + self._t("Note: Token was not saved in keyring; it won't persist across restarts.")
                            messagebox.showinfo("Hugging Face", info_msg)
                        except Exception:
                            pass
                    else:
                        self.hf_logged_in = False
                        self._hf_username = None
                        # Remove any previously stored token on failure
                        self._keyring_delete_token()
                        self.status_var.set(f"{self._t('Invalid Hugging Face token:')} {err}")
                        try:
                            messagebox.showerror("Hugging Face", f"{self._t('Invalid token:')} {err}")
                        except Exception:
                            pass
                    # Persist token and refresh UI state
                    # Do not save token to settings.json (avoid plaintext persistence)
                    self._apply_hf_login_state()
                self.master.after(0, _apply)

        threading.Thread(target=worker, args=(tok,), daemon=True).start()

    def _apply_hf_login_state(self) -> None:
        # Force-disable diarization if not logged in
        if not self.hf_logged_in and self.diarization.get():
            self.diarization.set(False)
        # ダイアリゼーションの有効化可否を切替
        self.diarization_chk.config(state=tk.NORMAL if self.hf_logged_in else tk.DISABLED)
        # ダイアリゼーション関連フィールドも更新
        self._update_diarization_fields()
        # Update controls with current running state
        self._set_running_state(self.api_proc is not None or self.backend_proc is not None)
        # Token widgets (entry/button) presentation
        self._update_hf_token_widgets()

class BackendSettingsDialog(tk.Toplevel):
    def __init__(self, master: tk.Misc, gui: 'WrapperGUI'):
        super().__init__(master)
        self.title("Advanced Settings")
        self.resizable(False, False)
        r = 0
        # Networking / Certificates
        ttk.Label(self, text="Custom CA certificate").grid(row=r, column=0, sticky=tk.W)
        ca = ttk.Frame(self)
        ca.grid(row=r, column=1, sticky="ew")
        ca.columnconfigure(0, weight=1)
        # Show and edit the path bound to gui.vad_certfile
        self._ca_entry = ttk.Entry(ca, textvariable=gui.vad_certfile, width=30)
        self._ca_entry.grid(row=0, column=0, sticky="ew")
        self._ca_browse = ttk.Button(ca, text="Custom CA certificate", command=lambda: self._choose_file(gui.vad_certfile))
        self._ca_browse.grid(row=0, column=1, padx=4)
        # Always enabled (independent from VAD toggle)
        r += 1
        ttk.Label(self, text="Warmup file").grid(row=r, column=0, sticky=tk.W)
        wf = ttk.Frame(self)
        wf.grid(row=r, column=1, sticky="ew")
        wf.columnconfigure(0, weight=1)
        ttk.Entry(wf, textvariable=gui.warmup_file, width=30).grid(row=0, column=0, sticky="ew")
        ttk.Button(wf, text="Browse...", command=lambda: self._choose_file(gui.warmup_file)).grid(row=0, column=1, padx=4)
        r += 1
        ttk.Checkbutton(self, text="Use confidence validation", variable=gui.confidence_validation).grid(row=r, column=0, columnspan=2, sticky=tk.W)
        r += 1
        ttk.Checkbutton(self, text="Use punctuation split", variable=gui.punctuation_split).grid(row=r, column=0, columnspan=2, sticky=tk.W)
        r += 1
        ttk.Label(self, text="Min chunk size").grid(row=r, column=0, sticky=tk.W)
        ttk.Entry(self, textvariable=gui.min_chunk_size, width=10).grid(row=r, column=1, sticky=tk.W)
        r += 1
        ttk.Label(self, text="Language").grid(row=r, column=0, sticky=tk.W)
        # 言語は主要コード＋autoを提示し、"Other..." で任意入力を許容
        lang_values = gui.available_languages()
        cur_lang = (gui.language.get() or "").strip()
        if cur_lang and cur_lang not in lang_values:
            lang_values = lang_values + [cur_lang]
        lang_values = lang_values + ["Other..."]
        self._lang_combo = ttk.Combobox(
            self,
            textvariable=gui.language,
            values=lang_values,
            state="readonly",
            width=15,
        )
        self._lang_combo.grid(row=r, column=1, sticky=tk.W)
        def _on_lang_selected(_e=None):  # pragma: no cover - UI
            try:
                val = self._lang_combo.get().strip()
                if val == "Other...":
                    new_val = simpledialog.askstring("Language", "Enter language code (e.g., en, ja):")
                    if new_val:
                        new_val = new_val.strip()
                        gui.language.set(new_val)
                        # 追加した言語を選択肢に反映
                        vals = list(self._lang_combo.cget("values"))
                        if new_val not in vals:
                            vals.insert(-1, new_val)
                            self._lang_combo.config(values=vals)
                        # Select the newly entered value
                        self._lang_combo.set(new_val)
                    else:
                        # Revert to previous if cancelled
                        prev = cur_lang if cur_lang else "auto"
                        gui.language.set(prev)
                        self._lang_combo.set(prev)
            except Exception:
                pass
        self._lang_combo.bind("<<ComboboxSelected>>", _on_lang_selected)
        r += 1
        ttk.Label(self, text="Task").grid(row=r, column=0, sticky=tk.W)
        ttk.Combobox(
            self,
            textvariable=gui.task,
            values=gui.available_tasks(),
            state="readonly",
            width=15,
        ).grid(row=r, column=1, sticky=tk.W)
        r += 1
        ttk.Label(self, text="Backend").grid(row=r, column=0, sticky=tk.W)
        ttk.Combobox(
            self,
            textvariable=gui.backend,
            values=gui.available_backends(),
            state="readonly",
            width=20,
        ).grid(row=r, column=1, sticky=tk.W)
        r += 1
        ttk.Label(
            self,
            text=gui._t(
                "For commercial use of the SimulStreaming backend, please check the SimulStreaming license."
            ),
            wraplength=300,
        ).grid(row=r, column=0, columnspan=2, sticky=tk.W, pady=(0, 8))
        r += 1
        ttk.Label(self, text="Buffer trimming").grid(row=r, column=0, sticky=tk.W)
        ttk.Combobox(
            self,
            textvariable=gui.buffer_trimming,
            values=["segment", "sentence"],
            state="readonly",
            width=10,
        ).grid(row=r, column=1, sticky=tk.W)
        r += 1
        ttk.Label(self, text="Buffer trimming sec").grid(row=r, column=0, sticky=tk.W)
        ttk.Entry(self, textvariable=gui.buffer_trimming_sec, width=10).grid(row=r, column=1, sticky=tk.W)
        r += 1
        ttk.Label(self, text="Log level").grid(row=r, column=0, sticky=tk.W)
        ttk.Combobox(
            self,
            textvariable=gui.log_level,
            values=gui.available_log_levels(),
            state="readonly",
            width=10,
        ).grid(row=r, column=1, sticky=tk.W)
        r += 1
        ttk.Label(self, text="SSL certfile").grid(row=r, column=0, sticky=tk.W)
        cf = ttk.Frame(self)
        cf.grid(row=r, column=1, sticky="ew")
        cf.columnconfigure(0, weight=1)
        ttk.Entry(cf, textvariable=gui.ssl_certfile, width=30).grid(row=0, column=0, sticky="ew")
        ttk.Button(cf, text="Browse...", command=lambda: self._choose_file(gui.ssl_certfile)).grid(row=0, column=1, padx=4)
        r += 1
        ttk.Label(self, text="SSL keyfile").grid(row=r, column=0, sticky=tk.W)
        kf = ttk.Frame(self)
        kf.grid(row=r, column=1, sticky="ew")
        kf.columnconfigure(0, weight=1)
        ttk.Entry(kf, textvariable=gui.ssl_keyfile, width=30).grid(row=0, column=0, sticky="ew")
        ttk.Button(kf, text="Browse...", command=lambda: self._choose_file(gui.ssl_keyfile)).grid(row=0, column=1, padx=4)
        r += 1
        ttk.Label(self, text="Frame threshold").grid(row=r, column=0, sticky=tk.W)
        ttk.Entry(self, textvariable=gui.frame_threshold, width=10).grid(row=r, column=1, sticky=tk.W)
        r += 1
        ttk.Button(self, text="Close", command=self.destroy).grid(row=r, column=0, columnspan=2, pady=(4, 0))

    def _choose_file(self, var: tk.StringVar) -> None:
        path = filedialog.askopenfilename()
        if path:
            var.set(path)


class VADSettingsDialog(tk.Toplevel):
    def __init__(self, master: tk.Misc, gui: 'WrapperGUI'):
        super().__init__(master)
        self.title("VAD Settings")
        self.resizable(False, False)
        ttk.Label(self, text="VAC chunk size").grid(row=0, column=0, sticky=tk.W)
        ttk.Entry(self, textvariable=gui.vac_chunk_size, width=10).grid(row=0, column=1, sticky=tk.W)
        ttk.Button(self, text="Close", command=self.destroy).grid(row=1, column=0, columnspan=2, pady=(4, 0))


class DiarizationSettingsDialog(tk.Toplevel):
    def __init__(self, master: tk.Misc, gui: 'WrapperGUI'):
        super().__init__(master)
        self.title("Diarization Settings")
        self.resizable(False, False)
        ttk.Label(self, text="Diarization backend").grid(row=0, column=0, sticky=tk.W)
        ttk.Combobox(
            self,
            textvariable=gui.diarization_backend,
            values=gui.available_diarization_backends(),
            state="readonly",
            width=15,
        ).grid(row=0, column=1, sticky=tk.W)
        ttk.Button(self, text="Close", command=self.destroy).grid(row=1, column=0, columnspan=2, pady=(4, 0))


class ModelManagerDialog(tk.Toplevel):
    def __init__(self, master: tk.Misc, gui: 'WrapperGUI | None' = None):
        super().__init__(master)
        self.title("Model Manager")
        # ウィンドウを見やすい初期サイズにし、リサイズを許可
        try:
            self.geometry("760x520")
        except Exception:
            pass
        try:
            self.resizable(True, True)
        except Exception:
            pass

        # レイアウト: 上にスクロール可能な一覧、下に操作ボタン
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        scroll = ScrollableFrame(self)
        scroll.grid(row=0, column=0, sticky="nsew")
        inner = scroll.inner
        # 列幅調整
        for c, w in [(0, 0), (1, 0), (2, 0), (3, 1), (4, 0)]:
            try:
                inner.columnconfigure(c, weight=w)
            except Exception:
                pass

        self.rows: dict[str, tuple[tk.StringVar, ttk.Progressbar, ttk.Button]] = {}
        _t = (gui._t if gui is not None and hasattr(gui, "_t") else (lambda s: s))
        self._tr = _t
        for i, name in enumerate(ALL_MODELS):
            ttk.Label(inner, text=name).grid(row=i, column=0, sticky=tk.W, padx=5, pady=2)
            ttk.Label(inner, text=MODEL_USAGE.get(name, "")).grid(row=i, column=1, sticky=tk.W)
            status = tk.StringVar()
            if model_manager.is_model_downloaded(name):
                status.set(_t("downloaded"))
            else:
                status.set(_t("missing"))
            ttk.Label(inner, textvariable=status).grid(row=i, column=2, sticky=tk.W)
            pb = ttk.Progressbar(inner, length=140)
            pb.grid(row=i, column=3, padx=5, sticky="ew")
            action = ttk.Button(
                inner,
                text="Delete" if model_manager.is_model_downloaded(name) else "Download",
                command=lambda n=name: self._on_action(n),
            )
            action.grid(row=i, column=4, padx=5)
            self.rows[name] = (status, pb, action)

        # 下段: 閉じるボタン
        btns = ttk.Frame(self)
        btns.grid(row=1, column=0, sticky="ew", padx=6, pady=(4, 6))
        try:
            btns.columnconfigure(0, weight=1)
        except Exception:
            pass
        ttk.Button(btns, text="Close", command=self.destroy).pack(anchor="e")

    def _on_action(self, name: str) -> None:
        status, pb, btn = self.rows[name]
        if model_manager.is_model_downloaded(name):
            model_manager.delete_model(name)
            status.set("missing")
            btn.config(text=self._tr("Download"))
            pb.config(value=0)
        else:
            btn.config(state=tk.DISABLED)

            def progress(frac: float) -> None:
                pb.config(value=frac * 100)

            def worker() -> None:
                try:
                    model_manager.download_model(name, progress_cb=progress)
                    status.set("downloaded")
                    btn.config(text=self._tr("Delete"))
                except Exception as e:  # pragma: no cover - GUI display
                    status.set(str(e))
                finally:
                    btn.config(state=tk.NORMAL)
                    pb.config(value=0)

            threading.Thread(target=worker, daemon=True).start()


def main():
    root = tk.Tk()
    gui = WrapperGUI(root)
    if gui.auto_start.get():
        root.after(100, gui.start_api)
    root.mainloop()


if __name__ == "__main__":
    main()
