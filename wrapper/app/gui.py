import os
import socket
import subprocess
import sys
import time
import webbrowser
import tkinter as tk
from tkinter import ttk, filedialog
import audioop
import json
import queue
import threading
from pathlib import Path
import shutil
from platformdirs import user_config_path


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
        self.auto_start = tk.BooleanVar(value=os.getenv("WRAPPER_API_AUTOSTART") == "1")

        self.web_endpoint = tk.StringVar()
        self.ws_endpoint = tk.StringVar()
        self.api_endpoint = tk.StringVar()

        # Recording-related variables
        self.ws_url = tk.StringVar()
        self.is_recording = False
        self.status_var = tk.StringVar(value="stopped")
        self.timer_var = tk.StringVar(value="00:00")
        self.level_var = tk.DoubleVar(value=0.0)
        self.save_path = tk.StringVar()

        self._load_settings()

        # Layout
        row = 0
        ttk.Label(master, text="Backend host").grid(column=0, row=row, sticky=tk.W)
        ttk.Entry(master, textvariable=self.backend_host, width=15).grid(column=1, row=row)
        row += 1
        ttk.Label(master, text="Backend port").grid(column=0, row=row, sticky=tk.W)
        ttk.Entry(master, textvariable=self.backend_port, width=15).grid(column=1, row=row)
        row += 1
        ttk.Label(master, text="API host").grid(column=0, row=row, sticky=tk.W)
        ttk.Entry(master, textvariable=self.api_host, width=15).grid(column=1, row=row)
        row += 1
        ttk.Label(master, text="API port").grid(column=0, row=row, sticky=tk.W)
        ttk.Entry(master, textvariable=self.api_port, width=15).grid(column=1, row=row)
        row += 1
        ttk.Checkbutton(master, text="Auto-start API on launch", variable=self.auto_start).grid(column=0, row=row, columnspan=2, sticky=tk.W)
        row += 1
        ttk.Button(master, text="Start API", command=self.start_api).grid(column=0, row=row)
        ttk.Button(master, text="Stop API", command=self.stop_api).grid(column=1, row=row)

        row += 1
        ttk.Label(master, text="Backend Web UI").grid(column=0, row=row, sticky=tk.W)
        ttk.Entry(master, textvariable=self.web_endpoint, width=40, state="readonly").grid(column=1, row=row)
        ttk.Button(master, text="Copy", command=lambda: self.copy_to_clipboard(self.web_endpoint.get())).grid(column=2, row=row)
        row += 1
        ttk.Label(master, text="Streaming WebSocket /asr").grid(column=0, row=row, sticky=tk.W)
        ttk.Entry(master, textvariable=self.ws_endpoint, width=40, state="readonly").grid(column=1, row=row)
        ttk.Button(master, text="Copy", command=lambda: self.copy_to_clipboard(self.ws_endpoint.get())).grid(column=2, row=row)
        row += 1
        ttk.Label(master, text="File transcription API").grid(column=0, row=row, sticky=tk.W)
        ttk.Entry(master, textvariable=self.api_endpoint, width=40, state="readonly").grid(column=1, row=row)
        ttk.Button(master, text="Copy", command=lambda: self.copy_to_clipboard(self.api_endpoint.get())).grid(column=2, row=row)

        row += 1
        ttk.Label(master, text="Recorder WebSocket").grid(column=0, row=row, sticky=tk.W)
        ttk.Entry(master, textvariable=self.ws_url, width=40).grid(column=1, row=row)
        ttk.Button(master, text="Copy", command=lambda: self.copy_to_clipboard(self.ws_url.get())).grid(column=2, row=row)

        row += 1
        self.record_btn = ttk.Button(master, text="Start Recording", command=self.toggle_recording)
        self.record_btn.grid(column=0, row=row, sticky=tk.W)
        ttk.Label(master, textvariable=self.status_var).grid(column=1, row=row, sticky=tk.W)
        row += 1
        ttk.Label(master, textvariable=self.timer_var).grid(column=0, row=row, sticky=tk.W)
        ttk.Progressbar(master, variable=self.level_var, maximum=1.0, length=150).grid(column=1, row=row, columnspan=2, sticky=tk.W)

        row += 1
        ttk.Label(master, text="Save transcript to").grid(column=0, row=row, sticky=tk.W)
        ttk.Entry(master, textvariable=self.save_path, width=40).grid(column=1, row=row)
        ttk.Button(master, text="Browse", command=self.choose_save_path).grid(column=2, row=row)

        row += 1
        ttk.Label(master, text="Transcript").grid(column=0, row=row, sticky=tk.W)
        row += 1
        self.transcript_box = tk.Text(master, height=8, width=60, state="disabled")
        self.transcript_box.grid(column=0, row=row, columnspan=3, sticky=tk.W)

        row += 1
        ttk.Button(master, text="Open Web GUI", command=self.open_web_gui).grid(column=0, row=row, sticky=tk.W)
        ttk.Button(master, text="License", command=self.show_license).grid(column=1, row=row, sticky=tk.W)

        self.backend_proc: subprocess.Popen | None = None
        self.api_proc: subprocess.Popen | None = None

        for var in [self.backend_host, self.backend_port, self.api_host, self.api_port]:
            var.trace_add("write", self.update_endpoints)
        self.update_endpoints()

        master.protocol("WM_DELETE_WINDOW", self.on_close)

    def start_api(self):
        if self.api_proc or self.backend_proc:
            return
        b_host = self.backend_host.get()
        b_port = self.backend_port.get()
        a_host = self.api_host.get()
        a_port = self.api_port.get()

        env = os.environ.copy()
        env["WRAPPER_BACKEND_HOST"] = b_host
        env["WRAPPER_BACKEND_PORT"] = b_port
        env["WRAPPER_API_HOST"] = a_host
        env["WRAPPER_API_PORT"] = a_port

        self.backend_proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "whisperlivekit.basic_server",
                "--host",
                b_host,
                "--port",
                b_port,
            ]
        )
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
        self.web_endpoint.set(f"http://{b_host}:{b_port}/")
        ws = f"ws://{b_host}:{b_port}/asr"
        self.ws_endpoint.set(ws)
        if not self.ws_url.get():
            self.ws_url.set(ws)
        self.api_endpoint.set(f"http://{a_host}:{a_port}/v1/audio/transcriptions")

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

    def _load_settings(self) -> None:
        if not CONFIG_FILE.exists() and OLD_CONFIG_FILE.exists():
            try:
                shutil.move(str(OLD_CONFIG_FILE), CONFIG_FILE)
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
        self.auto_start.set(data.get("auto_start", self.auto_start.get()))
        self.ws_url.set(data.get("ws_url", self.ws_url.get()))
        self.save_path.set(data.get("save_path", self.save_path.get()))

    def _save_settings(self) -> None:
        data = {
            "backend_host": self.backend_host.get(),
            "backend_port": self.backend_port.get(),
            "api_host": self.api_host.get(),
            "api_port": self.api_port.get(),
            "auto_start": self.auto_start.get(),
            "ws_url": self.ws_url.get(),
            "save_path": self.save_path.get(),
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
        if path:
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


def main():
    root = tk.Tk()
    gui = WrapperGUI(root)
    if gui.auto_start.get():
        root.after(100, gui.start_api)
    root.mainloop()


if __name__ == "__main__":
    main()
