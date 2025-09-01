#!/usr/bin/env python3
"""Generate third-party license information for project dependencies.

This script reads ``wrapper/requirements-nvidia.txt`` to determine
which packages to inspect. For each dependency installed in the current
Python environment, the script extracts its license metadata **and**
bundles the corresponding license text when available. Entries with
missing or ``UNKNOWN`` license values are skipped. The resulting
information is written to ``wrapper/licenses.json`` as a list of
``{"name": ..., "version": ..., "license": ..., "license_text": ...}``
objects.

Run this script whenever dependencies change to refresh the bundled
license information displayed by the GUI.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from importlib import metadata

# ``wrapper/scripts`` -> parent ``wrapper``
ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS = ROOT / "requirements-nvidia.txt"
OUTPUT = ROOT / "licenses.json"

name_pattern = re.compile(r"^[A-Za-z0-9_.-]+")


def _iter_requirements() -> list[str]:
    names: list[str] = []
    if not REQUIREMENTS.exists():
        return names
    for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = name_pattern.match(line)
        if match:
            names.append(match.group(0))
    return names


def _extract_license_text(dist: metadata.Distribution) -> str:
    """Try to read a license file from the distribution."""
    text: str = ""
    try:
        meta = dist.metadata
        for rel_path in meta.get_all("License-File", []):
            try:
                file_text = dist.read_text(rel_path)
            except FileNotFoundError:
                continue
            if file_text:
                text = file_text.strip()
                break
        else:
            # Fallback: search common license file names
            for file in dist.files or []:
                name = file.name.lower()
                if name.startswith("license") or name.startswith("copying"):
                    try:
                        file_text = dist.read_text(str(file))
                    except FileNotFoundError:
                        continue
                    if file_text:
                        text = file_text.strip()
                        break
    except Exception:
        pass
    return text


def main() -> None:
    licenses: list[dict[str, str]] = []
    for pkg in sorted(_iter_requirements(), key=str.lower):
        if pkg.lower() == "whisperlivekit":
            # Project's own license is shown separately
            continue
        try:
            dist = metadata.distribution(pkg)
        except metadata.PackageNotFoundError:
            continue
        meta = dist.metadata
        name = meta.get("Name", pkg)
        version = meta.get("Version", "")
        license_str = meta.get("License")
        if not license_str or license_str.upper() == "UNKNOWN":
            # Fallback to classifier information
            for classifier in meta.get_all("Classifier", []):
                if classifier.startswith("License ::"):
                    license_str = classifier.split("::")[-1].strip()
                    break
        if not license_str or license_str.upper() == "UNKNOWN":
            continue
        license_text = _extract_license_text(dist)
        licenses.append(
            {
                "name": name,
                "version": version,
                "license": license_str,
                "license_text": license_text,
            }
        )
    OUTPUT.write_text(
        json.dumps(licenses, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
