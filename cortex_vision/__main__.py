"""cortex-vision MCP server entry point.

An eyes-only vision-capture MCP for Cortex. On macOS it grabs an image (screen
capture, an image file, or a camera frame), runs an on-device Apple Vision task
(OCR, scene labelling, or barcode detection), and returns the extracted
text/labels plus a routing intent ('recall' or 'remember'). It never reads or
writes Cortex itself — after ``look``, the caller chains to the Cortex MCP
recall/remember tools as indicated by ``next_action``.

Run: ``python -m cortex_vision`` (stdio MCP transport).
"""

from __future__ import annotations

import signal
import sys

from fastmcp import FastMCP

from cortex_vision.server import mcp_tools

mcp = FastMCP(
    name="cortex-vision",
    version="1.0.0",
    instructions=(
        "Vision capture MCP for Cortex (macOS, on-device Apple Vision). Call "
        "check_vision_setup once to compile the helper and grant Camera + "
        "Screen Recording permissions. Call look to grab an image (screen, file, "
        "or camera) and run a vision task (ocr, scene, or barcode); it returns "
        "the extracted text/labels and an intent ('recall' or 'remember'). This "
        "server is eyes-only: after look, chain to the Cortex MCP recall or "
        "remember tool as indicated by next_action. It never reads or writes "
        "memories itself."
    ),
)

mcp_tools.register(mcp)


def _shutdown(sig=None, frame=None) -> None:
    sys.exit(0)


def main() -> None:
    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
