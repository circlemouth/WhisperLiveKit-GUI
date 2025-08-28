import os
import socket
import subprocess
import sys
import time
import webbrowser
import tkinter as tk
from tkinter import ttk


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
        self.master.destroy()

    def copy_to_clipboard(self, text: str) -> None:
        self.master.clipboard_clear()
        self.master.clipboard_append(text)

    def update_endpoints(self, *_: object) -> None:
        b_host = self.backend_host.get()
        b_port = self.backend_port.get()
        a_host = self.api_host.get()
        a_port = self.api_port.get()
        self.web_endpoint.set(f"http://{b_host}:{b_port}/")
        self.ws_endpoint.set(f"ws://{b_host}:{b_port}/asr")
        self.api_endpoint.set(f"http://{a_host}:{a_port}/v1/audio/transcriptions")

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
