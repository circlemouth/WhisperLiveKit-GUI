"""Run tests for the Avalonia UI project."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent / "app" / "avalonia_ui.Tests"


def main() -> int:
    try:
        result = subprocess.run(
            ["dotnet", "test", str(PROJECT_DIR)],
            check=False,
        )
        return result.returncode
    except FileNotFoundError:
        print("dotnet が見つかりません。先に .NET SDK をインストールしてください。", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
