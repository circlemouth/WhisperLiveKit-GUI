import os
import socket
import subprocess
import sys
import time
import webbrowser
import tkinter as tk
from tkinter import filedialog, simpledialog, font
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
ALL_MODELS = WHISPER_MODELS + SEGMENTATION_MODELS + EMBEDDING_MODELS


CONFIG_DIR = user_config_path("WhisperLiveKit", "wrapper")
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_FILE = CONFIG_DIR / "settings.json"
OLD_CONFIG_FILE = Path.home() / ".whisperlivekit-wrapper.json"
LICENSE_FILE = Path(__file__).resolve().parents[2] / "LICENSE"


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
        # 画面状態が最大化の場合はサイズ変更しない
        root = self.winfo_toplevel()
        try:
            if root.state() == "zoomed":
                return
        except Exception:
            pass
        # 現在の幅を維持しつつ、高さを内容に合わせて調整
        def _apply():
            try:
                root.update_idletasks()
                cur_w = root.winfo_width()
                # コンテンツに基づく推奨サイズ
                req_h = root.winfo_reqheight()
                # あまりに小さくならないよう最小高さを設定
                min_h = 480
                new_h = max(req_h, min_h)
                root.geometry(f"{cur_w}x{new_h}")
            except Exception:
                pass
        # レイアウト反映後に実施
        root.after(0, _apply)

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
            # スクロールが不要ならスクロールバーを隠す
            try:
                bbox = self._canvas.bbox("all")
                if bbox:
                    content_h = bbox[3] - bbox[1]
                    if content_h <= self._canvas.winfo_height() + 1:
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
            # スクロール必要性を再評価
            try:
                bbox = self._canvas.bbox("all")
                if bbox:
                    content_h = bbox[3] - bbox[1]
                    if content_h <= self._canvas.winfo_height() + 1:
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
        master.title("WhisperLiveKit Wrapper")

        # Variables
        # 固定テーマ: litera（切替不要のため強制適用）
        self.theme = tk.StringVar(value="litera")
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
        self.auto_start = tk.BooleanVar(value=os.getenv("WRAPPER_API_AUTOSTART", "1") == "1")
        # Allow external connections (bind 0.0.0.0)
        self.allow_external = tk.BooleanVar(value=os.getenv("WRAPPER_ALLOW_EXTERNAL") == "1")
        # Keep last local-only hosts to restore when toggled off
        self._last_local_backend_host = "127.0.0.1"
        self._last_local_api_host = "127.0.0.1"

        self.model = tk.StringVar(value=os.getenv("WRAPPER_MODEL", "large-v3"))
        # Use voice activity controller (Silero via torch.hub). Default off to avoid GitHub SSL/network issues.
        self.use_vac = tk.BooleanVar(value=os.getenv("WRAPPER_USE_VAC", "0") == "1")
        self.diarization = tk.BooleanVar(value=os.getenv("WRAPPER_DIARIZATION") == "1")
        self.segmentation_model = tk.StringVar(
            value=os.getenv("WRAPPER_SEGMENTATION_MODEL", "pyannote/segmentation-3.0")
        )
        self.embedding_model = tk.StringVar(
            value=os.getenv("WRAPPER_EMBEDDING_MODEL", "pyannote/embedding")
        )

        self.web_endpoint = tk.StringVar()
        self.ws_endpoint = tk.StringVar()
        self.api_endpoint = tk.StringVar()
        # HF login state (for diarization gating)
        self.hf_logged_in: bool = False
        self._hf_username: str | None = None

        # Recording-related variables
        self.ws_url = tk.StringVar()
        self.is_recording = False
        self.status_var = tk.StringVar(value="stopped")
        self.timer_var = tk.StringVar(value="00:00")
        self.level_var = tk.DoubleVar(value=0.0)
        self.save_path = tk.StringVar()
        self.save_enabled = tk.BooleanVar(value=False)

        self._load_settings()
        # テーマは litera を強制（既存設定を上書き）
        self.theme.set("litera")

        self.style = ttkb.Style(theme=self.theme.get())
        # 基本フォントと余白を拡大
        try:
            master.option_add("*Font", ("Segoe UI", 12))
        except Exception:
            pass
        self.style.configure("TLabel", padding=6)
        self.style.configure("TButton", padding=10)
        self.style.configure("TLabelframe", padding=12)
        # 見出しの視認性を向上（サイズ増、プライマリ色）
        primary_fg = None
        try:
            primary_fg = self.style.colors.primary
        except Exception:
            primary_fg = None
        self.style.configure("Header.TLabel", font=("Segoe UI", 18, "bold"))
        self.style.configure(
            "SectionHeader.TLabel",
            font=("Segoe UI", 14, "bold"),
            foreground=primary_fg if primary_fg else None,
        )

        master.columnconfigure(0, weight=1)

        row = 0
        # App header（テーマセレクタは撤去し、ライセンスのみ配置）
        header = ttk.Frame(master)
        header.grid(row=row, column=0, sticky="ew", padx=10, pady=(8, 0))
        header.columnconfigure(1, weight=1)
        ttk.Label(header, text="WhisperLiveKit Wrapper", style="Header.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Button(header, text="License", command=self.show_license).grid(row=0, column=2, sticky="e")
        row += 1

        # Toolbar with icon buttons
        toolbar = ttk.Frame(master)
        toolbar.grid(row=row, column=0, sticky="ew", padx=10, pady=5)
        self._icon_play = Emoji.get('black right-pointing triangle').char
        self._icon_stop = Emoji.get('black square button').char
        gear = Emoji.get('gear').char
        self.toolbar_record_btn = ttk.Button(toolbar, text=self._icon_play, width=3, bootstyle="success", command=self.toggle_recording)
        self.toolbar_record_btn.pack(side="left", padx=(0,5))
        ttk.Button(toolbar, text=gear, width=3, command=self._open_model_manager).pack(side="left")
        row += 1

        # 2カラムのメインコンテンツ領域（左: Server Settings、右: Recorder + Endpoints）
        content = ttk.Frame(master)
        content.grid(row=row, column=0, sticky="nsew", padx=10, pady=5)
        # 右カラム（Recorder）を優先的に拡張
        content.columnconfigure(0, weight=0)
        content.columnconfigure(1, weight=1)
        master.rowconfigure(row, weight=1)
        self.content = content

        # 左カラム: Server Settings + Endpoints（スクロールなし、常時表示）
        left_col = ttk.Frame(content)
        left_col.grid(row=0, column=0, sticky="n", padx=(0, 5))
        left_col.columnconfigure(0, weight=1)
        server_frame = ttk.Labelframe(left_col, text="Server Settings")
        server_frame.grid(row=0, column=0, sticky="ew")
        server_frame.columnconfigure(1, weight=1)
        config_frame = server_frame
        self.left_col = left_col
        self.server_frame = server_frame
        r = 0
        ttk.Label(config_frame, text="Backend host").grid(row=r, column=0, sticky=tk.W)
        self.backend_host_entry = ttk.Entry(config_frame, textvariable=self.backend_host, width=15)
        self.backend_host_entry.grid(row=r, column=1, sticky="ew")
        r += 1
        ttk.Label(config_frame, text="Backend port").grid(row=r, column=0, sticky=tk.W)
        self.backend_port_entry = ttk.Entry(config_frame, textvariable=self.backend_port, width=15)
        self.backend_port_entry.grid(row=r, column=1, sticky="ew")
        r += 1
        ttk.Label(config_frame, text="API host").grid(row=r, column=0, sticky=tk.W)
        self.api_host_entry = ttk.Entry(config_frame, textvariable=self.api_host, width=15)
        self.api_host_entry.grid(row=r, column=1, sticky="ew")
        r += 1
        ttk.Label(config_frame, text="API port").grid(row=r, column=0, sticky=tk.W)
        self.api_port_entry = ttk.Entry(config_frame, textvariable=self.api_port, width=15)
        self.api_port_entry.grid(row=r, column=1, sticky="ew")
        r += 1
        self.auto_start_chk = ttk.Checkbutton(config_frame, text="Auto-start API on launch", variable=self.auto_start)
        self.auto_start_chk.grid(row=r, column=0, columnspan=2, sticky=tk.W)
        r += 1
        # External connections toggle
        self.allow_external_chk = ttk.Checkbutton(
            config_frame,
            text="Allow external connections (0.0.0.0)",
            variable=self.allow_external,
            command=self._toggle_allow_external,
        )
        self.allow_external_chk.grid(row=r, column=0, columnspan=2, sticky=tk.W)
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
        # VAC toggle
        self.vac_chk = ttk.Checkbutton(
            config_frame,
            text="Use voice activity controller (VAD)",
            variable=self.use_vac,
        )
        self.vac_chk.grid(row=r, column=0, columnspan=2, sticky=tk.W)
        r += 1
        self.diarization_chk = ttk.Checkbutton(
            config_frame,
            text="Enable diarization",
            variable=self.diarization,
            command=self._on_diarization_toggle,
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
        self.hf_login_btn = ttk.Button(config_frame, text="Hugging Face Login", command=self.login_hf)
        self.hf_login_btn.grid(row=r, column=0, columnspan=2, sticky=tk.W)
        r += 1
        ttk.Button(
            config_frame,
            text="Manage models",
            command=self._open_model_manager,
        ).grid(row=r, column=0, columnspan=2, sticky=tk.W)
        r += 1
        # Hint about diarization requiring HF login
        self.hf_hint = tk.Label(
            config_frame,
            text="話者分離（Diarization）を有効化するには Hugging Face へのログインが必要です。",
            wraplength=460,
            justify="left",
        )
        self.hf_hint.grid(row=r, column=0, columnspan=2, sticky=tk.W)
        r += 1
        start_stop = ttk.Frame(config_frame)
        start_stop.grid(row=r, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        start_stop.columnconfigure(0, weight=1)
        self.start_btn = ttk.Button(start_stop, text="Start API", command=self.start_api, bootstyle="primary")
        self.start_btn.grid(row=0, column=1, padx=(0, 6), sticky="e")
        self.stop_btn = ttk.Button(start_stop, text="Stop API", command=self.stop_api, bootstyle="danger")
        self.stop_btn.grid(row=0, column=2, sticky="e")

        # 右カラム: Recorder（縦に拡張）
        right_panel = ttk.Frame(content)
        right_panel.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        right_panel.columnconfigure(0, weight=1)
        right_panel.rowconfigure(0, weight=1)
        self.right_panel = right_panel

        record_frame = ttk.Labelframe(right_panel, text="Recorder")
        record_frame.grid(row=0, column=0, sticky="nsew")
        record_frame.columnconfigure(1, weight=1)
        self.record_frame = record_frame
        # Recording controls
        r = 0
        self.record_btn = ttk.Button(record_frame, text="Start Recording", command=self.toggle_recording)
        self.record_btn.grid(row=r, column=0, sticky=tk.W)
        r += 1
        ttk.Label(record_frame, textvariable=self.timer_var).grid(row=r, column=0, sticky=tk.W)
        ttk.Progressbar(record_frame, variable=self.level_var, maximum=1.0).grid(row=r, column=1, columnspan=2, sticky="ew")
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
        # Transcript area inside Recorder
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
        self.transcript_box.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(trans_frame, orient="vertical", command=self.transcript_box.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.transcript_box.configure(yscrollcommand=scroll.set)
        # Endpoints（左カラム下）
        endpoints_frame = ttk.Labelframe(left_col, text="Endpoints")
        endpoints_frame.grid(row=1, column=0, sticky="ew", pady=(5, 0))
        endpoints_frame.columnconfigure(1, weight=1)
        self.endpoints_frame = endpoints_frame
        r = 0
        ttk.Label(endpoints_frame, text="Backend Web UI").grid(row=r, column=0, sticky=tk.W)
        ttk.Entry(endpoints_frame, textvariable=self.web_endpoint, width=40, state="readonly").grid(row=r, column=1, sticky="ew")
        self.open_web_btn = ttk.Button(endpoints_frame, text="Open Web GUI", command=self.open_web_gui, state=tk.DISABLED)
        self.open_web_btn.grid(row=r, column=2, padx=5)
        r += 1
        ttk.Label(endpoints_frame, text="Streaming WebSocket /asr").grid(row=r, column=0, sticky=tk.W)
        ttk.Entry(endpoints_frame, textvariable=self.ws_endpoint, width=40, state="readonly").grid(row=r, column=1, sticky="ew")
        ttk.Button(endpoints_frame, text="Copy", command=lambda: self.copy_to_clipboard(self.ws_endpoint.get())).grid(row=r, column=2, padx=5)
        r += 1
        ttk.Label(endpoints_frame, text="File transcription API").grid(row=r, column=0, sticky=tk.W)
        ttk.Entry(endpoints_frame, textvariable=self.api_endpoint, width=40, state="readonly").grid(row=r, column=1, sticky="ew")
        ttk.Button(endpoints_frame, text="Copy", command=lambda: self.copy_to_clipboard(self.api_endpoint.get())).grid(row=r, column=2, padx=5)
        row += 1

        # ステータスバーは最下段に全幅で配置
        row += 1
        status = ttk.Frame(master)
        status.grid(row=row, column=0, sticky="ew", padx=5, pady=(0,5))
        status.columnconfigure(1, weight=1)
        ttk.Label(status, textvariable=self.status_var).grid(row=0, column=0, sticky="w")
        self.progress = ttk.Progressbar(status, maximum=100, mode="determinate")
        self.progress.grid(row=0, column=1, sticky="ew", padx=(10,0))
        row += 1

        self.backend_proc: subprocess.Popen | None = None
        self.api_proc: subprocess.Popen | None = None

        self._update_diarization_fields()

        for var in [self.backend_host, self.backend_port, self.api_host, self.api_port]:
            var.trace_add("write", self.update_endpoints)
        # Update endpoints also when external toggle changes
        self.allow_external.trace_add("write", self.update_endpoints)
        # Save enable toggle should update widgets
        self.save_enabled.trace_add("write", lambda *_: self._update_save_widgets())
        self.update_endpoints()
        # Apply initial save widgets state
        self._update_save_widgets()

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

    def _apply_fixed_layout(self) -> None:
        # 2カラム固定: 左（Server + Endpoints）、右（Recorder）
        try:
            self.left_col.grid_forget()
            self.right_panel.grid_forget()
        except Exception:
            pass
        # 右カラムが縦に拡張、左は内容サイズ
        self.content.columnconfigure(0, weight=0)
        self.content.columnconfigure(1, weight=1)
        self.content.rowconfigure(0, weight=1)
        self.left_col.grid(row=0, column=0, sticky="n", padx=(0,5))
        self.right_panel.grid(row=0, column=1, sticky="nsew", padx=(5,0))
        self.master.update_idletasks()
        self._lock_minsize_by_content()

    def _lock_minsize_by_content(self) -> None:
        # 全要素が見切れない最小サイズを設定
        root = self.master
        try:
            root.update_idletasks()
            req_w = max(root.winfo_reqwidth(), 900)
            req_h = max(root.winfo_reqheight(), 650)
            root.minsize(req_w, req_h)
        except Exception:
            pass

    def start_api(self):
        if self.api_proc or self.backend_proc:
            return
        missing: list[str] = []
        model = self.model.get().strip()
        if model and not model_manager.is_model_downloaded(model):
            missing.append(model)
        if self.diarization.get() and self.hf_logged_in:
            seg = self.segmentation_model.get().strip()
            if seg and not model_manager.is_model_downloaded(seg):
                missing.append(seg)
            emb = self.embedding_model.get().strip()
            if emb and not model_manager.is_model_downloaded(emb):
                missing.append(emb)
        if missing:
            self.start_btn.config(state=tk.DISABLED)
            self._download_and_start(missing)
            return
        self._launch_server()

    def _download_and_start(self, models: list[str]) -> None:
        self.progress.config(value=0)

        def progress(frac: float) -> None:
            self.master.after(0, lambda v=frac * 100: self.progress.config(value=v))

        def worker() -> None:
            try:
                for m in models:
                    label = f"Downloading {m}"
                    self.master.after(0, lambda l=label: self.status_var.set(l))
                    model_manager.download_model(m, progress_cb=progress)
                self.master.after(0, self._on_download_success)
            except Exception as e:  # pragma: no cover - GUI display
                self.master.after(0, lambda err=e: self.status_var.set(f"Download failed: {err}"))
                self.master.after(0, lambda: self.progress.config(value=0))
                self.master.after(0, lambda: self.start_btn.config(state=tk.NORMAL))

        threading.Thread(target=worker, daemon=True).start()

    def _on_download_success(self) -> None:
        self.status_var.set("Download complete")
        self.progress.config(value=0)
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
        env["HF_HOME"] = str(model_manager.HF_CACHE_DIR)

        backend_cmd = [
            sys.executable,
            "-m",
            "whisperlivekit.basic_server",
            "--host",
            b_host,
            "--port",
            b_port,
        ]
        model = self.model.get().strip()
        if model:
            backend_cmd += ["--model_dir", str(model_manager.get_model_path(model))]
        if self.diarization.get() and self.hf_logged_in:
            backend_cmd.append("--diarization")
            seg = self.segmentation_model.get().strip()
            if seg:
                backend_cmd += ["--segmentation-model", seg]
            emb = self.embedding_model.get().strip()
            if emb:
                backend_cmd += ["--embedding-model", emb]

        # Disable VAC by default unless explicitly enabled to prevent torch.hub GitHub SSL failures
        if not self.use_vac.get():
            backend_cmd.append("--no-vac")

        self.backend_proc = subprocess.Popen(backend_cmd)
        time.sleep(2)
        try:
            webbrowser.open(f"http://{b_host}:{b_port}")
        except Exception:
            pass

        self.api_proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "wrapper.api.server:app",
                "--host",
                a_host,
                "--port",
                a_port,
            ],
            env=env,
        )
        self._set_running_state(True)

    def stop_api(self):
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

    def copy_to_clipboard(self, text: str) -> None:
        self.master.clipboard_clear()
        self.master.clipboard_append(text)

    def choose_save_path(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if path:
            self.save_path.set(path)

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
        self.web_endpoint.set(f"http://{display_b_host}:{b_port}/")
        ws = f"ws://{display_b_host}:{b_port}/asr"
        self.ws_endpoint.set(ws)
        # Recorder follows the backend WebSocket endpoint
        self.ws_url.set(ws)
        self.api_endpoint.set(f"http://{display_a_host}:{a_port}/v1/audio/transcriptions")
        # Note: in external mode, endpoints already display LAN IPs directly

    def open_web_gui(self) -> None:
        url = self.web_endpoint.get()
        try:
            webbrowser.open(url)
        except Exception:
            pass

    def show_license(self) -> None:
        top = tk.Toplevel(self.master)
        top.title("License")
        text = tk.Text(top, wrap="word")
        text.pack(fill=tk.BOTH, expand=True)
        scroll = ttk.Scrollbar(top, orient="vertical", command=text.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        text.configure(yscrollcommand=scroll.set)
        try:
            with open(LICENSE_FILE, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            content = f"Failed to load license: {e}"
        text.insert("1.0", content)
        text.config(state="disabled")

        link_frame = ttk.Frame(top)
        link_frame.pack(fill=tk.X, pady=5)
        ttk.Button(
            link_frame,
            text="QuentinFuxa/WhisperLiveKit",
            command=lambda: webbrowser.open("https://github.com/QuentinFuxa/WhisperLiveKit"),
        ).pack()
        small_font = font.nametofont("TkDefaultFont").copy()
        size = small_font.cget("size")
        try:
            size = int(size)
        except Exception:
            pass
        small_font.configure(size=max(size - 2, 8))
        tk.Label(
            link_frame,
            text="このアプリはこのレポジトリのラッパーです",
            font=small_font,
        ).pack()

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
                            f"Hugging Face login succeeded{f' as {username}' if username else ''}"
                        )
                    else:
                        self.status_var.set(
                            f"Token is valid{f' for {username}' if username else ''}, but storing credentials failed: {cli_err}"
                        )
                    self._apply_hf_login_state()
                self.master.after(0, _ok)
            else:
                def _ng():
                    self.status_var.set(f"Invalid Hugging Face token: {whoami_err}")
                    self.hf_logged_in = False
                    self._hf_username = None
                    self._apply_hf_login_state()
                self.master.after(0, _ng)
        except Exception as e:  # pragma: no cover - safety net
            def _ng2(err=e):
                self.status_var.set(f"Hugging Face token check failed: {err}")
                self.hf_logged_in = False
                self._hf_username = None
                self._apply_hf_login_state()
            self.master.after(0, _ng2)

    def _update_diarization_fields(self, *_: object) -> None:
        # Only active when diarization is toggled AND HF is logged in
        state = tk.NORMAL if (self.diarization.get() and self.hf_logged_in) else tk.DISABLED
        self.seg_model_combo.config(state=state)
        self.emb_model_combo.config(state=state)

    def _on_diarization_toggle(self) -> None:
        if self.diarization.get() and not self.hf_logged_in:
            # Revert and notify
            self.diarization.set(False)
            self.status_var.set("Diarization requires Hugging Face login")
        self._update_diarization_fields()

    def _open_model_manager(self) -> None:
        ModelManagerDialog(self.master)

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
        self.use_vac.set(data.get("use_vac", self.use_vac.get()))
        self.diarization.set(data.get("diarization", self.diarization.get()))
        self.segmentation_model.set(data.get("segmentation_model", self.segmentation_model.get()))
        self.embedding_model.set(data.get("embedding_model", self.embedding_model.get()))
        self.ws_url.set(data.get("ws_url", self.ws_url.get()))
        self.save_path.set(data.get("save_path", self.save_path.get()))
        self.save_enabled.set(data.get("save_enabled", False))
        self.allow_external.set(data.get("allow_external", self.allow_external.get()))
        self.theme.set(data.get("theme", self.theme.get()))

    def _save_settings(self) -> None:
        data = {
            "backend_host": self.backend_host.get(),
            "backend_port": self.backend_port.get(),
            "api_host": self.api_host.get(),
            "api_port": self.api_port.get(),
            "auto_start": self.auto_start.get(),
            "model": self.model.get(),
            "use_vac": self.use_vac.get(),
            "diarization": self.diarization.get(),
            "segmentation_model": self.segmentation_model.get(),
            "embedding_model": self.embedding_model.get(),
            "ws_url": self.ws_url.get(),
            "save_path": self.save_path.get(),
            "save_enabled": self.save_enabled.get(),
            "allow_external": self.allow_external.get(),
            "theme": self.theme.get(),
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
            self.record_btn.config(text="Start Recording")
            self.toolbar_record_btn.config(text=self._icon_play, bootstyle="success")
            self.status_var.set("stopping")
        else:
            self.is_recording = True
            self.record_btn.config(text="Stop Recording")
            self.toolbar_record_btn.config(text=self._icon_stop, bootstyle="danger")
            self.status_var.set("connecting")
            self.timer_var.set("00:00")
            self.transcript_box.configure(state="normal")
            self.transcript_box.delete("1.0", tk.END)
            self.transcript_box.configure(state="disabled")
            threading.Thread(target=self._recording_worker, daemon=True).start()
            self.start_time = time.time()
            self._update_timer()

    def _recording_worker(self) -> None:
        try:
            import sounddevice as sd
            from websockets.sync.client import connect
        except Exception as e:  # pragma: no cover - dependency missing
            self.master.after(0, lambda err=e: self.status_var.set(f"missing dependency: {err}"))
            self.is_recording = False
            return

        ws_url = self.ws_url.get()
        q: queue.Queue[bytes] = queue.Queue()

        def audio_callback(indata, frames, time_info, status):  # pragma: no cover - realtime
            q.put(bytes(indata))
            rms = audioop.rms(indata, 2) / 32768
            self.master.after(0, lambda v=rms: self.level_var.set(v))

        try:
            with connect(ws_url) as websocket:
                self.master.after(0, lambda: self.status_var.set("recording"))

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

                with sd.RawInputStream(
                    samplerate=16000,
                    channels=1,
                    dtype="int16",
                    blocksize=1600,
                    callback=audio_callback,
                ):
                    while self.is_recording:
                        data = q.get()
                        websocket.send(data)

                websocket.send(json.dumps({"eof": 1}))
                recv_thread.join(timeout=5)
        except Exception as e:
            self.master.after(0, lambda err=e: self.status_var.set(f"error: {err}"))
        finally:
            self.is_recording = False
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
        self.record_btn.config(text="Start Recording")
        self.status_var.set("stopped")
        path = self.save_path.get().strip()
        if self.save_enabled.get() and path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(self.transcript_box.get("1.0", tk.END))
                self.status_var.set(f"saved: {path}")
            except Exception as e:  # pragma: no cover - filesystem errors
                self.status_var.set(f"save failed: {e}")

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
        # Lock settings that affect server process while running
        state_entry = tk.DISABLED if running else tk.NORMAL
        # Entries
        self.backend_host_entry.config(state=state_entry)
        self.backend_port_entry.config(state=state_entry)
        self.api_host_entry.config(state=state_entry)
        self.api_port_entry.config(state=state_entry)
        # Checkbuttons
        self.auto_start_chk.config(state=state_entry)
        self.vac_chk.config(state=state_entry)
        # Diarization also gated by HF login
        self.diarization_chk.config(state=(tk.DISABLED if running or not self.hf_logged_in else tk.NORMAL))
        self.allow_external_chk.config(state=state_entry)
        # Comboboxes
        self.model_combo.config(state="disabled" if running else "readonly")
        # Respect diarization toggle for related combos
        if running:
            self.seg_model_combo.config(state="disabled")
            self.emb_model_combo.config(state="disabled")
        else:
            self._update_diarization_fields()
        # Buttons
        self.hf_login_btn.config(state=state_entry)
        self.start_btn.config(state=tk.DISABLED if running else tk.NORMAL)
        self.stop_btn.config(state=tk.NORMAL if running else tk.DISABLED)
        self.open_web_btn.config(state=tk.NORMAL if running else tk.DISABLED)

    def _update_save_widgets(self) -> None:
        state = tk.NORMAL if self.save_enabled.get() else tk.DISABLED
        self.save_entry.config(state=state)
        self.save_browse_btn.config(state=state)

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
                # Prefer env vars if provided explicitly
                for k in ("HF_TOKEN", "HUGGINGFACEHUB_API_TOKEN", "HUGGING_FACE_HUB_TOKEN"):
                    if os.getenv(k):
                        token = os.getenv(k)
                        break
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


class ModelManagerDialog(tk.Toplevel):
    def __init__(self, master: tk.Misc):
        super().__init__(master)
        self.title("Model Manager")
        self.resizable(False, False)

        self.rows: dict[str, tuple[tk.StringVar, ttk.Progressbar, ttk.Button]] = {}
        for i, name in enumerate(ALL_MODELS):
            ttk.Label(self, text=name).grid(row=i, column=0, sticky=tk.W, padx=5, pady=2)
            status = tk.StringVar()
            if model_manager.is_model_downloaded(name):
                status.set("downloaded")
            else:
                status.set("missing")
            ttk.Label(self, textvariable=status).grid(row=i, column=1, sticky=tk.W)
            pb = ttk.Progressbar(self, length=120)
            pb.grid(row=i, column=2, padx=5)
            action = ttk.Button(
                self,
                text="Delete" if model_manager.is_model_downloaded(name) else "Download",
                command=lambda n=name: self._on_action(n),
            )
            action.grid(row=i, column=3, padx=5)
            self.rows[name] = (status, pb, action)

    def _on_action(self, name: str) -> None:
        status, pb, btn = self.rows[name]
        if model_manager.is_model_downloaded(name):
            model_manager.delete_model(name)
            status.set("missing")
            btn.config(text="Download")
            pb.config(value=0)
        else:
            btn.config(state=tk.DISABLED)

            def progress(frac: float) -> None:
                pb.config(value=frac * 100)

            def worker() -> None:
                try:
                    model_manager.download_model(name, progress_cb=progress)
                    status.set("downloaded")
                    btn.config(text="Delete")
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
