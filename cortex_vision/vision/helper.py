"""Compile and drive the native ``viscap`` Swift helper.

The helper is compiled lazily (first ``ensure_binary`` call) with ``swiftc``
into the plugin's persistent deps/bin dir, carrying an embedded Info.plist so
macOS TCC shows a meaningful Camera usage string. The binary emits one JSON
object on stdout; this module runs it and parses that.

Screen Recording permission cannot be embedded in a plist — macOS only grants
it interactively via System Settings; ``check_setup`` surfaces that.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_INFO_PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" \
"http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleIdentifier</key><string>tools.ai-architect.cortex-vision</string>
  <key>CFBundleName</key><string>cortex-vision</string>
  <key>NSCameraUsageDescription</key>
  <string>cortex-vision grabs a camera frame to read text, scenes, or barcodes for Cortex memories.</string>
</dict>
</plist>
"""


class VisionHelperError(RuntimeError):
    """Raised when the native helper cannot be built, authorized, or run."""


def _plugin_root() -> Path:
    root = os.environ.get("CLAUDE_PLUGIN_ROOT", "")
    if root and Path(root).is_dir():
        return Path(root)
    return Path(__file__).resolve().parents[2]


def _bin_dir() -> Path:
    data = os.environ.get("CLAUDE_PLUGIN_DATA", "")
    base = Path(data) if data else _plugin_root() / "deps"
    target = base / "bin"
    target.mkdir(parents=True, exist_ok=True)
    return target


def _swiftc_cmd() -> list[str]:
    """Prefer ``xcrun swiftc`` so the compiler and macOS SDK stay aligned.

    Invoking swiftc by absolute path leaves SDKROOT unset, which fails with
    'unable to load standard library for target ...'. ``xcrun`` sets up the
    SDK environment; fall back to plain ``swiftc`` only if xcrun is absent.
    """
    try:
        out = subprocess.run(["xcrun", "--find", "swiftc"], capture_output=True, text=True)
        if out.returncode == 0 and out.stdout.strip():
            return ["xcrun", "swiftc"]
    except FileNotFoundError:
        pass
    return ["swiftc"]


def ensure_binary() -> Path:
    """Compile ``viscap`` if missing/stale; return the binary path."""
    if sys.platform != "darwin":
        raise VisionHelperError("cortex-vision requires macOS (Apple Vision framework).")
    src = _plugin_root() / "scripts" / "viscap.swift"
    if not src.is_file():
        raise VisionHelperError(f"helper source missing: {src}")
    binary = _bin_dir() / "viscap"
    if binary.is_file() and binary.stat().st_mtime >= src.stat().st_mtime:
        return binary

    plist = _bin_dir() / "viscap-Info.plist"
    plist.write_text(_INFO_PLIST)
    cmd = [
        *_swiftc_cmd(), str(src), "-O", "-o", str(binary),
        "-framework", "Vision", "-framework", "AVFoundation",
        "-framework", "ScreenCaptureKit", "-framework", "CoreImage",
        "-framework", "AppKit", "-framework", "Foundation",
        "-Xlinker", "-sectcreate", "-Xlinker", "__TEXT",
        "-Xlinker", "__info_plist", "-Xlinker", str(plist),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not binary.is_file():
        detail = (proc.stderr or proc.stdout or "").strip()[-2000:]
        raise VisionHelperError(f"swiftc failed to build viscap:\n{detail}")
    # Ad-hoc sign so TCC has a stable code identity for the binary.
    subprocess.run(
        ["codesign", "--force", "--sign", "-", str(binary)],
        capture_output=True, text=True,
    )
    return binary


def _run(args: list[str], timeout: float) -> dict:
    binary = ensure_binary()
    try:
        proc = subprocess.run(
            [str(binary), *args], capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        raise VisionHelperError(f"viscap timed out after {timeout}s")
    out = (proc.stdout or "").strip()
    if not out:
        stderr = (proc.stderr or "").strip()[-500:]
        raise VisionHelperError(f"viscap produced no output (stderr: {stderr})")
    last = out.splitlines()[-1]
    try:
        data = json.loads(last)
    except json.JSONDecodeError:
        raise VisionHelperError(f"viscap returned non-JSON: {last[:300]}")
    if "error" in data:
        raise VisionHelperError(str(data["error"]))
    return data


def check_auth(timeout: float = 90.0) -> dict:
    """Run ``--check-auth``; returns {'camera_auth': ..., 'screen_recording': ...}."""
    return _run(["--check-auth"], timeout=timeout)


def capture(
    source: str,
    task: str,
    path: str | None = None,
    region: str | None = None,
    max_results: int = 50,
) -> dict:
    """Grab an image from ``source`` and run vision ``task``; return results."""
    args = ["--capture", "--source", source, "--task", task,
            "--max-results", str(max_results)]
    if path:
        args += ["--path", path]
    if region:
        args += ["--region", region]
    # Camera frame grab can take a moment to warm up the device.
    timeout = 45.0 if source == "camera" else 30.0
    return _run(args, timeout=timeout)
