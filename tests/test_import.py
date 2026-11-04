"""Import-level checks that hold on every platform.

The capture helper (scripts/viscap.swift) needs macOS and user-granted permissions; the
Pipeline's `helper` job type-checks it there. These tests only prove the Python package
installs and wires its two tools, which is what the Linux `unit` job can measure.
"""

from __future__ import annotations

import asyncio
import importlib
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_package_modules_import() -> None:
    for name in (
        "cortex_vision",
        "cortex_vision.server.mcp_tools",
        "cortex_vision.vision.helper",
        "cortex_vision.vision.intent",
    ):
        importlib.import_module(name)


def test_register_declares_the_two_eyes_only_tools() -> None:
    from fastmcp import FastMCP

    from cortex_vision.server import mcp_tools

    mcp = FastMCP("cortex-vision-test")
    mcp_tools.register(mcp)
    # fastmcp >= 2: list_tools() is the public, async listing (verified on 4.1.6).
    names = {tool.name for tool in asyncio.run(mcp.list_tools())}
    assert names == {"look", "check_vision_setup"}, names


def test_declared_entry_point_resolves() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    target = project["scripts"]["cortex-vision"]
    module_name, attribute = target.split(":")
    assert callable(getattr(importlib.import_module(module_name), attribute))
