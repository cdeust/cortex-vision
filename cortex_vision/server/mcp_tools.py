"""MCP tool registration for the cortex-vision server.

Two tools, both eyes-only:
  * look               — grab an image + run a vision task, classify intent.
  * check_vision_setup — compile the helper and report camera/screen authorization.

Neither tool touches Cortex. ``look`` returns a ``next_action`` telling the
caller which Cortex MCP tool to chain to (recall or remember).
"""

from __future__ import annotations

import asyncio
import os

from fastmcp import FastMCP

from cortex_vision.vision import helper, intent

_VALID_MODES = ("auto", "recall", "remember")
_VALID_SOURCES = ("screen", "file", "camera")
_VALID_TASKS = ("ocr", "scene", "barcode")


def _default_mode() -> str:
    mode = os.environ.get("VISION_DEFAULT_MODE", "auto")
    return mode if mode in _VALID_MODES else "auto"


def _default_source() -> str:
    src = os.environ.get("VISION_DEFAULT_SOURCE", "screen")
    return src if src in _VALID_SOURCES else "screen"


def _default_task() -> str:
    task = os.environ.get("VISION_DEFAULT_TASK", "ocr")
    return task if task in _VALID_TASKS else "ocr"


def register(mcp: FastMCP) -> None:
    """Register cortex-vision tools on the FastMCP instance."""
    _register_look(mcp)
    _register_check_setup(mcp)


def _next_action(resolved: str) -> str:
    if resolved == "recall":
        return "Call the Cortex MCP recall tool with query=text."
    return (
        "Call the Cortex MCP remember tool with content=text and "
        "tags=suggested_tags + ['vision']."
    )


def _routing_text(result: dict, task: str) -> str:
    """Pick the snippet that drives intent classification + tagging."""
    text = (result.get("text") or "").strip()
    if text:
        return text
    if task == "scene":
        labels = result.get("labels") or []
        return " ".join(str(item.get("label", "")) for item in labels).strip()
    if task == "barcode":
        codes = result.get("barcodes") or []
        return " ".join(str(item.get("payload", "")) for item in codes).strip()
    return ""


def _register_look(mcp: FastMCP) -> None:
    @mcp.tool(
        name="look",
        description=(
            "Grab an image and run an on-device Apple Vision task. source: "
            "'screen' (ScreenCaptureKit, fallback screencapture), 'file' (path "
            "to an image), or 'camera' (AVFoundation frame grab). task: 'ocr' "
            "(recognize text), 'scene' (classify/label the image), or 'barcode' "
            "(detect barcodes/QR). Returns extracted text/labels/barcodes plus a "
            "routing hint. This tool does NOT touch Cortex: after calling it, "
            "chain to the Cortex MCP per next_action — intent 'recall' -> cortex "
            "recall(query); intent 'remember' -> cortex remember(content, tags). "
            "mode 'auto' lets the classifier decide; 'recall'/'remember' force it. "
            "region is an optional 'x,y,w,h' crop for screen capture; path is "
            "required for source='file'."
        ),
    )
    async def tool_look(
        source: str | None = None,
        task: str | None = None,
        mode: str = "auto",
        path: str | None = None,
        region: str | None = None,
        max_results: int = 50,
    ) -> dict:
        if mode not in _VALID_MODES:
            mode = _default_mode()
        src = source if source in _VALID_SOURCES else _default_source()
        tsk = task if task in _VALID_TASKS else _default_task()
        if src == "file" and not path:
            return {
                "ok": False,
                "error": "source='file' requires a 'path' to an image.",
            }
        try:
            result = await asyncio.to_thread(
                helper.capture, src, tsk, path, region, max_results
            )
        except helper.VisionHelperError as exc:
            return {
                "ok": False,
                "error": str(exc),
                "hint": (
                    "Run check_vision_setup to compile the helper and grant "
                    "Camera (and, for screen, Screen Recording) permissions."
                ),
            }
        routing_text = _routing_text(result, tsk)
        if not routing_text and not (result.get("labels") or result.get("barcodes")):
            return {
                "ok": False,
                "error": "no text, labels, or barcodes detected",
                "source": result.get("source", src),
                "task": tsk,
                "duration_s": result.get("duration"),
            }
        resolved = intent.classify(routing_text) if mode == "auto" else mode
        return {
            "ok": True,
            "task": tsk,
            "source": result.get("source", src),
            "text": result.get("text", ""),
            "labels": result.get("labels", []),
            "barcodes": result.get("barcodes", []),
            "intent": resolved,
            "suggested_tags": intent.suggest_tags(routing_text),
            "duration_s": result.get("duration"),
            "on_device": result.get("on_device", True),
            "next_action": _next_action(resolved),
        }


def _register_check_setup(mcp: FastMCP) -> None:
    @mcp.tool(
        name="check_vision_setup",
        description=(
            "Verify the cortex-vision capture helper: compile it if needed and "
            "report Camera + Screen Recording authorization. Call this once "
            "before first use to trigger the macOS Camera prompt. Screen "
            "Recording cannot be auto-granted — enable it manually in System "
            "Settings > Privacy & Security > Screen Recording if you use "
            "source='screen'."
        ),
    )
    async def tool_check_vision_setup() -> dict:
        try:
            binary = await asyncio.to_thread(helper.ensure_binary)
        except helper.VisionHelperError as exc:
            return {"ok": False, "error": str(exc)}
        try:
            auth = await asyncio.to_thread(helper.check_auth)
        except helper.VisionHelperError as exc:
            return {"ok": False, "binary": str(binary), "error": str(exc)}
        camera_ready = auth.get("camera_auth") == "authorized"
        screen_ready = auth.get("screen_recording") == "authorized"
        hints = []
        if not camera_ready:
            hints.append(
                "Grant Camera to your terminal/Claude app in System Settings > "
                "Privacy & Security > Camera (needed only for source='camera')."
            )
        if not screen_ready:
            hints.append(
                "Enable Screen Recording for your terminal/Claude app in System "
                "Settings > Privacy & Security > Screen Recording (needed only "
                "for source='screen')."
            )
        return {
            "ok": camera_ready or screen_ready,
            "binary": str(binary),
            "hint": " ".join(hints) or None,
            **auth,
        }
