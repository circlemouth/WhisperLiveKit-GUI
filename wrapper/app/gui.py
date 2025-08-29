import os
import socket
import subprocess
import sys
import time
import webbrowser
import tkinter as tk
from tkinter import ttk, filedialog, simpledialog, font, messagebox
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


class WrapperGUI:
    def __init__(self, master: tk.Tk):
        self.master = master
        master.title("WhisperLiveKit Wrapper")

        # Variables
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

        # Recording-related variables
        self.ws_url = tk.StringVar()
        self.is_recording = False
        self.status_var = tk.StringVar(value="stopped")
        self.timer_var = tk.StringVar(value="00:00")
        self.level_var = tk.DoubleVar(value=0.0)
        self.save_path = tk.StringVar()
        self.save_enabled = tk.BooleanVar(value=False)

        self._load_settings()

        style = ttk.Style()
        try:
            style.theme_use("vista")
        except tk.TclError:
            try:
                style.theme_use("winnative")
            except tk.TclError:
                style.theme_use("clam")
        # Modern-ish styling tweaks
        style.configure("TLabel", padding=4)
        style.configure("TButton", padding=8)
        style.configure("TLabelframe", padding=10)
        style.configure("Header.TLabel", font=("Segoe UI", 14, "bold"))
        try:
            master.option_add("*Font", ("Segoe UI", 10))
        except Exception:
            pass

        master.columnconfigure(0, weight=1)

        row = 0
        # App header
        ttk.Label(master, text="WhisperLiveKit Wrapper", style="Header.TLabel").grid(row=row, column=0, sticky="w", padx=10, pady=(8,0))
        row += 1
        config_frame = ttk.Labelframe(master, text="Server Settings")
        config_frame.grid(row=row, column=0, sticky="ew", padx=10, pady=5)
        config_frame.columnconfigure(1, weight=1)
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
        ttk.Button(
            config_frame,
            text="Manage models",
            command=self._open_model_manager,
        ).grid(row=r, column=1, sticky=tk.E)
        r += 1
        self.diarization_chk = ttk.Checkbutton(
            config_frame,
            text="Enable diarization",
            variable=self.diarization,
            command=self._on_diarization_toggle,
        )
        self.diarization_chk.grid(row=r, column=0, columnspan=2, sticky=tk.W)
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
        start_stop.grid(row=r, column=0, columnspan=2, sticky=tk.W)
        self.start_btn = ttk.Button(start_stop, text="Start API", command=self.start_api)
        self.start_btn.grid(row=0, column=0, padx=(0, 5))
        self.stop_btn = ttk.Button(start_stop, text="Stop API", command=self.stop_api)
        self.stop_btn.grid(row=0, column=1)
        row += 1

        endpoints_frame = ttk.Labelframe(master, text="Endpoints")
        endpoints_frame.grid(row=row, column=0, sticky="ew", padx=10, pady=5)
        endpoints_frame.columnconfigure(1, weight=1)
        r = 0
        ttk.Label(endpoints_frame, text="Backend Web UI").grid(row=r, column=0, sticky=tk.W)
        ttk.Entry(endpoints_frame, textvariable=self.web_endpoint, width=40, state="readonly").grid(row=r, column=1, sticky="ew")
        # Move Open Web GUI button here instead of Copy
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

        record_frame = ttk.Labelframe(master, text="Recorder")
        record_frame.grid(row=row, column=0, sticky="nsew", padx=10, pady=5)
        record_frame.columnconfigure(1, weight=1)
        # Recording controls
        r = 0
        self.record_btn = ttk.Button(record_frame, text="Start Recording", command=self.toggle_recording)
        self.record_btn.grid(row=r, column=0, sticky=tk.W)
        ttk.Label(record_frame, textvariable=self.status_var).grid(row=r, column=1, sticky=tk.W)
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
        self.transcript_box.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(trans_frame, orient="vertical", command=self.transcript_box.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.transcript_box.configure(yscrollcommand=scroll.set)
        # Allow main window to expand Recorder section
        master.rowconfigure(row, weight=1)
        row += 1

        bottom = ttk.Frame(master)
        bottom.grid(row=row, column=0, sticky="ew", padx=10, pady=5)
        bottom.columnconfigure(0, weight=1)
        ttk.Button(bottom, text="License", command=self.show_license).grid(row=0, column=1, sticky=tk.E)

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
        dlg = tk.Toplevel(self.master)
        dlg.title("Downloading models")
        label_var = tk.StringVar(value="")
        ttk.Label(dlg, textvariable=label_var).pack(padx=10, pady=10)
        pb = ttk.Progressbar(dlg, length=300, maximum=100)
        pb.pack(padx=10, pady=10)
        dlg.grab_set()

        def progress(frac: float) -> None:
            pb.config(value=frac * 100)

        def worker() -> None:
            try:
                for m in models:
                    label = f"Downloading {m}"
                    self.master.after(0, lambda l=label: label_var.set(l))
                    model_manager.download_model(m, progress_cb=progress)
                self.master.after(0, lambda: self._on_download_success(dlg))
            except Exception as e:  # pragma: no cover - GUI display
                self.master.after(0, lambda: self._on_download_failed(dlg, e))

        threading.Thread(target=worker, daemon=True).start()

    def _on_download_failed(self, dlg: tk.Toplevel, exc: Exception) -> None:
        dlg.destroy()
        messagebox.showerror("Download failed", str(exc))
        self.start_btn.config(state=tk.NORMAL)

    def _on_download_success(self, dlg: tk.Toplevel) -> None:
        dlg.destroy()
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
        try:
            subprocess.run(
                ["huggingface-cli", "login", "--token", token],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            def _ok():
                self.status_var.set("Hugging Face login succeeded")
                self.hf_logged_in = True
                self._apply_hf_login_state()
            self.master.after(0, _ok)
        except Exception as e:  # pragma: no cover - external command
            def _ng():
                self.status_var.set(f"Hugging Face login failed: {e}")
                self.hf_logged_in = False
                self._apply_hf_login_state()
            self.master.after(0, _ng)

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
        self.diarization.set(data.get("diarization", self.diarization.get()))
        self.segmentation_model.set(data.get("segmentation_model", self.segmentation_model.get()))
        self.embedding_model.set(data.get("embedding_model", self.embedding_model.get()))
        self.ws_url.set(data.get("ws_url", self.ws_url.get()))
        self.save_path.set(data.get("save_path", self.save_path.get()))
        self.save_enabled.set(data.get("save_enabled", False))
        self.allow_external.set(data.get("allow_external", self.allow_external.get()))

    def _save_settings(self) -> None:
        data = {
            "backend_host": self.backend_host.get(),
            "backend_port": self.backend_port.get(),
            "api_host": self.api_host.get(),
            "api_port": self.api_port.get(),
            "auto_start": self.auto_start.get(),
            "model": self.model.get(),
            "diarization": self.diarization.get(),
            "segmentation_model": self.segmentation_model.get(),
            "embedding_model": self.embedding_model.get(),
            "ws_url": self.ws_url.get(),
            "save_path": self.save_path.get(),
            "save_enabled": self.save_enabled.get(),
            "allow_external": self.allow_external.get(),
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
            self.status_var.set("stopping")
        else:
            self.is_recording = True
            self.record_btn.config(text="Stop Recording")
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
            self.master.after(0, lambda: self.status_var.set(f"missing dependency: {e}"))
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
            self.master.after(0, lambda: self.status_var.set(f"error: {e}"))
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
        # Prefer local token presence over online whoami to avoid network dependency
        logged = False
        try:
            # Check common env vars first
            for k in ("HF_TOKEN", "HUGGINGFACEHUB_API_TOKEN", "HUGGING_FACE_HUB_TOKEN"):
                if os.getenv(k):
                    logged = True
                    break
            if not logged:
                try:
                    from huggingface_hub import HfFolder  # type: ignore
                    token = HfFolder.get_token()
                    if token:
                        logged = True
                except Exception:
                    pass
            # Fallback to CLI whoami if still undetermined
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
            self.master.after(0, self._apply_hf_login_state)

    def _apply_hf_login_state(self) -> None:
        # Force-disable diarization if not logged in
        if not self.hf_logged_in and self.diarization.get():
            self.diarization.set(False)
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
